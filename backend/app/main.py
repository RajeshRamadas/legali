from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from uuid import uuid4
from datetime import datetime, timezone
import os

app = FastAPI(
    title="Homexo Property Services API",
    version="0.1.0",
    description="Starter API for Homexo service discovery and ticket intake."
)

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

SERVICES = [
    {
        "slug": "home-apartment-assistance",
        "name": "Home & Apartment Assistance",
        "category": "Homes",
        "description": "Help coordinating common home and apartment property-service requests.",
        "property_types": ["apartment", "independent_house", "commercial"],
    },
    {
        "slug": "ec-assistance",
        "name": "Encumbrance Certificate Assistance",
        "category": "Legal & Documents",
        "description": "Assistance understanding and requesting EC-related records through authorized channels.",
        "property_types": ["apartment", "independent_house", "residential_plot", "agricultural_land", "commercial"],
    },
    {
        "slug": "khata-property-records",
        "name": "Khata & Property Records",
        "category": "Legal & Documents",
        "description": "Assistance with khata and property account documentation.",
        "property_types": ["apartment", "independent_house", "residential_plot", "commercial"],
    },
    {
        "slug": "rtc-mutation-assistance",
        "name": "RTC / Mutation Assistance",
        "category": "Land & Plots",
        "description": "Assistance organizing details for RTC/Pahani and mutation record requests.",
        "property_types": ["agricultural_land", "residential_plot"],
    },
    {
        "slug": "plot-maintenance",
        "name": "Plot Cleaning & Maintenance",
        "category": "Maintenance",
        "description": "Request plot cleaning, inspection, fencing or related maintenance where available.",
        "property_types": ["residential_plot"],
    },
    {
        "slug": "property-inspection",
        "name": "Property Inspection & Report",
        "category": "Inspection",
        "description": "Request a property visit and photo/video condition report.",
        "property_types": ["apartment", "independent_house", "residential_plot", "commercial"],
    },
]

class TicketCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    contact: str = Field(min_length=5, max_length=254)
    property_type: str = Field(min_length=2, max_length=40)
    service_slug: str = Field(min_length=2, max_length=100)
    location: str = Field(min_length=2, max_length=180)
    description: str = Field(min_length=5, max_length=4000)

# DEMO ONLY: in-memory storage is cleared whenever the API restarts.
# Replace with PostgreSQL repositories, authentication, verification and audit logging.
TICKETS: list[dict] = []

@app.get("/health")
def health():
    return {"status": "ok", "service": "homexo-api"}

@app.get("/api/v1/services")
def list_services():
    return {"items": SERVICES}

@app.get("/api/v1/services/{slug}")
def get_service(slug: str):
    service = next((item for item in SERVICES if item["slug"] == slug), None)
    if service is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@app.post("/api/v1/tickets", status_code=201)
def create_ticket(payload: TicketCreate):
    if not any(service["slug"] == payload.service_slug for service in SERVICES):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Unknown service_slug")
    ticket = {
        "id": str(uuid4()),
        "ticket_number": f"HX-{datetime.now(timezone.utc):%y%m%d}-{uuid4().hex[:6].upper()}",
        **payload.model_dump(),
        "status": "submitted",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    TICKETS.append(ticket)
    return {
        "ticket_number": ticket["ticket_number"],
        "status": ticket["status"],
        "message": "Request received. An operations team member must review scope, availability and any estimate.",
    }

@app.get("/api/v1/demo/tickets")
def list_demo_tickets():
    """Development-only demo endpoint. Remove or protect before any deployment."""
    return {"items": TICKETS}
