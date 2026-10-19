"""Find and book a lawyer, Practo style: customers search lawyer profiles, compare them, pick an open slot and book a
video consultation; then see, move, cancel and rate their bookings. Lawyers keep their own profile and weekly hours.

A lawyer is a staff member with a listed profile. A booking is a ticket for the "advocate-consultation" service,
assigned to the lawyer, with a meeting on it, so it shows in the ticket queue and the lawyer calendar like any other.
"""
import re
import uuid
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, meetings, tickets
from .db import get_db
from .models import (
    CLOSED_STATUSES, WEEKDAYS, Assignment, Customer, LawyerProfile, LawyerReview, Meeting, ServiceRequest, ServiceType, User, utcnow,
)
from .public import NOT_FOUND, _find_for_customer
from .security import current_staff

router = APIRouter()

BOOKING_SERVICE = "advocate-consultation"

# Offered in the profile editor and as search filters. Lawyers may add others.
SPECIALISATIONS = (
    "Property & real estate", "Family & divorce", "Criminal", "Civil disputes", "Corporate & business", "Tax",
    "Consumer protection", "Labour & employment", "Cyber crime", "Wills & succession", "Banking & recovery",
    "Cheque bounce", "Intellectual property", "Immigration",
)
LANGUAGES = ("English", "Kannada", "Hindi", "Tamil", "Telugu", "Malayalam", "Marathi", "Bengali", "Urdu")

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

def _zone() -> ZoneInfo:
    return ZoneInfo(config.MEETING_TIMEZONE)

def _initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.replace("Adv.", "").strip()) if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"

def _slug_for(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "lawyer"
    slug, n = base, 1
    while db.scalars(select(LawyerProfile.user_id).where(LawyerProfile.slug == slug)).first():
        n += 1
        slug = f"{base}-{n}"
    return slug

def _listed(db: Session):
    return select(LawyerProfile).join(User, User.id == LawyerProfile.user_id).where(LawyerProfile.is_listed.is_(True), User.account_status == "active")

def _get_listed(db: Session, slug: str) -> LawyerProfile:
    profile = db.scalars(_listed(db).where(LawyerProfile.slug == slug)).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="We couldn't find that lawyer.")
    return profile

# ---- Slots ----

def _busy(db: Session, lawyer_ids: list[uuid.UUID], start: datetime, end: datetime, ignore: uuid.UUID | None = None) -> dict[uuid.UUID, list[tuple[datetime, datetime]]]:
    rows = db.execute(select(Meeting.lawyer_user_id, Meeting.starts_at, Meeting.ends_at).where(
        Meeting.lawyer_user_id.in_(lawyer_ids), Meeting.status == "scheduled", Meeting.starts_at < end, Meeting.ends_at > start,
        *([Meeting.id != ignore] if ignore else []),
    )).all()
    busy: dict = {}
    for lawyer_id, starts_at, ends_at in rows:
        busy.setdefault(lawyer_id, []).append((tickets.aware(starts_at), tickets.aware(ends_at)))
    return busy

def _slot_label(value: datetime) -> str:
    return value.astimezone(_zone()).strftime("%I:%M %p").lstrip("0").lower()

def _day_label(day: date, today: date) -> str:
    if day == today:
        return "Today"
    if day == today + timedelta(days=1):
        return "Tomorrow"
    return f"{day:%a} {day.day} {day:%b}"

