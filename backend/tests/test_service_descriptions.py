import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config
from app.bootstrap import sync_reference_data
from app.db import SessionLocal, engine
from app.main import app
from app.models import ApiRateBucket, AuditLog, Notification, ServiceRequest, ServiceType
from conftest import authenticate_customer
from test_service_availability import change

BASE = "/api/v1/admin/services"
SLUG = "title-verification"
PATH = f"{BASE}/{SLUG}/description"
COPY = "Reviewed title checks with an advocate. The team confirms the scope before proceeding."
REASON = "PRIVATE publication review for the pilot catalogue."


def publish(client, headers, **extra):
    if "description" in extra and extra["description"] is None and "standard_description" not in extra:
        extra["standard_description"] = next(row["default_description"] for row in client.get(BASE, headers=headers).json()["items"] if row["slug"] == SLUG)
    return client.patch(PATH, headers=headers, json={"description": COPY, "revision": 1, "reason": REASON, "confirmed": True, **extra})


def test_publication_access_private_history_and_public_allowlist(client, admin_headers, agent):
    assert client.patch(PATH, json={}).status_code == 401
    assert publish(client, agent["headers"]).status_code == 403
    authenticate_customer(client)
    assert client.get(PATH+"/history").status_code == 401
    assert publish(client, dict(client.headers)).status_code == 401
    result = publish(client, admin_headers)
    assert result.status_code == 200 and result.headers["cache-control"] == "private, no-store"
    assert result.json()["description_revision"] == 2 and result.json()["description_customized"]
    assert result.json()["revision"] == 1 and not result.json()["paused"]
    client.headers.pop("authorization", None)
    public = client.get(f"/api/v1/services/{SLUG}")
    assert public.json()["description"] == COPY
    assert set(public.json()) == {"slug", "name", "category", "description", "property_types"}
    assert public.headers["cache-control"] == "no-store"
    assert REASON not in client.get("/api/v1/services").text
    history = client.get(PATH+"/history", headers=admin_headers)
    assert history.headers["cache-control"] == "private, no-store"
    row = history.json()["items"][0]
    assert row["description"] == COPY and row["reason"] == REASON and row["actor"] == "Meera Admin"
    assert row["revision"] == 2 and not row["uses_standard"] and row["previous_description"] != COPY
    assert client.get(PATH+"/history", headers=agent["headers"]).status_code == 403


@pytest.mark.parametrize("extra", [{"description": " "*20}, {"description": "tiny"}, {"description": "x"*801},
    {"description": "Bad\x00 control character"}, {"description": "Bad\r control character"}, {"description": 123},
    {"reason": "          "}, {"reason": "PRIVATE\x00reason"}, {"confirmed": False}, {"confirmed": "true"},
    {"revision": True}, {"revision": "1"}, {"revision": 2147483647}, {"unknown": "value"}])
def test_strict_reviewed_payload_and_text_limits(client, admin_headers, extra):
    assert publish(client, admin_headers, **extra).status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(ServiceType).where(ServiceType.slug == SLUG)).description_revision == 1
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "service.description_changed")) == 0


def test_published_copy_survives_reference_sync_and_reset_uses_current_standard(client, admin_headers, monkeypatch):
    default = client.get(f"/api/v1/services/{SLUG}").json()["description"]
    assert publish(client, admin_headers, description="  "+COPY+"  ").json()["description"] == COPY
    with SessionLocal() as db:
        sync_reference_data(db)
        saved = db.scalar(select(ServiceType).where(ServiceType.slug == SLUG))
        assert saved.description_override == COPY and saved.description == default and saved.description_revision == 2
        saved.description = "Updated standard description for a later code release."; db.commit()
    reset = publish(client, admin_headers, description=None, revision=2)
    assert reset.status_code == 200 and not reset.json()["description_customized"]
    assert reset.json()["description"] == "Updated standard description for a later code release."
    assert reset.json()["description_revision"] == 3
    # A current no-op does not create another publication. A stale retry needs review.
    assert publish(client, admin_headers, description=None, revision=3).json()["description_revision"] == 3
    assert publish(client, admin_headers, revision=1).status_code == 409
    assert client.get(PATH+"/history", headers=admin_headers).json()["total"] == 2
    with SessionLocal() as db:
        sync_reference_data(db)
        assert db.scalar(select(ServiceType).where(ServiceType.slug == SLUG)).description_revision == 3
        assert db.scalar(select(func.count()).select_from(Notification)) == 0
        assert db.scalar(select(func.count()).select_from(ServiceRequest)) == 0


