from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_services_list():
    response = client.get("/api/v1/services")
    assert response.status_code == 200
    assert len(response.json()["items"]) >= 1

def test_ticket_create():
    response = client.post("/api/v1/tickets", json={
        "customer_name": "Sample Customer",
        "contact": "sample@example.com",
        "property_type": "apartment",
        "service_slug": "certified-copy-ec",
        "location": "Bengaluru",
        "description": "Need assistance with an EC request."
    })
    assert response.status_code == 201
    assert response.json()["ticket_number"].startswith("HX-")

def _raise_ticket(**overrides):
    payload = {
        "customer_name": "Sample Customer",
        "contact": "+91 98765 43210",
        "email": "sample@example.com",
        "property_type": "apartment",
        "service_slug": "legal-due-diligence",
        "package": "Shield Pro",
        "location": "Whitefield, Bengaluru",
        "source": "website",
        **overrides,
    }
    response = client.post("/api/v1/tickets", json=payload)
    assert response.status_code == 201
    return response.json()["ticket_number"]

def test_ticket_description_is_optional():
    assert _raise_ticket().startswith("HX-")

def test_ticket_lookup_by_phone_or_email():
    number = _raise_ticket()
    for contact in ["9876543210", "+91-98765-43210", "SAMPLE@example.com"]:
        response = client.post("/api/v1/tickets/lookup", json={"ticket_number": number.lower(), "contact": contact})
        assert response.status_code == 200
        body = response.json()
        assert body["ticket_number"] == number
        assert body["service_name"] == "Full Legal Due Diligence"
        assert body["status"] == "submitted"
        assert body["history"][0]["label"] == "Request received"
        assert "contact" not in body

def test_ticket_lookup_rejects_wrong_contact():
    number = _raise_ticket()
    response = client.post("/api/v1/tickets/lookup", json={"ticket_number": number, "contact": "9999999999"})
    assert response.status_code == 404

def _chat(message):
    response = client.post("/api/v1/chat", json={"message": message})
    assert response.status_code == 200
    return response.json()

def test_chat_suggests_a_service():
    body = _chat("Is this property safe to buy?")
    assert body["action"] == "request"
    assert body["service"]["slug"] == "title-verification"

def test_chat_prefers_most_specific_topic():
    assert _chat("We need bulk registration for 80 units")["service"]["slug"] == "bulk-registration-operations"
    assert _chat("How much does the Pro package cost?")["service"]["slug"] == "legal-due-diligence"

def test_chat_tracking_extracts_ticket_number():
    body = _chat("what is the status of hx-261018-abc123")
    assert body["action"] == "track"
    assert body["ticket_number"] == "HX-261018-ABC123"

def test_chat_fallback_offers_callback():
    body = _chat("qwerty")
    assert body["service"]["slug"] == "general-guidance"
