def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_services_list(client):
    response = client.get("/api/v1/services")
    assert response.status_code == 200
    assert len(response.json()["items"]) >= 1

def test_ticket_create(raise_ticket):
    assert raise_ticket().startswith("HX-")

def test_ticket_create_accepts_email_contact_from_older_app(client, raise_ticket):
    number = raise_ticket(contact="buyer@example.com", email=None, description="From the app")
    response = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "BUYER@example.com"})
    assert response.status_code == 200

def test_ticket_create_rejects_unknown_service(client):
    response = client.post("/api/v1/tickets", json={
        "customer_name": "A B", "contact": "9876543210", "property_type": "apartment", "service_slug": "nope", "location": "Bengaluru",
    })
    assert response.status_code == 422

def test_ticket_lookup_by_phone_or_email(client, raise_ticket):
    number = raise_ticket()
    for contact in ["9876543210", "+91-98765-43210", "SAMPLE@example.com"]:
        response = client.post("/api/v1/tickets/lookup", json={"ticket_number": number.lower(), "contact": contact})
        assert response.status_code == 200
        body = response.json()
        assert body["ticket_number"] == number
        assert body["service_name"] == "Full Legal Due Diligence"
        assert body["status"] == "submitted"
        assert body["history"][0]["label"] == "Request received"
        assert "customer" not in body and "contact" not in body

def test_ticket_lookup_rejects_wrong_contact(client, raise_ticket):
    number = raise_ticket()
    response = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "9999999999"})
    assert response.status_code == 404

def test_customer_reply_appears_in_thread(client, raise_ticket):
    number = raise_ticket()
    response = client.post("/api/v1/tickets/messages", json={"ticket_number": number, "contact": "9876543210", "message": "Seller sent the EC."})
    assert response.status_code == 201
    assert response.json()["messages"][0]["from"] == "homexo"
    assert "Please upload" in response.json()["messages"][0]["message"]
    assert response.json()["messages"][1:] == [{"from": "you", "message": "Seller sent the EC.", "at": response.json()["messages"][1]["at"]}]

def test_customer_reply_needs_matching_contact(client, raise_ticket):
    number = raise_ticket()
    response = client.post("/api/v1/tickets/messages", json={"ticket_number": number, "contact": "1111111111", "message": "hi"})
    assert response.status_code == 404

def test_returning_customer_is_reused(client, raise_ticket, admin_headers):
    raise_ticket()
    raise_ticket(customer_name="Sample C.", service_slug="title-verification")
    items = client.get("/api/v1/admin/tickets", headers=admin_headers).json()["items"]
    assert len(items) == 2
    details = [client.get(f"/api/v1/admin/tickets/{t['ticket_number']}", headers=admin_headers).json() for t in items]
    assert details[0]["customer"]["id"] == details[1]["customer"]["id"]
    # Each ticket keeps the name as it was typed on that request.
    assert {t["customer_name"] for t in items} == {"Sample Customer", "Sample C."}
