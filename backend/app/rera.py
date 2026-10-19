"""Karnataka RERA project check for home buyers: look up a registered project, see the developer's delivery record
and the locality's market, with plain-language warning signs. Read-only and public; the rows come from
app.rera_import (or app.rera_sample until real data is loaded).

The warning signs are worked out from the RERA record alone (dates, extensions, complaints, units booked). They are a
prompt to check further, not a legal opinion, and the pages say so.
"""
from collections import Counter, defaultdict
from datetime import date, datetime
from statistics import median
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import config
from .db import get_db
from .models import ReraProject

router = APIRouter(prefix="/api/v1/rera")

STATUS_LABELS = {
    "ongoing": "Under construction", "completed": "Completed", "lapsed": "Registration lapsed",
    "revoked": "Registration revoked", "withdrawn": "Withdrawn",
}
TYPE_LABELS = {"residential": "Apartments", "villa": "Villas", "plotted": "Plots", "commercial": "Commercial", "mixed": "Mixed use"}
RISK_LEVELS = ("green", "amber", "red")
RISK_LABELS = {"green": "No warning signs", "amber": "Check before you buy", "red": "High risk"}
# A project handed over within this many months of the date first promised counts as on time.
ON_TIME_GRACE_MONTHS = 3
# Ongoing projects this close to their deadline with fewer units booked than this get a slow-sales warning.
SLOW_SALES_MONTHS, SLOW_SALES_SHARE = 12, 0.4

def today() -> date:
    return datetime.now(ZoneInfo(config.MEETING_TIMEZONE)).date()

def months_between(start: date, end: date) -> int:
    return round((end - start).days / 30.44)

def deadline(p: ReraProject) -> date | None:
    return p.revised_completion or p.proposed_completion

def delay_months(p: ReraProject, on: date) -> int | None:
    """Months past the completion date first promised: to handover for completed projects, to today for the rest."""
    if p.proposed_completion is None:
        return None
    end = p.completed_on if p.status == "completed" else on
    if end is None:
        return None
    return max(0, months_between(p.proposed_completion, end))

def booked_share(p: ReraProject) -> float | None:
    if not p.total_units or p.booked_units is None:
        return None
    return min(1.0, p.booked_units / p.total_units)

def _pct(value: float | None) -> int | None:
    return None if value is None else round(value * 100)

def _fmt(d: date | None) -> str:
    return f"{d.day} {d:%b %Y}" if d else "not given"

def assess(p: ReraProject, on: date) -> dict:
    """Warning signs for a buyer, worst first, plus the good signs. Level is the worst sign's level."""
    flags: list[dict] = []
    good: list[str] = []
    late = delay_months(p, on)
    share = booked_share(p)
    due = deadline(p)

    def flag(level: str, title: str, detail: str) -> None:
        flags.append({"level": level, "title": title, "detail": detail})

    if p.status == "revoked":
        flag("red", "Registration revoked", "RERA has revoked this project's registration. The promoter can't sell units in it, and buyers usually have to pursue a refund or completion through RERA.")
    lapsed = p.status == "lapsed" or (p.status == "ongoing" and p.registration_valid_until and p.registration_valid_until < on)
    if lapsed:
        flag("red", "Registration has lapsed", f"The registration was valid until {_fmt(p.registration_valid_until)} and has not been renewed on record. Units shouldn't be sold until it is extended.")
    if p.status == "withdrawn":
        flag("amber", "Project withdrawn", "The promoter withdrew this registration. Confirm with the promoter and RERA whether the project is still going ahead.")
    if p.status in ("ongoing", "lapsed") and late:
        if late >= 12:
            flag("red", f"Running {late} months late", f"Completion was first promised for {_fmt(p.proposed_completion)}{f' and is now due {_fmt(p.revised_completion)}' if p.revised_completion else ''}.")
        else:
            flag("amber", "Past its promised completion date", f"Completion was promised for {_fmt(p.proposed_completion)}, {late} month{'s' if late != 1 else ''} ago.")
    if p.status == "completed" and late is not None and late > ON_TIME_GRACE_MONTHS:
        flag("amber", f"Handed over {late} months late", f"Promised for {_fmt(p.proposed_completion)}, completed {_fmt(p.completed_on)}.")
    if p.extensions >= 2:
        flag("amber", f"Deadline extended {p.extensions} times", "Repeated extensions often mean funding or approval trouble. Ask the promoter why, and check the latest construction update on the RERA portal.")
    if p.complaints >= 5:
        flag("red", f"{p.complaints} complaints with RERA", "Buyers have filed several complaints against this project. Read the orders on the RERA portal before paying anything.")
    elif p.complaints:
        flag("amber", f"{p.complaints} complaint{'s' if p.complaints > 1 else ''} with RERA", "Read the complaint and any order on the RERA portal to see what it was about.")
    if p.status == "ongoing" and share is not None and share < SLOW_SALES_SHARE and due and months_between(on, due) <= SLOW_SALES_MONTHS:
        flag("amber", "Slow sales close to the deadline", f"Only {_pct(share)}% of units are booked with completion due {_fmt(due)}. Slow sales can leave a promoter short of money to finish.")

    if p.status == "completed" and late is not None and late <= ON_TIME_GRACE_MONTHS:
        good.append("Handed over on time")
    if p.status == "ongoing" and late == 0 and not lapsed:
        good.append(f"On schedule for {_fmt(due)}")
    if not p.complaints:
        good.append("No complaints on record")
    if share is not None and share >= 0.75 and p.status == "ongoing":
        good.append(f"{_pct(share)}% of units already booked")
    if p.status in ("ongoing", "completed") and p.extensions == 0 and p.proposed_completion:
        good.append("No deadline extensions")

    order = {"red": 0, "amber": 1}
    flags.sort(key=lambda f: order[f["level"]])
    level = flags[0]["level"] if flags else "green"
    return {"level": level, "label": RISK_LABELS[level], "flags": flags, "good": good}