def _slots(profile: LawyerProfile, busy: list[tuple[datetime, datetime]], first_day: date, days: int, now: datetime) -> list[dict]:
    """Open slots by day in MEETING_TIMEZONE: the lawyer's weekly hours cut into consultation-length slots, minus
    booked meetings and anything sooner than BOOKING_MIN_NOTICE_MINUTES from now."""
    zone = _zone()
    earliest = now + timedelta(minutes=config.BOOKING_MIN_NOTICE_MINUTES)
    length = timedelta(minutes=profile.consultation_minutes)
    today = now.astimezone(zone).date()
    out = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        slots = []
        for start_text, end_text in (profile.weekly_hours or {}).get(WEEKDAYS[day.weekday()], []):
            start = datetime.combine(day, time.fromisoformat(start_text), tzinfo=zone)
            end = datetime.combine(day, time.fromisoformat(end_text), tzinfo=zone)
            while start + length <= end:
                utc_start = start.astimezone(ZoneInfo("UTC"))
                utc_end = utc_start + length
                if utc_start >= earliest and not any(b0 < utc_end and b1 > utc_start for b0, b1 in busy):
                    slots.append({"starts_at": utc_start.isoformat(), "label": _slot_label(utc_start)})
                start += length
        out.append({"date": day.isoformat(), "label": _day_label(day, today), "slots": slots})
    return out

def _window(days: int, now: datetime) -> tuple[date, datetime, datetime]:
    first_day = now.astimezone(_zone()).date()
    start = datetime.combine(first_day, time.min, tzinfo=_zone())
    return first_day, start, start + timedelta(days=days + 1)

def _next_slot(profile: LawyerProfile, busy: list, now: datetime) -> dict | None:
    first_day, _, _ = _window(config.BOOKING_DAYS_AHEAD, now)
    for day in _slots(profile, busy, first_day, config.BOOKING_DAYS_AHEAD, now):
        if day["slots"]:
            return {**day["slots"][0], "day": day["label"]}
    return None

# ---- Views ----

def _stats(db: Session, lawyer_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    ratings = db.execute(select(LawyerReview.lawyer_user_id, func.avg(LawyerReview.rating), func.count()).where(LawyerReview.lawyer_user_id.in_(lawyer_ids)).group_by(LawyerReview.lawyer_user_id)).all()
    done = db.execute(select(Meeting.lawyer_user_id, func.count()).where(Meeting.lawyer_user_id.in_(lawyer_ids), Meeting.status == "completed").group_by(Meeting.lawyer_user_id)).all()
    stats = {i: {"rating": None, "review_count": 0, "consultations": 0} for i in lawyer_ids}
    for lawyer_id, avg, count in ratings:
        stats[lawyer_id] |= {"rating": round(float(avg), 1), "review_count": count}
    for lawyer_id, count in done:
        stats[lawyer_id]["consultations"] = count
    return stats

def _card(profile: LawyerProfile, stats: dict, next_slot: dict | None) -> dict:
    name = profile.user.display_name
    return {
        "slug": profile.slug,
        "name": name,
        "initials": _initials(name),
        "headline": profile.headline,
        "specialisations": profile.specialisations,
        "languages": profile.languages,
        "experience_years": profile.experience_years,
        "consultation_fee": profile.consultation_fee,
        "consultation_minutes": profile.consultation_minutes,
        "city": profile.city,
        "locality": profile.locality,
        **stats,
        "next_available": next_slot,
    }

def _review_view(review: LawyerReview) -> dict:
    return {"rating": review.rating, "comment": review.comment, "reviewer_name": review.reviewer_name, "at": review.created_at.isoformat()}

def _hours_view(profile: LawyerProfile) -> list[dict]:
    hours = profile.weekly_hours or {}
    return [{"day": d, "hours": [f"{_fmt_hhmm(a)} – {_fmt_hhmm(b)}" for a, b in hours.get(d, [])]} for d in WEEKDAYS]

def _fmt_hhmm(value: str) -> str:
    return time.fromisoformat(value).strftime("%I:%M %p").lstrip("0").lower()

# ---- Public: search, profiles, slots ----

@router.get("/api/v1/lawyers/filters")
def lawyer_filters(db: Session = Depends(get_db)):
    """Filter options with how many listed lawyers match each, for the search page."""
    profiles = db.scalars(_listed(db)).unique().all()
    def counts(values) -> list[dict]:
        tally: dict[str, int] = {}
        for value in values:
            tally[value] = tally.get(value, 0) + 1
        return [{"value": v, "count": n} for v, n in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))]
    fees = [p.consultation_fee for p in profiles]
    return {
        "specialisations": counts(s for p in profiles for s in p.specialisations),
        "languages": counts(lang for p in profiles for lang in p.languages),
        "cities": counts(p.city for p in profiles),
        "fee_range": [min(fees), max(fees)] if fees else [0, 0],
        "total": len(profiles),
    }

