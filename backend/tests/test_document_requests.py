from sqlalchemy import select
from app import config, verification
from app.db import SessionLocal
from app.models import LawyerProfile, ServiceRequest, User, VerificationRun

CONTACT = "+91 98765 43210"
INTAKE = {"state": "Karnataka", "transaction": "purchase", "seller_capacity": "owner", "development": "resale", "granted_land": "no"}


def lookup(client, ticket):
    return client.post("/api/v1/tickets/lookup", json={"ticket_number": ticket, "contact": CONTACT}).json()


def test_requests_without_a_report_and_conditional_intake(client, raise_ticket, admin_headers):
    ticket = raise_ticket(property_type="residential_plot")
    first = lookup(client, ticket)
    assert first["report"] is None
    assert first["document_request"]["missing_count"] > 0
    assert first["document_request"]["questions"]
    assert "Please upload" in first["messages"][0]["message"]
    payload = {"ticket_number": ticket, "contact": CONTACT, "intake": {**INTAKE, "transaction": "inheritance", "seller_capacity": "legal_heir"}}
    assert client.post("/api/v1/tickets/property-intake", json={**payload, "contact": "9000000000"}).status_code == 404
    result = client.post("/api/v1/tickets/property-intake", json=payload).json()
    tags = {i["tag"] for i in result["document_request"]["items"]}
    assert {"death-certificate", "succession-records", "conversion-order", "litigation-search"} <= tags
    assert result["document_request"]["questions"] == []
    count = len(result["messages"])
    assert len(client.post("/api/v1/tickets/property-intake", json=payload).json()["messages"]) == count
    queue = client.get("/api/v1/admin/fetch-queue", headers=admin_headers).json()["items"]
    assert any(i["ticket_number"] == ticket and i["item"]["tag"] == "ec" and i["source"]["key"] == "kaveri" for i in queue)


def test_upload_and_delete_update_automatic_prompt(client, raise_ticket, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "S3_BUCKET", "")
    ticket = raise_ticket()
    before = lookup(client, ticket)["document_request"]["missing_count"]
    data = {"ticket_number": ticket, "contact": CONTACT, "tag": "sale-deed"}
    result = client.post("/api/v1/tickets/documents", data=data, files={"file": ("deed.pdf", b"%PDF-1.4\nfixture", "application/pdf")}).json()
    request = result["document_request"]
    assert request["missing_count"] == before - 1
    assert next(i for i in request["items"] if i["tag"] == "sale-deed")["status"] == "received"
    assert "Sale deed of the present owner" not in request["prompt"]
    doc = result["documents"][0]["id"]
    removed = client.post("/api/v1/tickets/documents/delete", json={"ticket_number": ticket, "contact": CONTACT, "document_id": doc}).json()
    assert removed["document_request"]["missing_count"] == before


def test_conditional_requests_non_karnataka_and_unrelated_services(client, raise_ticket):
    ticket = raise_ticket(property_intake={**INTAKE, "state": "Other", "seller_capacity": "power_of_attorney", "development": "new"})
    request = lookup(client, ticket)["document_request"]
    assert {"power-of-attorney", "promoter-title"} <= {i["tag"] for i in request["items"]}
    assert all(i["source"] is None for i in request["items"])
    unrelated = raise_ticket(service_slug="affidavit-drafting")
    assert lookup(client, unrelated)["document_request"]["items"] == []


def test_verified_chat_asks_for_current_missing_documents(client, raise_ticket, monkeypatch):
    from app import assistant
    monkeypatch.setattr(assistant, "answer", lambda *args: None)
    ticket = raise_ticket()
    body = client.post("/api/v1/chat", json={"message": "Which documents should I upload?", "ticket": {"ticket_number": ticket, "contact": CONTACT}}).json()
    assert body["action"] == "status"
    assert "Please upload" in body["reply"]
    assert body["ticket"]["document_request"]["missing_count"] > 0


