import io
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from reportlab.pdfgen import canvas

from app import config, upload_check, verification

CONTACT = "+91 98765 43210"


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "S3_BUCKET", "")
    monkeypatch.setattr(config, "VERIFICATION_LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(config, "VERIFICATION_LLM_MODEL", "")
    monkeypatch.setattr(config, "VERIFICATION_CLASSIFY_MODEL", "")
    monkeypatch.setattr(config, "VERIFICATION_EXTRACT_MODEL", "")
    monkeypatch.setattr(config, "VERIFICATION_COMPARE_MODEL", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "VERIFICATION_LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "VERIFICATION_UPLOAD_CHECKS", True)


def pdf(text="ENCUMBRANCE CERTIFICATE FORM 15. Search period 01-04-2015 to 31-03-2020. Survey No. 42/1."):
    out = io.BytesIO()
    page = canvas.Canvas(out)
    page.drawString(50, 700, text)
    page.save()
    return out.getvalue()


def upload(client, ticket, tag):
    r = client.post("/api/v1/tickets/documents", data={"ticket_number": ticket, "contact": CONTACT, "tag": tag},
                    files={"file": ("upload.pdf", pdf(), "application/pdf")})
    assert r.status_code == 201, r.text
    return r


def lookup(client, ticket):
    return client.post("/api/v1/tickets/lookup", json={"ticket_number": ticket, "contact": CONTACT}).json()


def ec_result(**overrides):
    values = dict(document_type="Encumbrance certificate (Form 15)", suggested_tag="ec", legible="yes", complete="yes",
                  issue_date="", period_from="2015-04-01", period_to="2020-03-31", summary="EC for Survey No. 42/1.", problems=[])
    return upload_check.UploadCheck(**(values | overrides))


def test_off_without_configuration(client, raise_ticket, monkeypatch):
    monkeypatch.setattr(config, "VERIFICATION_LLM_API_KEY", "")
    ticket = raise_ticket()
    with patch.object(verification, "model_call") as call:
        doc = upload(client, ticket, "ec").json()["documents"][0]
    call.assert_not_called()
    assert doc["check"] is None


def test_wrong_tag_and_short_old_ec_are_flagged(client, raise_ticket):
    ticket = raise_ticket()
    with patch.object(verification, "model_call", return_value=ec_result()) as call:
        first = upload(client, ticket, "sale-deed").json()["documents"][0]
    assert first["check"] == {"status": "pending"}
    assert call.call_args.kwargs["step"] == "classify" and call.call_args.kwargs["system"] == upload_check.SYSTEM
    [doc] = lookup(client, ticket)["documents"]
    check = doc["check"]
    assert check["status"] == "done" and check["suggested_tag"] == "ec" and check["tag_mismatch"] is True
    assert any("31 Mar 2020" in p for p in check["problems"])
    assert any("We need 30 years" in p for p in check["problems"])
    # Retagging to the suggested tag clears the mismatch without another model call.
    retagged = client.post("/api/v1/tickets/documents/tag", json={"ticket_number": ticket, "contact": CONTACT, "document_id": doc["id"], "tag": "ec"}).json()
    assert retagged["documents"][0]["check"]["tag_mismatch"] is False
    # Advice only: the checklist item is received, never verified or rejected by the check.
    assert all(i["status"] in ("pending", "received") for i in retagged["document_request"]["items"])


def test_current_full_ec_has_no_problems_and_unknown_tags_are_dropped(client, raise_ticket):
    ticket = raise_ticket()
    today = date.today()
    result = ec_result(period_from=(today - timedelta(days=31 * 365)).isoformat(), period_to=today.isoformat())
    with patch.object(verification, "model_call", return_value=result):
        upload(client, ticket, "ec")
    check = lookup(client, ticket)["documents"][0]["check"]
    assert check["problems"] == [] and check["tag_mismatch"] is False
    with patch.object(verification, "model_call", return_value=ec_result(suggested_tag="made-up", period_to="31/03/2020")):
        upload(client, ticket, "khata")
    check = next(d for d in lookup(client, ticket)["documents"] if d["tag"] == "khata")["check"]
    assert check["suggested_tag"] == "" and check["period_to"] == "" and check["tag_mismatch"] is False


def test_failure_is_recorded_and_staff_can_recheck(client, raise_ticket, admin_headers):
    import httpx
    ticket = raise_ticket()
    with patch.object(verification, "model_call", side_effect=httpx.ConnectError("down")):
        upload(client, ticket, "ec")
    [doc] = lookup(client, ticket)["documents"]
    assert doc["check"]["status"] == "failed"
    with patch.object(verification, "model_call", return_value=ec_result()):
        r = client.post(f"/api/v1/admin/tickets/{ticket}/documents/{doc['id']}/check", headers=admin_headers)
    assert r.status_code == 200, r.text
    staff_doc = next(d for d in r.json()["documents"] if d["id"] == doc["id"])
    assert staff_doc["check"]["status"] == "done"