@router.get("/api/v1/lawyers")
def search_lawyers(
    q: str | None = Query(None, max_length=100, description="Name, specialisation, headline or area."),
    specialisation: str | None = None,
    language: str | None = None,
    city: str | None = None,
    max_fee: int | None = Query(None, ge=0),
    min_experience: int | None = Query(None, ge=0),
    available: Literal["today", "3days"] | None = Query(None, description="Only lawyers with an open slot today or in the next 3 days."),
    sort: Literal["relevance", "experience", "fee_low", "fee_high", "rating", "soonest"] = "relevance",
    db: Session = Depends(get_db),
):
    profiles = list(db.scalars(_listed(db)).unique().all())
    def has(values: list[str], wanted: str) -> bool:
        return wanted.strip().lower() in {v.lower() for v in values}
    if specialisation:
        profiles = [p for p in profiles if has(p.specialisations, specialisation)]
    if language:
        profiles = [p for p in profiles if has(p.languages, language)]
    if city:
        profiles = [p for p in profiles if p.city.lower() == city.strip().lower()]
    if max_fee is not None:
        profiles = [p for p in profiles if p.consultation_fee <= max_fee]
    if min_experience is not None:
        profiles = [p for p in profiles if p.experience_years >= min_experience]
    if q and q.strip():
        terms = q.strip().lower().split()
        def text(p: LawyerProfile) -> str:
            return " ".join([p.user.display_name, p.headline, p.city, p.locality or "", *p.specialisations, *p.languages]).lower()
        profiles = [p for p in profiles if all(t in text(p) for t in terms)]

    now = utcnow()
    ids = [p.user_id for p in profiles]
    _, start, end = _window(config.BOOKING_DAYS_AHEAD, now)
    busy = _busy(db, ids, start, end) if ids else {}
    stats = _stats(db, ids) if ids else {}
    cards = [_card(p, stats[p.user_id], _next_slot(p, busy.get(p.user_id, []), now)) for p in profiles]

    if available:
        horizon = datetime.combine(now.astimezone(_zone()).date() + timedelta(days=1 if available == "today" else 3), time.min, tzinfo=_zone())
        cards = [c for c in cards if c["next_available"] and datetime.fromisoformat(c["next_available"]["starts_at"]) < horizon]
    far = "9999"
    keys = {
        "relevance": lambda c: (-(c["rating"] or 0) * min(c["review_count"], 20), -c["experience_years"], c["name"]),
        "experience": lambda c: (-c["experience_years"], c["name"]),
        "fee_low": lambda c: (c["consultation_fee"], c["name"]),
        "fee_high": lambda c: (-c["consultation_fee"], c["name"]),
        "rating": lambda c: (-(c["rating"] or 0), -c["review_count"], c["name"]),
        "soonest": lambda c: ((c["next_available"] or {}).get("starts_at", far), c["name"]),
    }
    cards.sort(key=keys[sort])
    return {"items": cards, "total": len(cards), "timezone": config.MEETING_TIMEZONE}

@router.get("/api/v1/lawyers/{slug}")
def lawyer_profile(slug: str, db: Session = Depends(get_db)):
    profile = _get_listed(db, slug)
    now = utcnow()
    _, start, end = _window(config.BOOKING_DAYS_AHEAD, now)
    busy = _busy(db, [profile.user_id], start, end).get(profile.user_id, [])
    reviews = db.scalars(select(LawyerReview).where(LawyerReview.lawyer_user_id == profile.user_id).order_by(LawyerReview.created_at.desc()).limit(20)).all()
    return {
        **_card(profile, _stats(db, [profile.user_id])[profile.user_id], _next_slot(profile, busy, now)),
        "bio": profile.bio,
        "courts": profile.courts,
        "bar_enrolment": profile.bar_enrolment,
        "education": profile.education,
        "hours": _hours_view(profile),
        "reviews": [_review_view(r) for r in reviews],
    }

