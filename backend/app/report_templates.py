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
# Every property: the title chain, encumbrances and who is selling.
COMMON = (
    ("sale-deed", "Sale deed of the present owner", "Registered copy, all pages"),
    ("title-deeds", "Previous title deeds (30 years)", "Mother deed and every deed in the chain for the last 30 years"),
    ("ec", "Encumbrance certificate (30 years)", "Form 15 / Form 16 from the sub-registrar, up to date"),
    ("owner-id", "Owner's identity proof", "Aadhaar or PAN of every owner and seller"),
)
# Property in a city or town: municipal khata and tax.
URBAN = (
    ("khata", "Khata certificate and extract", "BBMP / BDA / municipal khata in the owner's name, A or B khata. Waive for property in panchayat limits"),
    ("tax-receipts", "Property tax receipts", "Last 3 years"),
)
# Property in a village panchayat: e-Swathu records instead of a city khata.
PANCHAYAT = (
    ("eswathu", "e-Swathu Form 9 / Form 11", "Panchayat property record in the owner's name. Waive for property in city limits"),
)
# Land still on the revenue records: RTC, mutations, survey and land-reform checks.
REVENUE = (
    ("rtc", "RTC / Pahani (30 years)", "Record of rights for every survey number, from the earliest year available"),
    ("mutation", "Mutation register extracts", "Every mutation (MR) in the 30-year period"),
    ("survey-sketch", "Survey sketch, tippani and akarbandh", "Hissa sketch with tippani and akarbandh for each survey number"),
    ("grant-orders", "Grant, inam or land reform orders", "Saguvali chit, grant certificate or Land Tribunal order, if any part was granted"),
    ("ptcl", "PTCL non-alienation check", "Confirmation the land was not granted to SC/ST holders, or the government's permission to sell"),
)
# Built property: approvals for the structure.
BUILDING = (
    ("building-plan", "Sanctioned building plan", "Plan approval from BBMP / BDA / BMRDA / panchayat"),
    ("oc", "Occupancy certificate", "OC for the building, or completion certificate if OC is not issued yet"),
)
BY_PROPERTY_TYPE = {
    "apartment": URBAN + (
        ("jda", "Builder-landowner agreements", "Joint development agreement and GPA, if the building was developed"),
        *BUILDING,
        ("rera", "RERA registration", "Project registration number and certificate, if applicable"),
        ("sale-agreement", "Agreement for sale", "Draft or signed agreement with the builder or seller"),
        ("conversion-order", "Land conversion order", "DC conversion order for the land the project stands on"),
    ),
    "villa": URBAN + PANCHAYAT + (
        ("jda", "Builder-landowner agreements", "Joint development agreement and GPA for the layout"),
        ("layout-approval", "Layout and building approvals", "Approved layout plan with release order, and the villa's sanctioned plan"),
        ("oc", "Occupancy certificate", "OC or completion certificate for the villa"),
        ("rera", "RERA registration", "Project registration number and certificate"),
        ("conversion-order", "Land conversion order", "DC conversion order for the layout land"),
        ("sale-agreement", "Agreement for sale and association rules", "Builder agreement, and the owners' association bye-laws if any"),
    ),
    "independent_house": URBAN + BUILDING + (
        ("survey-sketch", "Survey sketch", "Hissa / survey sketch of the site"),
        ("conversion-order", "Land conversion order", "DC conversion order, if the site was carved out of farm land"),
    ),
    "residential_plot": URBAN + PANCHAYAT + (
        ("conversion-order", "Land conversion order", "DC conversion order for non-agricultural use"),
        ("layout-approval", "Layout approval", "Approved layout plan and release order from BDA / BMRDA / planning authority"),
        ("survey-sketch", "Survey sketch", "Hissa / survey sketch of the plot"),
    ),
    "agricultural_land": REVENUE + (
        ("buyer-eligibility", "Buyer's eligibility to buy farm land", "Karnataka Land Reforms Act sections 79A / 79B as they now apply, and income declaration if asked"),
        ("tenancy", "Tenancy and Land Tribunal check", "Any tenancy claim or Form 7 application on the land"),
    ),
    "farmhouse": REVENUE + PANCHAYAT + (
        ("conversion-order", "Conversion or farmhouse permission", "DC conversion order, or the panchayat permission for a farmhouse on farm land"),
        ("building-plan", "Farmhouse building approval", "Panchayat or planning authority approval for the structure"),
        ("farm-agreement", "Managed farmland agreements", "Sale and maintenance agreements with the farmland developer, and the sub-division sketch (11E / phodi)"),
        ("buyer-eligibility", "Buyer's eligibility to buy farm land", "Karnataka Land Reforms Act sections 79A / 79B as they now apply"),
    ),
    "plantation_estate": REVENUE + PANCHAYAT + (
        ("plantation-registration", "Plantation registration", "Coffee Board / Tea Board / Rubber Board / Spices Board registration of the estate"),
        ("land-reforms-exemption", "Land reforms plantation exemption", "Order or declaration exempting the plantation from the land ceiling"),
        ("forest-noc", "Forest and eco-sensitive zone check", "Forest department NOC or confirmation the land is not deemed forest or in an eco-sensitive zone"),
        ("estate-buildings", "Estate buildings and labour lines", "Approvals or panchayat records for bungalows, curing yards and labour lines"),
        ("water-rights", "Water and tree rights", "Water source permissions and any tree-felling or timber permits on record"),
    ),
    "industrial_land": (
        ("kiadb-allotment", "KIADB / KSSIDC allotment letter", "Allotment letter and the terms, for land in an industrial area"),
        ("lease-cum-sale", "Lease-cum-sale agreement", "Registered lease-cum-sale agreement with KIADB"),
        ("possession-certificate", "Possession certificate", "Possession certificate from KIADB"),
        ("absolute-sale-deed", "Absolute sale deed from KIADB", "Once the lease period is over and conditions are met"),
        ("conversion-order", "Land conversion order", "For industrial land outside KIADB areas"),
        ("building-plan", "Sanctioned factory building plan", "Plan approval from KIADB or the planning authority"),
        ("pcb-consent", "Pollution control board consent", "KSPCB consent to establish and operate"),
        ("fire-noc", "Fire and other NOCs", "Fire NOC and factory licence, if a unit is running"),
        *URBAN,
    ),
    "commercial": URBAN + BUILDING + (
        ("conversion-order", "Land conversion order", "DC conversion order for commercial use"),
        ("fire-noc", "Fire and other NOCs", "Fire NOC and any other approvals for the use"),
        ("trade-licence", "Trade licence and leases", "Trade licence, and leases with current tenants if the property is let"),
    ),
    "other": URBAN + PANCHAYAT + (
        ("rtc", "RTC / Pahani", "If the land is still on the revenue records"),
        ("survey-sketch", "Survey sketch", "Hissa / survey sketch of the property"),
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
