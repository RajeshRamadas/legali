"""The report format: sections of the preliminary and final reports, and the document checklists lawyers start from.

Lawyers can edit every section's text and add, drop or reword checklist items; these are only the starting point.
"""
import re

from . import gov_sources

SCOPE = ("We will examine the title of the present owner for the last 30 years, encumbrances, revenue and municipal records, "
         "and approvals for the property described above.")
INSTRUCTIONS = ("Please upload each document marked for you below under its tag. Clear scans or photos of every page are fine; we may ask "
                "for originals at the final stage. Public records marked for Homexo we will get from the government portals ourselves.")

# (key, heading, hint shown in the editor, starting text). The preliminary report goes to the customer with the checklist.
PRELIMINARY_SECTIONS = (
    ("property", "Property details", "Type, address, survey / PID number, extent and present owner, as the customer described it.", ""),
    ("scope", "Scope of scrutiny", "What this verification covers.", SCOPE),
    ("observations", "Preliminary observations", "What stands out so far and what the documents below should settle.", ""),
    ("instructions", "What we need from you", "How the customer should send the documents.", INSTRUCTIONS),
)

# Sections left empty are not printed.
FINAL_SECTIONS = (
    ("title_flow", "Flow of title", "Each transfer from the earliest document examined to the present owner, with document numbers and dates.", ""),
    ("encumbrances", "Encumbrances and litigation", "ECs examined and their result; any mortgage, lien, attachment or pending litigation.", ""),
    ("revenue_records", "Revenue and municipal records", "Khata, RTC / mutation and tax status, and whether they agree with the title documents.", ""),
    ("approvals", "Approvals and compliance", "Conversion, layout or plan approvals, occupancy certificate and RERA, as applicable.", ""),
    ("opinion", "Opinion", "Whether the title is clear and marketable, and subject to what.", ""),
    ("conditions", "Conditions and recommendations", "Steps to complete before or at registration.", ""),
)

def blank_sections(sections: tuple) -> dict:
    return {key: text for key, _, _, text in sections}

def section_view(sections: tuple, values: dict) -> list[dict]:
    return [{"key": key, "heading": heading, "hint": hint, "text": (values or {}).get(key, "")} for key, heading, hint, _ in sections]

# (tag, label, guidance). The tag is what customers file uploads under, so keep it short.
COMMON = (
    ("sale-deed", "Sale deed of the present owner", "Registered copy, all pages"),
    ("title-deeds", "Previous title deeds (30 years)", "Mother deed and every deed in the chain for the last 30 years"),
    ("ec", "Encumbrance certificate (30 years)", "Form 15 / Form 16 from the sub-registrar, up to date"),
    ("khata", "Khata certificate and extract", "BBMP / BDA / panchayat, in the owner's name"),
    ("tax-receipts", "Property tax receipts", "Last 3 years"),
    ("owner-id", "Owner's identity proof", "Aadhaar or PAN of every owner and seller"),
)
BY_PROPERTY_TYPE = {
    "apartment": (
        ("jda", "Builder-landowner agreements", "Joint development agreement and GPA, if the building was developed"),
        ("building-plan", "Sanctioned building plan", "Plan approval from BBMP / BDA / BMRDA"),
        ("oc", "Occupancy certificate", "OC for the building, or CC if OC is not issued yet"),
        ("rera", "RERA registration", "Project registration number and certificate, if applicable"),
        ("sale-agreement", "Agreement for sale", "Draft or signed agreement with the builder or seller"),
    ),
    "independent_house": (
        ("building-plan", "Sanctioned building plan", "Plan approval from BBMP / BDA / panchayat"),
        ("oc", "Occupancy certificate", "If the house was built after 2003 in BBMP limits"),
        ("survey-sketch", "Survey sketch", "Hissa / survey sketch of the site"),
    ),
    "residential_plot": (
        ("conversion-order", "Land conversion order", "DC conversion order for non-agricultural use"),
        ("layout-approval", "Layout approval", "Approved layout plan and release order from BDA / BMRDA"),
        ("survey-sketch", "Survey sketch", "Hissa / survey sketch of the plot"),
    ),
    "agricultural_land": (
        ("rtc", "RTC / Pahani (30 years)", "Record of rights for every survey number"),
        ("mutation", "Mutation register extracts", "Every mutation in the 30-year period"),
        ("survey-sketch", "Survey sketch and tippani", "Hissa sketch, tippani and akarbandh"),
        ("grant-orders", "Grant or land reform orders", "If any part was granted or subject to land reforms"),
    ),
    "commercial": (
        ("building-plan", "Sanctioned building plan", "Plan approval for commercial use"),
        ("oc", "Occupancy certificate", "OC for the building"),
        ("fire-noc", "Fire and other NOCs", "Fire NOC and any other approvals for the use"),
    ),
}

def make_tag(label: str, taken: set[str]) -> str:
    """A tag for an item the lawyer adds: 'Gift deed from father' -> 'gift-deed-from-father', with -2, -3 ... if already used."""
    base = normalize_tag(label)[:32].strip("-") or "document"
    tag, n = base, 1
    while tag in taken:
        n += 1
        tag = f"{base}-{n}"
    return tag

def normalize_tag(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower().lstrip("#")).strip("-")[:48]

def checklist_for(property_type: str | None) -> list[dict]:
    items, taken = [], set()
    for tag, label, guidance in COMMON + BY_PROPERTY_TYPE.get(property_type or "", ()):
        if tag not in taken:
            taken.add(tag)
            source = gov_sources.source_for(tag)
            # Public records Homexo can get from a government portal are fetched by the team, so the buyer has less to chase.
            items.append({"tag": tag, "label": label, "guidance": guidance, "fetch_by": "homexo" if tag in gov_sources.FETCH_BY_DEFAULT else "customer", "source": source})
    return items
