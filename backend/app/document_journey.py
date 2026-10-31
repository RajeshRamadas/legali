"""Plain-language view of where a case's documents stand: the stages of verification, how the requested documents
relate to each other, and which checks are done, in progress, waiting or have a problem.

Derived only from data the case already has (checklist item statuses, the report status and the latest verification
run's timestamp), so it adds no legal judgement of its own. Shown to customers and staff alike.
"""

# Each requested document belongs to one group. The groups are the questions a property verification answers,
# in the order they build on each other: who is selling, how they came to own it, then whether it is clean,
# recorded and approved, which together feed the advocate's opinion.
GROUPS = (
    ("identity", "Who is selling", "Is the seller who they say they are, with the right to sell?",
     "Identity, authority and inheritance papers show the person signing can actually sell.",
     ("owner-id", "power-of-attorney", "corporate-authority", "death-certificate", "succession-records")),
    ("title", "How they came to own it", "Does ownership pass cleanly from owner to owner for 30 years?",
     "Every deed should hand the property from the previous owner to the next with no gaps.",
     ("title-deeds", "sale-deed", "gift-deed", "partition-deed", "grant-orders", "jda", "promoter-title", "sale-agreement")),
    ("charges", "Loans and charges", "Is the property free of loans, mortgages and other charges?",
     "The encumbrance certificate lists every registered transaction on the property for the period searched.",
     ("ec",)),
    ("records", "Government records", "Do government records show the same owner and property?",
     "Khata, RTC, mutation, survey sketch and tax receipts should agree with the deeds.",
     ("khata", "tax-receipts", "rtc", "mutation", "survey-sketch")),
    ("approvals", "Approvals", "Is the land use and building approved?",
     "Conversion, layout, plan, occupancy and RERA approvals show the property can be used as intended.",
     ("conversion-order", "layout-approval", "building-plan", "oc", "rera", "fire-noc")),
    ("searches", "Court and government searches", "Are there no court cases or government acquisition?",
     "Searches of courts and acquisition notices look for disputes the deeds and EC don't show.",
     ("litigation-search", "acquisition-search")),
)
OTHER = ("other", "Other documents", "Has the advocate received the other documents they asked for?",
         "Documents your advocate added for this property.", ())
GROUP_OF = {tag: key for key, _, _, _, tags in GROUPS for tag in tags}
# Which groups feed which: drawn as arrows between the groups in the relationship map.
LINKS = (("identity", "title"), ("title", "charges"), ("title", "records"), ("title", "approvals"), ("title", "searches"))

DONE = ("verified", "waived")


def group_for(tag: str) -> str:
    return GROUP_OF.get(tag, "other")


def _flags(items, documents):
    """Problems the automatic upload check noticed in this group's files. Advice only: they never change a status."""
    flags = []
    for item in items:
        for doc_id in item["documents"]:
            check = (documents.get(doc_id) and documents[doc_id].ai_check) or {}
            if check.get("status") != "done":
                continue
            document = documents[doc_id]
            name = document.original_filename
            # Same rule as upload_check.view: the mismatch is computed now, so re-filing the document clears it.
            mismatch = check.get("suggested_tag") and document.tag and check["suggested_tag"] != document.tag
            if mismatch and check.get("document_type"):
                flags.append(f"{name} looks like {check['document_type']}, not {item['label']}.")
            flags += [f"{name}: {problem}" for problem in check.get("problems") or []]
    return flags


def _check(key, label, question, explains, items, documents):
    statuses = [i["status"] for i in items]
    accepted = sum(s in DONE for s in statuses)
    waiting = [i for i in items if i["status"] in ("pending", "rejected")]
    if any(s == "rejected" for s in statuses):
        status = "problem"
        rejected = [i["label"] for i in items if i["status"] == "rejected"]
        detail = "Needs attention: " + ", ".join(rejected) + "."
    elif accepted == len(items):
        status = "passed"
        detail = "All documents accepted by the advocate." if any(s == "verified" for s in statuses) else "Not needed for this property."
    elif not waiting:
        status = "in_review"
        detail = "All documents are in. The advocate is reviewing them."
    else:
        status = "waiting"
        yours = [i["label"] for i in waiting if i["fetch_by"] == "customer"]
        ours = [i["label"] for i in waiting if i["fetch_by"] == "homexo"]
        parts = []
        if yours:
            parts.append("Waiting for you: " + ", ".join(yours) + ".")
        if ours:
            parts.append("The case team is getting: " + ", ".join(ours) + ".")
        detail = " ".join(parts)
    return {"key": key, "label": label, "question": question, "explains": explains, "status": status,
            "detail": detail, "flags": _flags(items, documents), "accepted": accepted, "total": len(items), "tags": [i["tag"] for i in items]}


