"""Google Calendar events with Google Meet links, through the Calendar REST API.

A service account with domain-wide delegation acts as a Google Workspace user (GOOGLE_CALENDAR_USER), because
Meet links can only be created on a Workspace user's calendar. The customer and lawyer are added as attendees,
so Google emails them the invite and updates, and the meeting shows in the lawyer's own Google Calendar.
"""
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx
import jwt

from . import config

SCOPE = "https://www.googleapis.com/auth/calendar.events"
API = "https://www.googleapis.com/calendar/v3"

# Replaced in tests with a client on a mock transport.
http = httpx.Client(timeout=20)
_token: dict = {}

class CalendarError(Exception):
    pass

def enabled() -> bool:
    return bool(config.GOOGLE_SERVICE_ACCOUNT_JSON and config.GOOGLE_CALENDAR_USER)

def _service_account() -> dict:
    raw = config.GOOGLE_SERVICE_ACCOUNT_JSON.strip()
    return json.loads(raw if raw.startswith("{") else Path(raw).read_text())

def _access_token() -> str:
    if _token.get("expires_at", 0) > time.time() + 60:
        return _token["value"]
    account = _service_account()
    now = int(time.time())
    assertion = jwt.encode(
        {"iss": account["client_email"], "sub": config.GOOGLE_CALENDAR_USER, "scope": SCOPE, "aud": account["token_uri"], "iat": now, "exp": now + 3600},
        account["private_key"], algorithm="RS256",
    )
    response = http.post(account["token_uri"], data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion})
    if response.status_code != 200:
        raise CalendarError(f"Google sign-in failed ({response.status_code}): {response.text[:200]}")
    data = response.json()
    _token.update(value=data["access_token"], expires_at=now + int(data.get("expires_in", 3600)))
    return _token["value"]

def _call(method: str, path: str, **kwargs) -> dict:
    try:
        response = http.request(method, f"{API}/calendars/{config.GOOGLE_CALENDAR_ID}/events{path}", headers={"Authorization": f"Bearer {_access_token()}"}, **kwargs)
    except httpx.HTTPError as exc:
        raise CalendarError(f"Google Calendar is unreachable: {exc}") from exc
    # A deleted event is already gone, which is what a cancellation wants.
    if method == "DELETE" and response.status_code in (404, 410):
        return {}
    if response.status_code >= 400:
        try:
            message = response.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = response.text[:200]
        raise CalendarError(f"Google Calendar refused the request ({response.status_code}): {message}")
    return response.json() if response.content else {}

def _times(starts_at: datetime, ends_at: datetime) -> dict:
    return {
        "start": {"dateTime": starts_at.isoformat(), "timeZone": config.MEETING_TIMEZONE},
        "end": {"dateTime": ends_at.isoformat(), "timeZone": config.MEETING_TIMEZONE},
    }

def meet_link(event: dict) -> str | None:
    if event.get("hangoutLink"):
        return event["hangoutLink"]
    for entry in event.get("conferenceData", {}).get("entryPoints", []):
        if entry.get("entryPointType") == "video":
            return entry.get("uri")
    return None

def create_event(*, title: str, description: str, starts_at: datetime, ends_at: datetime, attendees: list[str]) -> tuple[str, str]:
    """Create the event with a Meet conference. Returns (event id, Meet link)."""
    body = {
        "summary": title,
        "description": description,
        **_times(starts_at, ends_at),
        "attendees": [{"email": email} for email in dict.fromkeys(attendees)],
        "conferenceData": {"createRequest": {"requestId": uuid.uuid4().hex, "conferenceSolutionKey": {"type": "hangoutsMeet"}}},
        "reminders": {"useDefault": False, "overrides": [{"method": "email", "minutes": 1440}, {"method": "popup", "minutes": 10}]},
        "guestsCanModify": False,
    }
    event = _call("POST", "", params={"conferenceDataVersion": 1, "sendUpdates": "all"}, json=body)
    link = meet_link(event)
    if not link:
        # Conference creation is normally immediate; read the event once more if it was still pending.
        event = _call("GET", f"/{event['id']}")
        link = meet_link(event)
    if not link:
        raise CalendarError("Google Calendar created the event but no Meet link. Check that Google Meet is enabled for the Workspace.")
    return event["id"], link

def update_event(event_id: str, *, starts_at: datetime, ends_at: datetime, description: str | None = None) -> None:
    body = _times(starts_at, ends_at) | ({"description": description} if description is not None else {})
    _call("PATCH", f"/{event_id}", params={"sendUpdates": "all"}, json=body)

def cancel_event(event_id: str) -> None:
    _call("DELETE", f"/{event_id}", params={"sendUpdates": "all"})