def test_reset_rejects_standard_copy_that_changed_after_preview(client, admin_headers):
    original = client.get(f"/api/v1/services/{SLUG}").json()["description"]
    assert publish(client, admin_headers).status_code == 200
    with SessionLocal() as db:
        service = db.scalar(select(ServiceType).where(ServiceType.slug == SLUG)); service.description = "Updated standard description after the preview."; db.commit()
    result = publish(client, admin_headers, description=None, standard_description=original, revision=2)
    assert result.status_code == 409 and "standard description changed" in result.json()["detail"]
    assert client.get(f"/api/v1/services/{SLUG}").json()["description"] == COPY


def test_pause_and_publication_revisions_are_independent_and_hidden_services_stay_hidden(client, admin_headers):
    assert change(client, admin_headers).status_code == 200
    updated = publish(client, admin_headers).json()
    assert updated["paused"] and updated["revision"] == updated["description_revision"] == 2
    assert client.get(f"/api/v1/services/{SLUG}").status_code == 404
    assert SLUG not in {row["slug"] for row in client.get("/api/v1/services").json()["items"]}
    assert change(client, admin_headers, paused=False, revision=2).json()["description"] == COPY
    assert publish(client, admin_headers, revision=2, description=COPY+" Updated.").status_code == 200
    with SessionLocal() as db:
        service = db.scalar(select(ServiceType).where(ServiceType.slug == SLUG)); service.is_active = False; db.commit()
    assert publish(client, admin_headers, revision=3).status_code == 409
    assert client.get(PATH+"/history", headers=admin_headers).json()["total"] == 2
    assert client.patch(f"{BASE}/unknown/description", headers=admin_headers, json={"description": COPY, "revision":1,"reason":REASON,"confirmed":True}).status_code == 404
    assert client.get(f"{BASE}/unknown/description/history", headers=admin_headers).status_code == 404


def test_history_is_scoped_paged_and_read_only_and_lookup_write_budgets_apply(client, admin_headers, monkeypatch):
    with SessionLocal() as db:
        service = db.scalar(select(ServiceType).where(ServiceType.slug == SLUG))
        other = db.scalar(select(ServiceType).where(ServiceType.slug == "general-guidance"))
        for number in range(22):
            db.add(AuditLog(action="service.description_changed", entity_type="service_type", entity_id=service.id if number < 21 else other.id,
                metadata_={"description": f"Published fixture {number}", "previous_description": COPY, "reason": REASON, "revision": number+2, "uses_standard":False}))
        db.commit()
    first = client.get(PATH+"/history", headers=admin_headers).json()
    second = client.get(PATH+"/history?page=2", headers=admin_headers).json()
    assert first["total"] == second["total"] == 21 and len(first["items"]) == 20 and len(second["items"]) == 1
    assert not {row["id"] for row in first["items"]} & {row["id"] for row in second["items"]}
    assert all(row["actor"] == "Former administrator" for row in first["items"])
    assert client.get(PATH+"/history?page=0", headers=admin_headers).status_code == 422
    assert client.get(PATH+"/history?page=10001", headers=admin_headers).status_code == 422
    with SessionLocal() as db: db.query(ApiRateBucket).delete(); db.commit()
    monkeypatch.setattr(config, "API_LOOKUPS_PER_MINUTE", 1)
    assert client.get(PATH+"/history", headers=admin_headers).status_code == 200
    assert client.get(PATH+"/history", headers=admin_headers).status_code == 429
    monkeypatch.setattr(config, "API_WRITES_PER_MINUTE", 1)
    assert publish(client, admin_headers).status_code == 200
    assert publish(client, admin_headers, revision=2).status_code == 429


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Publication row locks require PostgreSQL")
@pytest.mark.parametrize("availability", [False, True])
def test_concurrent_publication_and_admission_controls_serialize_without_lost_updates(client, admin_headers, availability):
    barrier = Barrier(2)
    def write(second):
        with TestClient(app) as peer:
            barrier.wait(timeout=10)
            return (change(peer, admin_headers) if second and availability else publish(peer, admin_headers, description=COPY+(" Second." if second else " First."))).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (False, True)))
    assert sorted(results) == ([200,200] if availability else [200,409])
    with SessionLocal() as db:
        service = db.scalar(select(ServiceType).where(ServiceType.slug == SLUG))
        assert service.description_revision == 2 and service.intake_paused == availability
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "service.description_changed")) == 1
