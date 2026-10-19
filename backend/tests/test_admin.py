def test_admin_routes_need_sign_in(client):
    assert client.get("/api/v1/admin/tickets").status_code == 401
    assert client.get("/api/v1/admin/tickets", headers={"Authorization": "Bearer nonsense"}).status_code == 401

def test_login_rejects_wrong_password(client, admin_headers):
    response = client.post("/api/v1/auth/login", json={"email": "admin@homexo.test", "password": "wrong"})
    assert response.status_code == 401

def test_admin_sees_new_ticket_in_queue(client, admin_headers, raise_ticket):
    number = raise_ticket()
    body = client.get("/api/v1/admin/tickets", headers=admin_headers).json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["ticket_number"] == number
    assert item["assignee"] is None and item["status"] == "submitted"
    summary = client.get("/api/v1/admin/reports/summary", headers=admin_headers).json()
    assert summary["open"] == 1 and summary["unassigned"] == 1 and summary["new_today"] == 1

def test_queue_filters(client, admin_headers, agent, raise_ticket):
    first = raise_ticket()
    raise_ticket(customer_name="Other Person", contact="9000000001", email=None, location="JP Nagar", service_slug="title-verification")
    client.post(f"/api/v1/admin/tickets/{first}/assignment", json={"agent_id": agent["id"]}, headers=admin_headers)

    def numbers(**params):
        return [t["ticket_number"] for t in client.get("/api/v1/admin/tickets", params=params, headers=admin_headers).json()["items"]]

    assert numbers(assignee="unassigned") != [first] and len(numbers(assignee="unassigned")) == 1
    assert numbers(assignee=agent["id"]) == [first]
    assert numbers(service="legal-due-diligence") == [first]
    assert len(numbers(q="jp nagar")) == 1
    assert numbers(q="98765") == [first]
    assert numbers(q=first[-6:].lower()) == [first]
    assert len(numbers(status="open")) == 2 and numbers(status="closed") == []

def test_status_change_is_visible_to_customer_and_notifies(client, admin_headers, raise_ticket):
    number = raise_ticket()
    response = client.patch(f"/api/v1/admin/tickets/{number}", json={"status": "waiting_for_customer", "note": "Please share the Mother Deed."}, headers=admin_headers)
    assert response.status_code == 200
    detail = response.json()
    assert detail["status_label"] == "Waiting for customer"
    assert [n["template"] for n in detail["notifications"]].count("status_changed") == 2  # SMS and email

    public = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "9876543210"}).json()
    assert public["history"][-1] == {**public["history"][-1], "label": "Waiting for your reply", "note": "Please share the Mother Deed."}

    # The customer's reply hands it back to the team.
    reply = client.post("/api/v1/tickets/messages", json={"ticket_number": number, "contact": "9876543210", "message": "Uploaded to email."}).json()
    assert reply["status"] == "under_review"
    assert client.get("/api/v1/admin/reports/summary", headers=admin_headers).json()["needs_reply"] == 1
    waiting = client.get("/api/v1/admin/tickets", params={"needs_reply": "true"}, headers=admin_headers).json()["items"]
    assert [t["ticket_number"] for t in waiting] == [number] and waiting[0]["needs_reply"]
    # Answering clears it.
    client.post(f"/api/v1/admin/tickets/{number}/messages", json={"message": "Got it, thanks.", "visibility": "customer"}, headers=admin_headers)
    assert client.get("/api/v1/admin/reports/summary", headers=admin_headers).json()["needs_reply"] == 0

def test_internal_notes_stay_internal(client, admin_headers, raise_ticket):
    number = raise_ticket()
    client.post(f"/api/v1/admin/tickets/{number}/messages", json={"message": "Seller seems evasive", "visibility": "internal"}, headers=admin_headers)
    detail = client.post(f"/api/v1/admin/tickets/{number}/messages", json={"message": "We'll call you at 4 pm.", "visibility": "customer"}, headers=admin_headers).json()
    assert [m["visibility"] for m in detail["messages"]] == ["internal", "customer"]
    public = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "9876543210"}).json()
    assert [m["message"] for m in public["messages"]] == ["We'll call you at 4 pm."]

