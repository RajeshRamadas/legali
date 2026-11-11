import copy
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, ProgrammingError

from app import audit_guard_v1, tickets
from app.db import SessionLocal, engine
from app.main import app
from app.models import AuditLog, CaseTask, ServiceRequest, TicketEvent, User
from test_operations import set_revision

NOW = datetime(2026,11,11,7,tzinfo=timezone.utc)
SECRET = "PRIVATE retained audit payload"


def seed(actor=None):
    with SessionLocal() as db:
        row=AuditLog(actor_user_id=actor,action="fixture.original",entity_type="service_type",entity_id=uuid.uuid4(),
            metadata_={"private":SECRET},created_at=NOW,request_id="original-reference",ip_hash="original-hash")
        db.add(row);db.commit();return row.id


def retained(key):
    with SessionLocal() as db:
        row=db.get(AuditLog,key)
        return {column.key:copy.deepcopy(getattr(row,column.key)) for column in AuditLog.__mapper__.column_attrs}


@pytest.mark.parametrize("field,value",[("id",uuid.uuid4()),("actor_user_id",None),("action","rewritten"),
    ("entity_type","rewritten"),("entity_id",uuid.uuid4()),("request_id","rewritten"),("ip_hash","rewritten"),
    ("metadata_",{"changed":True}),("created_at",NOW+timedelta(days=1))])
def test_every_audit_field_is_immutable_through_direct_sql(client,admin_headers,field,value):
    with SessionLocal() as db: actor=db.scalar(select(User.id).where(User.email=="admin@homexo.test"))
    key=seed(actor); before=retained(key)
    with SessionLocal() as db:
        with pytest.raises(IntegrityError,match="append-only"),db.begin_nested():
            db.execute(update(AuditLog).where(AuditLog.id==key).values({getattr(AuditLog,field):value}))
    assert retained(key)==before


def test_orm_changes_and_deletes_and_bulk_deletion_fail_without_losing_history():
    key=seed();before=retained(key)
    with SessionLocal() as db:
        row=db.get(AuditLog,key);row.metadata_={"changed":True}
        with pytest.raises(IntegrityError,match="append-only"):db.commit()
        db.rollback()
        db.delete(db.get(AuditLog,key))
        with pytest.raises(IntegrityError,match="append-only"):db.commit()
        db.rollback()
        with pytest.raises(IntegrityError,match="append-only"),db.begin_nested():db.execute(delete(AuditLog))
    assert retained(key)==before
    assert seed()!=key  # A correction is a new append, not a revision of the old event.


@pytest.mark.skipif(engine.dialect.name!="sqlite",reason="SQLite replacement semantics")
def test_sqlite_replace_cannot_bypass_delete_guards_when_recursive_triggers_are_off():
    key=seed();before=retained(key)
    with SessionLocal() as db:
        db.execute(text("PRAGMA recursive_triggers=OFF"))
        with pytest.raises(IntegrityError,match="append-only"),db.begin_nested():
            db.execute(AuditLog.__table__.insert().prefix_with("OR REPLACE").values(id=key,action="replacement",entity_type="service_type",metadata={}))
    assert retained(key)==before


@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="PostgreSQL truncate, upsert and FK semantics")
def test_postgres_truncate_upsert_and_actor_fk_rewrite_are_blocked(client,admin_headers):
    with SessionLocal() as db: actor=db.scalar(select(User.id).where(User.email=="admin@homexo.test"))
    key=seed(actor);before=retained(key)
    with SessionLocal() as db:
        for command in (text("TRUNCATE audit_logs"), text("TRUNCATE users CASCADE"),
            pg_insert(AuditLog).values(id=key,action="replacement",entity_type="service_type",metadata_={})
                .on_conflict_do_update(index_elements=[AuditLog.id],set_={"action":"replacement"}),
            delete(User).where(User.id==actor)):
            with pytest.raises(IntegrityError,match="append-only"),db.begin_nested():db.execute(command)
        assert db.get(User,actor) is not None
    assert retained(key)==before


@pytest.mark.skipif(engine.dialect.name!="postgresql",reason="PostgreSQL role and ALWAYS trigger behavior")
def test_postgres_ordinary_dml_role_and_replica_mode_cannot_rewrite_audit():
    key=seed();before=retained(key)
    with engine.begin() as connection:
        if not connection.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")):
            pytest.skip("A disposable superuser test database is needed to exercise restricted roles")
        role="audit_guard_test_"+uuid.uuid4().hex
        connection.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
        try:
            connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{role}"'))
            connection.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON audit_logs TO "{role}"'))
            connection.execute(text(f'SET LOCAL ROLE "{role}"'))
            for statement in (text("UPDATE audit_logs SET action='changed'"),text("DELETE FROM audit_logs"),text("TRUNCATE audit_logs")):
                with pytest.raises(IntegrityError,match="append-only"),connection.begin_nested():connection.execute(statement)
            with pytest.raises(ProgrammingError),connection.begin_nested():
                connection.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_append_only"))
            connection.execute(AuditLog.__table__.insert().values(action="fixture.appended",entity_type="fixture",metadata={}))
            connection.execute(text("RESET ROLE"))
            connection.execute(text("SET LOCAL session_replication_role = replica"))
            with pytest.raises(IntegrityError,match="append-only"),connection.begin_nested():
                connection.execute(text("DELETE FROM audit_logs"))
            connection.execute(text("SET LOCAL session_replication_role = origin"))
        finally:
            connection.execute(text("RESET ROLE"))
            connection.execute(text(f'REVOKE ALL ON audit_logs FROM "{role}"'))
            connection.execute(text(f'REVOKE ALL ON SCHEMA public FROM "{role}"'))
            connection.execute(text(f'DROP ROLE "{role}"'))
    assert retained(key)==before


