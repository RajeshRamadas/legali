import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app import config, google_calendar, notify, whatsapp
from app.db import SessionLocal
from app.models import Notification

MEET = "https://meet.google.com/abc-defg-hij"

def _at(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0).isoformat()

def _notifications(**filters) -> list[Notification]:
    with SessionLocal() as db:
        query = select(Notification).where(Notification.channel == "whatsapp").order_by(Notification.created_at, Notification.send_after)
        for key, value in filters.items():
            query = query.where(getattr(Notification, key) == value)
        return list(db.scalars(query).all())

@pytest.fixture
def google(monkeypatch):
    """Google Calendar on a mock transport. Records each request made."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    monkeypatch.setattr(config, "GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps({"client_email": "svc@homexo.iam.gserviceaccount.com", "private_key": pem, "token_uri": "https://oauth2.googleapis.com/token"}))
    monkeypatch.setattr(config, "GOOGLE_CALENDAR_USER", "meetings@homexo.test")
    google_calendar._token.clear()
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "token-1", "expires_in": 3600})
        if request.method == "POST":
            return httpx.Response(200, json={"id": "evt123", "hangoutLink": MEET, **json.loads(request.content)})
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"id": "evt123"})

    monkeypatch.setattr(google_calendar, "http", httpx.Client(transport=httpx.MockTransport(handler)))
    return calls

@pytest.fixture
def wa(monkeypatch):
    monkeypatch.setattr(config, "WHATSAPP_ACCESS_TOKEN", "wa-token")
    monkeypatch.setattr(config, "WHATSAPP_PHONE_NUMBER_ID", "1234")
    sent = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        if body["to"].endswith("0000000000"):
            return httpx.Response(400, json={"error": {"message": "Recipient not on WhatsApp", "code": 131026}})
        return httpx.Response(200, json={"messages": [{"id": f"wamid.{len(sent)}"}]})

    monkeypatch.setattr(whatsapp, "http", httpx.Client(transport=httpx.MockTransport(handler)))
    return sent

def test_needs_google_or_a_link(client, admin_headers, raise_ticket):
    number = raise_ticket()
    response = client.post(f"/api/v1/admin/tickets/{number}/meetings", json={"starts_at": _at(48)}, headers=admin_headers)
    assert response.status_code == 422 and "paste a meeting link" in response.json()["detail"]
    assert client.get("/api/v1/admin/meta", headers=admin_headers).json()["meetings"]["google_calendar"] is False

def test_manual_link_meeting_shows_to_customer_and_queues_whatsapp(client, admin_headers, raise_ticket):
    number = raise_ticket()
    response = client.post(f"/api/v1/admin/tickets/{number}/meetings", json={"starts_at": _at(48), "meet_link": MEET, "agenda": "Title chain questions"}, headers=admin_headers)
    assert response.status_code == 201, response.text
    meeting = response.json()["meetings"][0]
    assert meeting["meet_link"] == MEET and meeting["calendar"] == "manual" and meeting["lawyer"]["name"] == "Meera Admin"
    assert response.json()["events"][-1]["type"] == "meeting_scheduled"

    public = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "9876543210"}).json()
    assert public["meetings"][0]["meet_link"] == MEET and public["meetings"][0]["agenda"] == "Title chain questions"

    # The admin has no phone on file, so only the customer gets WhatsApp: the invite now, then 24h, 1h and 10 min reminders.
    queued = _notifications()
    assert [n.template_key for n in queued] == ["meeting_scheduled", "meeting_reminder", "meeting_reminder", "meeting_reminder"]
    assert all(n.recipient == "+91 98765 43210" and n.customer_id for n in queued)
    assert MEET in queued[0].body and "Sample Customer" in queued[0].body
    starts = datetime.fromisoformat(meeting["starts_at"])
    assert [n.send_after.replace(tzinfo=timezone.utc) for n in queued[1:]] == [starts - timedelta(minutes=m) for m in (1440, 60, 10)]

def test_google_meeting_lifecycle(client, admin_headers, agent, raise_ticket, google):
    number = raise_ticket()
    client.patch(f"/api/v1/admin/staff/{agent['id']}", json={"phone": "+91 90000 11111"}, headers=admin_headers)
    response = client.post(f"/api/v1/admin/tickets/{number}/meetings", json={"starts_at": _at(30), "lawyer_id": agent["id"]}, headers=admin_headers)
    assert response.status_code == 201, response.text
    meeting = response.json()["meetings"][0]
    assert meeting["meet_link"] == MEET and meeting["calendar"] == "google" and meeting["lawyer"]["name"] == "Kiran Agent"

    event = json.loads(google[1].content)
    assert google[1].url.params["conferenceDataVersion"] == "1" and google[1].url.params["sendUpdates"] == "all"
    assert event["conferenceData"]["createRequest"]["conferenceSolutionKey"] == {"type": "hangoutsMeet"}
    assert {a["email"] for a in event["attendees"]} == {"sample@example.com", "kiran@homexo.test"}
    # Customer and lawyer each get the invite.
    invites = _notifications(template_key="meeting_scheduled")
    assert {n.recipient for n in invites} == {"+91 98765 43210", "+91 90000 11111"}
    lawyer_invite = next(n for n in invites if n.user_id)
    assert lawyer_invite.params[0] == "Kiran Agent" and lawyer_invite.params[3] == "Sample Customer"

    # Rescheduling moves the Google event and replaces the queued messages.
    moved = client.patch(f"/api/v1/admin/meetings/{meeting['id']}", json={"starts_at": _at(50), "duration_minutes": 45}, headers=admin_headers)
    assert moved.status_code == 200, moved.text
    assert google[-1].method == "PATCH" and "evt123" in google[-1].url.path
    assert {n.delivery_status for n in _notifications(template_key="meeting_scheduled")} == {"cancelled"}
    assert len(_notifications(template_key="meeting_rescheduled")) == 2
    reminders = [n.delivery_status for n in _notifications(template_key="meeting_reminder")]
    assert reminders.count("cancelled") == 6 and reminders.count("queued") == 6  # 3 each for customer and lawyer

    # The lawyer sees it on their calendar and can open the ticket, though it isn't assigned to them.
    calendar = client.get("/api/v1/admin/meetings", params={"start": _at(0), "end": _at(24 * 7)}, headers=agent["headers"]).json()
    assert [m["ticket_number"] for m in calendar["items"]] == [number]
    assert client.get(f"/api/v1/admin/tickets/{number}", headers=agent["headers"]).status_code == 200

    cancelled = client.patch(f"/api/v1/admin/meetings/{meeting['id']}", json={"status": "cancelled", "reason": "Customer asked to postpone."}, headers=agent["headers"])
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled" and cancelled.json()["meet_link"] is None
    assert google[-1].method == "DELETE"
    assert [n.params[4] for n in _notifications(template_key="meeting_cancelled")] == ["Customer asked to postpone."] * 2
    assert not [n for n in _notifications(template_key="meeting_reminder") if n.delivery_status == "queued"]
    assert client.get("/api/v1/admin/meetings", params={"start": _at(0), "end": _at(24 * 7)}, headers=agent["headers"]).json()["items"] == []

def test_google_errors_are_reported(client, admin_headers, raise_ticket, google, monkeypatch):
    monkeypatch.setattr(google_calendar, "http", httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"access_token": "t", "expires_in": 3600}) if r.url.host == "oauth2.googleapis.com"
        else httpx.Response(403, json={"error": {"message": "Not authorized to access this resource/api"}}))))
    response = client.post(f"/api/v1/admin/tickets/{raise_ticket()}/meetings", json={"starts_at": _at(30)}, headers=admin_headers)
    assert response.status_code == 502 and "Not authorized" in response.json()["detail"]
    assert _notifications() == []

def test_clashes_past_times_and_agent_limits(client, admin_headers, agent, raise_ticket):
    number = raise_ticket()
    start = _at(26)
    assert client.post(f"/api/v1/admin/tickets/{number}/meetings", json={"starts_at": start, "meet_link": MEET}, headers=admin_headers).status_code == 201
    clash = client.post(f"/api/v1/admin/tickets/{number}/meetings", json={"starts_at": _at(26.25), "meet_link": MEET}, headers=admin_headers)
    assert clash.status_code == 409 and "Meera Admin already has a meeting" in clash.json()["detail"]
    assert client.post(f"/api/v1/admin/tickets/{number}/meetings", json={"starts_at": _at(-1), "meet_link": MEET}, headers=admin_headers).status_code == 422

    client.post(f"/api/v1/admin/tickets/{number}/assignment", json={"agent_id": agent["id"]}, headers=admin_headers)
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()["id"]
    assert client.post(f"/api/v1/admin/tickets/{number}/meetings", json={"starts_at": _at(30), "meet_link": MEET, "lawyer_id": me}, headers=agent["headers"]).status_code == 403
    own = client.post(f"/api/v1/admin/tickets/{number}/meetings", json={"starts_at": _at(26), "meet_link": MEET}, headers=agent["headers"])
    assert own.status_code == 201  # Different lawyer, so the same time is free.

    window = {"start": _at(0), "end": _at(24 * 7)}
    assert len(client.get("/api/v1/admin/meetings", params={**window, "lawyer": "all"}, headers=admin_headers).json()["items"]) == 2
    assert len(client.get("/api/v1/admin/meetings", params={**window, "lawyer": "all"}, headers=agent["headers"]).json()["items"]) == 1
    admin_meeting = client.get("/api/v1/admin/meetings", params=window, headers=admin_headers).json()["items"][0]
    assert client.patch(f"/api/v1/admin/meetings/{admin_meeting['id']}", json={"status": "completed"}, headers=agent["headers"]).status_code == 404

def test_delivery_sends_due_whatsapp_and_expires_stale(client, admin_headers, raise_ticket, wa):
    number = raise_ticket()
    client.post(f"/api/v1/admin/tickets/{number}/meetings", json={"starts_at": _at(2), "meet_link": MEET}, headers=admin_headers)
    with SessionLocal() as db:
        assert notify.deliver_due(db) == 1  # The invite; the 1h and 10 min reminders aren't due yet.
    assert wa[0]["to"] == "919876543210" and wa[0]["template"]["name"] == "meeting_scheduled"
    assert [p["text"] for p in wa[0]["template"]["components"][0]["parameters"]][4] == MEET

    with SessionLocal() as db:
        assert notify.deliver_due(db, now=datetime.now(timezone.utc) + timedelta(minutes=65)) == 1
        # Worker down past the start: the 10 minute reminder is dropped rather than sent late.
        assert notify.deliver_due(db, now=datetime.now(timezone.utc) + timedelta(hours=3)) == 0
    statuses = [(n.template_key, n.delivery_status, n.error_code) for n in _notifications()]
    assert statuses == [("meeting_scheduled", "sent", None), ("meeting_reminder", "sent", None), ("meeting_reminder", "cancelled", "expired")]
    assert _notifications()[0].provider_reference == "wamid.1"

def test_delivery_failure_is_recorded(client, admin_headers, raise_ticket, wa):
    number = raise_ticket(contact="0000000000")
    client.post(f"/api/v1/admin/tickets/{number}/meetings", json={"starts_at": _at(48), "meet_link": MEET}, headers=admin_headers)
    with SessionLocal() as db:
        notify.deliver_due(db)
    failed = _notifications(template_key="meeting_scheduled")[0]
    assert failed.delivery_status == "failed" and failed.error_code == "131026"

def test_no_whatsapp_credentials_keeps_messages_queued(client, admin_headers, raise_ticket):
    client.post(f"/api/v1/admin/tickets/{raise_ticket()}/meetings", json={"starts_at": _at(48), "meet_link": MEET}, headers=admin_headers)
    with SessionLocal() as db:
        assert notify.deliver_due(db) == 0
    assert {n.delivery_status for n in _notifications()} == {"queued"}

def test_daily_agenda_goes_once_to_each_lawyer(client, admin_headers, agent, raise_ticket, monkeypatch):
    monkeypatch.setattr(config, "MEETING_TIMEZONE", "UTC")
    monkeypatch.setattr(config, "LAWYER_AGENDA_HOUR", 0)
    client.patch(f"/api/v1/admin/staff/{agent['id']}", json={"phone": "9000011111"}, headers=admin_headers)
    now = datetime.now(timezone.utc).replace(hour=0, minute=5, second=0, microsecond=0)
    for hours in (10, 14):
        client.post(f"/api/v1/admin/tickets/{raise_ticket()}/meetings", json={"starts_at": (now + timedelta(hours=hours)).isoformat(), "meet_link": MEET, "lawyer_id": agent["id"]}, headers=admin_headers)
    with SessionLocal() as db:
        if now + timedelta(hours=10) <= datetime.now(timezone.utc):
            pytest.skip("Too late in the UTC day to book today's meetings in the future.")
        assert notify.queue_daily_agendas(db, now=now) == 1
        assert notify.queue_daily_agendas(db, now=now + timedelta(minutes=1)) == 0
    agenda = _notifications(template_key="lawyer_daily_agenda")[0]
    assert agenda.params[:2] == ["Kiran Agent", "2"] and "10:05 am Sample Customer" in agenda.params[2]
    assert agenda.params[3].endswith("/admin/calendar")

def test_staff_whatsapp_number(client, admin_headers, agent):
    response = client.post("/api/v1/admin/staff", json={"display_name": "Asha Advocate", "email": "asha@homexo.test", "password": "long-enough-pw", "role": "agent", "phone": "+91 99887 76655"}, headers=admin_headers)
    assert response.status_code == 201 and response.json()["phone"] == "+91 99887 76655"
    taken = client.patch(f"/api/v1/admin/staff/{agent['id']}", json={"phone": "+91 99887 76655"}, headers=admin_headers)
    assert taken.status_code == 409
    assert client.patch(f"/api/v1/admin/staff/{agent['id']}", json={"phone": "123"}, headers=admin_headers).status_code == 422
    cleared = client.patch(f"/api/v1/admin/staff/{response.json()['id']}", json={"phone": ""}, headers=admin_headers)
    assert cleared.json()["phone"] is None
