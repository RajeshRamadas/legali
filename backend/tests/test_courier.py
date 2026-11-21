from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog
from conftest import authenticate_customer


SERVICE = "document-retrieval-courier"
DISPATCH = {
    "carrier": "Example Courier",
    "tracking_number": "EX-123456",
    "status": "dispatched",
    "revision": 0,
}


def test_courier_status_updates_are_private_and_audited(client, raise_ticket, admin_headers):
    number = raise_ticket(service_slug=SERVICE)
    owner = dict(client.headers)
    case = f"/api/v1/admin/tickets/{number}"
    tracking = f"/api/v1/account/requests/{number}"
    assert client.get(tracking).json()["courier"] is None

    first = client.put(f"{case}/courier", json=DISPATCH, headers=admin_headers)
    assert first.status_code == 200, first.text
    assert first.json()["courier"]["revision"] == 1
    retry = client.put(f"{case}/courier", json=DISPATCH, headers=admin_headers)
    assert retry.json()["courier"]["revision"] == 1
    assert client.put(f"{case}/courier", json={**DISPATCH, "status": "in_transit"}, headers=admin_headers).status_code == 409

    for revision, status in enumerate(("in_transit", "delivery_issue", "out_for_delivery", "delivered"), start=1):
        updated = client.put(f"{case}/courier", json={**DISPATCH, "status": status, "revision": revision}, headers=admin_headers)
        assert updated.status_code == 200, updated.text
    assert client.put(f"{case}/courier", json={**DISPATCH, "status": "in_transit", "revision": 5}, headers=admin_headers).status_code == 409
    corrected = client.put(
        f"{case}/courier",
        json={**DISPATCH, "status": "delivered", "revision": 5, "tracking_number": "EX-654321"},
        headers=admin_headers,
    )
    assert corrected.status_code == 200, corrected.text
    view = client.get(tracking, headers=owner).json()["courier"]
    assert set(view) == {"carrier", "tracking_number", "status", "updated_at", "history"}
    assert view["status"] == "delivered"
    assert view["tracking_number"] == "EX-654321"
    assert [entry["status"] for entry in view["history"]] == [
        "dispatched", "in_transit", "delivery_issue", "out_for_delivery", "delivered",
    ]
    lookup = client.post(
        "/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "9876543210"}, headers=owner,
    )
    assert lookup.json()["courier"] == view
    assert "no-store" in lookup.headers["cache-control"]

    other = authenticate_customer(client, phone="9876543211")
    assert client.get(tracking, headers=other).status_code == 404
    assert client.post(
        "/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "9876543210"}, headers=other,
    ).status_code == 404
    client.headers.pop("authorization")
    assert client.get(tracking).status_code == 401
    with SessionLocal() as db:
        entries = db.scalars(select(AuditLog).where(AuditLog.action == "case.courier_updated")).all()
        assert len(entries) == 6
        assert all(set(entry.metadata_) == {"previous_status", "status", "revision"} for entry in entries)


def test_courier_updates_require_case_access_and_valid_dispatch(client, raise_ticket, agent, admin_headers):
    other = raise_ticket()
    number = raise_ticket(service_slug=SERVICE)
    case = f"/api/v1/admin/tickets/{number}"
    assert client.put(
        f"/api/v1/admin/tickets/{other}/courier", json=DISPATCH, headers=admin_headers,
    ).status_code == 404
    assert client.put(f"{case}/courier", json=DISPATCH).status_code in (401, 403)
    assert client.put(f"{case}/courier", json=DISPATCH, headers=agent["headers"]).status_code == 404
    assert client.put(
        f"{case}/courier", json={**DISPATCH, "status": "delivered"}, headers=admin_headers,
    ).status_code == 409
    for changes in ({"carrier": " "}, {"tracking_number": "https://example.com"}, {"revision": "0"}):
        assert client.put(f"{case}/courier", json={**DISPATCH, **changes}, headers=admin_headers).status_code == 422
    response = client.post(f"{case}/assignment", json={"agent_id": agent["id"]}, headers=admin_headers)
    assert response.status_code == 200, response.text
    response = client.put(f"{case}/courier", json=DISPATCH, headers=agent["headers"])
    assert response.status_code == 200, response.text
    assert response.json()["courier"]["status"] == "dispatched"
    assert client.post(f"{case}/assignment", json={"agent_id": None}, headers=admin_headers).status_code == 200
    assert client.put(
        f"{case}/courier", json={**DISPATCH, "status": "delivered", "revision": 1}, headers=agent["headers"],
    ).status_code == 404