def test_agent_sees_only_assigned_tickets(client, admin_headers, agent, raise_ticket):
    mine = raise_ticket()
    other = raise_ticket(contact="9000000002", email=None)
    detail = client.post(f"/api/v1/admin/tickets/{mine}/assignment", json={"agent_id": agent["id"], "note": "Whitefield cases"}, headers=admin_headers).json()
    assert detail["assignee"]["name"] == "Kiran Agent"
    assert detail["status"] == "assigned"

    items = client.get("/api/v1/admin/tickets", headers=agent["headers"]).json()["items"]
    assert [t["ticket_number"] for t in items] == [mine]
    assert client.get(f"/api/v1/admin/tickets/{other}", headers=agent["headers"]).status_code == 404
    assert client.patch(f"/api/v1/admin/tickets/{other}", json={"status": "in_progress"}, headers=agent["headers"]).status_code == 404
    assert client.patch(f"/api/v1/admin/tickets/{mine}", json={"status": "in_progress"}, headers=agent["headers"]).status_code == 200
    # Agents can't reassign or manage staff.
    assert client.post(f"/api/v1/admin/tickets/{mine}/assignment", json={"agent_id": None}, headers=agent["headers"]).status_code == 403
    assert client.post("/api/v1/admin/staff", json={"display_name": "X Y", "email": "x@y.test", "password": "long-enough-pw", "role": "admin"}, headers=agent["headers"]).status_code == 403

def test_reassign_and_unassign(client, admin_headers, agent, raise_ticket):
    number = raise_ticket()
    client.post(f"/api/v1/admin/tickets/{number}/assignment", json={"agent_id": agent["id"]}, headers=admin_headers)
    detail = client.post(f"/api/v1/admin/tickets/{number}/assignment", json={"agent_id": None}, headers=admin_headers).json()
    assert detail["assignee"] is None
    assert [e["type"] for e in detail["events"]][-1] == "unassigned"
    assert client.get("/api/v1/admin/tickets", headers=agent["headers"]).json()["items"] == []

def test_admin_manages_staff(client, admin_headers):
    created = client.post("/api/v1/admin/staff", json={"display_name": "New Agent", "email": "New@Homexo.test", "password": "long-enough-pw", "role": "agent"}, headers=admin_headers)
    assert created.status_code == 201
    assert client.post("/api/v1/auth/login", json={"email": "new@homexo.test", "password": "long-enough-pw"}).status_code == 200
    duplicate = client.post("/api/v1/admin/staff", json={"display_name": "Dup", "email": "new@homexo.test", "password": "long-enough-pw", "role": "agent"}, headers=admin_headers)
    assert duplicate.status_code == 409
    suspended = client.patch(f"/api/v1/admin/staff/{created.json()['id']}", json={"account_status": "suspended"}, headers=admin_headers)
    assert suspended.json()["account_status"] == "suspended"
    assert client.post("/api/v1/auth/login", json={"email": "new@homexo.test", "password": "long-enough-pw"}).status_code == 401
    names = [s["name"] for s in client.get("/api/v1/admin/staff", headers=admin_headers).json()["items"]]
    assert names == ["Meera Admin", "New Agent"]

def test_admin_cannot_lock_themselves_out(client, admin_headers):
    me = client.get("/api/v1/auth/me", headers=admin_headers).json()
    assert client.patch(f"/api/v1/admin/staff/{me['id']}", json={"role": "agent"}, headers=admin_headers).status_code == 422

def test_closed_ticket_rejects_customer_reply(client, admin_headers, raise_ticket):
    number = raise_ticket()
    client.patch(f"/api/v1/admin/tickets/{number}", json={"status": "completed"}, headers=admin_headers)
    response = client.post("/api/v1/tickets/messages", json={"ticket_number": number, "contact": "9876543210", "message": "one more thing"})
    assert response.status_code == 409
