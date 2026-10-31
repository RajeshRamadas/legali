"""Curated screening principles, not a live or exhaustive legal database.

Reference links lead to the official legislation search. Applicability, amendments,
state rules and case law must be checked by the signing advocate.
"""
from urllib.parse import quote

LAW_VERSION = "2026-10-31.1"

def law(key, act, sections, principle):
    return {"id": key, "act": act, "sections": sections, "principle": principle,
            "url": "https://www.indiacode.nic.in/simple-search?query=" + quote(act)}

LAWS = [
    law("tpa-sale", "Transfer of Property Act, 1882", "Sections 7, 8, 54 and 55",
        "Check the transferor's entitlement and authority, the conveyance and the seller's disclosures. A contract for sale alone does not create an interest in the property; section 54 prescribes registration for sales within its scope."),
    law("registration", "Registration Act, 1908", "Sections 17, 21 and 49",
        "Check compulsory registration where applicable, sufficient property description, and the consequences of non-registration, subject to statutory exceptions. A registration number in an uploaded copy is not independent registration verification."),
    law("stamp", "Indian Stamp Act, 1899", "Sections 3 and 35; applicable state stamp legislation",
        "Check chargeability and admissibility under the applicable stamp law. Rates and procedure vary by state; Karnataka uses the Karnataka Stamp Act, 1957. Do not infer duty payment from a document label."),
    law("litigation", "Transfer of Property Act, 1882", "Sections 52 and 58",
        "Investigate pending suits affecting the property and mortgages. A current EC alone does not establish absence of all claims, litigation or unregistered interests."),
    law("rera", "Real Estate (Regulation and Development) Act, 2016", "Sections 3, 4, 11 and 13",
        "For projects within scope, check registration, promoter disclosures and obligations, and the agreement before taking more than ten percent advance. Section 3 exemptions and state rules must be assessed; RERA is not universally required for every resale."),
    law("karnataka-land", "Karnataka Land Revenue Act, 1964", "Section 95; applicable amendments and exceptions",
        "Where relevant, check lawful diversion of agricultural land to the proposed use and conversion records. Revenue entries and tax receipts alone do not establish title."),
    law("karnataka-grant", "Karnataka Scheduled Castes and Scheduled Tribes (Prohibition of Transfer of Certain Lands) Act, 1978", "Sections 4 and 5",
        "For qualifying granted land, investigate grant conditions, prohibited transfers and restoration risk, with current amendments and judicial interpretation. Applicability needs the grant history, not assumptions from the current owner."),
]
BY_ID = {row["id"]: row for row in LAWS}
