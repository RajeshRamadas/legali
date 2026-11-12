from datetime import datetime, timedelta, timezone
import uuid

import jwt
import pytest
from sqlalchemy import event, func, select

from app import case_files, config, file_access, report_pdf, storage
from app.db import SessionLocal, engine
from app.models import ApiRateBucket, AuditLog, CustomerAccount, Document, LegalReport, ServiceRequest, User, utcnow
from conftest import authenticate_customer
from test_documents import _report, _template, _upload, local_storage

BASE = "/api/v1/admin/file-access"
SECRET = "PRIVATE-file-contents-or-credential@example.invalid"
WHEN = datetime(2026, 11, 11, 7, tzinfo=timezone.utc)


def accesses():
    with SessionLocal() as db:
        return list(db.scalars(select(AuditLog).where(AuditLog.action.in_(file_access.ACTIONS))))


def seed(ticket_id, *, action="file.customer_document_authorized", at=WHEN, key=None, actor=None, reference=None):
    with SessionLocal() as db:
        row = AuditLog(id=key or uuid.uuid4(), actor_user_id=actor, action=action, entity_type="service_request", entity_id=ticket_id,
            created_at=at, metadata_={"file_id": reference or str(uuid.uuid4()), "customer_account_id": str(uuid.uuid4()), "token": SECRET, "body": SECRET}, request_id=SECRET, ip_hash=SECRET)
        db.add(row); db.commit(); return str(row.id)


def test_customer_and_staff_file_requests_record_only_safe_references(client, raise_ticket, admin_headers, local_storage):
    number = raise_ticket()
    document = _upload(client, number, name="private-customer-deed.pdf").json()["documents"][0]
    assert accesses() == []
    assert client.get(document["download_url"]).status_code == 200
    assert client.get(document["download_url"], headers=admin_headers).status_code == 200
    rows = accesses()
    assert {row.action for row in rows} == {"file.customer_document_authorized", "file.staff_document_authorized"}
    with SessionLocal() as db:
        account = db.scalar(select(CustomerAccount))
        ticket = db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number == number))
        admin = db.scalar(select(User).where(User.email == "admin@homexo.test"))
        for row in rows:
            assert row.entity_type == "service_request" and row.entity_id == ticket.id
            assert row.request_id is None and row.ip_hash is None
            assert row.metadata_["file_id"] == document["id"]
            if row.action.startswith("file.customer"):
                assert row.actor_user_id is None and row.metadata_ == {"file_id": document["id"], "customer_account_id": str(account.id)}
            else:
                assert row.actor_user_id == admin.id and row.metadata_ == {"file_id": document["id"]}
    assert "private-customer-deed" not in str([row.metadata_ for row in rows])
    assert document["download_url"] not in str([row.metadata_ for row in rows])


def test_denied_quarantined_expired_and_missing_document_requests_do_not_create_authorizations(client, raise_ticket, admin_headers, agent, local_storage):
    number = raise_ticket()
    document = _upload(client, number).json()["documents"][0]
    owner = dict(client.headers)
    assert client.get(document["download_url"], headers=agent["headers"]).status_code == 404
    other = authenticate_customer(client, "9999900001")
    assert client.get(document["download_url"], headers=other).status_code == 404
    assert client.get(document["download_url"], headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.get("/api/v1/files/not-a-token", headers=admin_headers).status_code == 404
    expired = jwt.encode({"doc": document["id"], "aud": "homexo-download", "exp": utcnow()-timedelta(seconds=1)}, config.JWT_SECRET, algorithm="HS256")
    assert client.get("/api/v1/files/"+expired, headers=admin_headers).status_code == 404
    assert client.get(case_files.file_url(uuid.uuid4()), headers=admin_headers).status_code == 404
    with SessionLocal() as db:
        db.get(Document, uuid.UUID(document["id"])).scan_status = "infected"; db.commit()
    response = client.get(document["download_url"], headers=owner)
    assert response.status_code == 423
    assert accesses() == []


def test_draft_preliminary_report_is_staff_only_and_issued_report_has_customer_audit(client, raise_ticket, admin_headers, monkeypatch):
    number = raise_ticket()
    monkeypatch.setattr(report_pdf, "preliminary_pdf", lambda *args: b"%PDF synthetic report")
    _report(client, admin_headers, number, preliminary={"observations": "PRIVATE draft"}, items=_template(client, admin_headers, number)["items"][:1])
    with SessionLocal() as db:
        row = db.scalar(select(LegalReport)); url = case_files.preliminary_url(row); reference = str(row.id)
    assert client.get(url).status_code == 404 and accesses() == []
    assert client.get(url, headers=admin_headers).status_code == 200
    assert client.post(f"/api/v1/admin/tickets/{number}/report/issue", headers=admin_headers).status_code == 200
    assert client.get(url).status_code == 200
    assert {row.action for row in accesses()} == {"file.staff_preliminary_authorized", "file.customer_preliminary_authorized"}
    assert all(row.metadata_["file_id"] == reference for row in accesses())


def test_authorization_is_retained_if_storage_later_returns_missing_file(client, raise_ticket, local_storage):
    number = raise_ticket(); document = _upload(client, number).json()["documents"][0]
    with SessionLocal() as db: stored = db.get(Document, uuid.UUID(document["id"])).storage_key
    storage.delete(stored)
    assert client.get(document["download_url"]).status_code == 404
    assert len(accesses()) == 1


def test_ranges_record_separate_authorized_requests_and_records_survive_file_deletion(client, raise_ticket, local_storage):
    number = raise_ticket(); document = _upload(client, number).json()["documents"][0]
    response = client.get(document["download_url"], headers={"Range":"bytes=0-3"})
    assert response.status_code == 206 and response.content == b"%PDF"
    assert client.get(document["download_url"]).status_code == 200
    assert client.post("/api/v1/tickets/documents/delete", json={"ticket_number":number,"contact":"9876543210","document_id":document["id"]}).status_code == 200
    assert len(accesses()) == 2


def test_audit_failure_blocks_storage_opening_and_private_report_generation(client, raise_ticket, admin_headers, monkeypatch):
    from sqlalchemy.orm import Session
    number = raise_ticket(); document = _upload(client, number).json()["documents"][0]
    _report(client, admin_headers, number, preliminary={"observations":"PRIVATE"})
    with SessionLocal() as db: url = case_files.preliminary_url(db.scalar(select(LegalReport)))
    calls = []
    monkeypatch.setattr(storage, "download_response", lambda *args, **kwargs: calls.append("storage"))
    monkeypatch.setattr(report_pdf, "preliminary_pdf", lambda *args: calls.append("report"))
    def reject(session, context, instances):
        if any(isinstance(row, AuditLog) and row.action in file_access.ACTIONS for row in session.new):
            raise RuntimeError("Synthetic audit failure")
    event.listen(Session, "before_flush", reject)
    try:
        assert client.get(document["download_url"]).status_code == 500
        assert client.get(url, headers=admin_headers).status_code == 500
    finally: event.remove(Session, "before_flush", reject)
    assert calls == [] and accesses() == []


def test_history_is_admin_only_private_read_only_and_exposes_no_arbitrary_payload(client, raise_ticket, admin_headers, agent):
    number = raise_ticket()
    with SessionLocal() as db: ticket_id = db.scalar(select(ServiceRequest.id).where(ServiceRequest.ticket_number == number))
    key = seed(ticket_id)
    seed(ticket_id, action=SECRET)
    assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers=agent["headers"]).status_code == 403
    for method in ("post", "patch", "delete"): assert getattr(client, method)(BASE, headers=admin_headers).status_code == 405
    before = len(accesses())
    response = client.get(BASE, headers=admin_headers)
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    assert SECRET not in response.text and "9876543210" not in response.text and "customer_account_id" not in response.text
    assert len(response.json()["items"]) == 1 and response.json()["items"][0]["id"] == key
    assert set(response.json()["items"][0]) == {"id","at","reader","actor","kind","case_reference","ticket_number","file_reference"}
    assert client.get(BASE, headers=admin_headers).status_code == 200 and len(accesses()) == before


