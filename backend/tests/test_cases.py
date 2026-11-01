from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ServiceRequest

CONTACT = "+91 98765 43210"

def _case(client, headers, number):
    response = client.get(f"/api/v1/admin/tickets/{number}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()

def _patch(client, headers, number, **body):
    return client.patch(f"/api/v1/admin/tickets/{number}", json=body, headers=headers)

def _milestones(view):
    return {m["key"]: m["done"] for m in view["milestones"]}

def test_new_case_has_deadlines_milestones_and_a_scope_task(client, admin_headers, raise_ticket):
    number = raise_ticket()
    case = _case(client, admin_headers, number)["case"]
    assert [m["key"] for m in case["milestones"]] == ["received", "scoped", "assigned", "documents", "signed", "closed"]
    assert case["current_milestone"] == "scoped"
    assert case["deadlines"]["due_at"] and case["deadlines"]["first_response_due_at"] and not case["deadlines"]["overdue"]
    [task] = case["tasks"]
    assert task["playbook_key"] == "confirm-scope" and task["status"] == "open" and task["due_at"] == case["deadlines"]["first_response_due_at"]

    # The customer sees the same steps but no tasks or team.
    public = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": CONTACT}).json()
    assert [m["key"] for m in public["progress"]["milestones"]] == [m["key"] for m in case["milestones"]]
    assert "tasks" not in public["progress"] and public["progress"]["fee"] is None

def test_consultation_cases_skip_document_milestones(client, admin_headers, raise_ticket):
    number = raise_ticket(service_slug="advocate-consultation")
    keys = [m["key"] for m in _case(client, admin_headers, number)["case"]["milestones"]]
    assert keys == ["received", "scoped", "assigned", "closed"]

def test_playbook_follows_the_work(client, admin_headers, agent, raise_ticket):
    number = raise_ticket()
    assigned = client.post(f"/api/v1/admin/tickets/{number}/assignment", json={"agent_id": agent["id"]}, headers=admin_headers).json()
    tasks = {t["playbook_key"]: t for t in assigned["case"]["tasks"]}
    # Assignment counts as the first response, and moves the case past scope, so the scope task is ticked off.
    assert assigned["case"]["deadlines"]["first_response_at"]
    assert tasks["confirm-scope"]["status"] == "done"
    assert tasks["issue-report"]["status"] == "open" and tasks["issue-report"]["assignee"]["id"] == agent["id"]
    assert _milestones(assigned["case"])["assigned"] and assigned["case"]["owner"]["id"] == agent["id"]

    template = client.get("/api/v1/admin/report-template", params={"ticket": number}, headers=admin_headers).json()
    item = template["items"][0]
    client.put(f"/api/v1/admin/tickets/{number}/report", json={"items": [{k: item[k] for k in ("tag", "label", "guidance", "fetch_by", "source")}]}, headers=admin_headers)
    issued = client.post(f"/api/v1/admin/tickets/{number}/report/issue", headers=admin_headers).json()
    tasks = {t["playbook_key"]: t for t in issued["case"]["tasks"]}
    assert tasks["issue-report"]["status"] == "done" and tasks["chase-documents"]["status"] == "open"

    # Closing is blocked while the report is not signed; open tasks are only a warning.
    blocked = _patch(client, admin_headers, number, status="completed")
    assert blocked.status_code == 409 and "signed final report" in blocked.json()["detail"]
    check = _case(client, admin_headers, number)["case"]["closure"]
    assert not check["can_close"] and check["warnings"]

def test_transitions_close_out_and_reopen(client, admin_headers, raise_ticket):
    number = raise_ticket(service_slug="advocate-consultation")
    assert _patch(client, admin_headers, number, status="in_progress").status_code == 200
    closed = _patch(client, admin_headers, number, status="cancelled", outcome="withdrawn", closure_summary="Buyer dropped the deal.").json()
    assert closed["case"]["closed"]["outcome"] == "withdrawn" and closed["case"]["closure"] is None
    assert all(t["status"] != "open" for t in closed["case"]["tasks"])
    assert closed["case"]["allowed_statuses"] == ["reopened"]

    # A closed case can only be reopened, and only with a reason.
    assert _patch(client, admin_headers, number, status="in_progress").status_code == 409
    assert _patch(client, admin_headers, number, status="reopened").status_code == 422
    reopened = _patch(client, admin_headers, number, status="reopened", note="Buyer is back.").json()
    assert reopened["status"] == "reopened" and reopened["case"]["closed"] is None
    public = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": CONTACT}).json()
    assert public["progress"]["closed"] is None and public["can_reply"]

def test_fee_blocks_close_until_paid_and_admin_override(client, admin_headers, agent, raise_ticket):
    number = raise_ticket(service_slug="advocate-consultation")
    fee = f"/api/v1/admin/tickets/{number}/fee"
    assert client.put(fee, json={"action": "quote"}, headers=admin_headers).status_code == 422
    quoted = client.put(fee, json={"action": "quote", "amount": 15000}, headers=admin_headers).json()
    assert quoted["case"]["fee"]["status"] == "quoted" and _milestones(quoted["case"])["scoped"]
    public = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": CONTACT}).json()
    assert public["progress"]["fee"]["quote"] == 15000 and "15,000" in public["progress"]["next_step"]
    assert "reference" not in public["progress"]["fee"]

    blocked = _patch(client, admin_headers, number, status="completed")
    assert blocked.status_code == 409 and "fee" in blocked.json()["detail"]
    # An agent who owns the case can't override; an admin can, with a reason.
    client.post(f"/api/v1/admin/tickets/{number}/assignment", json={"agent_id": agent["id"]}, headers=admin_headers)
    assert _patch(client, agent["headers"], number, status="completed", override_reason="Paid in cash").status_code == 403

    assert client.put(fee, json={"action": "paid"}, headers=admin_headers).status_code == 422
    paid = client.put(fee, json={"action": "paid", "reference": "UPI 4321"}, headers=admin_headers).json()
    assert paid["case"]["fee"]["status"] == "paid" and paid["case"]["fee"]["paid"] == 15000
    done = _patch(client, agent["headers"], number, status="completed").json()
    assert done["status"] == "completed" and done["case"]["closed"]["outcome"] == "delivered"
    types = [e["type"] for e in done["events"]]
    assert "fee_quoted" in types and "fee_paid" in types and "case_closed" in types

def test_override_close_is_logged(client, admin_headers, raise_ticket):
    number = raise_ticket(service_slug="advocate-consultation")
    client.put(f"/api/v1/admin/tickets/{number}/fee", json={"action": "quote", "amount": 2000}, headers=admin_headers)
    done = _patch(client, admin_headers, number, status="completed", override_reason="Settled outside the platform.").json()
    closed = next(e for e in done["events"] if e["type"] == "case_closed")
    assert closed["new"]["override"] is True and closed["note"] == "Settled outside the platform."

def test_tasks_and_my_tasks(client, admin_headers, agent, raise_ticket):
    number = raise_ticket()
    base = f"/api/v1/admin/tickets/{number}/tasks"
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    created = client.post(base, json={"title": "Call the society secretary", "assignee_id": agent["id"], "due_at": yesterday}, headers=admin_headers).json()
    task = next(t for t in created["case"]["tasks"] if t["source"] == "manual")
    assert task["overdue"] and task["assignee"]["id"] == agent["id"] and created["case"]["overdue_tasks"] >= 1

    # The assignee isn't on the case yet, so they can't open it, but My tasks lists it.
    assert client.get(f"/api/v1/admin/tickets/{number}", headers=agent["headers"]).status_code == 404
    mine = client.get("/api/v1/admin/tasks", headers=agent["headers"]).json()["items"]
    assert [t["title"] for t in mine] == ["Call the society secretary"] and mine[0]["case"]["ticket_number"] == number

    client.post(f"/api/v1/admin/tickets/{number}/members", json={"user_id": agent["id"], "role": "paralegal"}, headers=admin_headers)
    done = client.patch(f"{base}/{task['id']}", json={"status": "done"}, headers=agent["headers"]).json()
    assert next(t for t in done["case"]["tasks"] if t["id"] == task["id"])["status"] == "done"
    assert client.get("/api/v1/admin/tasks", headers=agent["headers"]).json()["items"] == []

def test_case_team_access(client, admin_headers, agent, raise_ticket):
    number = raise_ticket()
    members = f"/api/v1/admin/tickets/{number}/members"
    assert client.get(f"/api/v1/admin/tickets/{number}", headers=agent["headers"]).status_code == 404
    added = client.post(members, json={"user_id": agent["id"], "role": "associate"}, headers=admin_headers).json()
    assert [m["role"] for m in added["case"]["team"]] == ["associate"]
    assert client.get(f"/api/v1/admin/tickets/{number}", headers=agent["headers"]).status_code == 200
    # Members who don't own the case can't change the team.
    assert client.post(members, json={"user_id": agent["id"], "role": "reviewer"}, headers=agent["headers"]).status_code == 403
    removed = client.delete(f"{members}/{agent['id']}", headers=admin_headers).json()
    assert removed["case"]["team"] == []
    assert client.get(f"/api/v1/admin/tickets/{number}", headers=agent["headers"]).status_code == 404

def test_due_date_moves_with_a_reason_and_board_flags_overdue(client, admin_headers, raise_ticket):
    late, fresh = raise_ticket(), raise_ticket(service_slug="advocate-consultation")
    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    assert _patch(client, admin_headers, late, due_at=past).status_code == 422
    moved = _patch(client, admin_headers, late, due_at=past, due_reason="Testing a late case").json()
    assert moved["case"]["deadlines"]["overdue"]

    board = client.get("/api/v1/admin/cases/board", headers=admin_headers).json()
    assert [c["key"] for c in board["columns"]] == ["scoped", "assigned", "documents", "signed", "closed"]
    scoped = board["columns"][0]["cards"]
    assert [c["ticket_number"] for c in scoped][0] == late and {c["ticket_number"] for c in scoped} == {late, fresh}
    assert board["counts"]["open"] == 2 and board["counts"]["overdue"] == 1

def test_first_response_missed_shows_on_board(client, admin_headers, raise_ticket):
    number = raise_ticket()
    with SessionLocal() as db:
        ticket = db.scalars(select(ServiceRequest).where(ServiceRequest.ticket_number == number)).one()
        ticket.first_response_due_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
    board = client.get("/api/v1/admin/cases/board", headers=admin_headers).json()
    assert board["counts"]["first_response_missed"] == 1
    # A reply to the customer meets it, late.
    view = client.post(f"/api/v1/admin/tickets/{number}/messages", json={"message": "Calling you now.", "visibility": "customer"}, headers=admin_headers).json()
    assert view["case"]["deadlines"]["first_response_at"] and view["case"]["deadlines"]["first_response_missed"]
    assert client.get("/api/v1/admin/cases/board", headers=admin_headers).json()["counts"]["first_response_missed"] == 0
