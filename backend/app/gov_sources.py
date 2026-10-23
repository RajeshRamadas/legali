"""Government portals that hold the public records a property check needs, so Homexo can get them instead of the buyer.

Karnataka's portals have no open API: most need a captcha, an OTP or a paid login. So a fetch is a task for the case team:
the item shows in the fetch queue with the portal, what to search by and the property's details, and staff upload the
certified copy under the item's tag. A portal that later offers an API (or a licensed aggregator) can be plugged in by
adding a fetcher here that returns the file; the checklist and the queue stay the same.
"""
from typing import Callable

# key -> portal. "provides" lists the checklist tags this portal can supply.
SOURCES: dict[str, dict] = {
    "kaveri": {
        "name": "Kaveri Online Services (IGR Karnataka)",
        "url": "https://kaveri.karnataka.gov.in",
        "provides": ("ec", "sale-deed", "title-deeds"),
        "search_by": "District, sub-registrar office and survey / property number for an EC; document number and year for a certified copy of a deed",
    },
    "bhoomi": {
        "name": "Bhoomi land records",
        "url": "https://landrecords.karnataka.gov.in",
        "provides": ("rtc", "mutation"),
        "search_by": "District, taluk, hobli, village and survey number with hissa",
    },
    "mojini": {
        "name": "Bhoomojini survey sketches",
        "url": "https://bhoomojini.karnataka.gov.in",
        "provides": ("survey-sketch",),
        "search_by": "District, taluk, hobli, village and survey number",
    },
    "bbmp": {
        "name": "BBMP e-Khata and property tax",
        "url": "https://bbmpeaasthi.karnataka.gov.in",
        "provides": ("khata", "tax-receipts"),
        "search_by": "BBMP PID / e-Khata number, or ward and owner name",
    },
    "eswathu": {
        "name": "e-Swathu (panchayat property records)",
        "url": "https://eswathu.karnataka.gov.in",
        "provides": ("eswathu",),
        "search_by": "District, taluk, gram panchayat, village and property / survey number",
    },
    "rera": {
        "name": "Karnataka RERA",
        "url": "https://rera.karnataka.gov.in",
        "provides": ("rera",),
        "search_by": "Project name or RERA registration number",
    },
}
# Public records the team fetches by default. Deeds can also come from Kaveri as certified copies, but the seller usually
# has them, so they start with the customer and the lawyer can switch them to Homexo.
FETCH_BY_DEFAULT = {"ec", "rtc", "mutation", "survey-sketch", "khata", "tax-receipts", "rera", "eswathu"}
TAG_SOURCES = {tag: key for key, source in SOURCES.items() for tag in source["provides"]}

# Automatic fetchers by source key: (ticket, item) -> (filename, content_type, bytes). None configured yet.
FETCHERS: dict[str, Callable] = {}

def source_for(tag: str) -> str | None:
    return TAG_SOURCES.get(tag)

def source_view(key: str | None) -> dict | None:
    if not key or key not in SOURCES:
        return None
    source = SOURCES[key]
    return {"key": key, "name": source["name"], "url": source["url"], "search_by": source["search_by"], "automatic": key in FETCHERS}
