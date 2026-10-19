"""Loads Karnataka RERA projects from a CSV or JSON export into rera_projects.

    python -m app.rera_import projects.csv            # add new projects, update existing ones by registration number
    python -m app.rera_import projects.json --replace # drop every project first, then load

Column names are matched loosely (case, spaces and punctuation are ignored, and common alternatives such as
"Promoter Name" / "Developer" or "Proposed Date of Completion" are understood); see COLUMNS. Rows without a
registration number, project name or promoter are skipped and counted. Loading real data removes the sample projects.
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import ReraProject

# Field -> header names seen in RERA exports, compared after lower-casing and dropping everything but letters and digits.
COLUMNS = {
    "registration_no": ("registrationno", "registrationnumber", "reraregistrationno", "reraregistrationnumber", "regno", "rerano", "projectregistrationno", "certificateno"),
    "name": ("name", "projectname", "nameoftheproject"),
    "promoter_name": ("promotername", "promoter", "developer", "developername", "builder", "buildername", "companyname"),
    "project_type": ("projecttype", "type", "typeofproject", "category"),
    "status": ("status", "projectstatus", "registrationstatus"),
    "district": ("district", "projectdistrict"),
    "taluk": ("taluk", "tehsil"),
    "locality": ("locality", "area", "village", "location", "projectlocation", "hobli"),
    "address": ("address", "projectaddress", "siteaddress"),
    "pincode": ("pincode", "pin", "postalcode"),
    "registered_on": ("registeredon", "registrationdate", "dateofregistration", "approvedon"),
    "registration_valid_until": ("validuntil", "registrationvalidupto", "validupto", "validtill", "expirydate", "registrationexpiry"),
    "proposed_completion": ("proposedcompletion", "proposedcompletiondate", "proposeddateofcompletion", "completiondate", "originalcompletiondate"),
    "revised_completion": ("revisedcompletion", "revisedcompletiondate", "extendedcompletiondate", "revisedproposeddateofcompletion"),
    "completed_on": ("completedon", "actualcompletiondate", "occupancycertificatedate", "ocdate"),
    "extensions": ("extensions", "noofextensions", "extensioncount", "numberofextensions"),
    "total_units": ("totalunits", "noofunits", "numberofunits", "totalapartments", "totalplots", "units"),
    "booked_units": ("bookedunits", "unitsbooked", "noofbookedunits", "soldunits", "unitssold", "bookings"),
    "unit_mix": ("unitmix", "unittypes"),
    "land_area_sqm": ("landareasqm", "landarea", "totallandarea", "plotarea"),
    "price_per_sqft": ("pricepersqft", "ratepersqft", "avgpricepersqft", "price"),
    "complaints": ("complaints", "noofcomplaints", "complaintcount", "numberofcomplaints"),
    "source_url": ("sourceurl", "url", "link", "projecturl", "detailsurl"),
}
REQUIRED = ("registration_no", "name", "promoter_name")
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d", "%m/%Y")

def slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:120].strip("-") or "x"

def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())

def _field_for(header: str) -> str | None:
    key = _key(header)
    for field, names in COLUMNS.items():
        if key == _key(field) or key in names:
            return field
    return None

def _text(value) -> str | None:
    value = " ".join(str(value).split()) if value is not None else ""
    return value or None

def _date(value) -> date | None:
    value = _text(value)
    if not value:
        return None
    value = value.split("T")[0].split(" 00:00")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {value!r}")

def _int(value) -> int | None:
    value = _text(value)
    if not value:
        return None
    try:
        return int(Decimal(value.replace(",", "")))
    except InvalidOperation:
        raise ValueError(f"not a number: {value!r}") from None

def _status(value) -> str:
    v = (_text(value) or "").lower()
    for word, status in (("revok", "revoked"), ("laps", "lapsed"), ("expir", "lapsed"), ("withdr", "withdrawn"), ("complet", "completed"), ("oc ", "completed")):
        if word in v:
            return status
    return "ongoing"

def _type(value) -> str:
    v = (_text(value) or "").lower()
    for word, kind in (("mix", "mixed"), ("plot", "plotted"), ("villa", "villa"), ("row", "villa"), ("commerc", "commercial"), ("office", "commercial")):
        if word in v:
            return kind
    return "residential"

def _unit_mix(value) -> dict:
    """Accepts {"2 BHK": 120} or text like "1BHK:20; 2 BHK - 80"."""
    if isinstance(value, dict):
        return {str(k): int(v) for k, v in value.items() if str(v).strip().isdigit()}
    text = _text(value)
    if not text:
        return {}
    if text.startswith("{"):
        return _unit_mix(json.loads(text))
    mix = {}
    for part in re.split(r"[;,|]", text):
        m = re.match(r"\s*(.+?)\s*[:=\-]\s*(\d+)\s*$", part)
        if m:
            mix[re.sub(r"(\d)\s*(bhk)", r"\1 BHK", m.group(1), flags=re.I)] = int(m.group(2))
    return mix

def normalise(raw: dict) -> dict:
    """One export row (any supported headers) as ReraProject fields. Raises ValueError for a row that can't be used."""
    row = {}
    for header, value in raw.items():
        field = _field_for(str(header))
        if field and field not in row:
            row[field] = value
    missing = [f for f in REQUIRED if not _text(row.get(f))]
    if missing:
        raise ValueError(f"missing {', '.join(missing)}")
    reg = _text(row["registration_no"])
    locality = _text(row.get("locality")) or _text(row.get("taluk")) or _text(row.get("district")) or "Unknown"
    promoter = _text(row["promoter_name"])
    area = _text(row.get("land_area_sqm"))
    out = {
        "registration_no": reg,
        "slug": slugify(reg),
        "name": _text(row["name"]),
        "promoter_name": promoter,
        "promoter_slug": slugify(promoter),
        "project_type": _type(row.get("project_type")),
        "status": _status(row.get("status")),
        "district": _text(row.get("district")) or "Unknown",
        "taluk": _text(row.get("taluk")),
        "locality": locality,
        "locality_slug": slugify(locality),
        "address": _text(row.get("address")),
        "pincode": _text(row.get("pincode")),
        "registered_on": _date(row.get("registered_on")),
        "registration_valid_until": _date(row.get("registration_valid_until")),
        "proposed_completion": _date(row.get("proposed_completion")),
        "revised_completion": _date(row.get("revised_completion")),
        "completed_on": _date(row.get("completed_on")),
        "extensions": _int(row.get("extensions")) or 0,
        "total_units": _int(row.get("total_units")),
        "booked_units": _int(row.get("booked_units")),
        "unit_mix": _unit_mix(row.get("unit_mix")),
        "land_area_sqm": Decimal(area.replace(",", "")) if area else None,
        "price_per_sqft": _int(row.get("price_per_sqft")),
        "complaints": _int(row.get("complaints")) or 0,
        "source_url": _text(row.get("source_url")),
    }
    if out["revised_completion"] and out["revised_completion"] == out["proposed_completion"]:
        out["revised_completion"] = None
    if out["completed_on"] and out["status"] == "ongoing":
        out["status"] = "completed"
    return out

