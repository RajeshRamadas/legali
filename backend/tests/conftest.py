import os

# Tests run on in-memory SQLite by default; set TEST_DATABASE_URL to run them against PostgreSQL.
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "sqlite://")
os.environ["NOTIFY_WORKER_ENABLED"] = "false"
os.environ["RERA_SAMPLE_WHEN_EMPTY"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import sync_reference_data
from app.db import SessionLocal, engine
from app.main import app
from app.models import Base, Role, User
from app.security import hash_password

PASSWORD = "correct-horse-battery"

@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_reference_data(db)
    yield
    engine.dispose()

@pytest.fixture
def client(database):
    with TestClient(app) as test_client:
        yield test_client

def _make_staff(name: str, email: str, role: str) -> None:
    with SessionLocal() as db:
        db.add(User(display_name=name, email=email, password_hash=hash_password(PASSWORD), roles=[db.scalars(select(Role).where(Role.name == role)).one()]))
        db.commit()

def _login(client: TestClient, email: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

@pytest.fixture
def admin_headers(client):
    _make_staff("Meera Admin", "admin@homexo.test", "admin")
    return _login(client, "admin@homexo.test")

@pytest.fixture
def agent(client):
    _make_staff("Kiran Agent", "kiran@homexo.test", "agent")
    headers = _login(client, "kiran@homexo.test")
    agent_id = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    return {"id": agent_id, "headers": headers}

@pytest.fixture
def raise_ticket(client):
    def _raise(**overrides) -> str:
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
        assert response.status_code == 201, response.text
        return response.json()["ticket_number"]
    return _raise