# ---- Views ----

def card(p: ReraProject, on: date, risk: dict | None = None) -> dict:
    risk = risk or assess(p, on)
    return {
        "registration_no": p.registration_no,
        "slug": p.slug,
        "name": p.name,
        "promoter": {"name": p.promoter_name, "slug": p.promoter_slug},
        "locality": {"name": p.locality, "slug": p.locality_slug},
        "district": p.district,
        "project_type": p.project_type,
        "type_label": TYPE_LABELS.get(p.project_type, p.project_type.title()),
        "status": p.status,
        "status_label": STATUS_LABELS[p.status],
        "deadline": deadline(p).isoformat() if deadline(p) else None,
        "completed_on": p.completed_on.isoformat() if p.completed_on else None,
        "total_units": p.total_units,
        "booked_units": p.booked_units,
        "booked_pct": _pct(booked_share(p)),
        "price_per_sqft": p.price_per_sqft,
        "delay_months": delay_months(p, on),
        "risk": {"level": risk["level"], "label": risk["label"], "headline": risk["flags"][0]["title"] if risk["flags"] else None},
        "sample": p.is_sample,
    }

def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None

def detail(p: ReraProject, on: date) -> dict:
    risk = assess(p, on)
    return {
        **card(p, on, risk),
        "taluk": p.taluk,
        "address": p.address,
        "pincode": p.pincode,
        "registered_on": _iso(p.registered_on),
        "registration_valid_until": _iso(p.registration_valid_until),
        "proposed_completion": _iso(p.proposed_completion),
        "revised_completion": _iso(p.revised_completion),
        "extensions": p.extensions,
        "unit_mix": [{"type": k, "units": v} for k, v in p.unit_mix.items()],
        "land_area_sqm": float(p.land_area_sqm) if p.land_area_sqm is not None else None,
        "complaints": p.complaints,
        "source_url": p.source_url,
        "risk": risk,
    }