def load(db: Session, rows: list[dict], *, sample: bool = False, replace: bool = False) -> dict:
    """Upserts rows by registration number. Real data clears out sample projects; sample data never touches real rows."""
    if replace:
        db.execute(delete(ReraProject))
    elif not sample:
        db.execute(delete(ReraProject).where(ReraProject.is_sample.is_(True)))
    existing = {p.registration_no: p for p in db.scalars(select(ReraProject)).all()}
    added = updated = 0
    skipped: list[str] = []
    seen_slugs = {p.slug: p.registration_no for p in existing.values()}
    for n, raw in enumerate(rows, start=1):
        try:
            fields = normalise(raw)
        except ValueError as exc:
            skipped.append(f"row {n}: {exc}")
            continue
        project = existing.get(fields["registration_no"])
        if project is None:
            if seen_slugs.get(fields["slug"]) not in (None, fields["registration_no"]):
                fields["slug"] = f"{fields['slug']}-{n}"
            project = ReraProject(registration_no=fields["registration_no"])
            db.add(project)
            existing[project.registration_no] = project
            added += 1
        else:
            fields.pop("slug")  # keep the project's address stable
            updated += 1
        for field, value in fields.items():
            setattr(project, field, value)
        project.is_sample = sample
        seen_slugs[project.slug] = project.registration_no
    db.commit()
    return {"added": added, "updated": updated, "skipped": skipped}

def read_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["projects"] if isinstance(data, dict) else data
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("path", type=Path, help="CSV, JSON (a list of objects) or JSON Lines file")
    parser.add_argument("--replace", action="store_true", help="delete every project before loading")
    args = parser.parse_args(argv)
    with SessionLocal() as db:
        result = load(db, read_rows(args.path), replace=args.replace)
    print(f"Added {result['added']}, updated {result['updated']}, skipped {len(result['skipped'])}.")
    for line in result["skipped"][:20]:
        print(f"  skipped {line}", file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
