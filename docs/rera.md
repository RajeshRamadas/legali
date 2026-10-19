# Karnataka RERA project check

Public pages for home buyers, built from Karnataka RERA registrations:

- `/rera`: search projects by name, RERA number, developer, locality or PIN code, with filters for locality, district, status, type and warning signs. Below the search, a market report: supply by completion year, warning signs across all projects, unit mix, localities (units, share booked, median price per sq ft, share running late) and developers (on-time delivery, complaints, record).
- `/rera/projects/<registration-number-slug>`: one project's warning signs, timeline (registered, promised, revised, valid until, completed), units booked, the developer's record and the locality's market.
- `/rera/developers/<slug>`: a developer's delivery record and projects.
- `/rera/localities/<slug>`: a locality's market, upcoming supply, developers and projects.

The pages render on the server and refresh every five minutes. The API is `GET /api/v1/rera/{summary,filters,projects,projects/{slug},developers/{slug},localities/{slug}}` (`backend/app/rera.py`).

## Loading data

```bash
cd backend
python -m app.rera_import path/to/projects.csv            # add or update by registration number
python -m app.rera_import path/to/projects.json --replace # wipe the table first
```

CSV, JSON (a list of objects, or `{"projects": [...]}`) and JSON Lines are accepted. Column names are matched loosely, so exports with headers such as `RERA Registration No.`, `Promoter Name`, `Proposed Date of Completion` or `Units Sold` work as they are; the full list is `COLUMNS` in `backend/app/rera_import.py`. Only registration number, project name and promoter are required. Dates can be `2027-03-31`, `31/03/2027`, `31-Mar-2027` and similar. Rows that can't be read are skipped and listed.

| Field | Used for |
|---|---|
| registration_no, name, promoter_name | Required. The URL is made from the registration number. |
| status | Ongoing, completed, lapsed, revoked or withdrawn (matched from words like "Under construction", "Revoked", "OC received"). |
| district, taluk, locality, address, pincode | Locality pages and search. Locality falls back to taluk, then district. |
| registered_on, registration_valid_until | Launches by year; lapsed registration warning. |
| proposed_completion, revised_completion, completed_on, extensions | Delay, on-time delivery, extension warning. |
| total_units, booked_units, unit_mix | Share booked, slow-sales warning, unit mix. `unit_mix` is JSON or text like `2BHK: 80; 3BHK: 40`. |
| price_per_sqft, land_area_sqm | Locality prices. |
| complaints | Complaint warnings and developer record. |
| source_url | "View on the RERA portal" link. |

## Sample data

Until real data is loaded, the API fills an empty table with 150 made-up projects on startup (`backend/app/rera_sample.py`; every developer is "Sample Developer …" and every registration number contains SAMPLE). The pages show a sample-data notice while only those rows exist. Importing real data deletes them. Set `RERA_SAMPLE_WHEN_EMPTY=false` in production.

## Warning signs

Worked out in `assess()` in `backend/app/rera.py` from the RERA record alone:

- **High risk**: registration revoked; registration lapsed (or past its validity while under construction); 12 or more months past the completion date first promised; 5 or more complaints.
- **Check before you buy**: withdrawn; up to 12 months late; handed over more than 3 months late; deadline extended 2 or more times; 1 to 4 complaints; under 40% of units booked within 12 months of the deadline.

A developer's record is *strong* (75%+ of completed projects handed over within 3 months of the promised date, few complaints), *mixed*, *weak* (any lapsed or revoked project, under 40% on time, or many complaints) or *too new to judge* (fewer than 2 completed projects). These are prompts to look further, not legal opinions, and the pages say so.
