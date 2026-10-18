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
        "service_slug": "ec-assistance",
        "location": "Bengaluru",
        "description": "Need assistance with an EC request."
    })
    assert response.status_code == 201
    assert response.json()["ticket_number"].startswith("HX-")