def test_protection_inspection_and_readiness_detect_missing_or_changed_guards(client,admin_headers):
    set_revision();key=seed();before=retained(key)
    assert client.get("/ready").status_code==200
    assert client.get("/api/v1/admin/operations",headers=admin_headers).json()["audit_history"]=={"state":"configured"}
    try:
        with engine.begin() as connection:
            if engine.dialect.name=="postgresql":connection.execute(text("ALTER TABLE audit_logs DISABLE TRIGGER audit_logs_append_only"))
            else:connection.execute(text("DROP TRIGGER audit_logs_no_update"))
        assert client.get("/ready").status_code==503
        result=client.get("/api/v1/admin/operations",headers=admin_headers).json()
        assert result["status"]=="attention" and result["audit_history"]=={"state":"missing"}
        with engine.begin() as connection:
            if engine.dialect.name=="postgresql":
                connection.execute(text("ALTER TABLE audit_logs ENABLE ALWAYS TRIGGER audit_logs_append_only"))
                connection.execute(text("CREATE OR REPLACE FUNCTION homexo_audit_guard_v1() RETURNS trigger LANGUAGE plpgsql AS $$BEGIN RETURN NULL; END;$$"))
            else:connection.execute(text("CREATE TRIGGER audit_logs_no_update BEFORE UPDATE ON audit_logs BEGIN SELECT 1; END"))
        assert client.get("/ready").status_code==503  # A trigger name alone does not establish protection.
        if engine.dialect.name=="postgresql":
            with engine.begin() as connection:
                audit_guard_v1.remove(connection);audit_guard_v1.install(connection)
                connection.execute(text("DROP TRIGGER audit_logs_append_only ON audit_logs"))
                connection.execute(text("CREATE TRIGGER audit_logs_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON audit_logs FOR EACH STATEMENT WHEN (false) EXECUTE FUNCTION homexo_audit_guard_v1()"))
                connection.execute(text("ALTER TABLE audit_logs ENABLE ALWAYS TRIGGER audit_logs_append_only"))
            assert client.get("/ready").status_code==503  # A matching function with a false condition is not protection.
    finally:
        with engine.begin() as connection:
            audit_guard_v1.remove(connection);audit_guard_v1.install(connection)
    assert client.get("/ready").status_code==200 and retained(key)==before


def test_staff_suspension_and_role_changes_append_without_rewriting_prior_events(client,admin_headers,agent):
    key=seed(uuid.UUID(agent["id"]));before=retained(key)
    for payload in ({"account_status":"suspended"},{"account_status":"active","role":"admin"}):
        result=client.patch("/api/v1/admin/staff/"+agent["id"],headers=admin_headers,json=payload)
        assert result.status_code==200
    assert retained(key)==before
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=="staff.updated"))==2


def test_manual_task_changes_append_safe_audit_records_and_noops_do_not(client,admin_headers,raise_ticket):
    number=raise_ticket();base=f"/api/v1/admin/tickets/{number}/tasks"
    result=client.post(base,headers=admin_headers,json={"title":"PRIVATE task title","notes":"PRIVATE task notes"})
    assert result.status_code==201
    task=next(row for row in result.json()["case"]["tasks"] if row["source"]=="manual")
    assert client.patch(base+"/"+task["id"],headers=admin_headers,json={"notes":"PRIVATE revised notes","status":"done"}).status_code==200
    assert client.patch(base+"/"+task["id"],headers=admin_headers,json={"notes":"PRIVATE revised notes","status":"done"}).status_code==200
    with SessionLocal() as db:
        rows=list(db.scalars(select(AuditLog).where(AuditLog.action.in_(("case.task_created","case.task_updated"))).order_by(AuditLog.created_at)))
        assert [row.action for row in rows]==["case.task_created","case.task_updated"]
        assert all(row.actor_user_id and row.entity_id for row in rows)
        assert rows[1].metadata_["changed_fields"]==["notes","status"]
        assert rows[1].metadata_["previous_status"]=="open" and rows[1].metadata_["status"]=="done"
        assert "PRIVATE" not in str([row.metadata_ for row in rows])
    history=client.get("/api/v1/admin/activity",headers=admin_headers,params={"category":"cases"}).json()
    assert {row["activity"] for row in history["items"]}>={"Case task created","Case task updated"}


def test_task_creation_and_audit_commit_are_atomic(client,admin_headers,raise_ticket,monkeypatch):
    number=raise_ticket()
    with SessionLocal() as db:
        before=[db.scalar(select(func.count()).select_from(model)) for model in (CaseTask,TicketEvent,AuditLog)]
    real=tickets.audit
    def fail(db,user,action,*args,**kwargs):
        if action=="case.task_created":raise RuntimeError("Synthetic audit insert failure")
        return real(db,user,action,*args,**kwargs)
    monkeypatch.setattr(tickets,"audit",fail)
    with TestClient(app,raise_server_exceptions=False) as peer:
        result=peer.post(f"/api/v1/admin/tickets/{number}/tasks",headers=admin_headers,json={"title":"Atomic task creation"})
        assert result.status_code==500
    with SessionLocal() as db:
        assert before==[db.scalar(select(func.count()).select_from(model)) for model in (CaseTask,TicketEvent,AuditLog)]
