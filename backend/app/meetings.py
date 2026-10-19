"""Video consultations on tickets: scheduling with a Google Meet link, WhatsApp invites and reminders for the
customer and the lawyer, and the lawyer calendar.

A lawyer is any active staff member. Agents schedule meetings with themselves; admins can book any lawyer.
"""
import uuid
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import admin, config, google_calendar, tickets
from .db import get_db
from .models import CLOSED_STATUSES, Meeting, Notification, ServiceRequest, User, utcnow
from .security import current_staff

router = APIRouter(prefix="/api/v1/admin")

# The WhatsApp templates these keys name must be approved in WhatsApp Manager with the same placeholders
# (docs/meetings.md). The bodies here are what staff see in the ticket's notification list.
TEMPLATES = {
    "meeting_scheduled": "Hi {1}, your Homexo Legal consultation on {2} is booked for {3} with {4}. Join on Google Meet: {5}",
    "meeting_rescheduled": "Hi {1}, your Homexo Legal consultation on {2} has moved to {3} with {4}. Join on Google Meet: {5}",
    "meeting_reminder": "Hi {1}, reminder: your Homexo Legal consultation on {2} with {4} starts at {3}. Tap to join: {5}",
    "meeting_cancelled": "Hi {1}, your Homexo Legal consultation on {2} at {3} with {4} has been cancelled. {5}",
    "lawyer_daily_agenda": "Good morning {1}, you have {2} Homexo Legal consultation(s) today: {3}. Your calendar: {4}",
}

# Customer bookings made while Google Calendar isn't connected have no link until staff add one.
LINK_TO_FOLLOW = "we will send the meeting link before it starts."

def render(template_key: str, params: list[str]) -> str:
    text = TEMPLATES[template_key]
    for index, value in enumerate(params, start=1):
        text = text.replace("{" + str(index) + "}", value)
    return text

class MeetingCreate(BaseModel):
    starts_at: datetime = Field(description="Start time. Without a UTC offset it is read in MEETING_TIMEZONE.")
    duration_minutes: int = Field(default=30, ge=15, le=240)
    lawyer_id: uuid.UUID | None = Field(default=None, description="Staff member who takes the meeting; defaults to you.")
    agenda: str | None = Field(default=None, max_length=1000, description="Shared with the customer in the invite.")
    meet_link: str | None = Field(default=None, max_length=500, pattern=r"^https://\S+$", description="Use this link instead of creating one in Google Calendar.")

class MeetingUpdate(BaseModel):
    starts_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=240)
    status: Literal["completed", "cancelled"] | None = None
    reason: str | None = Field(default=None, max_length=500, description="Sent to both parties when a meeting is cancelled.")
    meet_link: str | None = Field(default=None, max_length=500, pattern=r"^https://\S+$", description="Add or replace the join link; both parties are sent it.")

def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(config.MEETING_TIMEZONE))
    return value.astimezone(ZoneInfo("UTC"))

def _check_times(db: Session, lawyer: User, starts_at: datetime, ends_at: datetime, ignore: uuid.UUID | None = None) -> None:
    if starts_at <= utcnow():
        raise HTTPException(status_code=422, detail="Pick a time in the future.")
    clash = db.scalars(select(Meeting).where(
        Meeting.lawyer_user_id == lawyer.id, Meeting.status == "scheduled", Meeting.starts_at < ends_at, Meeting.ends_at > starts_at,
        *([Meeting.id != ignore] if ignore else []),
    )).first()
    if clash:
        raise HTTPException(status_code=409, detail=f"{lawyer.display_name} already has a meeting at {tickets.format_when(clash.starts_at)} ({clash.service_request.ticket_number}).")

def _parties(meeting: Meeting) -> list[dict]:
    """Who gets WhatsApp messages about a meeting: the customer and the lawyer, each with a phone on file."""
    ticket = meeting.service_request
    customer_name = (ticket.structured_answers or {}).get("customer_name") or ticket.customer.full_name
    parties = [
        {"kind": "customer", "phone": ticket.customer.phone, "name": customer_name, "other": meeting.lawyer.display_name, "customer_id": ticket.customer_id},
        {"kind": "lawyer", "phone": meeting.lawyer.phone, "name": meeting.lawyer.display_name, "other": customer_name, "user_id": meeting.lawyer_user_id},
    ]
    return [p for p in parties if p["phone"]]

def _queue(db: Session, meeting: Meeting, template_key: str, last_param: str | None = None, *, send_after: datetime | None = None,
           dedupe: str | None = None, kinds: tuple[str, ...] = ("customer", "lawyer")) -> None:
    ticket = meeting.service_request
    for party in _parties(meeting):
        if party["kind"] not in kinds:
            continue
        params = [party["name"], f"{ticket.service_type.name} ({ticket.ticket_number})", tickets.format_when(meeting.starts_at), party["other"], last_param or meeting.meet_link or LINK_TO_FOLLOW]
        db.add(Notification(
            service_request_id=ticket.id, customer_id=party.get("customer_id"), user_id=party.get("user_id"), meeting_id=meeting.id,
            channel="whatsapp", template_key=template_key, recipient=party["phone"], params=params, body=render(template_key, params),
            send_after=send_after or utcnow(), dedupe_key=f"{dedupe}:{party['kind']}" if dedupe else None,
        ))

