def _chat(client, message):
    response = client.post("/api/v1/chat", json={"message": message})
    assert response.status_code == 200
    return response.json()

def test_chat_suggests_a_service(client):
    body = _chat(client, "Is this property safe to buy?")
    assert body["action"] == "request"
    assert body["service"]["slug"] == "title-verification"

def test_chat_prefers_most_specific_topic(client):
    assert _chat(client, "We need bulk registration for 80 units")["service"]["slug"] == "bulk-registration-operations"
    assert _chat(client, "How much does the Pro package cost?")["service"]["slug"] == "legal-due-diligence"

def test_chat_tracking_extracts_ticket_number(client):
    body = _chat(client, "what is the status of hx-261018-abc123")
    assert body["action"] == "track"
    assert body["ticket_number"] == "HX-261018-ABC123"

def test_chat_fallback_offers_callback(client):
    body = _chat(client, "qwerty")
    assert body["service"]["slug"] == "general-guidance"

import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app import assistant, config

class FakeClaude:
    """Stands in for anthropic.Anthropic: records each request and answers with a canned reply."""
    def __init__(self, reply=None, stop_reason="end_turn", error=None):
        self.calls, self.reply, self.stop_reason, self.error = [], reply, stop_reason, error
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params):
        self.calls.append(params)
        if self.error:
            raise self.error
        return SimpleNamespace(stop_reason=self.stop_reason, _request_id="req_test",
                               content=[SimpleNamespace(type="text", text=json.dumps(self.reply))])

def _reply(**overrides):
    return {"reply": "Shield Pro costs ₹9,999.", "action": "none", "service_slug": "", "ticket_number": "", "suggestions": [], "sources": [], **overrides}

@pytest.fixture
def claude(monkeypatch):
    def _install(**kwargs):
        fake = FakeClaude(**kwargs)
        monkeypatch.setattr(assistant, "_client", fake)
        return fake
    return _install

def test_ai_answers_from_retrieved_knowledge(client, claude):
    fake = claude(reply=_reply(action="request", service_slug="legal-due-diligence", suggestions=["What does Pro include?"], sources=["packages/shield-pro-9-999", "made-up/section"]))
    body = _chat(client, "How much is Shield Pro?")
    assert body["mode"] == "ai"
    assert body["reply"] == "Shield Pro costs ₹9,999."
    assert body["service"]["slug"] == "legal-due-diligence"
    # Only ids that were actually retrieved come back as sources.
    assert body["sources"] == [{"title": "Buyer packages", "section": "Shield Pro (₹9,999)"}]
    params = fake.calls[0]
    assert params["model"] == config.CHAT_MODEL
    assert params["output_config"]["effort"] == "low"
    assert params["system"][0]["cache_control"] == {"type": "ephemeral"}
    question = params["messages"][-1]["content"]
    assert "Shield Pro (₹9,999)" in question and "has not verified a ticket" in question

def test_refusal_fallback_is_opt_in(client, claude, monkeypatch):
    fake = claude(reply=_reply())
    _chat(client, "hello")
    assert "fallbacks" not in fake.calls[0]
    monkeypatch.setattr(config, "CHAT_FALLBACKS", "default")
    _chat(client, "hello again")
    assert fake.calls[1]["fallbacks"] == "default" and fake.calls[1]["betas"] == ["server-side-fallback-2026-07-01"]

def test_ai_gets_verified_ticket_but_never_internal_notes(client, claude, raise_ticket, admin_headers):
    number = raise_ticket()
    client.post(f"/api/v1/admin/tickets/{number}/messages", headers=admin_headers, json={"message": "Please share the Mother Deed.", "visibility": "customer"})
    client.post(f"/api/v1/admin/tickets/{number}/messages", headers=admin_headers, json={"message": "Seller seems evasive.", "visibility": "internal"})
    fake = claude(reply=_reply(reply="The team needs the Mother Deed.", action="status"))
    body = client.post("/api/v1/chat", json={"message": "What do you need from me?", "ticket": {"ticket_number": number, "contact": "9876543210"}}).json()
    question = fake.calls[0]["messages"][-1]["content"]
    assert "Please share the Mother Deed." in question
    assert "Seller seems evasive." not in question
    assert body["ticket_verified"] is True
    assert body["action"] == "status" and body["ticket"]["ticket_number"] == number

def test_wrong_contact_gets_no_ticket_context(client, claude, raise_ticket):
    number = raise_ticket()
    fake = claude(reply=_reply(action="status"))
    body = client.post("/api/v1/chat", json={"message": "status?", "ticket": {"ticket_number": number, "contact": "9000000000"}}).json()
    assert number not in fake.calls[0]["messages"][-1]["content"]
    assert body["ticket_verified"] is False
    # Without a verified ticket the AI can only ask the customer to verify.
    assert body["action"] == "track" and body["ticket"] is None

def test_history_is_trimmed_and_starts_with_user(client, claude):
    fake = claude(reply=_reply())
    history = [{"role": "assistant", "content": "Hi!"}] + [{"role": r, "content": f"turn {i}"} for i, r in enumerate(["user", "assistant"] * 10)]
    client.post("/api/v1/chat", json={"message": "and Complete?", "history": history})
    messages = fake.calls[0]["messages"]
    assert messages[0]["role"] == "user"
    assert all(a["role"] != b["role"] for a, b in zip(messages, messages[1:]))
    assert len(messages) <= 13 and "turn 19" in messages[-2]["content"]

@pytest.mark.parametrize("kwargs", [
    {"stop_reason": "refusal"},
    {"stop_reason": "max_tokens"},
    {"error": anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))},
])
def test_falls_back_to_rules_when_ai_fails(client, claude, kwargs):
    claude(reply=_reply(), **kwargs)
    body = _chat(client, "Is this property safe to buy?")
    assert body["mode"] == "rules"
    assert body["service"]["slug"] == "title-verification"

def test_rules_show_status_for_verified_ticket(client, raise_ticket):
    number = raise_ticket()
    body = client.post("/api/v1/chat", json={"message": "track my request", "ticket": {"ticket_number": number, "contact": "sample@example.com"}}).json()
    assert body["mode"] == "rules" and body["action"] == "status"
    assert body["ticket"]["status_label"] == "Request received"

def test_chat_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(config, "CHAT_RATE_LIMIT_PER_MINUTE", 3)
    codes = [client.post("/api/v1/chat", json={"message": "hi"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
