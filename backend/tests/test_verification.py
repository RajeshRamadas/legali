import io
from unittest.mock import patch

import pytest
from reportlab.pdfgen import canvas
from app import config, document_reader, verification

@pytest.fixture(autouse=True)
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "S3_BUCKET", "")
    monkeypatch.setattr(config, "VERIFICATION_LLM_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")

def pdf():
    out = io.BytesIO()
    page = canvas.Canvas(out)
    page.drawString(50, 700, "SALE DEED: Survey number 42. Seller: Ravi. Buyer: Meera.")
    page.drawString(50, 680, "The property is subject to an outstanding mortgage to Example Bank.")
    page.save()
    return out.getvalue()

def upload(client, ticket):
    r = client.post("/api/v1/tickets/documents", data={"ticket_number": ticket, "contact": "+91 98765 43210", "tag": "sale-deed"}, files={"file": ("sale.pdf", pdf(), "application/pdf")})
    assert r.status_code == 201
    return r.json()["documents"][0]["id"]

def endpoint(ticket):
    return f"/api/v1/admin/tickets/{ticket}/verification"

def test_extraction_and_invalid_files():
    result = document_reader.extract(pdf(), "sale.pdf")
    assert not result["warnings"]
    assert "Survey number 42" in result["pages"][0]["text"]
    assert result["pages"][0]["method"] == "embedded_text"
    for name, data in [("scan.heic", b"bad"), ("bad.pdf", b"%PDF-1.4 broken"), ("bad.docx", b"PK\x03\x04")]:
        result = document_reader.extract(data, name)
        assert result["warnings"] and not result["pages"]

def test_run_history_staleness_and_access(client, raise_ticket, admin_headers, agent):
    ticket = raise_ticket()
    assert client.post(endpoint(ticket), headers=admin_headers, json={"state": "Karnataka"}).status_code == 422
    doc_id = upload(client, ticket)
    assert client.post(endpoint(ticket), json={"state": "Karnataka"}).status_code == 401
    assert client.get(endpoint(ticket), headers=agent["headers"]).status_code == 404
    response = client.post(endpoint(ticket), headers=admin_headers, json={"state": "Karnataka"})
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["verdict"] == "insufficient_evidence" and data["llm_status"] == "not_requested"
    assert data["stale"] is False and len(data["trace"]) == 4
    assert data["documents"][0]["pages"][0]["text"]
    assert client.post(endpoint(ticket), headers=admin_headers, json={"state": "Karnataka"}).status_code == 429
    client.patch(f"/api/v1/admin/tickets/{ticket}/documents/{doc_id}", headers=admin_headers, json={"tag": "title-deeds"})
    assert client.get(endpoint(ticket), headers=admin_headers).json()["items"][0]["stale"] is True

def test_consent_and_configuration(client, raise_ticket, admin_headers):
    ticket = raise_ticket()
    upload(client, ticket)
    payload = {"state": "Karnataka", "use_llm": True}
    assert client.post(endpoint(ticket), headers=admin_headers, json=payload).status_code == 422
    payload["consent_to_external_processing"] = True
    assert client.post(endpoint(ticket), headers=admin_headers, json=payload).status_code == 409
    assert "API_KEY" not in client.get("/api/v1/admin/verification/config", headers=admin_headers).text

@pytest.mark.parametrize("quote,law,expected", [("outstanding mortgage", "litigation", "completed"), ("invented court order", "litigation", "failed"), ("outstanding mortgage", "invented-law", "failed")])
def test_grounding_and_no_automatic_approval(client, raise_ticket, admin_headers, monkeypatch, quote, law, expected):
    monkeypatch.setattr(config, "VERIFICATION_LLM_API_KEY", "test-key")
    ticket = raise_ticket()
    doc_id = upload(client, ticket)
    evidence = {"document_id": doc_id, "page": 1, "quote": quote}
    facts = verification.Facts(facts=[verification.Fact(field="encumbrance", value="Mortgage stated in deed", evidence=evidence)])
    findings = verification.Findings(findings=[verification.Finding(title="Mortgage requires investigation", severity="high", reason="The deed describes an outstanding mortgage; obtain confirmation and a release.", action="Check lender records and discharge documentation.", law_ids=[law], evidence=[evidence])])
    with patch.object(verification, "model_call", side_effect=[facts, findings]):
        response = client.post(endpoint(ticket), headers=admin_headers, json={"state": "Tamil Nadu", "use_llm": True, "consent_to_external_processing": True})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["llm_status"] == expected
    assert result["verdict"] == ("high_risk" if expected == "completed" else "insufficient_evidence")
    assert not any(l["id"].startswith("karnataka") for l in result["laws"])
    assert "test-key" not in response.text
    assert client.get(f"/api/v1/admin/tickets/{ticket}", headers=admin_headers).json()["report"] is None
    if expected == "failed":
        assert result["facts"] == result["findings"] == []

def test_openai_transport(monkeypatch):
    import httpx
    monkeypatch.setattr(config, "VERIFICATION_LLM_API_KEY", "test")
    monkeypatch.setattr(config, "VERIFICATION_LLM_PROVIDER", "openai")
    def respond(request):
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"facts": []}'}}]})
    real_client = httpx.Client
    with patch.object(verification.httpx, "Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(respond))):
        assert verification.model_call("extract", {}, verification.Facts).facts == []

def test_scanned_image_ocr():
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (1100, 180), "white")
    ImageDraw.Draw(image).text((30, 50), "SALE DEED SURVEY NUMBER 42", fill="black", font=ImageFont.load_default(size=32))
    out = io.BytesIO()
    image.save(out, format="PNG")
    result = document_reader.extract(out.getvalue(), "scan.png")
    assert not result["warnings"]
    assert "SURVEY" in result["pages"][0]["text"]
    assert result["pages"][0]["method"] == "ocr"


def test_pdf_page_limit_is_explicit():
    out = io.BytesIO()
    page = canvas.Canvas(out)
    for number in range(16):
        page.drawString(50, 700, f"Page {number + 1}: SALE DEED Survey number 42. Property description and parties for screening.")
        page.showPage()
    page.save()
    result = document_reader.extract(out.getvalue(), "long.pdf")
    assert len(result["pages"]) == 15
    assert any("15 of 16" in warning for warning in result["warnings"])


def test_anthropic_transport(monkeypatch):
    import httpx
    monkeypatch.setattr(config, "VERIFICATION_LLM_API_KEY", "test")
    monkeypatch.setattr(config, "VERIFICATION_LLM_PROVIDER", "anthropic")
    def respond(request):
        assert request.url.host == "api.anthropic.com"
        assert request.headers["anthropic-version"] == "2023-06-01"
        return httpx.Response(200, json={"stop_reason": "end_turn", "content": [{"type": "text", "text": '{"facts": []}'}]})
    real_client = httpx.Client
    with patch.object(verification.httpx, "Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(respond))):
        assert verification.model_call("extract", {}, verification.Facts).facts == []
