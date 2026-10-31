import io

import pytest

from app import config

CONTACT = "+91 98765 43210"
PDF = b"%PDF-1.4\n% sample\n"
INTAKE = {"state": "Karnataka", "transaction": "purchase", "seller_capacity": "owner", "development": "resale", "granted_land": "no"}


@pytest.fixture(autouse=True)
def local_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOCAL_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(config, "S3_BUCKET", "")


def journey(client, ticket):
    return client.post("/api/v1/tickets/lookup", json={"ticket_number": ticket, "contact": CONTACT}).json()["document_request"]["journey"]


def by_key(rows):
    return {r["key"]: r for r in rows}


def test_automatic_request_journey_groups_and_next_upload(client, raise_ticket):
    ticket = raise_ticket(property_intake=INTAKE)
    first = journey(client, ticket)
    stages = by_key(first["stages"])
    assert [s["key"] for s in first["stages"]] == ["details", "upload", "official", "reading", "review", "report"]
    assert stages["details"]["status"] == "done" and stages["upload"]["status"] == "current" and stages["report"]["status"] == "upcoming"
    groups = by_key(first["groups"])
    assert "sale-deed" in groups["title"]["tags"] and groups["charges"]["tags"] == ["ec"] and "litigation-search" in groups["searches"]["tags"]
    assert {"from": "identity", "to": "title"} in first["links"]
    checks = by_key(first["checks"])
    assert checks["title"]["status"] == "waiting" and "Waiting for you" in checks["title"]["detail"]
    assert "case team is getting" in checks["charges"]["detail"] and checks["opinion"]["status"] == "waiting"

    request = client.post("/api/v1/tickets/lookup", json={"ticket_number": ticket, "contact": CONTACT}).json()["document_request"]
    first_needed = next(i for i in request["items"] if i["id"] == first["next_upload"])
    assert first_needed["fetch_by"] == "customer" and first_needed["group"]

    data = {"ticket_number": ticket, "contact": CONTACT, "tag": "owner-id"}
    client.post("/api/v1/tickets/documents", data=data, files={"file": ("id.pdf", io.BytesIO(PDF), "application/pdf")})
    after = journey(client, ticket)
    assert by_key(after["checks"])["identity"]["status"] == "in_review"
    assert by_key(after["stages"])["reading"]["status"] == "current"


def test_reviewed_items_drive_check_status(client, raise_ticket, admin_headers):
    ticket = raise_ticket(property_intake=INTAKE)
    template = client.get("/api/v1/admin/report-template", params={"ticket": ticket}, headers=admin_headers).json()
    items = [i for i in template["items"] if i["tag"] in ("sale-deed", "ec", "owner-id")] + [{"label": "Family tree", "guidance": "Notarised"}]
    client.put(f"/api/v1/admin/tickets/{ticket}/report", json={"items": items}, headers=admin_headers)
    report = client.post(f"/api/v1/admin/tickets/{ticket}/report/issue", headers=admin_headers).json()["report"]
    ids = {i["tag"]: i["id"] for i in report["items"]}
    patch = lambda tag, body: client.patch(f"/api/v1/admin/tickets/{ticket}/report/items/{ids[tag]}", json=body, headers=admin_headers)
    patch("sale-deed", {"status": "rejected", "note": "Page 3 is missing."})
    patch("owner-id", {"status": "verified"})
    patch("ec", {"status": "waived", "note": "Fresh EC ordered separately."})
    view = journey(client, ticket)
    checks = by_key(view["checks"])
    assert checks["title"]["status"] == "problem" and "Sale deed" in checks["title"]["detail"]
    assert checks["identity"]["status"] == "passed" and checks["charges"]["status"] == "passed"
    assert checks["other"]["tags"] == ["family-tree"]
    assert by_key(view["stages"])["review"]["status"] == "current"
    # A rejected document is asked for again before anything new.
    request = client.post("/api/v1/tickets/lookup", json={"ticket_number": ticket, "contact": CONTACT}).json()["document_request"]
    assert view["next_upload"] == next(i["id"] for i in request["items"] if i["tag"] == "sale-deed")
    staff = client.get(f"/api/v1/admin/tickets/{ticket}", headers=admin_headers).json()
    assert by_key(staff["document_request"]["journey"]["checks"])["title"]["status"] == "problem"


def test_upload_check_problems_show_as_flags(client, raise_ticket):
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import Document

    ticket = raise_ticket(property_intake=INTAKE)
    data = {"ticket_number": ticket, "contact": CONTACT, "tag": "sale-deed"}
    client.post("/api/v1/tickets/documents", data=data, files={"file": ("deed.pdf", io.BytesIO(PDF), "application/pdf")})
    with SessionLocal() as db:
        doc = db.scalar(select(Document).where(Document.original_filename == "deed.pdf"))
        # Stored exactly as upload_check.assess stores it: tag_mismatch is never saved, only suggested_tag.
        doc.ai_check = {"status": "done", "document_type": "Khata certificate", "suggested_tag": "khata", "problems": ["Page 2 is cut off."]}
        db.commit()
    view = journey(client, ticket)
    title = by_key(view["checks"])["title"]
    assert title["flags"] == ["deed.pdf looks like Khata certificate, not Sale deed of the present owner.", "deed.pdf: Page 2 is cut off."]
    assert by_key(view["groups"])["title"]["flagged"]

    # Once the file is filed under the tag the check suggested, the mismatch flag goes without another check.
    with SessionLocal() as db:
        doc = db.scalar(select(Document).where(Document.original_filename == "deed.pdf"))
        doc.ai_check = {**doc.ai_check, "suggested_tag": "sale-deed"}
        db.commit()
    assert by_key(journey(client, ticket)["checks"])["title"]["flags"] == ["deed.pdf: Page 2 is cut off."]
