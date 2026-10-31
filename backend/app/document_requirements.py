"""Deterministic intake-driven document requests; no LLM or legal opinion required."""
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from . import gov_sources, report_templates
from .models import CLOSED_STATUSES

SERVICES = {"title-verification", "legal-due-diligence", "developer-land-screening", "acquisition-due-diligence"}

class PropertyIntake(BaseModel):
    state: Literal["Karnataka", "Other", "Unknown"] = "Unknown"
    transaction: Literal["purchase", "inheritance", "gift", "partition", "other", "unknown"] = "unknown"
    seller_capacity: Literal["owner", "power_of_attorney", "legal_heir", "company", "unknown"] = "unknown"
    development: Literal["new", "resale", "land", "unknown"] = "unknown"
    granted_land: Literal["yes", "no", "unknown"] = "unknown"
    survey_number: str = Field(default="", max_length=60)
    property_id_or_pid: str = Field(default="", max_length=60)
    village: str = Field(default="", max_length=100)
    taluk: str = Field(default="", max_length=100)
    district: str = Field(default="", max_length=100)


def intake(ticket):
    return PropertyIntake.model_validate((ticket.structured_answers or {}).get("property_intake", {})).model_dump()


def checklist(ticket):
    answers = intake(ticket)
    items = report_templates.checklist_for(ticket.prop.property_type if ticket.prop else None)
    extras = []
    if answers["seller_capacity"] == "power_of_attorney":
        extras.append(("power-of-attorney", "Power of attorney and principal's authority", "All pages of the POA, registration/authentication details where applicable, and evidence that it remains effective."))
    if answers["seller_capacity"] == "legal_heir" or answers["transaction"] == "inheritance":
        extras += [("death-certificate", "Death certificate of the previous owner", "For each deceased owner in the title chain."),
                   ("succession-records", "Inheritance and succession documents", "Family tree, applicable heirship records, any will, probate/administration where required, and releases/partitions. Your advocate determines what applies; a succession certificate alone is not proof of title to land.")]
    if answers["seller_capacity"] == "company":
        extras.append(("corporate-authority", "Company ownership and signatory authority", "Company particulars, board authorisation and the instrument authorising the signatory, as applicable."))
    if answers["transaction"] in ("gift", "partition"):
        extras.append((answers["transaction"] + "-deed", "Gift deed" if answers["transaction"] == "gift" else "Partition deed", "Complete executed/registered instrument where applicable, including schedules and all parties."))
    if answers["development"] == "new":
        extras.append(("promoter-title", "Promoter's title and development authority", "Landowner title, development agreement, authority to sell and project approvals, as applicable."))
    if answers["granted_land"] == "yes":
        extras.append(("grant-orders", "Original grant and transfer permissions", "Grant order, conditions, grant history and any required transfer permission; advocate must assess applicability."))
    taken = {i["tag"] for i in items}
    for tag, label, guidance in extras:
        if tag not in taken:
            items.append({"tag": tag, "label": label, "guidance": guidance, "fetch_by": "customer", "source": None})
            taken.add(tag)
    for tag, label, guidance in (
        ("litigation-search", "Court and litigation search record", "Record the courts searched, party/property identifiers, date, results and limitations. An EC alone does not establish absence of litigation."),
        ("acquisition-search", "Acquisition and government-notice search", "Check applicable acquisition notifications, reservations and restrictions. Retain the official search result or a dated search memorandum."),
    ):
        items.append({"tag": tag, "label": label, "guidance": guidance, "fetch_by": "homexo", "source": gov_sources.source_for(tag)})
    # Karnataka portal assignments must not silently be applied to another state.
    if answers["state"] != "Karnataka":
        for item in items:
            item["source"] = None
            if item["fetch_by"] == "homexo":
                item["guidance"] += " The case team must identify the correct authority for the property's state."
    return items


def view(ticket):
    answers = intake(ticket)
    report = ticket.report
    docs = [d for d in ticket.documents if d.document_category not in ("final_report", "signed_report")]
    if report and report.status != "draft":
        rows = [{"id": str(i.id), "tag": i.tag, "label": i.label, "guidance": i.guidance,
                 "status": i.status, "fetch_by": i.fetch_by, "source": gov_sources.source_view(i.source), "note": i.review_note} for i in report.items]
        origin = "advocate_checklist"
    elif ticket.service_type.slug in SERVICES:
        rows = [{**i, "id": str(uuid.uuid5(ticket.id, i["tag"])), "status": "pending", "note": None,
                 "source": gov_sources.source_view(i["source"])} for i in checklist(ticket)]
        origin = "automatic_intake"
    else:
        rows, origin = [], "not_applicable"
    labels = {"pending": "Needed", "received": "Received, under review", "verified": "Accepted", "rejected": "Please upload again", "waived": "Not needed"}
    for row in rows:
        row["documents"] = [str(d.id) for d in docs if d.tag == row["tag"]]
        if origin == "automatic_intake" and row["documents"]:
            row["status"] = "received"
        row["status_label"] = "Case team to obtain" if row["status"] == "pending" and row["fetch_by"] == "homexo" else labels[row["status"]]
    missing = [i for i in rows if i["fetch_by"] == "customer" and i["status"] in ("pending", "rejected")]
    official = [i for i in rows if i["fetch_by"] == "homexo" and i["status"] in ("pending", "rejected")]
    questions = []
    if rows:
        if answers["state"] == "Unknown": questions.append("Which state is the property in?")
        if answers["transaction"] == "unknown": questions.append("Is this a purchase, inheritance, gift or partition?")
        if answers["seller_capacity"] == "unknown": questions.append("Is the seller the owner, an attorney, a legal heir or a company?")
        if answers["development"] == "unknown": questions.append("Is this a new development, resale or land transaction?")
        if answers["granted_land"] == "unknown": questions.append("Was the land originally granted by the government? Choose unknown if unsure.")
    prompt = "Please upload " + ", ".join(i["label"] for i in missing[:4]) + (f" and {len(missing) - 4} other requested documents" if len(missing) > 4 else "") + "." if missing else "No further customer uploads are currently requested; received files still need advocate review."
    if official: prompt += f" The case team has {len(official)} official-record tasks to complete."
    if ticket.status in CLOSED_STATUSES:
        prompt = "This request is closed. Contact the case team if documents or property details need to change."
    result = {"origin": origin, "intake": answers, "items": rows, "missing_count": len(missing), "official_count": len(official),
              "questions": questions, "prompt": prompt if rows else "The case team will confirm documents for this service.",
              "note": "This is a provisional document request, not an issued legal opinion. Applicability and any additional documents are confirmed by the advocate."}
    from . import document_journey
    result["journey"] = document_journey.journey(ticket, result)
    return result
