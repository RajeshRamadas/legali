import json
from types import SimpleNamespace

import pytest

from app import blog_agent, blog_checks

JUDGMENT_URL = "https://indiankanoon.org/doc/123456/"
NEWS_URL = "https://www.livelaw.in/high-court/karnataka-high-court/rera-refund-ruling-2026?utm_source=x"
JUDGMENT_TEXT = (
    "IN THE HIGH COURT OF KARNATAKA AT BENGALURU. W.P. No. 12345/2026. Dated this the 28th day of October 2026. "
    "The petitioner booked a flat in Whitefield in 2019 for Rs. 85,00,000. The promoter failed to hand over possession. "
    "Under Section 18 of the Real Estate (Regulation and Development) Act, 2016, the allottee is entitled to a refund with interest. "
    "The writ petition filed by the promoter is dismissed and the order of the Karnataka RERA is upheld."
)

def _response(blocks, stop="end_turn", searches=0):
    usage = SimpleNamespace(input_tokens=1000, output_tokens=500, server_tool_use=SimpleNamespace(web_search_requests=searches, web_fetch_requests=0))
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=usage, _request_id="req_test")

class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **params):
        self.calls.append(params)
        return self.responses.pop(0)

@pytest.fixture
def fake(monkeypatch):
    def install(*responses):
        client = FakeClient(responses)
        monkeypatch.setattr(blog_agent, "get_client", lambda: client)
        return client
    return install

def _search_result(*urls):
    return {"type": "web_search_tool_result", "tool_use_id": "s1", "content": [{"type": "web_search_result", "url": u, "title": "t"} for u in urls]}

def _text(data):
    return {"type": "text", "text": json.dumps(data)}

LEAD = {
    "title": "Karnataka HC upholds RERA refund for delayed Whitefield flat", "url": NEWS_URL, "source_name": "LiveLaw",
    "court": "Karnataka High Court", "case_number": "W.P. No. 12345/2026", "decision_date": "2026-10-28",
    "summary": "The court dismissed the promoter's challenge.", "why_it_matters": "Buyers can claim refunds.", "topics": ["RERA"], "relevance": 5,
}