def _queue_reminders(db: Session, meeting: Meeting) -> None:
    now, starts_at = utcnow(), tickets.aware(meeting.starts_at)
    for minutes in config.MEETING_REMINDER_MINUTES:
        send_at = starts_at - timedelta(minutes=minutes)
        if send_at > now:
            _queue(db, meeting, "meeting_reminder", send_after=send_at, dedupe=f"reminder:{meeting.id}:{minutes}:{int(starts_at.timestamp())}")

def _cancel_queued(db: Session, meeting: Meeting) -> None:
    """Drop invites and reminders not yet sent, e.g. for the old time of a rescheduled meeting."""
    db.execute(update(Notification).where(Notification.meeting_id == meeting.id, Notification.delivery_status == "queued").values(delivery_status="cancelled", error_code="superseded"))

def _description(ticket: ServiceRequest, agenda: str | None) -> str:
    lines = [f"Homexo Legal consultation for {ticket.service_type.name}, request {ticket.ticket_number}."]
    if agenda:
        lines.append(f"Agenda: {agenda}")
    lines.append("Join with the Google Meet link in this invite. To change the time, reply on WhatsApp or call your case team.")
    return "\n\n".join(lines)

def _calendar_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except google_calendar.CalendarError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

def _get_meeting(db: Session, user: User, meeting_id: uuid.UUID) -> Meeting:
    meeting = db.get(Meeting, meeting_id)
    if meeting is None or not (user.is_admin or meeting.lawyer_user_id == user.id):
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting

def lock_lawyer(db: Session, lawyer_id: uuid.UUID) -> User | None:
    """Load the lawyer with a row lock, so two bookings for the same time can't both pass the clash check."""
    return db.get(User, lawyer_id, with_for_update=True)

def create_meeting(db: Session, ticket: ServiceRequest, lawyer: User, starts_at: datetime, ends_at: datetime, *, actor: User | None,
                   agenda: str | None = None, meet_link: str | None = None, require_link: bool = True) -> Meeting:
    """Book a meeting: checks the lawyer is free, creates the Google Meet event, records it and queues WhatsApp messages.

    actor is None when the customer booked it themselves. The caller commits.
    """
    _check_times(db, lawyer, starts_at, ends_at)
    title = f"Homexo Legal consultation · {ticket.ticket_number}"
    event_id = None
    link = meet_link
    if not link and google_calendar.enabled():
        attendees = [e for e in (ticket.customer.email, lawyer.email) if e]
        event_id, link = _calendar_call(google_calendar.create_event, title=title, description=_description(ticket, agenda), starts_at=starts_at, ends_at=ends_at, attendees=attendees)
    elif not link and require_link:
        raise HTTPException(status_code=422, detail="Google Calendar isn't connected yet, so paste a meeting link.")

    meeting = Meeting(
        service_request_id=ticket.id, lawyer_user_id=lawyer.id, created_by_user_id=actor.id if actor else None, title=title, agenda=agenda,
        starts_at=starts_at, ends_at=ends_at, meet_link=link, calendar_event_id=event_id,
    )
    db.add(meeting)
    ticket.meetings.append(meeting)
    db.flush()
    db.refresh(meeting)
    tickets.add_event(db, ticket, "meeting_scheduled", actor, new={"when": tickets.format_when(starts_at), "lawyer": lawyer.display_name})
    _queue(db, meeting, "meeting_scheduled")
    _queue_reminders(db, meeting)
    tickets.audit(db, actor, "meeting.scheduled", ticket.id, meeting_id=str(meeting.id), lawyer_id=str(lawyer.id))
    ticket.updated_at = utcnow()
    return meeting

def cancel_meeting(db: Session, meeting: Meeting, actor: User | None, reason: str | None) -> None:
    if meeting.calendar_event_id:
        _calendar_call(google_calendar.cancel_event, meeting.calendar_event_id)
    meeting.status = "cancelled"
    meeting.cancelled_at = utcnow()
    _cancel_queued(db, meeting)
    _queue(db, meeting, "meeting_cancelled", reason or "Your case team will contact you to find a new time.")
    tickets.add_event(db, meeting.service_request, "meeting_cancelled", actor, old={"when": tickets.format_when(meeting.starts_at)}, reason=reason)

def move_meeting(db: Session, meeting: Meeting, actor: User | None, starts_at: datetime, duration: int, reason: str | None = None) -> None:
    ends_at = starts_at + timedelta(minutes=duration)
    _check_times(db, meeting.lawyer, starts_at, ends_at, ignore=meeting.id)
    if meeting.calendar_event_id:
        _calendar_call(google_calendar.update_event, meeting.calendar_event_id, starts_at=starts_at, ends_at=ends_at)
    old_when = tickets.format_when(meeting.starts_at)
    moved = starts_at != tickets.aware(meeting.starts_at)
    meeting.starts_at, meeting.ends_at = starts_at, ends_at
    if moved:
        _cancel_queued(db, meeting)
        _queue(db, meeting, "meeting_rescheduled")
        _queue_reminders(db, meeting)
    tickets.add_event(db, meeting.service_request, "meeting_rescheduled", actor, old={"when": old_when}, new={"when": tickets.format_when(starts_at), "minutes": duration}, reason=reason)