def track_record(projects: list[ReraProject], on: date) -> dict:
    """How a developer (or any group of projects) has delivered."""
    completed = [p for p in projects if p.status == "completed"]
    timed = [d for d in (delay_months(p, on) for p in completed) if d is not None]
    on_time = sum(1 for d in timed if d <= ON_TIME_GRACE_MONTHS)
    ongoing = [p for p in projects if p.status == "ongoing"]
    running_late = sum(1 for p in ongoing if delay_months(p, on))
    troubled = sum(1 for p in projects if p.status in ("lapsed", "revoked"))
    complaints = sum(p.complaints for p in projects)
    on_time_pct = _pct(on_time / len(timed)) if timed else None
    if troubled or (on_time_pct is not None and len(timed) >= 2 and on_time_pct < 40) or complaints >= 3 * max(1, len(projects)):
        verdict = "weak"
    elif len(timed) < 2:
        verdict = "new"
    elif on_time_pct >= 75 and complaints <= len(projects):
        verdict = "strong"
    else:
        verdict = "mixed"
    return {
        "projects": len(projects),
        "ongoing": len(ongoing),
        "completed": len(completed),
        "lapsed_or_revoked": troubled,
        "units": sum(p.total_units or 0 for p in projects),
        "on_time_pct": on_time_pct,
        "avg_delay_months": round(sum(timed) / len(timed), 1) if timed else None,
        "running_late": running_late,
        "complaints": complaints,
        "verdict": verdict,
        "verdict_label": {"strong": "Strong delivery record", "mixed": "Mixed delivery record", "weak": "Weak delivery record", "new": "Too few completed projects to judge"}[verdict],
    }

def market(projects: list[ReraProject], on: date) -> dict:
    """Supply, sales and price figures for a set of projects (a locality, a district or the whole state)."""
    live = [p for p in projects if p.status in ("ongoing", "completed")]
    units = sum(p.total_units or 0 for p in live if p.booked_units is not None)
    booked = sum(p.booked_units or 0 for p in live if p.total_units)
    prices = [p.price_per_sqft for p in live if p.price_per_sqft]
    ongoing = [p for p in projects if p.status == "ongoing"]
    late = [p for p in ongoing if delay_months(p, on)]
    return {
        "projects": len(projects),
        "ongoing": len(ongoing),
        "units": sum(p.total_units or 0 for p in projects),
        "booked_pct": _pct(booked / units) if units else None,
        "median_price_per_sqft": round(median(prices)) if prices else None,
        "price_range": [min(prices), max(prices)] if prices else None,
        "late_pct": _pct(len(late) / len(ongoing)) if ongoing else None,
    }

def supply_by_year(projects: list[ReraProject], on: date, years: int = 5) -> list[dict]:
    """Units in ongoing projects by the year they're due, with anything already overdue in its own bucket."""
    buckets: dict[str, dict] = {"Overdue": {"label": "Overdue", "projects": 0, "units": 0}}
    for y in range(on.year, on.year + years):
        buckets[str(y)] = {"label": str(y), "projects": 0, "units": 0}
    last = f"{on.year + years - 1}"
    for p in projects:
        due = deadline(p)
        if p.status != "ongoing" or due is None:
            continue
        key = "Overdue" if due < on else (str(due.year) if due.year < on.year + years else last)
        buckets[key]["projects"] += 1
        buckets[key]["units"] += p.total_units or 0
    out = list(buckets.values())
    out[-1]["label"] = f"{last}+"
    return out

def launches_by_year(projects: list[ReraProject], on: date, years: int = 8) -> list[dict]:
    first = on.year - years + 1
    counts = {y: {"year": y, "projects": 0, "units": 0} for y in range(first, on.year + 1)}
    for p in projects:
        if p.registered_on and p.registered_on.year >= first and p.registered_on.year in counts:
            counts[p.registered_on.year]["projects"] += 1
            counts[p.registered_on.year]["units"] += p.total_units or 0
    return list(counts.values())

def unit_mix(projects: list[ReraProject]) -> list[dict]:
    totals: Counter = Counter()
    for p in projects:
        totals.update({k: v for k, v in p.unit_mix.items() if isinstance(v, int)})
    return [{"type": k, "units": v} for k, v in sorted(totals.items(), key=lambda kv: -kv[1])]

def _data_info(db: Session) -> dict:
    count, sample, updated = db.execute(select(func.count(), func.count().filter(ReraProject.is_sample.is_(True)), func.max(ReraProject.updated_at))).one()
    return {"projects": count, "sample": bool(count) and sample == count, "updated_at": updated.isoformat() if updated else None}

def _all(db: Session, *where) -> list[ReraProject]:
    return list(db.scalars(select(ReraProject).where(*where)).all())

