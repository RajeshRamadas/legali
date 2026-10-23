"""WhatsApp Business messages through Meta's Cloud API.

Messages a business starts (invites, reminders, agendas) must use a template approved in WhatsApp Manager, so each
notification's template_key names a template and its params fill the template's {{1}}, {{2}}... placeholders.
The templates are listed in docs/meetings.md.
"""
import re

import httpx

from . import config

# Replaced in tests with a client on a mock transport.
http = httpx.Client(timeout=20)

class WhatsAppError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code

def enabled() -> bool:
    return bool(config.WHATSAPP_ACCESS_TOKEN and config.WHATSAPP_PHONE_NUMBER_ID)

def to_wa_number(phone: str) -> str:
    """Digits with country code, as the Cloud API expects. Bare 10-digit numbers get the default country code."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        digits = config.WHATSAPP_DEFAULT_COUNTRY_CODE + digits
    return digits

def _param(value: str) -> str:
    # Template parameters can't hold newlines, tabs or long runs of spaces.
    return re.sub(r"\s+", " ", str(value)).strip()[:1000] or "-"

def send_template(phone: str, template: str, params: list[str], *, button_param: str | None = None) -> str:
    """Send a template message. Returns the WhatsApp message id.

    button_param fills the first button's parameter, which authentication templates with a copy-code button need.
    """
    components = [{"type": "body", "parameters": [{"type": "text", "text": _param(p)} for p in params]}] if params else []
    if button_param is not None:
        components.append({"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": button_param}]})
    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_number(phone),
        "type": "template",
        "template": {
            "name": template,
            "language": {"code": config.WHATSAPP_TEMPLATE_LANGUAGE},
            "components": components,
        },
    }
    try:
        response = http.post(
            f"{config.WHATSAPP_API_BASE}/{config.WHATSAPP_PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {config.WHATSAPP_ACCESS_TOKEN}"}, json=payload,
        )
    except httpx.HTTPError as exc:
        raise WhatsAppError(f"WhatsApp is unreachable: {exc}", "unreachable") from exc
    data = response.json() if response.content else {}
    if response.status_code >= 400:
        error = data.get("error", {}) if isinstance(data, dict) else {}
        raise WhatsAppError(error.get("message", response.text[:200]), str(error.get("code", response.status_code)))
    return data["messages"][0]["id"]
