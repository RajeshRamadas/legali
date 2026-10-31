"""Database models. Alembic migrations in backend/migrations are generated from these.

Types are kept portable (JSON becomes JSONB on PostgreSQL) so tests can also run on SQLite.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Table, Text, UniqueConstraint, Uuid, text,
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
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
POST_TYPES = ("article", "case_study")
POST_STATUSES = ("draft", "published")
UPLOADER_TYPES = ("customer", "staff", "system")
# draft: the lawyer is writing the preliminary report. issued: the customer sees it and uploads the documents asked for.
# final_generated: the final PDF is made and waits to be printed and signed. signed: the signed scan is uploaded.
REPORT_STATUSES = ("draft", "issued", "final_generated", "signed")
# received is set when the customer files a document under the item's tag; the lawyer then verifies, rejects or waives it.
REPORT_ITEM_STATUSES = ("pending", "received", "verified", "rejected", "waived")
PAYMENT_STATUSES = ("created", "paid", "refund_due", "refunded")
PAYMENT_PROVIDERS = ("razorpay", "test")
PAYMENT_KINDS = ("checkout", "link")
RERA_STATUSES = ("ongoing", "completed", "lapsed", "revoked", "withdrawn")

class Base(DeclarativeBase):
    pass

class VerificationRun(Base):
    __tablename__ = "verification_runs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), index=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    result: Mapped[dict] = mapped_column(JSONType, nullable=False)

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
    # Staff only: whether the team can phone them now (e.g. a lawyer free for a quick call), with an optional note.
    # The phone number stays inside the staff workspace; customers never see it.
    available_for_calls: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    availability_note: Mapped[str | None] = mapped_column(Text)
    availability_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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

class CustomerAccount(TimestampMixin, Base):
    """A customer who signs in with a code sent to their phone. Their tickets, bookings and payments are the ones
    raised with the same phone number (customers.phone_normalized), so requests made before signing up show too."""
    __tablename__ = "customer_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Last 10 digits, like customers.phone_normalized. Proven by a login code.
    phone_normalized: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Part of every session token; raising it signs the account out on every device.
    token_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)

class LoginCode(Base):
    """A one-time sign-in code sent to a phone. Only a hash of the code is kept."""
    __tablename__ = "login_codes"
    __table_args__ = (
        Index("idx_login_codes_phone_created", "phone_normalized", "created_at"),
        Index("idx_login_codes_client_created", "client_key", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    phone_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set when the code signs someone in, or when a newer code replaces it.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Salted hash of the requester's address (see chat.client_key), to limit codes per address.
    client_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

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
    documents: Mapped[list["Document"]] = relationship(order_by="Document.created_at", lazy="selectin")
    report: Mapped["LegalReport | None"] = relationship(lazy="selectin")

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
        CheckConstraint(_check_in("uploader_type", UPLOADER_TYPES), name="ck_documents_uploader_type"),
        Index("idx_documents_request", "service_request_id"),
        Index("idx_documents_request_tag", "service_request_id", "tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False)
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    checksum_sha256: Mapped[str | None] = mapped_column(Text)
    # Set on files the system keeps for the report: "final_report" (unsigned, staff only) and "signed_report".
    document_category: Mapped[str | None] = mapped_column(Text)
    uploader_type: Mapped[str] = mapped_column(Text, default="customer", server_default="customer", nullable=False)
    # Files a document under a checklist item of the ticket's report (or any label the customer picks), e.g. "sale-deed".
    tag: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    scan_status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    access_classification: Mapped[str] = mapped_column(Text, default="confidential", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class LegalReport(TimestampMixin, Base):
    """A ticket's legal report. Starts as the preliminary report: what the lawyer understands so far and a checklist of
    documents needed, each with a tag the customer files uploads under. Once every item is verified or waived, the lawyer
    generates the final report as a PDF to print, sign and upload back as a scan."""
    __tablename__ = "legal_reports"
    __table_args__ = (CheckConstraint(_check_in("status", REPORT_STATUSES), name="ck_legal_reports_status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="draft", nullable=False)
    # Section key to text, keys from report_templates.PRELIMINARY_SECTIONS and FINAL_SECTIONS.
    preliminary: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    final: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    lawyer_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    # Second signature block on the final report, e.g. the reviewing advocate. Optional.
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="SET NULL"))
    final_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("documents.id", ondelete="SET NULL"))
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list["ReportItem"]] = relationship(back_populates="report", order_by="ReportItem.position", cascade="all, delete-orphan", lazy="selectin")
    lawyer: Mapped[User | None] = relationship(foreign_keys=[lawyer_user_id], lazy="joined")
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewer_user_id], lazy="joined")

class ReportItem(Base):
    """One document the report asks for. Its tag is unique in the report and is what customer uploads are filed under."""
    __tablename__ = "report_items"
    __table_args__ = (
        CheckConstraint(_check_in("status", REPORT_ITEM_STATUSES), name="ck_report_items_status"),
        CheckConstraint(_check_in("fetch_by", ("customer", "homexo")), name="ck_report_items_fetch_by"),
        UniqueConstraint("report_id", "tag", name="uq_report_items_tag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("legal_reports.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tag: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # What exactly to send, e.g. "Certified copy, last 30 years".
    guidance: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(Text, default="pending", nullable=False)
    # Who provides it: the customer uploads it, or Homexo gets it from a government portal (gov_sources.SOURCES key in source).
    fetch_by: Mapped[str] = mapped_column(Text, default="customer", nullable=False)
    source: Mapped[str | None] = mapped_column(Text)
    # The lawyer's note on a rejection (shown to the customer) or verification.
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    report: Mapped[LegalReport] = relationship(back_populates="items")

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

class LawyerProfile(TimestampMixin, Base):
    """A lawyer's public listing: what customers search, compare and book. One per staff member."""
    __tablename__ = "lawyer_profiles"
    __table_args__ = (
        CheckConstraint("experience_years >= 0", name="ck_lawyer_profiles_experience"),
        CheckConstraint("consultation_fee >= 0", name="ck_lawyer_profiles_fee"),
        CheckConstraint("consultation_minutes BETWEEN 15 AND 120", name="ck_lawyer_profiles_minutes"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    headline: Mapped[str] = mapped_column(Text, default="", nullable=False)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    specialisations: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    languages: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    courts: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    experience_years: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Whole rupees for one video consultation.
    consultation_fee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consultation_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    city: Mapped[str] = mapped_column(Text, default="Bengaluru", nullable=False)
    locality: Mapped[str | None] = mapped_column(Text)
    bar_enrolment: Mapped[str | None] = mapped_column(Text)
    education: Mapped[str | None] = mapped_column(Text)
    # Bookable hours by weekday in MEETING_TIMEZONE, e.g. {"mon": [["10:00", "13:00"], ["15:00", "18:00"]]}.
    weekly_hours: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    # Customers only see and book listed profiles.
    is_listed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship(lazy="joined")

class LawyerReview(Base):
    """A customer's rating of a consultation they had. One per meeting."""
    __tablename__ = "lawyer_reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_lawyer_reviews_rating"),
        Index("idx_lawyer_reviews_lawyer_created", "lawyer_user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    lawyer_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    meeting_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Shown as written, e.g. "Priya S."
    reviewer_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class Payment(TimestampMixin, Base):
    """An attempt to collect a booking's consultation fee: a Razorpay order (website Checkout) or payment link (app).

    Card, UPI and bank details stay with Razorpay; only its ids and the outcome are kept here.
    """
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(_check_in("status", PAYMENT_STATUSES), name="ck_payments_status"),
        CheckConstraint(_check_in("provider", PAYMENT_PROVIDERS), name="ck_payments_provider"),
        CheckConstraint(_check_in("kind", PAYMENT_KINDS), name="ck_payments_kind"),
        CheckConstraint("amount_paise > 0", name="ck_payments_amount"),
        Index("idx_payments_request", "service_request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, default="INR", nullable=False)
    status: Mapped[str] = mapped_column(Text, default="created", nullable=False)
    # order_... for Checkout, plink_... for a payment link.
    provider_order_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    pay_url: Mapped[str | None] = mapped_column(Text)
    provider_payment_id: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str | None] = mapped_column(Text)
    # The last failed attempt's reason from Razorpay, shown so the customer can try another way.
    failure_reason: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    service_request: Mapped[ServiceRequest] = relationship()

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

class Post(TimestampMixin, Base):
    """A blog article or case study. Admins write the body in Markdown; the website renders published posts."""
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint(_check_in("post_type", POST_TYPES), name="ck_posts_type"),
        CheckConstraint(_check_in("status", POST_STATUSES), name="ck_posts_status"),
        Index("idx_posts_published", "status", "published_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    post_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="draft", nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cover_image_url: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    # Short facts shown beside a case study, e.g. [{"label": "Location", "value": "Whitefield"}].
    highlights: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    # Set the first time the post is published and kept if it is unpublished and published again.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped[User | None] = relationship(lazy="joined")

class ReraProject(TimestampMixin, Base):
    """A project registered with Karnataka RERA, loaded by app.rera_import (or app.rera_sample in development).
    The public RERA pages and market figures are computed from these rows; nothing here is entered by staff."""
    __tablename__ = "rera_projects"
    __table_args__ = (
        CheckConstraint(_check_in("status", RERA_STATUSES), name="ck_rera_projects_status"),
        Index("idx_rera_projects_promoter", "promoter_slug"),
        Index("idx_rera_projects_locality", "locality_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    registration_no: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # The registration number with "/" and spaces turned into "-", for URLs.
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    promoter_name: Mapped[str] = mapped_column(Text, nullable=False)
    promoter_slug: Mapped[str] = mapped_column(Text, nullable=False)
    project_type: Mapped[str] = mapped_column(Text, default="residential", nullable=False)
    status: Mapped[str] = mapped_column(Text, default="ongoing", nullable=False)
    district: Mapped[str] = mapped_column(Text, nullable=False)
    taluk: Mapped[str | None] = mapped_column(Text)
    locality: Mapped[str] = mapped_column(Text, nullable=False)
    locality_slug: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    pincode: Mapped[str | None] = mapped_column(Text)
    registered_on: Mapped[date | None] = mapped_column(Date)
    registration_valid_until: Mapped[date | None] = mapped_column(Date)
    proposed_completion: Mapped[date | None] = mapped_column(Date)
    revised_completion: Mapped[date | None] = mapped_column(Date)
    completed_on: Mapped[date | None] = mapped_column(Date)
    extensions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_units: Mapped[int | None] = mapped_column(Integer)
    booked_units: Mapped[int | None] = mapped_column(Integer)
    # Units by type, e.g. {"2 BHK": 120, "3 BHK": 60}.
    unit_mix: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    land_area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    price_per_sqft: Mapped[int | None] = mapped_column(Integer)
    complaints: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    # Made-up rows from app.rera_sample, shown with a "sample data" notice. Importing real data removes them.
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
