import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, func, select

from app import config, task_queue
from app.db import SessionLocal, engine
from app.models import ApiRateBucket, Assignment, AuditLog, CaseMember, CaseTask, Meeting, Notification, ServiceRequest, TicketEvent
from conftest import authenticate_customer

BASE = "/api/v1/admin/task-queue"
LEGACY = "/api/v1/admin/tasks"
NOW = datetime(2026, 11, 11, 7, tzinfo=timezone.utc)
SECRET = "PRIVATE task notes or structured answer"


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(task_queue, "utcnow", lambda: NOW)


def case(raise_ticket, *, status="submitted", priority="normal"):
    number = raise_ticket()
    with SessionLocal() as db:
        row = db.scalar(select(ServiceRequest).where(ServiceRequest.ticket_number == number))
        db.query(CaseTask).filter(CaseTask.service_request_id == row.id).delete(synchronize_session=False)
        row.status, row.priority = status, priority
        row.structured_answers = {**row.structured_answers, "private_answer": SECRET}
        db.commit(); return row.id, number


def task(case_id, *, assignee=None, title="Review the transaction checklist", due=NOW, status="open", key=None):
    with SessionLocal() as db:
        row = CaseTask(id=key or uuid.uuid4(), service_request_id=case_id, assignee_user_id=uuid.UUID(assignee) if isinstance(assignee,str) else assignee,
            title=title, notes=SECRET, due_at=due, status=status, source="manual")
        db.add(row); db.commit(); return str(row.id)


def get(client, headers, **params):
    result = client.get(BASE, headers=headers, params=params)
    assert result.status_code == 200, result.text
    return result.json()


def test_staff_authentication_and_agent_scope_boundaries(client, admin_headers, agent, raise_ticket):
    for path in (BASE, LEGACY):
        result = client.get(path); assert result.status_code == 401 and result.headers["cache-control"] == "private, no-store"
    authenticate_customer(client); assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers=admin_headers).status_code == 200
    assert client.get(BASE, headers=agent["headers"]).status_code == 200
    for scope in ("all", "unassigned", agent["id"]):
        result = client.get(BASE, headers=agent["headers"], params={"assignee":scope})
        assert result.status_code == 403 and result.headers["cache-control"] == "private, no-store"
    assert client.post(BASE, headers=admin_headers).status_code == 405


def test_task_assignment_does_not_grant_case_access_and_team_removal_hides_rows_and_counts(client, admin_headers, agent, raise_ticket):
    visible, number = case(raise_ticket); key = task(visible, assignee=agent["id"])
    hidden, _ = case(raise_ticket); task(hidden, assignee=agent["id"], title="PRIVATE inaccessible task")
    assert get(client, agent["headers"])["total"] == 0
    assert client.get(LEGACY, headers=agent["headers"]).json()["items"] == []
    members = f"/api/v1/admin/tickets/{number}/members"
    assert client.post(members, headers=admin_headers, json={"user_id":agent["id"],"role":"reviewer"}).status_code == 201
    result = get(client, agent["headers"])
    assert result["total"] == result["summary"]["open"] == 1 and result["items"][0]["id"] == key
    assert "PRIVATE inaccessible" not in str(result)
    assert client.delete(members+"/"+agent["id"], headers=admin_headers).status_code == 200
    assert get(client, agent["headers"])["summary"] == {"open":0,"overdue":0,"due_today":0,"unscheduled":0}
    assert client.get(LEGACY, headers=agent["headers"]).json()["items"] == []
    with SessionLocal() as db: assert db.get(CaseTask, uuid.UUID(key)).assignee_user_id == uuid.UUID(agent["id"])


def test_owner_and_meeting_access_are_current_and_multiple_access_paths_never_duplicate_tasks(client, admin_headers, agent, raise_ticket):
    case_id, _ = case(raise_ticket); key = task(case_id, assignee=agent["id"])
    with SessionLocal() as db:
        owner = Assignment(service_request_id=case_id, agent_user_id=uuid.UUID(agent["id"]))
        member = CaseMember(service_request_id=case_id, user_id=uuid.UUID(agent["id"]), role="reviewer")
        meeting = Meeting(service_request_id=case_id, lawyer_user_id=uuid.UUID(agent["id"]), title="Private meeting",
            starts_at=NOW, ends_at=NOW+timedelta(hours=1), status="scheduled")
        db.add_all([owner,member,meeting]); db.commit(); ids = owner.id, member.id, meeting.id
    result = get(client, agent["headers"]); assert result["total"] == 1 and result["items"][0]["id"] == key
    with SessionLocal() as db:
        db.get(Assignment,ids[0]).unassigned_at=NOW; db.get(CaseMember,ids[1]).removed_at=NOW; db.commit()
    assert get(client, agent["headers"])["total"] == 1  # Existing meeting-based case access still applies.
    with SessionLocal() as db: db.get(Meeting,ids[2]).status="cancelled"; db.commit()
    assert get(client, agent["headers"])["total"] == 0


