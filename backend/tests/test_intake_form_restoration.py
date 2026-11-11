import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config
from app.db import SessionLocal, engine
from app.main import app
from app.models import ApiRateBucket, AuditLog, Notification, ServiceType
from conftest import authenticate_customer
from test_intake import start
from test_service_intake_forms import BASE, SLUG, KEY, question, publish, complete

PATH = f"{BASE}/{SLUG}/restore"
ORIGINAL = [question()]
REVISED = [question(prompt="Updated transaction timing question?",kind="select",options=["Soon","Later"])]


@pytest.fixture
def versions(client,admin_headers):
    assert publish(client,admin_headers,questions=ORIGINAL).status_code == 200
    assert publish(client,admin_headers,revision=2,questions=REVISED).status_code == 200
    return ORIGINAL


def restore(client,headers,**extra):
    return client.post(PATH,headers=headers,json={"revision":3,"source_revision":2,"preview_questions":ORIGINAL,
        "reason":"Restore the reviewed original question set.","confirmed":True,**extra})


def test_restoration_creates_new_version_with_trace_and_preserves_pinned_customer_draft(client,admin_headers,versions):
    authenticate_customer(client);draft=complete(client,start(client,service_slug=SLUG),**{KEY:"2"})
    with SessionLocal() as db:
        old_events={str(row.id):copy.deepcopy(row.metadata_) for row in db.scalars(select(AuditLog).where(AuditLog.action=="service.intake_form_published"))}
    result=restore(client,admin_headers)
    assert result.status_code == 200 and result.headers["cache-control"] == "private, no-store"
    assert result.json()["revision"] == 4 and result.json()["questions"] == ORIGINAL
    loaded=client.get("/api/v1/intake/drafts/"+draft["id"]).json()
    assert loaded["service_form_revision"] == 3 and loaded["answers"][KEY] == "2" and loaded["questions"][-1]["options"][1]["label"] == "Later"
    assert start(client,service_slug=SLUG)["service_form_revision"] == 4
    with SessionLocal() as db:
        events=list(db.scalars(select(AuditLog).where(AuditLog.action=="service.intake_form_published")))
        assert len(events) == 3
        for event in events:
            if str(event.id) in old_events:assert event.metadata_ == old_events[str(event.id)]
        restored=next(event for event in events if event.metadata_["revision"]==4)
        assert restored.metadata_["restored_from_revision"] == 2 and restored.metadata_["source_snapshot"] == "questions"
        assert restored.metadata_["source_event_id"] in old_events and restored.metadata_["previous_questions"] == REVISED
        assert db.scalar(select(func.count()).select_from(Notification)) == 0
    history=client.get(f"{BASE}/{SLUG}/history",headers=admin_headers).json()
    assert history["items"][0]["restored_from_revision"] == 2


def test_original_empty_form_and_following_retained_snapshot_are_restorable(client,admin_headers,versions):
    with SessionLocal() as db:
        event=db.scalar(select(AuditLog).where(AuditLog.action=="service.intake_form_published",AuditLog.metadata_["revision"].as_integer()==2))
        db.delete(event);db.commit()
    # Version 3 retains version 2's preceding definition even after its own event is unavailable.
    result=restore(client,admin_headers);assert result.status_code == 200
    with SessionLocal() as db:
        event=db.scalar(select(AuditLog).where(AuditLog.action=="service.intake_form_published",AuditLog.metadata_["revision"].as_integer()==4))
        assert event.metadata_["source_snapshot"] == "previous_questions"
    assert restore(client,admin_headers,revision=4,source_revision=1,preview_questions=[]).status_code == 404


def test_version_one_restores_empty_form_without_removing_earlier_publications(client,admin_headers,versions):
    result=restore(client,admin_headers,source_revision=1,preview_questions=[])
    assert result.status_code == 200 and result.json()["revision"] == 4 and result.json()["questions"] == []
    assert client.get(f"{BASE}/{SLUG}/history",headers=admin_headers).json()["total"] == 3


