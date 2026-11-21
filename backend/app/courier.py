"""Staff-recorded tracking for physical document delivery."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from . import admin, tickets
from .db import get_db
from .models import COURIER_STATUSES, CourierShipment, ServiceRequest, User, utcnow
from .security import current_staff

router = APIRouter(prefix="/api/v1")
SERVICE = "document-retrieval-courier"
STATUS_EVENT = "courier_status_recorded"
TRANSITIONS = {
    "dispatched": ("in_transit", "out_for_delivery", "delivered", "delivery_issue", "returned"),
    "in_transit": ("out_for_delivery", "delivered", "delivery_issue", "returned"),
    "out_for_delivery": ("delivered", "delivery_issue", "returned"),
    "delivery_issue": ("in_transit", "out_for_delivery", "delivered", "returned"),
    "delivered": (),
    "returned": (),
}


class ShipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    carrier: str = Field(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f<>]+$")
    tracking_number: str = Field(max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    status: Literal[COURIER_STATUSES]  # type: ignore[valid-type]
    revision: int = Field(ge=0, le=2147483646, strict=True)


def ticket_fields(ticket: ServiceRequest, *, staff: bool = False) -> dict:
    if ticket.service_type.slug != SERVICE:
        return {}
    shipment = ticket.courier_shipment
    if shipment is None:
        return {"courier": None}
    view = {
        "carrier": shipment.carrier,
        "tracking_number": shipment.tracking_number,
        "status": shipment.status,
        "updated_at": tickets.aware(shipment.updated_at).isoformat(),
        "history": [
            {"status": event.new_value["status"], "at": tickets.aware(event.created_at).isoformat()}
            for event in ticket.events
            if event.event_type == STATUS_EVENT and event.new_value
        ][-20:],
    }
    if staff:
        view.update(revision=shipment.revision, next_statuses=TRANSITIONS[shipment.status])
    return {"courier": view}


@router.put("/admin/tickets/{ticket_number}/courier")
def update_shipment(
    ticket_number: str,
    payload: ShipmentUpdate,
    user: User = Depends(current_staff),
    db: Session = Depends(get_db),
):
    # Serialize shipment creation and updates on the existing case row.
    ticket = admin._get_ticket(db, user, ticket_number, lock=True)
    if ticket.service_type.slug != SERVICE:
        raise HTTPException(404, "Courier tracking is available on document retrieval and courier requests.")

    shipment = ticket.courier_shipment
    previous_status = shipment.status if shipment else None
    revision = shipment.revision if shipment else 0
    if shipment and (shipment.status, shipment.carrier, shipment.tracking_number) == (
        payload.status, payload.carrier, payload.tracking_number,
    ):
        return admin._detail(db, ticket)
    if payload.revision != revision:
        raise HTTPException(409, "Courier details changed. Reload the latest shipment before saving.")
    allowed = TRANSITIONS[previous_status] if previous_status else ("dispatched",)
    if payload.status != previous_status and payload.status not in allowed:
        raise HTTPException(409, "This delivery status change is unavailable.")

    if shipment is None:
        shipment = CourierShipment(service_request_id=ticket.id)
        ticket.courier_shipment = shipment
    shipment.status = payload.status
    shipment.carrier = payload.carrier
    shipment.tracking_number = payload.tracking_number
    shipment.revision = revision + 1
    shipment.updated_at = utcnow()

    if previous_status != payload.status:
        tickets.add_event(db, ticket, STATUS_EVENT, user, new={"status": payload.status})
    else:
        tickets.add_event(db, ticket, "courier_details_updated", user)
    tickets.audit(
        db, user, "case.courier_updated", ticket.id,
        previous_status=previous_status, status=payload.status, revision=shipment.revision,
    )
    db.commit()
    return admin._detail(db, ticket)