def test_admin_ownership_status_priority_search_and_closed_case_filters(client, admin_headers, agent, raise_ticket):
    first, number = case(raise_ticket, priority="urgent")
    assigned = task(first, assignee=agent["id"], title="Call the society secretary")
    unassigned = task(first, due=None, title="Obtain the approval copy")
    done = task(first, assignee=agent["id"], status="done", title="Finished transaction check")
    closed, _ = case(raise_ticket, status="completed"); task(closed, assignee=agent["id"])
    assert get(client, admin_headers)["total"] == 0
    assert get(client, admin_headers, assignee="all")["total"] == 2
    assert get(client, admin_headers, assignee="unassigned")["items"][0]["id"] == unassigned
    assert get(client, admin_headers, assignee=agent["id"])["items"][0]["id"] == assigned
    assert get(client, admin_headers, assignee="all", status="done")["items"][0]["id"] == done
    assert get(client, admin_headers, assignee="all", priority="normal")["total"] == 0
    assert get(client, admin_headers, assignee="all", priority="urgent", q="  SOCIETY  ")["items"][0]["id"] == assigned
    assert get(client, admin_headers, assignee="all", q=number.lower())["total"] == 2
    result = get(client, admin_headers, assignee="all", status="all")
    assert result["total"] == 3 and result["summary"] == {"open":2,"overdue":0,"due_today":1,"unscheduled":1}


def test_india_day_and_rolling_week_boundaries_include_only_matching_tasks(client, admin_headers, raise_ticket):
    case_id, _ = case(raise_ticket, status="on_hold")
    start = datetime(2026,11,10,18,30,tzinfo=timezone.utc); end=start+timedelta(days=1)
    before=task(case_id,due=start-timedelta(microseconds=1)); midnight=task(case_id,due=start)
    last=task(case_id,due=end-timedelta(microseconds=1)); nextday=task(case_id,due=end)
    now=task(case_id,due=NOW); weeklast=task(case_id,due=NOW+timedelta(days=7)-timedelta(microseconds=1))
    task(case_id,due=NOW+timedelta(days=7)); unscheduled=task(case_id,due=None)
    task(case_id,due=start,status="done")
    ids=lambda **params:{row["id"] for row in get(client,admin_headers,assignee="all",**params)["items"]}
    assert ids(due="today") == {midnight,last,now}
    assert ids(due="week") == {now,last,nextday,weeklast}
    assert ids(due="overdue") == {before,midnight}
    assert ids(due="unscheduled") == {unscheduled}
    assert not get(client,admin_headers,assignee="all",status="done",due="overdue")["items"]
    # Holding a case pauses case targets, not the task dates recorded here.
    assert all(row["case"]["status"] == "on_hold" for row in get(client,admin_headers,assignee="all")["items"])


def test_open_tasks_sort_by_due_then_case_priority_then_uuid_with_global_counts(client, admin_headers, raise_ticket):
    normal, _=case(raise_ticket); urgent,_=case(raise_ticket,priority="urgent")
    first=task(normal,due=NOW-timedelta(days=1)); urgent_tie=task(urgent,key=uuid.UUID(int=3)); normal_tie=task(normal,key=uuid.UUID(int=1))
    none=task(urgent,due=None); finished=task(urgent,due=NOW-timedelta(days=2),status="done")
    results=[get(client,admin_headers,assignee="all",status="all",page=page,page_size=2) for page in (1,2,3)]
    assert [row["id"] for result in results for row in result["items"]] == [first,urgent_tie,normal_tie,none,finished]
    assert all(result["total"]==5 and result["summary"]=={"open":4,"overdue":1,"due_today":2,"unscheduled":1} for result in results)
    assert get(client,admin_headers,assignee="all",page=10)["items"] == []


def test_title_search_treats_wildcards_literally(client, admin_headers, raise_ticket):
    case_id,_=case(raise_ticket); key=task(case_id,title="Check 50%_\\ title")
    task(case_id,title="Another title")
    result=get(client,admin_headers,assignee="all",q="%_\\")
    assert [row["id"] for row in result["items"]] == [key]


def test_queue_reads_omit_private_data_and_do_not_change_tasks_events_or_notifications(client, admin_headers, raise_ticket):
    case_id,_=case(raise_ticket); task(case_id)
    with SessionLocal() as db:
        before=[db.scalar(select(func.count()).select_from(model)) for model in (CaseTask,AuditLog,TicketEvent,Notification)]
    statements=[]
    def capture(connection,cursor,statement,parameters,context,many):
        if "case_tasks" in statement: statements.append(statement)
    event.listen(engine,"before_cursor_execute",capture)
    try:
        response=client.get(BASE,headers=admin_headers,params={"assignee":"all"})
        assert response.status_code==200 and response.headers["cache-control"]=="private, no-store"
        assert SECRET not in response.text and "98765" not in response.text and "sample@example.com" not in response.text
        assert "authorization" in response.headers["vary"].lower()
        row=response.json()["items"][0]
        assert set(row)=={"id","title","status","source","due_at","overdue","assignee","case"}
    finally:event.remove(engine,"before_cursor_execute",capture)
    assert len(statements)==2 and all("case_tasks.notes" not in sql and "structured_answers" not in sql for sql in statements)
    with SessionLocal() as db:
        assert before==[db.scalar(select(func.count()).select_from(model)) for model in (CaseTask,AuditLog,TicketEvent,Notification)]


@pytest.mark.parametrize("params",[{"status":"private"},{"due":"tomorrow"},{"priority":"unknown"},{"assignee":"bad"},
    {"page":0},{"page":10001},{"page_size":0},{"page_size":101},{"q":"x"*101},{"q":"bad\x00text"}])
def test_invalid_filters_are_rejected(client,admin_headers,params):
    assert client.get(BASE,headers=admin_headers,params=params).status_code==422


def test_legacy_and_new_task_reads_share_lookup_budget(client,admin_headers,monkeypatch):
    with SessionLocal() as db:db.query(ApiRateBucket).delete();db.commit()
    monkeypatch.setattr(config,"API_LOOKUPS_PER_MINUTE",1)
    assert client.get(BASE,headers=admin_headers).status_code==200
    result=client.get(LEGACY,headers=admin_headers)
    assert result.status_code==429 and result.headers["retry-after"] and result.headers["cache-control"]=="private, no-store"
