from datetime import date

from app import rera
from app.db import SessionLocal
from app.models import ReraProject
from app.rera_import import load, normalise
from app.rera_sample import load_sample

ON = date(2026, 10, 19)

def _project(**overrides) -> ReraProject:
    fields = {
        "registration_no": "PRM/KA/RERA/1251/446/PR/200101/000001", "slug": "x", "name": "Test Towers", "promoter_name": "Test Dev",
        "promoter_slug": "test-dev", "project_type": "residential", "status": "ongoing", "district": "Bengaluru Urban",
        "locality": "Hebbal", "locality_slug": "hebbal", "extensions": 0, "complaints": 0, "unit_mix": {},
        "registered_on": date(2023, 1, 1), "registration_valid_until": date(2027, 12, 31), "proposed_completion": date(2027, 12, 31),
        "total_units": 100, "booked_units": 60, "is_sample": False, **overrides,
    }
    return ReraProject(**fields)

def _levels(p: ReraProject) -> list[tuple[str, str]]:
    return [(f["level"], f["title"]) for f in rera.assess(p, ON)["flags"]]

def test_on_schedule_project_has_no_warning_signs():
    risk = rera.assess(_project(), ON)
    assert risk["level"] == "green" and risk["flags"] == []
    assert "On schedule for 31 Dec 2027" in risk["good"] and "No complaints on record" in risk["good"]

def test_warning_signs_are_worst_first():
    late = _project(proposed_completion=date(2025, 6, 30), revised_completion=date(2027, 3, 31), registration_valid_until=date(2027, 3, 31), extensions=2, complaints=1)
    assert _levels(late) == [("red", "Running 16 months late"), ("amber", "Deadline extended 2 times"), ("amber", "1 complaint with RERA")]

    lapsed = _project(proposed_completion=date(2026, 8, 1), registration_valid_until=date(2026, 8, 1))
    assert _levels(lapsed)[0] == ("red", "Registration has lapsed")
    assert ("amber", "Past its promised completion date") in _levels(lapsed)

    assert _levels(_project(status="revoked"))[0] == ("red", "Registration revoked")
    assert _levels(_project(complaints=6)) == [("red", "6 complaints with RERA")]

def test_slow_sales_only_matter_near_the_deadline():
    assert _levels(_project(booked_units=20, proposed_completion=date(2027, 6, 30))) == [("amber", "Slow sales close to the deadline")]
    assert _levels(_project(booked_units=20, proposed_completion=date(2029, 6, 30))) == []

def test_completed_projects_count_late_handover():
    on_time = _project(status="completed", proposed_completion=date(2024, 3, 31), completed_on=date(2024, 5, 15))
    assert rera.assess(on_time, ON)["level"] == "green" and "Handed over on time" in rera.assess(on_time, ON)["good"]
    late = _project(status="completed", proposed_completion=date(2024, 3, 31), completed_on=date(2025, 3, 31))
    assert _levels(late) == [("amber", "Handed over 12 months late")]

def test_developer_track_record():
    projects = [
        _project(status="completed", proposed_completion=date(2022, 1, 1), completed_on=date(2022, 1, 20)),
        _project(status="completed", proposed_completion=date(2023, 1, 1), completed_on=date(2023, 2, 1)),
        _project(status="completed", proposed_completion=date(2024, 1, 1), completed_on=date(2024, 12, 1)),
        _project(proposed_completion=date(2026, 1, 1)),
    ]
    record = rera.track_record(projects, ON)
    assert record["completed"] == 3 and record["on_time_pct"] == 67 and record["running_late"] == 1 and record["verdict"] == "mixed"
    assert rera.track_record(projects + [_project(status="revoked")], ON)["verdict"] == "weak"
    assert rera.track_record(projects[:1], ON)["verdict"] == "new"

