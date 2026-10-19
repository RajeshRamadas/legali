"""Service catalogue. Synced into the service_types table at startup; the website and app read it from the API."""

ALL_PROPERTY_TYPES = [
    "apartment", "villa", "independent_house", "residential_plot", "agricultural_land", "farmhouse", "plantation_estate",
    "industrial_land", "commercial", "other",
]
BUILT_PROPERTY_TYPES = ["apartment", "villa", "independent_house", "farmhouse", "commercial", "other"]
LAND_PROPERTY_TYPES = ["residential_plot", "agricultural_land", "farmhouse", "plantation_estate", "industrial_land", "commercial", "other"]

# Mirrors the "Service needed" options on the website callback form.
SERVICES = [
    {
        "slug": "title-verification",
        "name": "Title Verification",
        "category": "Buyers",
        "description": "Title deed chain, Mother Deed, Encumbrance Certificate, RERA and basic litigation checks with a Go / No-Go verdict.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "legal-due-diligence",
        "name": "Full Legal Due Diligence",
        "category": "Buyers",
        "description": "30-year title history, BBMP / BDA / BMRDA approvals, acquisition notices and SRO field verification.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "sale-agreement-deed",
        "name": "Sale Agreement / Sale Deed",
        "category": "Buyers",
        "description": "Buyer-protective sale agreement and sale deed drafting or vetting with the responsible advocate.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "property-registration",
        "name": "Property Registration",
        "category": "Buyers",
        "description": "Readiness checklist, deed and SRO appointment coordination and registration-day support.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "khata-tax-bescom-transfer",
        "name": "Khata / Tax / BESCOM Transfer",
        "category": "Post-purchase",
        "description": "Khata transfer, property-tax name change and BESCOM name transfer after registration.",
        "property_types": BUILT_PROPERTY_TYPES + ["residential_plot"],
    },
    {
        "slug": "developer-land-screening",
        "name": "Developer Land Screening",
        "category": "Developers",
        "description": "Initial title, encumbrance, land-classification and survey checks before committing to a parcel.",
        "property_types": LAND_PROPERTY_TYPES,
    },
    {
        "slug": "acquisition-due-diligence",
        "name": "Acquisition Due Diligence",
        "category": "Developers",
        "description": "Title-chain reconstruction, revenue and EC reconciliation, litigation and development-rights review.",
        "property_types": LAND_PROPERTY_TYPES,
    },
    {
        "slug": "bulk-registration-operations",
        "name": "Bulk Registration Operations",
        "category": "Developers",
        "description": "Unit-level readiness, buyer document coordination, SRO appointments and registration tracking for projects.",
        "property_types": ["apartment", "villa", "independent_house", "residential_plot", "commercial"],
    },
    {
        "slug": "mutation-records-management",
        "name": "Mutation & Records Management",
        "category": "Developers",
        "description": "Mutation follow-up, Khata and property-tax updates and utility transfers after sale.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "document-retrieval-courier",
        "name": "Government Document Retrieval & Courier",
        "category": "Documents",
        "description": "We confirm the issuing authority and requirements, coordinate the request and courier physical documents.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "certified-copy-ec",
        "name": "Certified Copy / Encumbrance Certificate",
        "category": "Documents",
        "description": "Encumbrance Certificate, registered deed copies and eligible certified-copy requests.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "rtc-mutation-survey-records",
        "name": "RTC / Mutation / Survey Records",
        "category": "Documents",
        "description": "RTC / Pahani, Mutation Register extracts, mutation orders and eligible survey records.",
        "property_types": LAND_PROPERTY_TYPES,
    },
    {
        "slug": "khata-property-tax-documents",
        "name": "Khata / Property Tax Documents",
        "category": "Documents",
        "description": "Khata / e-Khata guidance, property-tax records and application follow-up.",
        "property_types": BUILT_PROPERTY_TYPES + ["residential_plot"],
    },
    {
        "slug": "deed-drafting-registration",
        "name": "Deed Drafting / Registration Support",
        "category": "Documents",
        "description": "POA, Gift Deed, Will and other property-deed drafting, vetting and registration support.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "affidavit-drafting",
        "name": "Affidavit Drafting & Notarisation",
        "category": "Documents",
        "description": "Name change, address proof, gap, loss and other affidavits drafted by an advocate on stamp paper, with notarisation arranged.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "advocate-consultation",
        "name": "Advocate Consultation",
        "category": "Consultation",
        "description": "A 30-minute video consultation with a senior property advocate, with a written summary.",
        "property_types": ALL_PROPERTY_TYPES,
    },
    {
        "slug": "general-guidance",
        "name": "Not sure — need guidance",
        "category": "Consultation",
        "description": "Tell us about the property and a specialist will suggest the right service.",
        "property_types": ALL_PROPERTY_TYPES,
    },
]
SERVICES_BY_SLUG = {service["slug"]: service for service in SERVICES}
