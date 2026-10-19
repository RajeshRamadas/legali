"""Database models. Alembic migrations in backend/migrations are generated from these.

Types are kept portable (JSON becomes JSONB on PostgreSQL) so tests can also run on SQLite.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, Table, Text, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSONType = JSON().with_variant(JSONB(), "postgresql")

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _check_in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"

TICKET_STATUSES = (
    "draft", "submitted", "under_review", "waiting_for_customer", "approved_for_processing", "assigned",
    "in_progress", "quality_review", "completed", "cancelled", "rejected", "on_hold", "reopened",
)
CLOSED_STATUSES = ("completed", "cancelled", "rejected")
PRIORITIES = ("low", "normal", "high", "urgent")
TICKET_SOURCES = ("website", "chat", "mobile", "phone", "whatsapp", "admin", "referral")
PROPERTY_TYPES = ("apartment", "independent_house", "commercial", "residential_plot", "agricultural_land", "other")
STAFF_ROLES = ("agent", "admin")
MEETING_STATUSES = ("scheduled", "completed", "cancelled")

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("granted_at", DateTime(timezone=True), default=utcnow, nullable=False),
)

class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_check_in("account_status", ("active", "pending_verification", "suspended", "deleted")), name="ck_users_account_status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(Text, unique=True)
    phone: Mapped[str | None] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    account_status: Mapped[str] = mapped_column(Text, default="active", nullable=False)

    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, lazy="selectin")

    @property
    def role_names(self) -> set[str]:
        return {role.name for role in self.roles}

    @property
    def is_admin(self) -> bool:
        return bool(self.role_names & {"admin", "super_admin"})

class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint(_check_in("preferred_contact_channel", ("email", "phone", "sms", "whatsapp", "in_app")), name="ck_customers_channel"),
        Index("idx_customers_phone_normalized", "phone_normalized"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    # Last 10 digits of the phone, used to match ticket lookups however the number was typed.
    phone_normalized: Mapped[str | None] = mapped_column(Text)
    preferred_contact_channel: Mapped[str | None] = mapped_column(Text)

class Property(TimestampMixin, Base):
    __tablename__ = "properties"
    __table_args__ = (CheckConstraint(_check_in("property_type", PROPERTY_TYPES), name="ck_properties_type"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="SET NULL"))
    property_type: Mapped[str] = mapped_column(Text, nullable=False)
    address_line: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    district: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)
    project_or_apartment_name: Mapped[str | None] = mapped_column(Text)
    flat_or_unit_number: Mapped[str | None] = mapped_column(Text)
    property_id_or_pid: Mapped[str | None] = mapped_column(Text)
    survey_number: Mapped[str | None] = mapped_column(Text)
    subdivision_or_surnoc: Mapped[str | None] = mapped_column(Text)
    village: Mapped[str | None] = mapped_column(Text)
    hobli: Mapped[str | None] = mapped_column(Text)
    taluk: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(Text, default="IN", nullable=False)

class ServiceType(TimestampMixin, Base):
    __tablename__ = "service_types"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    supported_property_types: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    required_fields: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    required_documents: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    indicative_fee_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    indicative_fee_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    estimated_turnaround_hours: Mapped[int | None] = mapped_column(Integer)
    location_rules: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    disclaimer: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(_check_in("state", ("active", "submitted", "closed", "abandoned")), name="ck_conversations_state"),
        Index("idx_conversations_client_key", "client_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="SET NULL"))
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id", ondelete="SET NULL"))
    service_type_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_types.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(Text, default="active", nullable=False)
    intake_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    consent_notice_version: Mapped[str | None] = mapped_column(Text)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Salted hash of the chat client's address, for rate limiting across API workers. Never the raw IP.
    client_key: Mapped[str | None] = mapped_column(Text)

    messages: Mapped[list["ConversationMessage"]] = relationship(order_by="ConversationMessage.created_at")

class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        CheckConstraint(_check_in("sender_type", ("customer", "assistant", "system", "agent")), name="ck_conversation_messages_sender"),
        Index("idx_conversation_messages_conversation", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    sender_type: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class ServiceRequest(TimestampMixin, Base):
    __tablename__ = "service_requests"
    __table_args__ = (
        CheckConstraint(_check_in("status", TICKET_STATUSES), name="ck_service_requests_status"),
        CheckConstraint(_check_in("priority", PRIORITIES), name="ck_service_requests_priority"),
        CheckConstraint(_check_in("source", TICKET_SOURCES), name="ck_service_requests_source"),
        Index("idx_requests_status_created", "status", "created_at"),
        Index("idx_requests_customer_created", "customer_id", "created_at"),
        Index("idx_requests_service", "service_type_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ticket_number: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customers.id"), nullable=False)
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id", ondelete="SET NULL"))
    service_type_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_types.id"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    package: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="submitted", nullable=False)
    priority: Mapped[str] = mapped_column(Text, default="normal", nullable=False)
    source: Mapped[str] = mapped_column(Text, default="website", nullable=False)
    structured_answers: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    estimated_fee_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    estimated_fee_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship(lazy="joined")
    prop: Mapped[Property | None] = relationship(lazy="joined")
    service_type: Mapped[ServiceType] = relationship(lazy="joined")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="service_request", order_by="Assignment.assigned_at", lazy="selectin")
    events: Mapped[list["TicketEvent"]] = relationship(order_by="TicketEvent.created_at", lazy="selectin")
    messages: Mapped[list["TicketMessage"]] = relationship(order_by="TicketMessage.created_at", lazy="selectin")
    meetings: Mapped[list["Meeting"]] = relationship(back_populates="service_request", order_by="Meeting.starts_at", lazy="selectin")
    conversation: Mapped[Conversation | None] = relationship()

    @property
    def active_assignment(self) -> "Assignment | None":
        return next((a for a in reversed(self.assignments) if a.unassigned_at is None), None)

class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        Index("idx_assignments_agent_active", "agent_user_id", "assigned_at", postgresql_where=text("unassigned_at IS NULL"), sqlite_where=text("unassigned_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False)
    agent_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"))
    assignment_note: Mapped[str | None] = mapped_column(Text)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service_request: Mapped[ServiceRequest] = relationship(back_populates="assignments")
    agent: Mapped[User] = relationship(foreign_keys=[agent_user_id], lazy="joined")

class TicketEvent(Base):
    __tablename__ = "ticket_events"
    __table_args__ = (Index("idx_events_request_created", "service_request_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[dict | None] = mapped_column(JSONType)
    new_value: Mapped[dict | None] = mapped_column(JSONType)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    actor: Mapped[User | None] = relationship(lazy="joined")

class TicketMessage(Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        CheckConstraint(_check_in("visibility", ("customer", "internal")), name="ck_ticket_messages_visibility"),
        CheckConstraint(_check_in("author_type", ("customer", "staff", "system")), name="ck_ticket_messages_author_type"),
        Index("idx_messages_request_created", "service_request_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    # Customers write without an account, so who wrote a message is recorded here rather than inferred from author_user_id.
    author_type: Mapped[str] = mapped_column(Text, default="staff", nullable=False)
    visibility: Mapped[str] = mapped_column(Text, default="customer", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    author: Mapped[User | None] = relationship(lazy="joined")

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint("byte_size >= 0", name="ck_documents_byte_size"),
        CheckConstraint(_check_in("scan_status", ("pending", "clean", "infected", "failed")), name="ck_documents_scan_status"),
        CheckConstraint(_check_in("access_classification", ("internal", "confidential", "restricted")), name="ck_documents_classification"),
        Index("idx_documents_request", "service_request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(Text)
    document_category: Mapped[str | None] = mapped_column(Text)
    scan_status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    access_classification: Mapped[str] = mapped_column(Text, default="confidential", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class Meeting(TimestampMixin, Base):
    """A video consultation between a ticket's customer and a lawyer (a staff member), with its Google Meet link."""
    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint(_check_in("status", MEETING_STATUSES), name="ck_meetings_status"),
        CheckConstraint("ends_at > starts_at", name="ck_meetings_times"),
        Index("idx_meetings_lawyer_starts", "lawyer_user_id", "starts_at"),
        Index("idx_meetings_request", "service_request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False)
    lawyer_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    agenda: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, default="scheduled", nullable=False)
    meet_link: Mapped[str | None] = mapped_column(Text)
    # Set when the event lives in Google Calendar; null when staff pasted a link themselves.
    calendar_event_id: Mapped[str | None] = mapped_column(Text)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service_request: Mapped[ServiceRequest] = relationship(back_populates="meetings")
    lawyer: Mapped[User] = relationship(foreign_keys=[lawyer_user_id], lazy="joined")

