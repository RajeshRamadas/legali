import json

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Notification

from test_lawyers import CUSTOMER, _book, lawyer  # noqa: F401  (fixture)

LAWYER_PHONE = "+91 90000 11111"

def test_staff_set_their_availability_and_the_team_sees_it(client, agent, admin_headers):
    no_phone = client.put("/api/v1/admin/me/availability", json={"available": True}, headers=agent["headers"])
    assert no_phone.status_code == 422 and "mobile number" in no_phone.text

    me = client.put("/api/v1/admin/me/availability", json={"available": True, "note": "Till 6 pm", "phone": LAWYER_PHONE}, headers=agent["headers"]).json()
    assert me["available_for_calls"] and me["availability_note"] == "Till 6 pm" and me["availability_updated_at"]

    team = client.get("/api/v1/admin/team", headers=admin_headers).json()["items"]
    assert [(m["name"], m["available_for_calls"], m["phone"]) for m in team] == [("Kiran Agent", True, LAWYER_PHONE), ("Meera Admin", False, None)]
    # Agents see the team too, so they know whom to call.
    assert len(client.get("/api/v1/admin/team", headers=agent["headers"]).json()["items"]) == 2
    assert client.get("/api/v1/admin/team").status_code == 401

    off = client.put("/api/v1/admin/me/availability", json={"available": False}, headers=agent["headers"]).json()
    assert not off["available_for_calls"] and off["availability_note"] is None and off["phone"] == LAWYER_PHONE

def test_urgent_tasks_reach_the_assignee(client, agent, admin_headers, raise_ticket):
    client.put("/api/v1/admin/me/availability", json={"available": False, "phone": LAWYER_PHONE}, headers=agent["headers"])
    number = raise_ticket()
    client.post(f"/api/v1/admin/tickets/{number}/assignment", json={"agent_id": agent["id"]}, headers=admin_headers)
    assert client.get("/api/v1/admin/urgent", headers=agent["headers"]).json()["items"] == []

    client.patch(f"/api/v1/admin/tickets/{number}", json={"priority": "urgent", "priority_note": "Court hearing tomorrow 10 am."}, headers=admin_headers)
    urgent = client.get("/api/v1/admin/urgent", headers=agent["headers"]).json()["items"]
    assert [u["ticket_number"] for u in urgent] == [number]
    assert urgent[0]["urgent_note"] == "Court hearing tomorrow 10 am." and urgent[0]["flagged_by"] == "Meera Admin"
    assert client.get("/api/v1/admin/reports/summary", headers=agent["headers"]).json()["urgent"] == 1

    with SessionLocal() as db:
        alerts = db.scalars(select(Notification).where(Notification.template_key == "urgent_task")).all()
        assert [(n.recipient, n.channel) for n in alerts] == [(LAWYER_PHONE, "whatsapp")]
        assert "Court hearing tomorrow" in alerts[0].body and f"/admin/tickets/{number}" in alerts[0].body

    # Reassigning an urgent ticket alerts the new owner; marking your own ticket urgent alerts nobody.
    client.post(f"/api/v1/admin/tickets/{number}/assignment", json={"agent_id": None}, headers=admin_headers)
    client.post(f"/api/v1/admin/tickets/{number}/assignment", json={"agent_id": agent["id"]}, headers=admin_headers)
    client.patch(f"/api/v1/admin/tickets/{number}", json={"priority": "normal"}, headers=agent["headers"])
    client.patch(f"/api/v1/admin/tickets/{number}", json={"priority": "urgent"}, headers=agent["headers"])
    with SessionLocal() as db:
        assert len(db.scalars(select(Notification).where(Notification.template_key == "urgent_task")).all()) == 2

def test_lawyer_phone_never_reaches_customers(client, lawyer):
    client.put("/api/v1/admin/me/availability", json={"available": True, "phone": LAWYER_PHONE}, headers=lawyer["headers"])
    digits = "9000011111"
    booking = _book(client, lawyer["slug"]).json()
    ref = {"ticket_number": booking["ticket_number"], "contact": CUSTOMER["phone"]}
    public = [
        client.get("/api/v1/lawyers").json(), client.get(f"/api/v1/lawyers/{lawyer['slug']}").json(), booking,
        client.post("/api/v1/bookings/lookup", json=ref).json(), client.post("/api/v1/tickets/lookup", json=ref).json(),
    ]
    for response in public:
        assert digits not in json.dumps(response).replace(" ", "")
    with SessionLocal() as db:
        to_customer = db.scalars(select(Notification).where(Notification.customer_id.is_not(None))).all()
        assert to_customer and all(digits not in (n.body or "").replace(" ", "") for n in to_customer)