def _group(projects: list[ReraProject], key) -> dict[str, list[ReraProject]]:
    groups: dict[str, list[ReraProject]] = defaultdict(list)
    for p in projects:
        groups[key(p)].append(p)
    return groups

# ---- Public API ----

@router.get("/summary")
def summary(district: str | None = Query(None, max_length=80), db: Session = Depends(get_db)):
    on = today()
    projects = _all(db, *([func.lower(ReraProject.district) == district.lower()] if district else []))
    risks = Counter(assess(p, on)["level"] for p in projects)
    statuses = Counter(p.status for p in projects)
    completed = [p for p in projects if p.status == "completed"]
    by_locality = _group(projects, lambda p: p.locality_slug)
    by_promoter = _group(projects, lambda p: p.promoter_slug)
    localities = [{"name": ps[0].locality, "slug": slug, "district": ps[0].district, **market(ps, on)} for slug, ps in by_locality.items()]
    localities.sort(key=lambda l: (-l["units"], l["name"]))
    developers = [{"name": ps[0].promoter_name, "slug": slug, **track_record(ps, on)} for slug, ps in by_promoter.items()]
    developers.sort(key=lambda d: (-d["projects"], -(d["on_time_pct"] or 0), d["name"]))
    return {
        "data": _data_info(db),
        "district": district,
        "as_of": on.isoformat(),
        "market": market(projects, on),
        "delivery": track_record(completed, on),
        "statuses": [{"status": s, "label": STATUS_LABELS[s], "projects": statuses.get(s, 0)} for s in STATUS_LABELS],
        "risk": [{"level": r, "label": RISK_LABELS[r], "projects": risks.get(r, 0)} for r in RISK_LEVELS],
        "supply_by_year": supply_by_year(projects, on),
        "launches_by_year": launches_by_year(projects, on),
        "unit_mix": unit_mix([p for p in projects if p.status == "ongoing"]),
        "localities": localities[:15],
        "developers": developers[:12],
    }

@router.get("/filters")
def filters(db: Session = Depends(get_db)):
    rows = db.execute(select(ReraProject.district, ReraProject.locality, ReraProject.locality_slug, func.count()).group_by(ReraProject.district, ReraProject.locality, ReraProject.locality_slug)).all()
    districts = Counter()
    for district, _, _, n in rows:
        districts[district] += n
    types = db.execute(select(ReraProject.project_type, func.count()).group_by(ReraProject.project_type)).all()
    return {
        "districts": [{"name": d, "projects": n} for d, n in sorted(districts.items())],
        "localities": sorted(({"name": l, "slug": s, "district": d, "projects": n} for d, l, s, n in rows), key=lambda x: x["name"]),
        "statuses": [{"value": k, "label": v} for k, v in STATUS_LABELS.items()],
        "types": [{"value": t, "label": TYPE_LABELS.get(t, t.title()), "projects": n} for t, n in sorted(types)],
        "risk": [{"value": k, "label": v} for k, v in RISK_LABELS.items()],
    }

ProjectSort = Literal["name", "deadline", "newest", "units", "risk", "price_low"]

@router.get("/projects")
def search_projects(
    q: str | None = Query(None, max_length=120, description="Project name, registration number, developer, locality or PIN code."),
    district: str | None = Query(None, max_length=80),
    locality: str | None = Query(None, max_length=120, description="Locality slug."),
    promoter: str | None = Query(None, max_length=160, description="Developer slug."),
    status: Literal[tuple(STATUS_LABELS)] | None = None,  # type: ignore[valid-type]
    type: str | None = Query(None, max_length=40),
    risk: Literal[RISK_LEVELS] | None = None,  # type: ignore[valid-type]
    sort: ProjectSort = "name",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=60),
    db: Session = Depends(get_db),
):
    on = today()
    where = []
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        where.append(or_(*(func.lower(c).like(like) for c in (ReraProject.name, ReraProject.registration_no, ReraProject.promoter_name, ReraProject.locality, ReraProject.pincode))))
    if district:
        where.append(func.lower(ReraProject.district) == district.lower())
    if locality:
        where.append(ReraProject.locality_slug == locality)
    if promoter:
        where.append(ReraProject.promoter_slug == promoter)
    if status:
        where.append(ReraProject.status == status)
    if type:
        where.append(ReraProject.project_type == type)
    rows = [(p, assess(p, on)) for p in _all(db, *where)]
    if risk:
        rows = [(p, r) for p, r in rows if r["level"] == risk]
    far = date.max
    keys = {
        "name": lambda pr: pr[0].name.lower(),
        "deadline": lambda pr: deadline(pr[0]) or far,
        "newest": lambda pr: -(pr[0].registered_on or date.min).toordinal(),
        "units": lambda pr: -(pr[0].total_units or 0),
        "risk": lambda pr: (-RISK_LEVELS.index(pr[1]["level"]), -len(pr[1]["flags"])),
        "price_low": lambda pr: pr[0].price_per_sqft or 10**9,
    }
    rows.sort(key=lambda pr: (keys[sort](pr), pr[0].name.lower()))
    start = (page - 1) * page_size
    return {
        "items": [card(p, on, r) for p, r in rows[start:start + page_size]],
        "total": len(rows),
        "page": page,
        "page_size": page_size,
        "data": _data_info(db),
    }

