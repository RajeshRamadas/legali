import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config, intake
from app.bootstrap import sync_reference_data
from app.db import SessionLocal, engine
from app.main import app
from app.models import ApiRateBucket, AuditLog, ConversationMessage, IntakeDraft, ServiceRequest, ServiceType
from conftest import authenticate_customer
from test_intake import BASE as DRAFTS, DEFAULTS, start, answer, submit
from test_service_availability import change

BASE = "/api/v1/admin/intake-forms"
SLUG = "title-verification"
REASON = "PRIVATE form review for the service intake."
ID = "726fb188-309e-4c19-94a4-e67d559219ce"
KEY = "extra_"+uuid.UUID(ID).hex


def question(**extra):
    return {"id": ID, "prompt": "When is your planned transaction?", "help": "Approximate timing is enough.", "kind": "text", "required": True, "max_length":100, "options":[], **extra}


def publish(client, headers, questions=None, revision=1, slug=SLUG, **extra):
    return client.patch(f"{BASE}/{slug}", headers=headers,
        json={"revision":revision,"questions":[question()] if questions is None else questions,"reason":REASON,"confirmed":True,**extra})


def complete(client, draft, **extras):
    for _ in range(40):
        if not draft["next_question"]: return draft
        key=draft["next_question"]
        draft=answer(client,draft,key,extras.get(key,"Next month") if key.startswith("extra_") else DEFAULTS[key])
    pytest.fail("Supplemental intake did not finish")


def test_admin_publication_private_history_and_public_payload_boundaries(client, admin_headers, agent):
    assert client.get(BASE).status_code == 401
    assert client.get(BASE,headers=agent["headers"]).status_code == 403
    assert publish(client,agent["headers"]).status_code == 403
    authenticate_customer(client)
    assert client.get(BASE).status_code == 401
    result=publish(client,admin_headers)
    assert result.status_code == 200 and result.json()["revision"] == 2
    assert result.headers["cache-control"] == "private, no-store"
    assert client.get(BASE+f"/{SLUG}/history").status_code == 401
    history=client.get(BASE+f"/{SLUG}/history",headers=admin_headers)
    assert history.headers["cache-control"] == "private, no-store"
    assert history.json()["items"][0]["reason"] == REASON
    assert history.json()["items"][0]["actor"] == "Meera Admin"
    assert REASON not in str(start(client,service_slug=SLUG))
    public=client.get("/api/v1/services").json()
    assert REASON not in str(public) and "intake_questions" not in str(public) and "When is your planned" not in str(public)


@pytest.mark.parametrize("extra",[{"revision":True},{"revision":"1"},{"confirmed":False},{"confirmed":"true"},
    {"reason":"          "},{"unknown":True}, {"questions":[question()]*2}, {"questions":[question(id=str(uuid.uuid4())) for _ in range(6)]},
    {"questions":[question(prompt="    ")]}, {"questions":[question(prompt="Bad\x00question")]},
    {"questions":[question(kind="email")]}, {"questions":[question(required="false")]},
    {"questions":[question(max_length=1001)]}, {"questions":[question(max_length=True)]},
    {"questions":[question(options=["Unexpected"])]}, {"questions":[question(kind="select",options=["one"])]},
    {"questions":[question(kind="select",options=["Same"," same "])]},
    {"questions":[question(kind="select",options=["One","Bad\nchoice"])]}])
def test_rejects_unreviewed_unbounded_or_ambiguous_definitions(client,admin_headers,extra):
    assert publish(client,admin_headers,**extra).status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(ServiceType).where(ServiceType.slug==SLUG)).intake_form_revision == 1