@router.get("/api/v1/lawyers/{slug}/slots")
def lawyer_slots(slug: str, days: int = Query(7, ge=1, le=31), db: Session = Depends(get_db)):
    profile = _get_listed(db, slug)
    now = utcnow()
    days = min(days, config.BOOKING_DAYS_AHEAD)
    first_day, start, end = _window(days, now)
    busy = _busy(db, [profile.user_id], start, end).get(profile.user_id, [])
    return {"days": _slots(profile, busy, first_day, days, now), "minutes": profile.consultation_minutes, "timezone": config.MEETING_TIMEZONE}

# ---- Public: booking and managing a booking ----

class BookingCreate(BaseModel):
    starts_at: datetime = Field(description="A slot's starts_at, exactly as the slots endpoint returned it.")
    customer_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=20, description="Invites, reminders and the join link go to this number on WhatsApp.")
    email: str | None = Field(default=None, max_length=254, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
    issue: str = Field(min_length=10, max_length=2000, description="What the customer wants to discuss. Shared with the lawyer.")
    source: Literal["website", "mobile"] = "website"

class BookingRef(BaseModel):
    ticket_number: str = Field(min_length=5, max_length=40)
    contact: str = Field(min_length=5, max_length=254)

class BookingCancel(BookingRef):
    reason: str | None = Field(default=None, max_length=500)

class BookingMove(BookingRef):
    starts_at: datetime

class BookingReview(BookingRef):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)

def _slot_open(db: Session, profile: LawyerProfile, starts_at: datetime, ignore: uuid.UUID | None = None) -> datetime:
    """The requested time as UTC if it is one of the lawyer's open slots right now, else a 409 to pick again."""
    starts_at = meetings._as_utc(starts_at)
    now = utcnow()
    day = starts_at.astimezone(_zone()).date()
    day_start = datetime.combine(day, time.min, tzinfo=_zone())
    busy = _busy(db, [profile.user_id], day_start, day_start + timedelta(days=1), ignore=ignore).get(profile.user_id, [])
    horizon = now.astimezone(_zone()).date() + timedelta(days=config.BOOKING_DAYS_AHEAD)
    open_slots = {s["starts_at"] for s in _slots(profile, busy, day, 1, now)[0]["slots"]} if day < horizon else set()
    if starts_at.isoformat() not in open_slots:
        raise HTTPException(status_code=409, detail="That slot was just taken or is no longer available. Please pick another time.")
    return starts_at

def _booking_meeting(ticket: ServiceRequest) -> Meeting:
    if not ticket.meetings:
        raise HTTPException(status_code=404, detail="There's no consultation booked on this request.")
    # The most recent booking on the ticket is the one the customer manages.
    return max(ticket.meetings, key=lambda m: m.created_at)

def _reviewer_name(full_name: str) -> str:
    parts = full_name.split()
    return f"{parts[0]} {parts[-1][0]}." if len(parts) > 1 else parts[0]

def booking_view(db: Session, ticket: ServiceRequest, meeting: Meeting) -> dict:
    now = utcnow()
    profile = db.get(LawyerProfile, meeting.lawyer_user_id)
    review = db.scalars(select(LawyerReview).where(LawyerReview.meeting_id == meeting.id)).first()
    scheduled = meeting.status == "scheduled"
    return {
        "ticket_number": ticket.ticket_number,
        "status": ticket.status,
        "status_label": tickets.status_label(ticket.status),
        "issue": ticket.description,
        "lawyer": {
            "slug": profile.slug if profile else None,
            "name": meeting.lawyer.display_name,
            "initials": _initials(meeting.lawyer.display_name),
            "headline": profile.headline if profile else "",
        },
        "fee": (ticket.structured_answers or {}).get("fee"),
        "meeting": tickets.meeting_view(meeting),
        "can_change": scheduled and tickets.aware(meeting.starts_at) - now > timedelta(hours=config.CUSTOMER_CHANGE_HOURS) and profile is not None,
        "can_review": meeting.status != "cancelled" and tickets.aware(meeting.ends_at) <= now and review is None,
        "review": _review_view(review) if review else None,
    }