@router.post("/tickets/{ticket_number}/meetings", status_code=201)
def schedule_meeting(ticket_number: str, payload: MeetingCreate, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    ticket = admin._get_ticket(db, user, ticket_number)
    if ticket.status in CLOSED_STATUSES:
        raise HTTPException(status_code=422, detail="Reopen the ticket before booking a meeting.")
    lawyer = lock_lawyer(db, user.id)
    if payload.lawyer_id and payload.lawyer_id != user.id:
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="Agents can book meetings only for themselves.")
        lawyer = lock_lawyer(db, payload.lawyer_id)
        if lawyer is None or lawyer.account_status != "active" or not (lawyer.role_names & {"agent", "admin", "super_admin"}):
            raise HTTPException(status_code=422, detail="Choose an active staff member.")
    starts_at = _as_utc(payload.starts_at)
    ends_at = starts_at + timedelta(minutes=payload.duration_minutes)
    create_meeting(db, ticket, lawyer, starts_at, ends_at, actor=user, agenda=(payload.agenda or "").strip() or None, meet_link=payload.meet_link)
    db.commit()
    return admin._detail(db, ticket)

@router.patch("/meetings/{meeting_id}")
def update_meeting(meeting_id: uuid.UUID, payload: MeetingUpdate, user: User = Depends(current_staff), db: Session = Depends(get_db)):
    meeting = _get_meeting(db, user, meeting_id)
    ticket = meeting.service_request
    if meeting.status != "scheduled":
        raise HTTPException(status_code=422, detail=f"This meeting is already {meeting.status}.")
    reason = (payload.reason or "").strip() or None

    if payload.status == "cancelled":
        cancel_meeting(db, meeting, user, reason)
    elif payload.status == "completed":
        meeting.status = "completed"
        _cancel_queued(db, meeting)
        tickets.add_event(db, ticket, "meeting_completed", user, old={"when": tickets.format_when(meeting.starts_at)})
    elif payload.starts_at or payload.duration_minutes:
        lock_lawyer(db, meeting.lawyer_user_id)
        starts_at = _as_utc(payload.starts_at) if payload.starts_at else tickets.aware(meeting.starts_at)
        duration = payload.duration_minutes or int((tickets.aware(meeting.ends_at) - tickets.aware(meeting.starts_at)).total_seconds() // 60)
        move_meeting(db, meeting, user, starts_at, duration, reason)
    elif payload.meet_link:
        # A customer booking made without Google Calendar gets its link here; both sides are sent it.
        meeting.meet_link = payload.meet_link
        for queued in db.scalars(select(Notification).where(Notification.meeting_id == meeting.id, Notification.delivery_status == "queued")).all():
            if queued.template_key == "meeting_reminder":
                queued.params = [*queued.params[:4], meeting.meet_link]
                queued.body = render(queued.template_key, queued.params)
            else:
                queued.delivery_status, queued.error_code = "cancelled", "superseded"
        _queue(db, meeting, "meeting_scheduled")
        tickets.add_event(db, ticket, "meeting_link_added", user)
    else:
        raise HTTPException(status_code=422, detail="Nothing to change.")
    tickets.audit(db, user, "meeting.updated", ticket.id, meeting_id=str(meeting.id), **payload.model_dump(mode="json", exclude_none=True))
    meeting.updated_at = ticket.updated_at = utcnow()
    db.commit()
    db.refresh(meeting)
    return tickets.meeting_view(meeting, staff=True)

@router.get("/meetings")
def list_meetings(
    start: datetime = Query(description="Window start (ISO 8601)."),
    end: datetime = Query(description="Window end (ISO 8601). At most 62 days after start."),
    lawyer: str = Query("me", description="'me', 'all' (admins) or a staff id."),
    include_cancelled: bool = False,
    user: User = Depends(current_staff),
    db: Session = Depends(get_db),
):
    """The calendar: meetings starting in the window, for one lawyer or (admins) everyone."""
    start, end = _as_utc(start), _as_utc(end)
    if end <= start or end - start > timedelta(days=62):
        raise HTTPException(status_code=422, detail="Choose a window of up to 62 days.")
    query = select(Meeting).where(Meeting.starts_at >= start, Meeting.starts_at < end)
    if lawyer == "me" or not user.is_admin:
        query = query.where(Meeting.lawyer_user_id == user.id)
    elif lawyer != "all":
        try:
            query = query.where(Meeting.lawyer_user_id == uuid.UUID(lawyer))
        except ValueError:
            raise HTTPException(status_code=422, detail="lawyer must be 'me', 'all' or a staff id")
    if not include_cancelled:
        query = query.where(Meeting.status != "cancelled")
    meetings = db.scalars(query.order_by(Meeting.starts_at)).unique().all()
    return {"items": [tickets.meeting_view(m, staff=True) for m in meetings], "timezone": config.MEETING_TIMEZONE}