def _latest_run(ticket):
    from sqlalchemy import select
    from sqlalchemy.orm import object_session

    from .models import VerificationRun

    session = object_session(ticket)
    if session is None:
        return None
    return session.scalar(select(VerificationRun).where(VerificationRun.service_request_id == ticket.id)
                          .order_by(VerificationRun.created_at.desc()).limit(1))


def _reading_stage(ticket, has_documents):
    from . import verification

    run = _latest_run(ticket)
    if run is None:
        return {"status": "current" if has_documents else "upcoming",
                "detail": "Your case team will read the documents once they are in." if has_documents else "Starts once documents are uploaded."}
    stale = run.result.get("input_fingerprint") != verification.fingerprint(verification.snapshot(ticket))
    when = run.created_at.date().isoformat()
    if stale:
        return {"status": "current", "detail": f"Read on {when}. New documents arrived since, so they will be read again.", "at": run.created_at.isoformat()}
    return {"status": "done", "detail": f"Documents read and compared on {when}.", "at": run.created_at.isoformat()}


def journey(ticket, request: dict) -> dict:
    """request is document_requirements.view's dict (before this block is added to it)."""
    items = request["items"]
    report = ticket.report
    for item in items:
        item["group"] = group_for(item["tag"])

    documents = {str(d.id): d for d in ticket.documents}
    groups, checks = [], []
    for key, label, question, explains, _ in GROUPS + (OTHER,):
        members = [i for i in items if i["group"] == key]
        if not members:
            continue
        check = _check(key, label, question, explains, members, documents)
        checks.append(check)
        groups.append({"key": key, "label": label, "explains": explains, "status": check["status"], "tags": check["tags"], "flagged": bool(check["flags"])})
    present = {g["key"] for g in groups}
    links = [{"from": a, "to": b} for a, b in LINKS if a in present and b in present]

    signed = bool(report and report.status == "signed")
    if items:
        if signed:
            opinion = {"status": "passed", "detail": "The advocates have signed the final legal report."}
        elif report and report.status == "final_generated":
            opinion = {"status": "in_review", "detail": "Every document is checked. The final report is with the advocates for signature."}
        else:
            opinion = {"status": "waiting", "detail": "Given once every check above is complete."}
        checks.append({"key": "opinion", "label": "Advocate's opinion", "question": "Is the title clear and marketable?",
                       "explains": "The advocate weighs every check above and signs the legal report.", "accepted": int(signed), "total": 1, "tags": [], "flags": [], **opinion})

    customer_waiting = request["missing_count"]
    official_waiting = request["official_count"]
    has_documents = any(i["documents"] for i in items)
    all_done = bool(items) and all(i["status"] in DONE for i in items)
    stages = [
        {"key": "details", "label": "Property details",
         **({"status": "current", "detail": f"{len(request['questions'])} question{'s' if len(request['questions']) != 1 else ''} about the property will tailor your list."}
            if request["questions"] else {"status": "done", "detail": "Property details are in."})},
        {"key": "upload", "label": "Your documents",
         **({"status": "current", "detail": f"{customer_waiting} document{'s' if customer_waiting != 1 else ''} still needed from you."}
            if customer_waiting else {"status": "done", "detail": "Nothing more needed from you right now."})},
        {"key": "official", "label": "Official records",
         **({"status": "current", "detail": f"The case team is getting {official_waiting} record{'s' if official_waiting != 1 else ''} from government offices."}
            if official_waiting else {"status": "done", "detail": "Official records are in."})},
        {"key": "reading", "label": "Documents read", **_reading_stage(ticket, has_documents)},
        {"key": "review", "label": "Advocate review",
         **({"status": "done", "detail": "Every document is accepted or marked not needed."} if all_done
            else {"status": "current" if report else "upcoming",
                  "detail": "The advocate is checking each document." if report else "Starts once the advocate issues your preliminary report."})},
        {"key": "report", "label": "Signed report",
         **({"status": "done", "detail": "Your signed legal report is ready to download."} if signed
            else {"status": "current", "detail": "With the advocates for signature."} if report and report.status == "final_generated"
            else {"status": "upcoming", "detail": "Issued after the advocate's review."})},
    ]
    if not items:
        stages = []
    # Uploads and official records run side by side, so more than one stage can be current at once.
    next_upload = next((i for i in items if i["fetch_by"] == "customer" and i["status"] == "rejected"), None) \
        or next((i for i in items if i["fetch_by"] == "customer" and i["status"] == "pending"), None)
    return {"stages": stages, "groups": groups, "links": links, "checks": checks,
            "next_upload": next_upload["id"] if next_upload else None}