@router.get("/projects/{slug}")
def get_project(slug: str, db: Session = Depends(get_db)):
    p = db.scalars(select(ReraProject).where(ReraProject.slug == slug)).first()
    if p is None:
        raise HTTPException(status_code=404, detail="We couldn't find that RERA project.")
    on = today()
    siblings = [x for x in _all(db, ReraProject.promoter_slug == p.promoter_slug)]
    neighbours = [x for x in _all(db, ReraProject.locality_slug == p.locality_slug)]
    return {
        **detail(p, on),
        "developer": {"name": p.promoter_name, "slug": p.promoter_slug, **track_record(siblings, on)},
        "locality_market": {"name": p.locality, "slug": p.locality_slug, **market(neighbours, on)},
        "developer_projects": [card(x, on) for x in sorted(siblings, key=lambda x: x.name) if x.id != p.id][:6],
        "nearby": [card(x, on) for x in sorted(neighbours, key=lambda x: x.name) if x.id != p.id and x.promoter_slug != p.promoter_slug][:6],
        "data": _data_info(db),
    }

@router.get("/developers/{slug}")
def get_developer(slug: str, db: Session = Depends(get_db)):
    projects = _all(db, ReraProject.promoter_slug == slug)
    if not projects:
        raise HTTPException(status_code=404, detail="We couldn't find that developer.")
    on = today()
    localities = Counter((p.locality, p.locality_slug) for p in projects)
    return {
        "name": projects[0].promoter_name,
        "slug": slug,
        "record": track_record(projects, on),
        "localities": [{"name": n, "slug": s, "projects": c} for (n, s), c in localities.most_common()],
        "projects": [card(p, on) for p in sorted(projects, key=lambda p: (p.status != "ongoing", -(p.registered_on or date.min).toordinal()))],
        "data": _data_info(db),
    }

@router.get("/localities/{slug}")
def get_locality(slug: str, db: Session = Depends(get_db)):
    projects = _all(db, ReraProject.locality_slug == slug)
    if not projects:
        raise HTTPException(status_code=404, detail="We couldn't find that locality.")
    on = today()
    developers = [{"name": ps[0].promoter_name, "slug": s, "projects": len(ps), **{k: v for k, v in track_record(ps, on).items() if k in ("on_time_pct", "verdict", "verdict_label")}}
                  for s, ps in _group(projects, lambda p: p.promoter_slug).items()]
    developers.sort(key=lambda d: (-d["projects"], d["name"]))
    risks = Counter(assess(p, on)["level"] for p in projects)
    return {
        "name": projects[0].locality,
        "slug": slug,
        "district": projects[0].district,
        "taluk": projects[0].taluk,
        "market": market(projects, on),
        "delivery": track_record([p for p in projects if p.status == "completed"], on),
        "risk": [{"level": r, "label": RISK_LABELS[r], "projects": risks.get(r, 0)} for r in RISK_LEVELS],
        "supply_by_year": supply_by_year(projects, on),
        "unit_mix": unit_mix([p for p in projects if p.status == "ongoing"]),
        "developers": developers,
        "projects": [card(p, on) for p in sorted(projects, key=lambda p: (p.status != "ongoing", p.name.lower()))],
        "data": _data_info(db),
    }
