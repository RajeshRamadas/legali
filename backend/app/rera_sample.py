"""Made-up Karnataka RERA projects so the RERA pages have something to show before real data is imported.

    python -m app.rera_sample

Every developer is called "Sample Developer …" and every registration number contains SAMPLE, so nothing can be
mistaken for a real project, and the website shows a sample-data notice while only these rows are loaded. Re-running
updates them in place. Importing real data with app.rera_import removes them.
"""
import random
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .db import SessionLocal
from .rera_import import load

# Locality, district, taluk, PIN code, typical price per sq ft.
LOCALITIES = [
    ("Whitefield", "Bengaluru Urban", "Bengaluru East", "560066", 8200),
    ("Sarjapur Road", "Bengaluru Urban", "Anekal", "562125", 7400),
    ("Electronic City", "Bengaluru Urban", "Anekal", "560100", 5900),
    ("Hebbal", "Bengaluru Urban", "Bengaluru North", "560024", 10500),
    ("Yelahanka", "Bengaluru Urban", "Yelahanka", "560064", 7100),
    ("Devanahalli", "Bengaluru Rural", "Devanahalli", "562110", 5400),
    ("Kanakapura Road", "Bengaluru Urban", "Bengaluru South", "560062", 7300),
    ("Bannerghatta Road", "Bengaluru Urban", "Bengaluru South", "560076", 7900),
    ("Hennur", "Bengaluru Urban", "Bengaluru East", "560043", 7600),
    ("Thanisandra", "Bengaluru Urban", "Bengaluru North", "560077", 7800),
    ("Varthur", "Bengaluru Urban", "Bengaluru East", "560087", 6900),
    ("Chandapura", "Bengaluru Urban", "Anekal", "560099", 4700),
    ("Rajajinagar", "Bengaluru Urban", "Bengaluru North", "560010", 14500),
    ("Vijayanagar, Mysuru", "Mysuru", "Mysuru", "570017", 5100),
    ("Kadri, Mangaluru", "Dakshina Kannada", "Mangaluru", "575002", 6400),
]
# Developer name suffix and how reliably they deliver (0 = always late, 1 = always on time).
DEVELOPERS = [
    ("Alpha", 0.9), ("Beta", 0.75), ("Gamma", 0.55), ("Delta", 0.3), ("Epsilon", 0.85), ("Zeta", 0.6), ("Eta", 0.15),
    ("Theta", 0.7), ("Iota", 0.95), ("Kappa", 0.45), ("Lambda", 0.65), ("Mu", 0.8), ("Nu", 0.25), ("Xi", 0.5),
]
FIRST = ("Maple", "Lotus", "Banyan", "Silver", "Emerald", "Cedar", "Amber", "Coral", "Jasmine", "Orchid", "Sandal", "Teak", "Mist", "Indigo", "Saffron")
SECOND = ("Court", "Heights", "Residency", "Meadows", "Enclave", "Gardens", "Towers", "Greens", "Park", "Vista", "Woods", "Square")
ANCHOR = date(2026, 10, 1)

def _months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, min(d.day, 28))

def rows(count: int = 150, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    names: set[str] = set()
    out = []
    for n in range(1, count + 1):
        dev, reliability = DEVELOPERS[(n - 1) % len(DEVELOPERS)]
        if rng.random() < 0.35:
            dev, reliability = rng.choice(DEVELOPERS)
        locality, district, taluk, pin, base_price = rng.choice(LOCALITIES)
        while (name := f"{rng.choice(FIRST)} {rng.choice(SECOND)}") in names:
            pass
        names.add(name)
        kind = rng.choices(["residential", "villa", "plotted", "mixed"], weights=[70, 10, 15, 5])[0]
        registered = ANCHOR - timedelta(days=rng.randint(60, 8 * 365))
        build_months = rng.randint(30, 60)
        proposed = _months(registered, build_months)
        total = rng.randint(40, 900) if kind != "villa" else rng.randint(20, 160)
        on_time = rng.random() < reliability
        delay = 0 if on_time else rng.randint(4, 30)
        extensions = 0 if on_time else rng.choice([1, 1, 2, 3])
        revised = _months(proposed, delay) if delay else None
        status, completed_on = "Ongoing", None
        finish = _months(proposed, delay)
        if finish <= ANCHOR and rng.random() < 0.85:
            status, completed_on = "Completed", finish - timedelta(days=rng.randint(0, 40))
        elif proposed < ANCHOR and not on_time and reliability < 0.35 and rng.random() < 0.25:
            status = rng.choice(["Lapsed", "Revoked"])
        age = max(0.05, min(1.0, (ANCHOR - registered).days / max(1, (finish - registered).days)))
        booked = total if status == "Completed" else round(total * min(1.0, age * rng.uniform(0.5, 1.15)))
        complaints = rng.choice([0, 1, 2, 3, 5, 8]) if not on_time else 0 if rng.random() < 0.85 else 1
        if kind == "plotted":
            mix = {"Plots": total}
        elif kind == "villa":
            mix = {"3 BHK villa": total // 2, "4 BHK villa": total - total // 2}
        else:
            two = round(total * rng.uniform(0.35, 0.6))
            three = round((total - two) * rng.uniform(0.5, 0.9))
            mix = {"1 BHK": max(0, total - two - three), "2 BHK": two, "3 BHK": three}
            mix = {k: v for k, v in mix.items() if v}
        price = round(base_price * rng.uniform(0.85, 1.25) * (0.55 if kind == "plotted" else 1) / 50) * 50
        out.append({
            "registration_no": f"PRM/KA/RERA/SAMPLE/{registered:%y%m%d}/{n:04d}",
            "name": name,
            "promoter_name": f"Sample Developer {dev}",
            "project_type": kind,
            "status": status,
            "district": district,
            "taluk": taluk,
            "locality": locality,
            "pincode": pin,
            "address": f"Survey no. {rng.randint(10, 299)}/{rng.randint(1, 9)}, {locality}",
            "registered_on": registered.isoformat(),
            "registration_valid_until": (revised or proposed).isoformat() if status != "Lapsed" else proposed.isoformat(),
            "proposed_completion": proposed.isoformat(),
            "revised_completion": revised.isoformat() if revised else "",
            "completed_on": completed_on.isoformat() if completed_on else "",
            "extensions": extensions,
            "total_units": total,
            "booked_units": booked,
            "unit_mix": mix,
            "land_area_sqm": round(total * rng.uniform(25, 60), 2),
            "price_per_sqft": price,
            "complaints": complaints,
        })
    return out

def load_sample(db: Session) -> dict:
    return load(db, rows(), sample=True)

if __name__ == "__main__":
    with SessionLocal() as session:
        result = load_sample(session)
    print(f"Sample RERA projects: added {result['added']}, updated {result['updated']}.")