def test_pinned_drafts_survive_publication_and_submission_retains_original_labels(client,admin_headers):
    publish(client,admin_headers,questions=[question(kind="select",options=["This month","Later"],required=False)])
    authenticate_customer(client);draft=start(client,service_slug=SLUG)
    assert draft["service_form_revision"] == 2
    publish(client,admin_headers,questions=[question(kind="select",options=["Changed first choice","Other"],required=False)],revision=2)
    draft=complete(client,draft,**{KEY:"1"})
    assert draft["questions"][-1]["options"][0]["label"] == "This month"
    loaded=client.get(DRAFTS+"/"+draft["id"]).json()
    assert loaded["answers"][KEY] == "1" and loaded["service_form_revision"] == 2
    created=submit(client,draft);assert created.status_code == 200,created.text
    with SessionLocal() as db:
        ticket=db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number==created.json()["ticket_number"]))
        guided=ticket.structured_answers["guided_intake"]
        assert guided["service_form"]["revision"] == 2 and guided["service_form"]["questions"][0]["options"] == ["This month","Later"]
        assert guided["answers"][KEY] == "1" and guided["saving_notice_version"] == "guided-request-v2"
        bodies=list(db.scalars(select(ConversationMessage.body).where(ConversationMessage.conversation_id==ticket.conversation_id)))
        assert "This month" in bodies and "Changed first choice" not in bodies
    assert submit(client,draft).json()["ticket_number"] == created.json()["ticket_number"]
    assert start(client,service_slug=SLUG)["service_form_revision"] == 3


def test_current_question_validation_required_optional_and_unknown_keys(client,admin_headers):
    publish(client,admin_headers,questions=[question(max_length=10)])
    authenticate_customer(client);draft=start(client,service_slug=SLUG)
    path=DRAFTS+"/"+draft["id"]
    assert client.patch(path,json={"revision":draft["revision"],"key":KEY,"value":"Too early"}).status_code == 422
    while draft["next_question"] != KEY:
        draft=answer(client,draft,draft["next_question"],DEFAULTS[draft["next_question"]])
    for value in ("", "x"*11,"Bad\x00input"):
        assert client.patch(path,json={"revision":draft["revision"],"key":KEY,"value":value}).status_code == 422
    assert submit(client,draft).status_code == 422
    draft=answer(client,draft,KEY,"Next week")
    publish(client,admin_headers,questions=[question(kind="select",required=False,options=["Yes","Unknown"])],revision=2)
    optional=start(client,service_slug=SLUG);optional=complete(client,optional,**{KEY:""})
    assert optional["answers"][KEY] == "" and submit(client,optional).status_code == 200


def test_service_change_replaces_snapshot_and_prunes_cross_service_answers(client,admin_headers):
    publish(client,admin_headers)
    publish(client,admin_headers,slug="general-guidance",questions=[question(prompt="Different service question?")])
    authenticate_customer(client);draft=complete(client,start(client,service_slug=SLUG))
    draft=answer(client,draft,"service_slug","general-guidance")
    assert KEY not in draft["answers"] and draft["questions"][-1]["prompt"] == "Different service question?"
    draft=answer(client,draft,"service_slug",SLUG)
    assert draft["questions"][-1]["prompt"] == "When is your planned transaction?"
    assert KEY not in draft["answers"]
    publish(client,admin_headers,revision=2,questions=[])
    assert client.get(DRAFTS+"/"+draft["id"]).json()["questions"][-1]["key"] == KEY
    fresh=start(client,service_slug=SLUG)
    assert not any(row["key"].startswith("extra_") for row in fresh["questions"])


