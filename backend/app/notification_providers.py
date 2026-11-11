"""Transactional email/SMS adapters. Errors contain safe codes, never provider response bodies."""
import re
from urllib.parse import quote

import httpx

from . import config

http = httpx.Client(timeout=20, follow_redirects=False)


class DeliveryError(Exception):
    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def enabled(channel: str) -> bool:
    if channel == "email":
        return bool(config.RESEND_API_KEY and config.EMAIL_FROM)
    if channel == "sms":
        return bool(config.TWILIO_ACCOUNT_SID and config.TWILIO_AUTH_TOKEN
                    and (config.TWILIO_FROM_NUMBER or config.TWILIO_MESSAGING_SERVICE_SID))
    return False


SUBJECTS = {
    "ticket_created": "Request received", "status_changed": "Request update",
    "documents_requested": "Documents requested", "staff_message": "Message from your case team",
    "payment_received": "Payment update", "meeting_scheduled": "Consultation booked",
    "meeting_rescheduled": "Consultation moved", "meeting_cancelled": "Consultation cancelled",
    "meeting_reminder": "Consultation reminder", "report_issued": "Report ready",
    "report_signed": "Signed report ready", "document_rejected": "Document update",
}


def customer_message(notification, ticket_number: str | None = None) -> tuple[str, str]:
    """Keep legal details, documents and staff-message excerpts inside the verified portal."""
    if notification.template_key == "support_deadline_email":
        subject = "Escalated support response target" if notification.params == ["escalated"] else "Support response target missed"
        return f"Homexo staff: {subject}", f"Homexo Legal staff: {subject}. Sign in to review current support alerts at {config.PUBLIC_SITE_URL.rstrip('/')}/admin/support/alerts. Acknowledging does not change the response target."
    if notification.template_key == "support_reply":
        return "Homexo Legal: New support reply", f"Homexo Legal: You have a new support reply. Sign in to read it securely: {config.PUBLIC_SITE_URL.rstrip('/')}/account/support"
    if notification.template_key == "case_deadline_alert":
        kind, phase = notification.params or ["case_due", "initial"]
        label = "First response overdue" if kind == "first_response" else "Case target missed"
        subject = ("Escalated: " if phase == "escalated" else "") + label
        return f"Homexo staff: {subject}", f"Homexo Legal staff: {subject}. Case reference: {ticket_number or 'open staff alerts'}. Review the case and acknowledge the alert at {config.PUBLIC_SITE_URL}/admin/alerts. Acknowledging does not change the case target."
    subject = SUBJECTS.get(notification.template_key, "Request update")
    ticket = ticket_number
    # No customer-provided message text or authentication links go into notifications.
    reference = f"Request reference: {ticket}. " if ticket else ""
    if notification.template_key == "ticket_created":
        text = "We received your request. A specialist will contact you to confirm the next steps."
    elif notification.template_key == "documents_requested":
        text = "Your request has a document checklist. Sign in to see what is needed."
    else:
        text = "There is an update on your request. Sign in to read it securely."
    return f"Homexo Legal: {subject}", f"Homexo Legal: {text} {reference}Visit {config.PUBLIC_SITE_URL}/account"


def send_email(notification, ticket_number: str | None = None) -> str:
    recipient = notification.recipient or ""
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", recipient):
        raise DeliveryError("invalid_email")
    subject, body = customer_message(notification, ticket_number)
    try:
        response = http.post("https://api.resend.com/emails", headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Idempotency-Key": f"homexo-notification/{notification.id}",
        }, json={"from": config.EMAIL_FROM, "to": [recipient], "subject": subject, "text": body})
    except httpx.HTTPError as exc:
        raise DeliveryError("email_unreachable", retryable=True) from exc
    if response.status_code == 429 or response.status_code >= 500:
        raise DeliveryError(f"email_http_{response.status_code}", retryable=True)
    if response.status_code >= 300:
        raise DeliveryError(f"email_http_{response.status_code}")
    try:
        value = response.json()["id"]
        if not isinstance(value, str) or not value:
            raise ValueError
        return value
    except (ValueError, KeyError, TypeError) as exc:
        raise DeliveryError("email_invalid_response", retryable=True) from exc


def send_staff_reset(recipient: str, token: str, reference: str) -> None:
    """An authentication link is sent directly, never saved in notification bodies or ticket views."""
    url = f"{config.PUBLIC_SITE_URL}/admin/reset-password#token={quote(token, safe='')}"
    try:
        response = http.post("https://api.resend.com/emails", headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}", "Idempotency-Key": f"homexo-staff-reset/{reference}",
        }, json={"from": config.EMAIL_FROM, "to": [recipient], "subject": "Reset your Homexo staff password",
                 "text": f"Reset your staff password using this link within 20 minutes:\n{url}\n\nIf two-factor sign-in is enabled, you will also need your authenticator or a recovery code. If you did not request this, ignore this email. Your password has not changed."})
    except httpx.HTTPError as exc:
        raise DeliveryError("staff_reset_unreachable") from exc
    if not 200 <= response.status_code < 300:
        raise DeliveryError(f"staff_reset_http_{response.status_code}")


def sms_number(phone: str) -> str:
    if re.search(r"[^\d+() .-]", phone):
        raise DeliveryError("invalid_phone")
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and not phone.strip().startswith("+"):
        digits = config.SMS_DEFAULT_COUNTRY_CODE + digits
    if not re.fullmatch(r"[1-9]\d{7,14}", digits):
        raise DeliveryError("invalid_phone")
    return "+" + digits


def send_sms(notification, ticket_number: str | None = None) -> str:
    _, body = customer_message(notification, ticket_number)
    form = {"To": sms_number(notification.recipient or ""), "Body": body}
    if config.TWILIO_MESSAGING_SERVICE_SID:
        form["MessagingServiceSid"] = config.TWILIO_MESSAGING_SERVICE_SID
    else:
        form["From"] = config.TWILIO_FROM_NUMBER
    try:
        response = http.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{quote(config.TWILIO_ACCOUNT_SID, safe='')}/Messages.json",
            auth=httpx.BasicAuth(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN), data=form,
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
        raise DeliveryError("sms_connect_failed", retryable=True) from exc
    except httpx.HTTPError as exc:
        # A read/write timeout may happen after Twilio accepted the message. Do not resend.
        raise DeliveryError("sms_outcome_unknown") from exc
    if response.status_code == 429:
        raise DeliveryError("sms_rate_limited", retryable=True)
    if response.status_code >= 500:
        raise DeliveryError("sms_outcome_unknown")
    if response.status_code >= 300:
        raise DeliveryError(f"sms_http_{response.status_code}")
    try:
        data = response.json()
        value = data["sid"]
        if not isinstance(value, str) or not value:
            raise ValueError
        if data.get("status") in ("failed", "undelivered", "canceled"):
            raise DeliveryError("sms_rejected")
        return value
    except (ValueError, KeyError, TypeError) as exc:
        raise DeliveryError("sms_outcome_unknown") from exc
