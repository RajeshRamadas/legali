"""Allowlisted, read-only review of submitted intake; never consult the live catalogue."""
import uuid
from datetime import datetime

FIELDS = {
    "service_slug": "Selected service", "goal": "Customer goal", "property_type": "Property type",
    "location": "Area and city", "state": "Property state", "state_name": "State name", "role": "Customer role",
    "transaction": "Transaction", "seller_capacity": "Seller capacity", "development": "Development or resale",
    "granted_land": "Government grant history", "survey_number": "Survey number", "village": "Village",
    "taluk": "Taluk", "property_id_or_pid": "Property ID or PID", "district": "District",
    "available_documents": "Available document names", "customer_name": "Customer name", "email": "Email",
    "contact_preference": "Preferred follow-up",
}


def capture(questions, answers):
    return [{"key": question["key"], "question": question["prompt"], "value": answers[question["key"]],
        "answer": next((option["label"] for option in question["options"] if option["value"] == answers[question["key"]]), answers[question["key"]]),
        "skipped": answers[question["key"]] == ""} for question in questions]


def text(value, limit):
    return isinstance(value, str) and len(value) <= limit and "\x00" not in value


def timestamp(value):
    if not text(value, 80): return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.isoformat() if parsed.tzinfo else None
    except ValueError:
        return None


def review(guided):
    if not isinstance(guided, dict) or not isinstance(guided.get("answers"), dict): return None
    answers = guided["answers"]
    if not text(answers.get("service_slug"), 100) or not answers["service_slug"]: return None
    form = guided.get("service_form")
    form = form if isinstance(form, dict) and form.get("service_slug") == answers["service_slug"] else {}
    definitions = form.get("questions", [])
    invalid_definitions = not isinstance(definitions, list)
    definitions = definitions if isinstance(definitions, list) else []
    extra, incomplete = {}, invalid_definitions or len(definitions) > 5
    for row in definitions[:5]:
        try:
            key = "extra_"+uuid.UUID(row["id"]).hex
            if not text(row.get("prompt"), 160) or not row["prompt"].strip() or row.get("kind") not in ("text", "textarea", "select"):
                raise ValueError("Invalid retained question")
            if key in extra: raise ValueError("Duplicate retained question")
            extra[key] = row
        except (KeyError, TypeError, ValueError, AttributeError):
            incomplete = True
    allowed = set(FIELDS) | set(extra)
    incomplete |= any(key not in allowed for key in answers)
    rows = []
    snapshot = guided.get("submitted_answers")
    incomplete |= "submitted_answers" in guided and not isinstance(snapshot, list)
    if isinstance(snapshot, list):
        incomplete |= len(snapshot) > 40
        seen = set()
        for row in snapshot[:40]:
            if not isinstance(row, dict): incomplete = True; continue
            key = row.get("key")
            if not isinstance(key, str) or key not in allowed or key in seen or key not in answers or not text(answers[key], 4000) or row.get("value") != answers[key] or not text(row.get("question"), 500) or not row["question"].strip() or not text(row.get("answer"), 4000):
                incomplete = True; continue
            seen.add(key)
            rows.append({"key": key, "question": row["question"], "answer": row["answer"], "skipped": answers[key] == "", "section": "service" if key in extra else "general"})
        incomplete |= any(key not in seen for key in answers if key in allowed)
    else:
        # Legacy core values have no retained display labels. Do not reconstruct
        # original wording from today's questions or a later conversation message.
        for key, label in FIELDS.items():
            if key not in answers: continue
            if not text(answers[key], 4000): incomplete = True; continue
            rows.append({"key": key, "question": label, "answer": answers[key], "skipped": answers[key] == "", "section": "general"})
        for key, question in extra.items():
            if key not in answers or not text(answers[key], 1000): incomplete = True; continue
            value = answers[key]
            if question["kind"] == "select" and value:
                options = question.get("options")
                if not isinstance(options, list) or len(options) > 8 or value not in {str(index+1) for index in range(len(options))} or not text(options[int(value)-1], 80):
                    incomplete = True; continue
                value = options[int(value)-1]
            rows.append({"key": key, "question": question["prompt"], "answer": value, "skipped": answers[key] == "", "section": "service"})
    version = form.get("revision")
    return {"format": "snapshot" if isinstance(snapshot, list) else "legacy", "answers": rows, "incomplete": incomplete,
        "service_form_revision": version if type(version) is int and 1 <= version <= 2147483647 else None,
        "submitted_at": timestamp(guided.get("consented_at")), "saving_consented_at": timestamp(guided.get("saving_consented_at")),
        "submission_notice": guided.get("notice_version") if text(guided.get("notice_version"), 80) else None,
        "saving_notice": guided.get("saving_notice_version") if text(guided.get("saving_notice_version"), 80) else None}