def test_reader_kind_case_and_india_day_filters_combine(client, raise_ticket, admin_headers):
    number = raise_ticket()
    with SessionLocal() as db:
        ticket_id = db.scalar(select(ServiceRequest.id).where(ServiceRequest.ticket_number == number))
        actor = db.scalar(select(User.id).where(User.email == "admin@homexo.test"))
    first = datetime(2026,11,10,18,30,tzinfo=timezone.utc); last = first+timedelta(days=1)-timedelta(microseconds=1)
    kept = {seed(ticket_id, action="file.staff_preliminary_authorized", at=first, actor=actor), seed(ticket_id, action="file.staff_preliminary_authorized", at=last, actor=actor)}
    seed(ticket_id, action="file.staff_preliminary_authorized", at=first-timedelta(microseconds=1))
    seed(ticket_id, action="file.staff_preliminary_authorized", at=last+timedelta(microseconds=1))
    seed(ticket_id); seed(uuid.uuid4(), action="file.staff_preliminary_authorized")
    response = client.get(BASE, headers=admin_headers, params={"reader":"staff","kind":"preliminary_report","ticket_number":number.lower(),"from_date":"2026-11-11","to_date":"2026-11-11"})
    assert response.status_code == 200 and {row["id"] for row in response.json()["items"]} == kept
    assert all(row["actor"] == "Meera Admin" for row in response.json()["items"])


def test_cursor_ties_and_new_records_preserve_older_pages(client, admin_headers):
    ticket_id = uuid.uuid4()
    keys = {seed(ticket_id, key=uuid.UUID(int=n)) for n in range(1,8)}
    result = client.get(BASE, headers=admin_headers, params={"page_size":2}).json()
    seen = [row["id"] for row in result["items"]]
    seed(ticket_id, at=WHEN+timedelta(hours=1))
    while result["next_cursor"]:
        result = client.get(BASE, headers=admin_headers, params={"page_size":2,"cursor":result["next_cursor"]}).json()
        seen.extend(row["id"] for row in result["items"])
    assert len(seen) == 7 and set(seen) == keys
    assert all(row["ticket_number"] is None for row in result["items"])


@pytest.mark.parametrize("params", [{"reader":"unknown"},{"kind":"unknown"},{"page_size":51},{"cursor":"broken"},{"ticket_number":"<script>"},{"from_date":"2026-11-12","to_date":"2026-11-11"}])
def test_invalid_filters_fail_validation(client, admin_headers, params):
    assert client.get(BASE, headers=admin_headers, params=params).status_code == 422


@pytest.mark.parametrize("value", [SECRET, {"token":SECRET}, [SECRET], 10])
def test_malformed_file_references_never_expose_private_json(client, admin_headers, value):
    seed(uuid.uuid4(), reference=value)
    response = client.get(BASE, headers=admin_headers)
    assert response.status_code == 200 and response.json()["items"][0]["file_reference"] is None
    assert SECRET not in response.text


def test_history_reads_use_shared_lookup_budget(client, admin_headers, monkeypatch):
    with SessionLocal() as db: db.query(ApiRateBucket).delete(); db.commit()
    monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(BASE, headers=admin_headers).status_code == 200
    assert client.get(BASE, headers=admin_headers).status_code == 429