def test_legacy_drafts_and_no_service_yet_follow_explicit_notice_and_selection_rules(client,admin_headers):
    authenticate_customer(client)
    legacy=start(client,service_slug=SLUG);empty=start(client);chosen=start(client,service_slug=SLUG)
    with SessionLocal() as db:
        old=db.get(IntakeDraft,uuid.UUID(legacy["id"]));old.service_form_snapshot={};old.saving_notice_version="guided-request-v1";db.commit()
    publish(client,admin_headers)
    assert not any(row["key"]==KEY for row in client.get(DRAFTS+"/"+chosen["id"]).json()["questions"])
    empty=answer(client,empty,"service_slug",SLUG)
    assert empty["service_form_revision"] == 2
    legacy=answer(client,legacy,"service_slug","general-guidance")
    legacy=answer(client,legacy,"service_slug",SLUG)
    assert legacy["service_form_revision"] is None and not any(row["key"]==KEY for row in legacy["questions"])
    legacy=complete(client,legacy);assert submit(client,legacy).status_code == 200
    with SessionLocal() as db:
        sync_reference_data(db)
        service=db.scalar(select(ServiceType).where(ServiceType.slug==SLUG));assert service.intake_form_revision == 2 and service.intake_questions


def test_draft_owner_discard_pause_and_publication_conflicts(client,admin_headers):
    assert publish(client,admin_headers).status_code == 200
    assert publish(client,admin_headers).status_code == 409
    assert publish(client,admin_headers,revision=2).json()["revision"] == 2  # No-op.
    assert change(client,admin_headers).status_code == 200
    assert publish(client,admin_headers,revision=2,questions=[]).status_code == 200
    assert change(client,admin_headers,revision=2,paused=False).status_code == 200
    owner=authenticate_customer(client);draft=complete(client,start(client,service_slug=SLUG))
    authenticate_customer(client,"9123456789")
    assert client.get(DRAFTS+"/"+draft["id"]).status_code == 404
    assert submit(client,draft).status_code == 404
    assert client.delete(DRAFTS+"/"+draft["id"],headers=owner).status_code == 200
    with SessionLocal() as db:
        deleted=db.get(IntakeDraft,uuid.UUID(draft["id"]));assert deleted.answers == deleted.service_form_snapshot == {}
        service=db.scalar(select(ServiceType).where(ServiceType.slug==SLUG));service.is_active=False;db.commit()
    assert publish(client,admin_headers,revision=3).status_code == 409
    assert publish(client,admin_headers,slug="unknown").status_code == 404
    assert client.get(BASE+"/unknown/history",headers=admin_headers).status_code == 404


def test_history_paging_and_shared_budgets(client,admin_headers,monkeypatch):
    with SessionLocal() as db:
        service=db.scalar(select(ServiceType).where(ServiceType.slug==SLUG))
        for number in range(21):db.add(AuditLog(action="service.intake_form_published",entity_type="service_type",entity_id=service.id,metadata_={"revision":number+2,"questions":[],"previous_questions":[],"reason":REASON}))
        db.commit()
    first=client.get(BASE+f"/{SLUG}/history",headers=admin_headers).json()
    second=client.get(BASE+f"/{SLUG}/history?page=2",headers=admin_headers).json()
    assert first["total"] == second["total"] == 21 and len(first["items"]) == 20 and len(second["items"]) == 1
    assert not {row["id"] for row in first["items"]} & {row["id"] for row in second["items"]}
    assert client.get(BASE+f"/{SLUG}/history?page=0",headers=admin_headers).status_code == 422
    with SessionLocal() as db:db.query(ApiRateBucket).delete();db.commit()
    monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(BASE,headers=admin_headers).status_code == 200
    assert client.get(BASE,headers=admin_headers).status_code == 429
    monkeypatch.setattr(config,"API_WRITES_PER_MINUTE",1)
    assert publish(client,admin_headers).status_code == 200
    assert publish(client,admin_headers,revision=2).status_code == 429


@pytest.mark.skipif(engine.dialect.name != "postgresql",reason="Publication row locks require PostgreSQL")
def test_simultaneous_publications_have_one_winner(client,admin_headers):
    barrier=Barrier(2)
    def save(number):
        with TestClient(app) as peer:
            barrier.wait(timeout=10)
            return publish(peer,admin_headers,questions=[question(prompt=f"Reviewed transaction timing {number}?")]).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(save,(1,2))) == [200,409]
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="service.intake_form_published")) == 1
