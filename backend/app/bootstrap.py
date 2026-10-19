"""Idempotent startup data: roles, the service catalogue and the first admin."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .catalogue import SERVICES
from .models import Role, ServiceType, User
from .security import hash_password

log = logging.getLogger("homexo")

ROLE_NAMES = ("customer", "agent", "admin", "super_admin")

def sync_reference_data(db: Session) -> None:
    existing_roles = set(db.scalars(select(Role.name)).all())
    for name in ROLE_NAMES:
        if name not in existing_roles:
            db.add(Role(name=name))

    by_slug = {s.slug: s for s in db.scalars(select(ServiceType)).all()}
    for item in SERVICES:
        service = by_slug.pop(item["slug"], None) or ServiceType(slug=item["slug"])
        service.name = item["name"]
        service.category = item["category"]
        service.description = item["description"]
        service.supported_property_types = item["property_types"]
        service.is_active = True
        db.add(service)
    # Services dropped from the catalogue stay in the table for old tickets but can't be requested.
    for retired in by_slug.values():
        retired.is_active = False
    db.flush()

    if config.BOOTSTRAP_ADMIN_EMAIL and config.BOOTSTRAP_ADMIN_PASSWORD:
        admin_role = db.scalars(select(Role).where(Role.name == "admin")).one()
        has_admin = db.scalars(select(User).where(User.roles.any(Role.name.in_(("admin", "super_admin"))))).first()
        if has_admin is None:
            db.add(User(
                display_name=config.BOOTSTRAP_ADMIN_NAME, email=config.BOOTSTRAP_ADMIN_EMAIL.strip().lower(),
                password_hash=hash_password(config.BOOTSTRAP_ADMIN_PASSWORD), roles=[admin_role],
            ))
            log.warning("Created bootstrap admin %s. Change its password and unset BOOTSTRAP_ADMIN_PASSWORD.", config.BOOTSTRAP_ADMIN_EMAIL)
    db.commit()