@router.post("/api/v1/lawyers/{slug}/bookings", status_code=201)
def book_lawyer(slug: str, payload: BookingCreate, db: Session = Depends(get_db)):
    profile = _get_listed(db, slug)
    lawyer = meetings.lock_lawyer(db, profile.user_id)
    starts_at = _slot_open(db, profile, payload.starts_at)
    phone = tickets.normalize_phone(payload.phone)
    if len(phone) < 10:
        raise HTTPException(status_code=422, detail="phone: Enter a full mobile number. We send the meeting link on WhatsApp.")
    upcoming = db.scalar(select(func.count()).select_from(Meeting).join(ServiceRequest).join(Customer).where(
        Customer.phone_normalized == phone, Meeting.status == "scheduled", Meeting.created_by_user_id.is_(None), Meeting.starts_at > utcnow(),
    ))
    if upcoming >= config.MAX_UPCOMING_BOOKINGS_PER_PHONE:
        raise HTTPException(status_code=429, detail=f"This number already has {upcoming} upcoming consultations. Cancel one, or call us to book more.")
    service = db.scalars(select(ServiceType).where(ServiceType.slug == BOOKING_SERVICE)).one()

    ticket = tickets.create_ticket(
        db, customer_name=payload.customer_name.strip(), phone=payload.phone.strip(), email=(payload.email or "").strip() or None,
        property_type="other", service=service, package=None, location=f"Video consultation · {profile.city}",
        description=payload.issue.strip(), source=payload.source,
    )
    ticket.title = f"Consultation with {lawyer.display_name}"
    ticket.structured_answers = {**ticket.structured_answers, "lawyer": profile.slug, "fee": profile.consultation_fee, "booked_online": True}
    assignment = Assignment(service_request_id=ticket.id, agent_user_id=lawyer.id, assignment_note="Booked online by the customer.")
    db.add(assignment)
    ticket.assignments.append(assignment)
    tickets.add_event(db, ticket, "assigned", None, new={"agent": lawyer.display_name}, reason="Booked online by the customer.")
    tickets.change_status(db, ticket, "assigned", None, f"Consultation booked with {lawyer.display_name}.")
    meeting = meetings.create_meeting(
        db, ticket, lawyer, starts_at, starts_at + timedelta(minutes=profile.consultation_minutes),
        actor=None, agenda=payload.issue.strip()[:1000], require_link=False,
    )
    db.commit()
    return booking_view(db, ticket, meeting)

@router.post("/api/v1/bookings/lookup")
def lookup_booking(payload: BookingRef, db: Session = Depends(get_db)):
    ticket = _find_for_customer(db, payload.ticket_number, payload.contact)
    return booking_view(db, ticket, _booking_meeting(ticket))

def _changeable(db: Session, payload: BookingRef) -> tuple[ServiceRequest, Meeting]:
    ticket = _find_for_customer(db, payload.ticket_number, payload.contact)
    meeting = _booking_meeting(ticket)
    if not booking_view(db, ticket, meeting)["can_change"]:
        raise HTTPException(status_code=422, detail=f"This booking can no longer be changed online. Bookings can be moved or cancelled up to {config.CUSTOMER_CHANGE_HOURS} hours before they start; please call us.")
    return ticket, meeting

