"""Verified customer choices for optional transactional alerts; authentication is separate."""
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from .customer_auth import current_customer
from .db import get_db
from .models import AuditLog, Customer, CustomerAccount, CustomerNotificationPreference, Notification, utcnow

router = APIRouter(prefix="/api/v1/account/notification-preferences")
CHANNELS = ("email", "sms", "whatsapp")


def view(preference):
    if preference is None:
        return {"email": True, "sms": True, "whatsapp": True, "revision": 0, "updated_at": None}
    value = preference.updated_at
    return {**{channel: getattr(preference, channel) for channel in CHANNELS}, "revision": preference.revision,
        "updated_at": (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()}


def delivery_allowed(db: Session, notification: Notification) -> bool:
    if notification.channel not in CHANNELS or notification.user_id is not None:
        return True
    if notification.account_id is not None:
        enabled = db.scalar(select(getattr(CustomerNotificationPreference, notification.channel))
            .where(CustomerNotificationPreference.account_id == notification.account_id))
        return enabled is not False
    if notification.customer_id is None:
        return True
    # Query scalar values every time, including after a worker's claim commit;
    # the session identity map must not retain an old channel choice.
    enabled = db.scalar(select(getattr(CustomerNotificationPreference, notification.channel))
        .join(CustomerAccount, CustomerAccount.id == CustomerNotificationPreference.account_id)
        .join(Customer, Customer.phone_normalized == CustomerAccount.phone_normalized)
        .where(Customer.id == notification.customer_id))
    return enabled is not False


def queue_customer_notification(db: Session, **values) -> None:
    notification = Notification(**values)
    if not delivery_allowed(db, notification):
        notification.delivery_status, notification.error_code = "cancelled", "preference_disabled"
    db.add(notification)


@router.get("")
def preferences(account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    return view(db.get(CustomerNotificationPreference, account.id))


class Choices(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: bool = Field(strict=True)
    sms: bool = Field(strict=True)
    whatsapp: bool = Field(strict=True)
    revision: int = Field(strict=True, ge=0, le=2147483646)


@router.put("")
def save_preferences(payload: Choices, account: CustomerAccount = Depends(current_customer), db: Session = Depends(get_db)):
    # Serialize first-time creation as well as later updates across devices.
    db.execute(select(CustomerAccount.id).where(CustomerAccount.id == account.id).with_for_update())
    preference = db.get(CustomerNotificationPreference, account.id, populate_existing=True)
    current = view(preference)
    if payload.revision != current["revision"]:
        raise HTTPException(409, "Your notification preferences changed on another device. Reload the saved choices before saving again.")
    values = {channel: getattr(payload, channel) for channel in CHANNELS}
    if preference is not None and all(values[channel] == current[channel] for channel in CHANNELS):
        return current
    if preference is None:
        preference = CustomerNotificationPreference(account_id=account.id)
        db.add(preference)
    for channel, value in values.items():
        setattr(preference, channel, value)
    preference.revision, preference.updated_at = current["revision"] + 1, utcnow()
    disabled = [channel for channel, enabled in values.items() if not enabled]
    if disabled:
        customers = select(Customer.id).where(Customer.phone_normalized == account.phone_normalized)
        db.execute(update(Notification).where(or_(Notification.customer_id.in_(customers), Notification.account_id == account.id), Notification.user_id.is_(None),
            Notification.channel.in_(disabled), Notification.delivery_status == "queued")
            .values(delivery_status="cancelled", error_code="preference_disabled", claim_token=None, processing_until=None))
    db.add(AuditLog(action="notification.preferences_changed", entity_type="customer_account", entity_id=account.id,
        metadata_={"source": "customer", "channels": values, "revision": preference.revision}))
    db.commit()
    return view(preference)