class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(_check_in("channel", ("email", "sms", "whatsapp", "in_app")), name="ck_notifications_channel"),
        CheckConstraint(_check_in("delivery_status", ("queued", "sent", "delivered", "failed", "cancelled")), name="ck_notifications_status"),
        Index("idx_notifications_request", "service_request_id"),
        Index("idx_notifications_due", "delivery_status", "send_after"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="SET NULL"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="SET NULL"))
    # Staff recipient (a lawyer's meeting invite, reminder or daily agenda).
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("meetings.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    template_key: Mapped[str] = mapped_column(Text, nullable=False)
    recipient: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    # Values for the provider's approved message template (WhatsApp needs these for business-initiated messages).
    params: Mapped[list | None] = mapped_column(JSONType)
    # Not sent before this time; reminders are queued ahead with their send time.
    send_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Stops the same reminder or agenda being queued twice.
    dedupe_key: Mapped[str | None] = mapped_column(Text, unique=True)
    delivery_status: Mapped[str] = mapped_column(Text, default="queued", nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Consent(Base):
    __tablename__ = "consents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="SET NULL"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="SET NULL"))
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    notice_version: Mapped[str] = mapped_column(Text, nullable=False)
    consented: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    request_id: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(Text)
    # "metadata" is reserved on declarative models, so the attribute name differs from the column.
    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