@router.post("/api/v1/bookings/cancel")
def cancel_booking(payload: BookingCancel, db: Session = Depends(get_db)):
    ticket, meeting = _changeable(db, payload)
    reason = (payload.reason or "").strip() or None
    meetings.cancel_meeting(db, meeting, None, f"Cancelled by {ticket.customer.full_name.split()[0]}." + (f" {reason}" if reason else ""))
    # A ticket that was only this booking closes with it.
    if (ticket.structured_answers or {}).get("booked_online") and not any(m.status == "scheduled" for m in ticket.meetings) and ticket.status not in CLOSED_STATUSES:
        tickets.change_status(db, ticket, "cancelled", None, "You cancelled the consultation.")
    tickets.audit(db, None, "booking.cancelled", ticket.id, meeting_id=str(meeting.id))
    db.commit()
    return booking_view(db, ticket, meeting)

@router.post("/api/v1/bookings/reschedule")
def reschedule_booking(payload: BookingMove, db: Session = Depends(get_db)):
    ticket, meeting = _changeable(db, payload)
    profile = db.get(LawyerProfile, meeting.lawyer_user_id)
    meetings.lock_lawyer(db, meeting.lawyer_user_id)
    starts_at = _slot_open(db, profile, payload.starts_at, ignore=meeting.id)
    duration = int((tickets.aware(meeting.ends_at) - tickets.aware(meeting.starts_at)).total_seconds() // 60)
    meetings.move_meeting(db, meeting, None, starts_at, duration, "Moved by the customer.")
    tickets.audit(db, None, "booking.rescheduled", ticket.id, meeting_id=str(meeting.id))
    meeting.updated_at = ticket.updated_at = utcnow()
    db.commit()
    return booking_view(db, ticket, meeting)

@router.post("/api/v1/bookings/review", status_code=201)
def review_booking(payload: BookingReview, db: Session = Depends(get_db)):
    ticket = _find_for_customer(db, payload.ticket_number, payload.contact)
    meeting = _booking_meeting(ticket)
    if not booking_view(db, ticket, meeting)["can_review"]:
        raise HTTPException(status_code=422, detail="You can rate a consultation once, after it has taken place.")
    db.add(LawyerReview(
        lawyer_user_id=meeting.lawyer_user_id, meeting_id=meeting.id, rating=payload.rating, comment=payload.comment.strip(),
        reviewer_name=_reviewer_name((ticket.structured_answers or {}).get("customer_name") or ticket.customer.full_name),
    ))
    tickets.add_event(db, ticket, "review_added", None, new={"rating": payload.rating})
    db.commit()
    return booking_view(db, ticket, meeting)

# ---- Staff: a lawyer's own profile and hours ----

class ProfileUpdate(BaseModel):
    headline: str = Field(default="", max_length=160)
    bio: str = Field(default="", max_length=3000)
    specialisations: list[str] = Field(default_factory=list, max_length=8)
    languages: list[str] = Field(default_factory=list, max_length=8)
    courts: list[str] = Field(default_factory=list, max_length=8)
    experience_years: int = Field(default=0, ge=0, le=70)
    consultation_fee: int = Field(default=0, ge=0, le=100000)
    consultation_minutes: int = Field(default=30, ge=15, le=120)
    city: str = Field(default="Bengaluru", min_length=2, max_length=80)
    locality: str | None = Field(default=None, max_length=120)
    bar_enrolment: str | None = Field(default=None, max_length=60)
    education: str | None = Field(default=None, max_length=300)
    weekly_hours: dict[str, list[list[str]]] = Field(default_factory=dict, description='{"mon": [["10:00", "13:00"]], ...} in MEETING_TIMEZONE.')
    is_listed: bool = False

    @field_validator("specialisations", "languages", "courts")
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        seen, out = set(), []
        for value in (v.strip() for v in values):
            if value and len(value) <= 60 and value.lower() not in seen:
                seen.add(value.lower())
                out.append(value)
        return out

    @field_validator("weekly_hours")
    @classmethod
    def _check_hours(cls, hours: dict[str, list[list[str]]]) -> dict:
        cleaned = {}
        for day, ranges in hours.items():
            if day not in WEEKDAYS:
                raise ValueError(f"unknown day '{day}'; use {', '.join(WEEKDAYS)}")
            if len(ranges) > 4:
                raise ValueError(f"at most 4 time ranges on {day}")
            if any(len(r) != 2 for r in ranges):
                raise ValueError(f"{day}: each range is [start, end]")
            ordered = sorted(ranges)
            for start, end in ordered:
                if not (HHMM.match(start) and HHMM.match(end)) or start >= end:
                    raise ValueError(f"{day}: each range needs a start before its end, as HH:MM")
            for (_, prev_end), (next_start, _) in zip(ordered, ordered[1:]):
                if next_start < prev_end:
                    raise ValueError(f"{day}: time ranges overlap")
            if ordered:
                cleaned[day] = [list(r) for r in ordered]
        return cleaned

def _profile_owner(db: Session, user: User, user_id: uuid.UUID | None) -> User:
    if user_id is None or user_id == user.id:
        return user
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="You can edit only your own profile.")
    owner = db.get(User, user_id)
    if owner is None or not (owner.role_names & {"agent", "admin", "super_admin"}):
        raise HTTPException(status_code=404, detail="Staff member not found")
    return owner