def test_roles_unknown_service_retired_and_noop_restores(client,admin_headers,agent,versions):
    assert restore(client,dict(client.headers)).status_code == 401
    assert restore(client,agent["headers"]).status_code == 403
    authenticate_customer(client);assert restore(client,dict(client.headers)).status_code == 401
    assert restore(client,admin_headers,source_revision=3,preview_questions=REVISED).status_code == 409
    assert restore(client,admin_headers,source_revision=4).status_code == 409
    assert restore(client,admin_headers,revision=2).status_code == 409
    assert publish(client,admin_headers,revision=3,questions=ORIGINAL).status_code == 200
    assert restore(client,admin_headers,revision=4).status_code == 409  # Same questions, older version.
    with SessionLocal() as db:
        service=db.scalar(select(ServiceType).where(ServiceType.slug==SLUG));service.is_active=False;db.commit()
    assert restore(client,admin_headers,revision=4,source_revision=3,preview_questions=REVISED).status_code == 409
    assert client.post(BASE+"/unknown/restore",headers=admin_headers,json={"revision":3,"source_revision":2,"preview_questions":ORIGINAL,"confirmed":True,"reason":"Review missing service history."}).status_code == 404


@pytest.mark.parametrize("extra",[{"revision":True},{"source_revision":"2"},{"source_revision":0},{"confirmed":False},
    {"confirmed":"true"},{"reason":"          "},{"preview_questions":[question()]*6},{"preview_questions":[question(),question()]},{"unknown":True}])
def test_strict_reviewed_restore_payload(client,admin_headers,versions,extra):
    assert restore(client,admin_headers,**extra).status_code == 422
    assert client.get(BASE,headers=admin_headers).json()["items"]
    with SessionLocal() as db:assert db.scalar(select(ServiceType).where(ServiceType.slug==SLUG)).intake_form_revision == 3


def test_preview_mismatch_invalid_and_ambiguous_history_never_write(client,admin_headers,versions):
    assert restore(client,admin_headers,preview_questions=REVISED).status_code == 409
    with SessionLocal() as db:
        event=db.scalar(select(AuditLog).where(AuditLog.action=="service.intake_form_published",AuditLog.metadata_["revision"].as_integer()==2))
        original=copy.deepcopy(event.metadata_)
        event.metadata_={**original,"questions":[{"prompt":"Invalid retained data"}]};db.commit()
    assert restore(client,admin_headers).status_code == 409
    with SessionLocal() as db:
        event=db.scalar(select(AuditLog).where(AuditLog.action=="service.intake_form_published",AuditLog.metadata_["revision"].as_integer()==2))
        event.metadata_=original
        db.add(AuditLog(action=event.action,entity_type=event.entity_type,entity_id=event.entity_id,metadata_=original));db.commit()
    assert restore(client,admin_headers).status_code == 409
    with SessionLocal() as db:assert db.scalar(select(ServiceType).where(ServiceType.slug==SLUG)).intake_form_revision == 3


def test_other_service_history_cannot_be_restored_and_bad_metadata_does_not_break_lookup(client,admin_headers,versions):
    with SessionLocal() as db:
        other=db.scalar(select(ServiceType).where(ServiceType.slug=="general-guidance"));other.intake_form_revision=3
        service=db.scalar(select(ServiceType).where(ServiceType.slug==SLUG))
        db.add(AuditLog(action="service.intake_form_published",entity_type="service_type",entity_id=service.id,metadata_={"revision":"invalid metadata","questions":[]}));db.commit()
    result=client.post(BASE+"/general-guidance/restore",headers=admin_headers,json={"revision":3,"source_revision":2,"preview_questions":ORIGINAL,"confirmed":True,"reason":"Prevent cross-service restoration."})
    assert result.status_code == 404
    assert restore(client,admin_headers).status_code == 200


def test_restore_consumes_shared_write_budget(client,admin_headers,versions,monkeypatch):
    with SessionLocal() as db:db.query(ApiRateBucket).delete();db.commit()
    monkeypatch.setattr(config,"API_WRITES_PER_MINUTE",1)
    assert restore(client,admin_headers).status_code == 200
    assert restore(client,admin_headers,revision=4,source_revision=3,preview_questions=REVISED).status_code == 429


@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="Publication row locks require PostgreSQL")
def test_restoration_and_publication_race_have_one_winner(client,admin_headers,versions):
    barrier=Barrier(2)
    def save(restoring):
        with TestClient(app) as peer:
            barrier.wait(timeout=10)
            return (restore(peer,admin_headers) if restoring else publish(peer,admin_headers,revision=3,questions=[question(prompt="A simultaneous new question?")])).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(save,(True,False))) == [200,409]
    with SessionLocal() as db:assert db.scalar(select(ServiceType).where(ServiceType.slug==SLUG)).intake_form_revision == 4
