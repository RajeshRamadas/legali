from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import config
from app.db import SessionLocal
from app.meetings import LINK_TO_FOLLOW
from app.models import Meeting, Notification

ALL_DAY = {d: [["00:00", "12:00"], ["12:00", "23:30"]] for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
PROFILE = {
    "headline": "Property title and RERA disputes", "bio": "Helps buyers check title before they pay.",
    "specialisations": ["Property & real estate", "Consumer protection"], "languages": ["English", "Kannada"],
    "courts": ["Karnataka High Court"], "experience_years": 12, "consultation_fee": 1500, "consultation_minutes": 30,
    "city": "Bengaluru", "locality": "Jayanagar", "weekly_hours": ALL_DAY, "is_listed": True,
}
CUSTOMER = {"customer_name": "Priya Sharma", "phone": "+91 98450 12345", "email": "priya@example.com", "issue": "Builder has delayed possession by two years."}

@pytest.fixture
def lawyer(client, agent):
    response = client.put("/api/v1/admin/lawyer-profile", json=PROFILE, headers=agent["headers"])
    assert response.status_code == 200, response.text
    return {**agent, "slug": response.json()["slug"]}

def _first_slot(client, slug: str, skip: int = 0) -> str:
    days = client.get(f"/api/v1/lawyers/{slug}/slots", params={"days": 3}).json()["days"]
    return [s["starts_at"] for d in days for s in d["slots"]][skip]

def _book(client, slug: str, **overrides):
    return client.post(f"/api/v1/lawyers/{slug}/bookings", json={"starts_at": _first_slot(client, slug), **CUSTOMER, **overrides})

def _whatsapp(template: str) -> list[Notification]:
    with SessionLocal() as db:
        return list(db.scalars(select(Notification).where(Notification.channel == "whatsapp", Notification.template_key == template)).all())

def test_profile_needs_basics_before_listing_and_agents_edit_only_their_own(client, agent, admin_headers):
    response = client.put("/api/v1/admin/lawyer-profile", json={"is_listed": True}, headers=agent["headers"])
    assert response.status_code == 422 and "a headline, a specialisation, a language, weekly hours" in response.json()["detail"]

    bad_hours = client.put("/api/v1/admin/lawyer-profile", json={**PROFILE, "weekly_hours": {"mon": [["10:00", "13:00"], ["12:00", "14:00"]]}}, headers=agent["headers"])
    assert bad_hours.status_code == 422 and "overlap" in bad_hours.text

    draft = client.put("/api/v1/admin/lawyer-profile", json={**PROFILE, "is_listed": False}, headers=agent["headers"]).json()
    assert draft["slug"] == "kiran-agent" and draft["exists"] and draft["public_url"].endswith("/lawyers/kiran-agent")
    assert client.get("/api/v1/lawyers").json()["total"] == 0  # unlisted profiles are hidden

    me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    assert client.get("/api/v1/admin/lawyer-profile", params={"user_id": me["id"]}, headers=agent["headers"]).status_code == 403
    # Admins can list someone else's profile.
    listed = client.put("/api/v1/admin/lawyer-profile", params={"user_id": agent["id"]}, json=PROFILE, headers=admin_headers)
    assert listed.status_code == 200 and listed.json()["is_listed"] is True
    roster = client.get("/api/v1/admin/lawyer-profiles", headers=admin_headers).json()["items"]
    assert {(r["name"], r["listed"]) for r in roster} == {("Kiran Agent", True), ("Meera Admin", False)}

def test_search_filters_and_profile(client, lawyer, admin_headers):
    client.put("/api/v1/admin/lawyer-profile", json={**PROFILE, "headline": "Divorce and custody", "specialisations": ["Family & divorce"], "languages": ["Hindi"], "experience_years": 5, "consultation_fee": 800}, headers=admin_headers)

    everyone = client.get("/api/v1/lawyers").json()
    assert everyone["total"] == 2 and [c["name"] for c in everyone["items"]] == ["Kiran Agent", "Meera Admin"]  # more experience first
    card = everyone["items"][0]
    assert card["initials"] == "KA" and card["next_available"]["starts_at"] and card["rating"] is None

    def names(**params) -> list[str]:
        return [c["name"] for c in client.get("/api/v1/lawyers", params=params).json()["items"]]
    assert names(specialisation="family & divorce") == ["Meera Admin"]
    assert names(language="Kannada") == ["Kiran Agent"]
    assert names(max_fee=1000) == ["Meera Admin"]
    assert names(min_experience=10) == ["Kiran Agent"]
    assert names(q="rera jayanagar") == ["Kiran Agent"]
    assert names(sort="fee_low") == ["Meera Admin", "Kiran Agent"]
    assert names(available="3days") == ["Kiran Agent", "Meera Admin"]

    filters = client.get("/api/v1/lawyers/filters").json()
    assert {"value": "Property & real estate", "count": 1} in filters["specialisations"] and filters["fee_range"] == [800, 1500]

    profile = client.get(f"/api/v1/lawyers/{lawyer['slug']}").json()
    assert profile["bio"].startswith("Helps buyers") and profile["courts"] == ["Karnataka High Court"] and len(profile["hours"]) == 7
    assert client.get("/api/v1/lawyers/nobody").status_code == 404

def test_booking_creates_assigned_ticket_and_meeting(client, lawyer):
    slot = _first_slot(client, lawyer["slug"])
    response = _book(client, lawyer["slug"])
    assert response.status_code == 201, response.text
    booking = response.json()
    assert booking["meeting"]["starts_at"] == slot and booking["meeting"]["meet_link"] is None and booking["lawyer"]["name"] == "Kiran Agent"
    assert booking["fee"] == 1500 and booking["can_change"] and not booking["can_review"]

    # The slot is gone for the next customer, and the same time can't be booked twice.
    assert _first_slot(client, lawyer["slug"]) != slot
    again = client.post(f"/api/v1/lawyers/{lawyer['slug']}/bookings", json={"starts_at": slot, **CUSTOMER, "phone": "9000000001"})
    assert again.status_code == 409
    off_grid = datetime.fromisoformat(slot) + timedelta(minutes=7)
    assert client.post(f"/api/v1/lawyers/{lawyer['slug']}/bookings", json={"starts_at": off_grid.isoformat(), **CUSTOMER}).status_code == 409

    # The lawyer owns the ticket and sees the meeting on their calendar.
    ticket = client.get(f"/api/v1/admin/tickets/{booking['ticket_number']}", headers=lawyer["headers"]).json()
    assert ticket["assignee"]["name"] == "Kiran Agent" and ticket["status"] == "assigned" and ticket["service_slug"] == "advocate-consultation"
    assert ticket["meetings"][0]["agenda"] == CUSTOMER["issue"]
    window = {"start": datetime.now(timezone.utc).isoformat(), "end": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()}
    assert [m["ticket_number"] for m in client.get("/api/v1/admin/meetings", params=window, headers=lawyer["headers"]).json()["items"]] == [booking["ticket_number"]]

    # Without Google Calendar the customer's WhatsApp invite says the link will follow; staff then add it.
    invite = _whatsapp("meeting_scheduled")[0]
    assert invite.params[4] == LINK_TO_FOLLOW and invite.recipient == CUSTOMER["phone"]
    meeting_id = ticket["meetings"][0]["id"]
    linked = client.patch(f"/api/v1/admin/meetings/{meeting_id}", json={"meet_link": "https://meet.google.com/abc-defg-hij"}, headers=lawyer["headers"])
    assert linked.status_code == 200 and linked.json()["meet_link"] == "https://meet.google.com/abc-defg-hij"
    assert [n.delivery_status for n in _whatsapp("meeting_scheduled")] == ["cancelled", "queued"]
    assert _whatsapp("meeting_scheduled")[1].params[4] == "https://meet.google.com/abc-defg-hij"

def test_customer_finds_moves_and_cancels_a_booking(client, lawyer):
    booking = _book(client, lawyer["slug"]).json()
    ref = {"ticket_number": booking["ticket_number"], "contact": "98450 12345"}
    assert client.post("/api/v1/bookings/lookup", json=ref).json()["meeting"]["id"] == booking["meeting"]["id"]
    assert client.post("/api/v1/bookings/lookup", json={**ref, "contact": "9999999999"}).status_code == 404

    new_slot = _first_slot(client, lawyer["slug"], skip=2)
    moved = client.post("/api/v1/bookings/reschedule", json={**ref, "starts_at": new_slot})
    assert moved.status_code == 200, moved.text
    assert moved.json()["meeting"]["starts_at"] == new_slot and len(_whatsapp("meeting_rescheduled")) == 1

    cancelled = client.post("/api/v1/bookings/cancel", json={**ref, "reason": "Sorted it out with the builder."})
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["meeting"]["status"] == "cancelled" and body["status"] == "cancelled" and not body["can_change"]
    assert _whatsapp("meeting_cancelled")[0].params[4] == "Cancelled by Priya. Sorted it out with the builder."
    # The time is free again.
    assert new_slot in [s["starts_at"] for d in client.get(f"/api/v1/lawyers/{lawyer['slug']}/slots", params={"days": 3}).json()["days"] for s in d["slots"]]

def test_changes_close_shortly_before_the_start(client, lawyer, monkeypatch):
    booking = _book(client, lawyer["slug"]).json()
    monkeypatch.setattr(config, "CUSTOMER_CHANGE_HOURS", 24 * 7)
    ref = {"ticket_number": booking["ticket_number"], "contact": CUSTOMER["phone"]}
    assert client.post("/api/v1/bookings/lookup", json=ref).json()["can_change"] is False
    assert client.post("/api/v1/bookings/cancel", json=ref).status_code == 422

def test_review_after_the_consultation(client, lawyer):
    booking = _book(client, lawyer["slug"]).json()
    ref = {"ticket_number": booking["ticket_number"], "contact": CUSTOMER["email"]}
    assert client.post("/api/v1/bookings/review", json={**ref, "rating": 5}).status_code == 422  # hasn't happened yet

    with SessionLocal() as db:
        meeting = db.get(Meeting, __import__("uuid").UUID(booking["meeting"]["id"]))
        meeting.starts_at = datetime.now(timezone.utc) - timedelta(hours=2)
        meeting.ends_at = meeting.starts_at + timedelta(minutes=30)
        meeting.status = "completed"
        db.commit()

    reviewed = client.post("/api/v1/bookings/review", json={**ref, "rating": 4, "comment": "Clear advice on the RERA complaint."})
    assert reviewed.status_code == 201, reviewed.text
    assert reviewed.json()["review"]["reviewer_name"] == "Priya S." and not reviewed.json()["can_review"]
    assert client.post("/api/v1/bookings/review", json={**ref, "rating": 1}).status_code == 422

    card = client.get(f"/api/v1/lawyers/{lawyer['slug']}").json()
    assert (card["rating"], card["review_count"], card["consultations"]) == (4.0, 1, 1)
    assert card["reviews"][0]["comment"] == "Clear advice on the RERA complaint."

def test_one_phone_cannot_fill_the_diary(client, lawyer, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPCOMING_BOOKINGS_PER_PHONE", 2)
    assert _book(client, lawyer["slug"]).status_code == 201
    assert _book(client, lawyer["slug"]).status_code == 201
    third = _book(client, lawyer["slug"], phone="098450-12345")
    assert third.status_code == 429 and "2 upcoming" in third.json()["detail"]