def _staff_profile_view(db: Session, owner: User, profile: LawyerProfile | None) -> dict:
    fields = ProfileUpdate().model_dump() if profile is None else {k: getattr(profile, k) for k in ProfileUpdate.model_fields}
    return {
        "user_id": str(owner.id),
        "name": owner.display_name,
        "exists": profile is not None,
        "slug": profile.slug if profile else None,
        **fields,
        "public_url": f"{config.PUBLIC_SITE_URL}/lawyers/{profile.slug}" if profile else None,
        "options": {"specialisations": SPECIALISATIONS, "languages": LANGUAGES},
        "timezone": config.MEETING_TIMEZONE,
    }

@router.get("/api/v1/admin/lawyer-profile")
def get_my_profile(user_id: uuid.UUID | None = None, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    owner = _profile_owner(db, user, user_id)
    return _staff_profile_view(db, owner, db.get(LawyerProfile, owner.id))

@router.put("/api/v1/admin/lawyer-profile")
def save_my_profile(payload: ProfileUpdate, user_id: uuid.UUID | None = None, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    owner = _profile_owner(db, user, user_id)
    if payload.is_listed:
        missing = [label for label, ok in (
            ("a headline", payload.headline.strip()), ("a specialisation", payload.specialisations),
            ("a language", payload.languages), ("weekly hours", payload.weekly_hours),
        ) if not ok]
        if missing:
            raise HTTPException(status_code=422, detail=f"Add {', '.join(missing)} before listing the profile.")
    profile = db.get(LawyerProfile, owner.id)
    if profile is None:
        profile = LawyerProfile(user_id=owner.id, slug=_slug_for(db, owner.display_name))
        db.add(profile)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value.strip() if isinstance(value, str) else value)
    profile.locality = profile.locality or None
    profile.bar_enrolment = profile.bar_enrolment or None
    profile.education = profile.education or None
    tickets.audit(db, user, "lawyer_profile.saved", None, user_id=str(owner.id), listed=payload.is_listed)
    db.commit()
    db.refresh(profile)
    return _staff_profile_view(db, owner, profile)

@router.get("/api/v1/admin/lawyer-profiles")
def list_profiles(user: User = Depends(current_staff), db: Session = Depends(get_db)):
    """Every staff member with whether their profile is listed, for admins choosing whose profile to edit."""
    staff = [user] if not user.is_admin else db.scalars(
        select(User).where(User.roles.any(), User.account_status == "active").order_by(User.display_name)
    ).all()
    profiles = {p.user_id: p for p in db.scalars(select(LawyerProfile).where(LawyerProfile.user_id.in_([s.id for s in staff]))).all()}
    return {"items": [
        {"user_id": str(s.id), "name": s.display_name, "listed": bool(profiles.get(s.id) and profiles[s.id].is_listed), "slug": profiles[s.id].slug if s.id in profiles else None}
        for s in staff if s.role_names & {"agent", "admin", "super_admin"}
    ]}