def test_report_draft_approval_and_final_gates(client, raise_ticket, admin_headers):
    ticket = raise_ticket(property_intake=INTAKE)
    base = f"/api/v1/admin/tickets/{ticket}"
    with SessionLocal() as db:
        found = db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number == ticket))
        # Fixture result represents an already grounded model analysis. Network/provider tests live in test_verification.
        result = {"input_fingerprint": verification.fingerprint(verification.snapshot(found)), "llm_status": "completed", "state": "Karnataka",
            "law_version": "2026-10-31.1", "verdict": "insufficient_evidence", "reason": "Records require independent checks.",
            "findings": [], "documents": [], "open_checks": [{"title": "Official searches", "action": "Complete current searches."}],
            "limitations": ["Not a signed opinion."], "title_chain": {"note": "Chain not established.", "transfers": []}}
        run = VerificationRun(service_request_id=found.id, result=result)
        db.add(run); db.commit(); run_id = str(run.id)
    draft = client.post(base + "/verification/report-draft", headers=admin_headers, json={"run_id": run_id})
    assert draft.status_code == 200, draft.text
    report = draft.json()["report"]
    assert report["status"] == "draft" and report["items"]
    assert "AUTOMATED DRAFT" in next(s["text"] for s in report["final_sections"] if s["key"] == "opinion")
    assert client.post(base + "/report/final", headers=admin_headers).status_code == 409
    review = {"sources": ["https://www.indiacode.nic.in/"], "notes": "Reviewed applicable current law, case records and limitations; opinion remains conditional.", "current_law_and_applicability_confirmed": True, "official_checks_reviewed": True}
    assert client.post(base + "/verification/approve", headers=admin_headers, json=review).status_code == 403
    # A recorded advocate profile is required; enrolment itself is not independently verified by the app.
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "admin@homexo.test"))
        db.add(LawyerProfile(user_id=user.id, slug="review-advocate", bar_enrolment="KAR-TEST")); db.commit()
    assert client.post(base + "/verification/approve", headers=admin_headers, json=review).status_code == 409
    client.post(base + "/report/issue", headers=admin_headers)
    # Customer cannot silently rewrite the advocate-issued checklist.
    assert client.post("/api/v1/tickets/property-intake", json={"ticket_number": ticket, "contact": CONTACT, "intake": INTAKE}).status_code == 409
    for item in report["items"]:
        assert client.patch(base + f"/report/items/{item['id']}", headers=admin_headers, json={"status": "waived", "note": "Synthetic test only: advocate records a reason for the waiver."}).status_code == 200
    assert client.post(base + "/verification/approve", headers=admin_headers, json=review).status_code == 409
    assert client.put(base + "/report", headers=admin_headers, json={"final": {"opinion": "Advocate's conditional opinion: the limitations and outstanding independent checks prevent a clear-title recommendation."}}).status_code == 200
    assert client.post(base + "/verification/approve", headers=admin_headers, json={**review, "sources": ["https://example.com/law"]}).status_code == 422
    assert client.post(base + "/verification/approve", headers=admin_headers, json=review).status_code == 200
    # An edit after approval invalidates the approval; the agent cannot sign off its own changes.
    assert client.put(base + "/report", headers=admin_headers, json={"final": {"opinion": "Changed opinion after approval"}}).status_code == 200
    assert client.post(base + "/report/final", headers=admin_headers).status_code == 409
    assert client.post(base + "/verification/approve", headers=admin_headers, json=review).status_code == 200
    assert client.post(base + "/report/final", headers=admin_headers).status_code == 200


def test_title_chain_keeps_exact_evidence_and_missing_fields():
    facts = [{"field": "seller", "value": "Ravi", "evidence": {"document_id": "d1", "page": 1, "quote": "Seller: Ravi"}}]
    chain = verification.title_chain(facts, [{"id": "d1", "filename": "deed.pdf"}])
    assert chain["transfers"][0]["fields"]["seller"][0]["evidence"]["quote"] == "Seller: Ravi"
    assert any("buyer" in gap for gap in chain["transfers"][0]["gaps"])
    assert chain["status"] == "candidate_transfers_only"


def test_title_chain_chronology_flags_identity_limits():
    facts = []
    for doc, seller, buyer, day in [("new", "Meera", "Kiran", "2023-01-01"), ("old", "Ravi", "Meera", "2020-01-01")]:
        for field, value in [("seller", seller), ("buyer", buyer), ("execution_date", day)]:
            facts.append({"field": field, "value": value, "evidence": {"document_id": doc, "page": 1, "quote": value}})
    documents = [{"id": "new", "filename": "new.pdf"}, {"id": "old", "filename": "old.pdf"}]
    chain = verification.title_chain(facts, documents)
    assert chain["chronology"] == ["old", "new"]
    assert chain["links"][0]["status"] == "name_match_only"
    facts[0]["value"] = "Different person"
    assert verification.title_chain(facts, documents)["links"][0]["status"] == "unresolved"