def _scan_response():
    invented = {**LEAD, "title": "Invented", "url": "https://www.livelaw.in/made-up", "case_number": "W.P. 9/2026"}
    off_list = {**LEAD, "title": "Blog", "url": "https://randomblog.example.com/post", "case_number": "W.P. 8/2026"}
    return _response([
        {"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "Karnataka RERA refund"}},
        _search_result(NEWS_URL, "https://randomblog.example.com/post"),
        _text({"leads": [LEAD, invented, off_list]}),
    ], searches=1)

def _draft_response(body=None, claims=None):
    fetch = {"type": "web_fetch_tool_result", "tool_use_id": "f1", "content": {
        "type": "web_fetch_result", "url": JUDGMENT_URL,
        "content": {"type": "document", "title": "Prestige Builders v. K-RERA", "source": {"type": "text", "media_type": "text/plain", "data": JUDGMENT_TEXT}},
    }}
    body = body or (
        "## What happened\n\nA buyer booked a Whitefield flat in 2019 for ₹85,00,000 and never got possession.\n\n"
        "## What the court decided\n\nOn 28 October 2026 the Karnataka High Court upheld the RERA order under Section 18, and set a deadline of 15 March 2027.\n\n"
        "## What this means for buyers\n\nYou can ask for your money back with interest when possession is delayed."
    )
    claims = claims if claims is not None else [
        {"claim": "The Karnataka High Court heard the case", "quote": "IN THE HIGH COURT OF KARNATAKA AT BENGALURU", "source_url": JUDGMENT_URL},
        {"claim": "The flat cost ₹85 lakh", "quote": "booked a flat in Whitefield in 2019 for Rs. 85,00,000", "source_url": JUDGMENT_URL},
        {"claim": "Refund with interest under Section 18", "quote": "the allottee is entitled to a refund with interest", "source_url": "https://www.livelaw.in/other"},
        {"claim": "The promoter must pay within 60 days", "quote": "pay within sixty days", "source_url": JUDGMENT_URL},
    ]
    return _response([fetch, _text({
        "post_type": "case_study", "title": "Delayed flat? The High Court backs a RERA refund", "excerpt": "A Whitefield buyer gets a refund with interest.",
        "body": body, "tags": ["RERA", "Karnataka High Court"], "highlights": [{"label": "Court", "value": "Karnataka High Court"}],
        "case": {"name": "Prestige Builders v. K-RERA", "court": "High Court of Karnataka", "case_number": "W.P. No. 12345/2026", "decision_date": "2026-10-28"},
        "claims": claims,
    })])

def test_desk_is_off_without_an_api_key(client, admin_headers, agent, monkeypatch):
    monkeypatch.setattr(blog_agent, "get_client", lambda: None)
    assert client.get("/api/v1/admin/blog-agent", headers=agent["headers"]).status_code == 403
    status = client.get("/api/v1/admin/blog-agent", headers=admin_headers).json()
    assert status["available"] is False and status["scheduled"] is False and "livelaw.in" in status["domains"]
    assert client.post("/api/v1/admin/blog-agent/scan", headers=admin_headers).status_code == 503

def test_scan_keeps_only_real_allow_listed_new_leads(client, admin_headers, fake):
    calls = fake(_scan_response(), _scan_response())
    run = client.post("/api/v1/admin/blog-agent/scan", headers=admin_headers)
    assert run.status_code == 202
    tools = calls.calls[0]["tools"]
    assert tools[0]["type"] == "web_search_20260209" and "indiankanoon.org" in tools[0]["allowed_domains"]

    leads = client.get("/api/v1/admin/blog-agent/leads", headers=admin_headers).json()["items"]
    # The invented URL and the off-list site are dropped; tracking parameters and www. are removed.
    assert [lead["url"] for lead in leads] == ["https://livelaw.in/high-court/karnataka-high-court/rera-refund-ruling-2026"]
    assert leads[0]["status"] == "new" and leads[0]["relevance"] == 5 and leads[0]["decision_date"] == "2026-10-28"
    status = client.get("/api/v1/admin/blog-agent", headers=admin_headers).json()
    assert status["runs"][0]["status"] == "done" and status["runs"][0]["found"] == 3 and status["runs"][0]["added"] == 1
    assert status["runs"][0]["usage"]["web_search_requests"] == 1

    # A second scan returning the same ruling adds nothing.
    client.post("/api/v1/admin/blog-agent/scan", headers=admin_headers)
    assert len(client.get("/api/v1/admin/blog-agent/leads", headers=admin_headers).json()["items"]) == 1
    assert "rera-refund-ruling-2026" in calls.calls[1]["messages"][0]["content"]  # known leads go in the prompt

def _lead_id(client, headers, fake):
    fake(_scan_response())
    client.post("/api/v1/admin/blog-agent/scan", headers=headers)
    return client.get("/api/v1/admin/blog-agent/leads", headers=headers).json()["items"][0]["id"]

def test_draft_checks_every_claim_and_needs_a_confirmed_review_to_publish(client, admin_headers, fake):
    lead_id = _lead_id(client, admin_headers, fake)
    fake(_draft_response())
    assert client.post(f"/api/v1/admin/blog-agent/leads/{lead_id}/draft", headers=admin_headers).status_code == 202
    lead = client.get("/api/v1/admin/blog-agent/leads", headers=admin_headers).json()["items"][0]
    assert lead["status"] == "drafted" and lead["post_id"]

    post = client.get(f"/api/v1/admin/posts/{lead['post_id']}", headers=admin_headers).json()
    assert post["origin"] == "ai" and post["status"] == "draft" and post["author"] == "Homexo Legal"
    review = post["ai_review"]
    assert "text" not in review["sources"][0] and review["sources"][0]["url"] == JUDGMENT_URL
    supported = [c["supported"] for c in review["claims"]]
    assert supported == [True, True, True, False]
    # Right quote, wrong link: pointed at the source that has it.
    assert review["claims"][2]["source_url"] == JUDGMENT_URL
    checks = review["checks"]
    assert checks["unsupported"] == 1 and checks["unverified_figures"] == ["15 March 2027"]
    assert any("not backed" in w for w in checks["warnings"])
    # Sources and the disclaimer come from code.
    assert "## Sources" in post["body"] and JUDGMENT_URL in post["body"] and "rera-refund-ruling-2026" in post["body"] and "not legal advice" in post["body"]

    url = f"/api/v1/admin/posts/{post['id']}"
    refused = client.patch(url, json={"status": "published"}, headers=admin_headers)
    assert refused.status_code == 409 and "confirm the review" in refused.json()["detail"]
    published = client.patch(url, json={"status": "published", "review_confirmed": True}, headers=admin_headers).json()
    assert published["status"] == "published" and published["reviewed_by"] == "Meera Admin" and published["reviewed_at"]
    assert client.get(f"/api/v1/posts/{post['slug']}").status_code == 200
    # Once reviewed, it can be unpublished and published again like any post.
    client.patch(url, json={"status": "draft"}, headers=admin_headers)
    assert client.patch(url, json={"status": "published"}, headers=admin_headers).status_code == 200

    # Drafting the same lead twice is refused.
    assert client.post(f"/api/v1/admin/blog-agent/leads/{lead_id}/draft", headers=admin_headers).status_code == 409

def test_recheck_after_editing(client, admin_headers, fake):
    lead_id = _lead_id(client, admin_headers, fake)
    fake(_draft_response())
    client.post(f"/api/v1/admin/blog-agent/leads/{lead_id}/draft", headers=admin_headers)
    post_id = client.get("/api/v1/admin/blog-agent/leads", headers=admin_headers).json()["items"][0]["post_id"]
    post = client.get(f"/api/v1/admin/posts/{post_id}", headers=admin_headers).json()
    fixed = post["body"].replace(", and set a deadline of 15 March 2027", "")
    client.patch(f"/api/v1/admin/posts/{post_id}", json={"body": fixed}, headers=admin_headers)
    rechecked = client.post(f"/api/v1/admin/posts/{post_id}/recheck", headers=admin_headers).json()
    assert rechecked["ai_review"]["checks"]["unverified_figures"] == []

    manual = client.post("/api/v1/admin/posts", json={"post_type": "article", "title": "Hand written"}, headers=admin_headers).json()
    assert manual["origin"] == "manual" and manual["ai_review"] is None
    assert client.post(f"/api/v1/admin/posts/{manual['id']}/recheck", headers=admin_headers).status_code == 409
    # Hand-written posts publish as before.
    assert client.patch(f"/api/v1/admin/posts/{manual['id']}", json={"status": "published"}, headers=admin_headers).status_code == 200

def test_draft_fails_when_no_source_was_read(client, admin_headers, fake):
    lead_id = _lead_id(client, admin_headers, fake)
    fake(_response([_text({"post_type": "article", "title": "From memory", "body": "x" * 100, "claims": []})]))
    client.post(f"/api/v1/admin/blog-agent/leads/{lead_id}/draft", headers=admin_headers)
    lead = client.get("/api/v1/admin/blog-agent/leads", headers=admin_headers).json()["items"][0]
    assert lead["status"] == "failed" and "No source page" in lead["note"] and lead["post_id"] is None
    assert client.get("/api/v1/admin/posts", headers=admin_headers).json()["total"] == 0
    # A failed lead can be tried again or dismissed.
    dismissed = client.post(f"/api/v1/admin/blog-agent/leads/{lead_id}/dismiss", json={"reason": "Not about property"}, headers=admin_headers).json()
    assert dismissed["status"] == "dismissed" and dismissed["note"] == "Not about property"

def test_paused_turns_are_resumed(client, admin_headers, fake):
    paused = _response([{"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "q"}}, _search_result(NEWS_URL)], stop="pause_turn", searches=1)
    finished = _response([_text({"leads": [LEAD]})], searches=1)
    calls = fake(paused, finished)
    client.post("/api/v1/admin/blog-agent/scan", headers=admin_headers)
    assert len(calls.calls) == 2 and calls.calls[1]["messages"][1]["role"] == "assistant"
    assert len(client.get("/api/v1/admin/blog-agent/leads", headers=admin_headers).json()["items"]) == 1

def test_scheduled_run_drafts_the_best_leads_only(client, admin_headers, fake, monkeypatch):
    monkeypatch.setattr(blog_agent.config, "BLOG_AGENT_AUTO_DRAFTS", 1)
    fake(_scan_response(), _draft_response())
    blog_agent.run_scheduled()
    leads = client.get("/api/v1/admin/blog-agent/leads", headers=admin_headers).json()["items"]
    assert leads[0]["status"] == "drafted"
    posts = client.get("/api/v1/admin/posts", headers=admin_headers).json()["items"]
    assert len(posts) == 1 and posts[0]["status"] == "draft"
    assert client.get("/api/v1/posts").json()["total"] == 0  # nothing goes live on its own
    assert blog_agent._due() is False

def test_checks():
    assert blog_checks.quote_found("“The writ petition … is dismissed”", "x") is False
    assert blog_checks.quote_found("the writ petition filed by the promoter is dismissed", JUDGMENT_TEXT)
    assert blog_checks.quote_found("Real Estate Regulation and Development Act 2016", JUDGMENT_TEXT)  # punctuation lost in PDFs
    assert blog_checks.unverified_figures("Decided on 28th October 2026 for ₹85,00,000 under Section 18 in W.P. No. 12345/2026.", [JUDGMENT_TEXT]) == []
    assert blog_checks.unverified_figures("Under Section 21 for Rs. 9,00,000.", [JUDGMENT_TEXT]) == ["Section 21", "Rs. 9,00,000"]
    assert blog_checks.overlap(JUDGMENT_TEXT, [JUDGMENT_TEXT]) == 1.0
    assert blog_checks.overlap("A buyer in Whitefield waited years for a flat and finally got a refund from the court.", [JUDGMENT_TEXT]) == 0.0