def test_import_understands_common_export_headers():
    row = normalise({
        "RERA Registration No.": " PRM/KA/RERA/1251/309/PR/171015/000123 ", "Project Name": "Lake View", "Promoter Name": "Acme Estates Pvt Ltd",
        "Project Type": "Plotted Development", "Project Status": "Under Construction", "District": "Bengaluru Urban", "Village": "Jakkur",
        "Date of Registration": "15/10/2017", "Proposed Date of Completion": "31-Dec-2021", "Revised Completion Date": "2023-06-30",
        "No. of Units": "1,200", "Units Sold": "900", "Unit Mix": "2BHK: 800; 3 BHK - 400", "No. of Complaints": "2", "Unknown column": "ignored",
    })
    assert row["registration_no"] == "PRM/KA/RERA/1251/309/PR/171015/000123" and row["slug"] == "prm-ka-rera-1251-309-pr-171015-000123"
    assert row["promoter_slug"] == "acme-estates-pvt-ltd" and row["locality"] == "Jakkur" and row["project_type"] == "plotted"
    assert row["registered_on"] == date(2017, 10, 15) and row["proposed_completion"] == date(2021, 12, 31) and row["revised_completion"] == date(2023, 6, 30)
    assert row["total_units"] == 1200 and row["booked_units"] == 900 and row["complaints"] == 2 and row["status"] == "ongoing"
    assert row["unit_mix"] == {"2 BHK": 800, "3 BHK": 400}

def test_real_import_replaces_sample_data(client):
    with SessionLocal() as db:
        load_sample(db)
    info = client.get("/api/v1/rera/summary").json()["data"]
    assert info["sample"] is True and info["projects"] == 150

    rows = [
        {"registration_no": "PRM/KA/RERA/1/2", "name": "One", "promoter_name": "Acme", "locality": "Hebbal", "district": "Bengaluru Urban", "proposed_completion": "2027-01-01"},
        {"registration_no": "PRM/KA/RERA/1/3", "name": "Two", "promoter_name": "Acme", "locality": "Hebbal", "district": "Bengaluru Urban", "status": "Revoked"},
        {"name": "No number", "promoter_name": "Acme"},
    ]
    with SessionLocal() as db:
        result = load(db, rows)
    assert result["added"] == 2 and result["skipped"] == ["row 3: missing registration_no"]
    summary = client.get("/api/v1/rera/summary").json()
    assert summary["data"] == {**summary["data"], "projects": 2, "sample": False}
    assert {s["status"]: s["projects"] for s in summary["statuses"]}["revoked"] == 1

    # Loading again updates in place.
    with SessionLocal() as db:
        assert load(db, [{**rows[0], "name": "One Renamed"}]) == {"added": 0, "updated": 1, "skipped": []}
    assert client.get("/api/v1/rera/projects/prm-ka-rera-1-2").json()["name"] == "One Renamed"

def test_search_and_pages(client):
    with SessionLocal() as db:
        load_sample(db)
    everything = client.get("/api/v1/rera/projects", params={"page_size": 60}).json()
    assert everything["total"] == 150 and len(everything["items"]) == 60

    red = client.get("/api/v1/rera/projects", params={"risk": "red", "page_size": 60}).json()
    assert red["total"] and {p["risk"]["level"] for p in red["items"]} == {"red"}

    hebbal = client.get("/api/v1/rera/projects", params={"locality": "hebbal", "status": "ongoing"}).json()
    assert hebbal["total"] and all(p["locality"]["slug"] == "hebbal" and p["status"] == "ongoing" for p in hebbal["items"])

    first = everything["items"][0]
    by_number = client.get("/api/v1/rera/projects", params={"q": first["registration_no"].lower()}).json()
    assert [p["slug"] for p in by_number["items"]] == [first["slug"]]

    project = client.get(f"/api/v1/rera/projects/{first['slug']}").json()
    assert project["developer"]["slug"] == first["promoter"]["slug"] and project["locality_market"]["slug"] == first["locality"]["slug"]
    assert all(p["promoter"]["slug"] == first["promoter"]["slug"] for p in project["developer_projects"])

    developer = client.get(f"/api/v1/rera/developers/{first['promoter']['slug']}").json()
    assert developer["record"]["projects"] == len(developer["projects"]) == sum(l["projects"] for l in developer["localities"])

    locality = client.get(f"/api/v1/rera/localities/{first['locality']['slug']}").json()
    assert locality["market"]["projects"] == len(locality["projects"]) and sum(r["projects"] for r in locality["risk"]) == len(locality["projects"])

    filters = client.get("/api/v1/rera/filters").json()
    assert sum(d["projects"] for d in filters["districts"]) == 150
    for path in ("projects/nope", "developers/nope", "localities/nope"):
        assert client.get(f"/api/v1/rera/{path}").status_code == 404

def test_empty_database_still_answers(client):
    summary = client.get("/api/v1/rera/summary").json()
    assert summary["data"] == {"projects": 0, "sample": False, "updated_at": None} and summary["localities"] == []
