"""Database models. Alembic migrations in backend/migrations are generated from these.

Types are kept portable (JSON becomes JSONB on PostgreSQL) so tests can also run on SQLite.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON, BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Table, Text, UniqueConstraint, Uuid, event, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from . import audit_guard_v1

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
PROPERTY_TYPES = (
    "apartment", "villa", "independent_house", "commercial", "residential_plot", "agricultural_land", "farmhouse", "plantation_estate",
    "industrial_land", "other",
)
STAFF_ROLES = ("agent", "admin")
MEETING_STATUSES = ("scheduled", "completed", "cancelled")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
POST_TYPES = ("article", "case_study")
POST_STATUSES = ("draft", "published")
POST_ORIGINS = ("manual", "ai")
CASE_SCAN_TRIGGERS = ("schedule", "admin", "cli")
CASE_SCAN_STATUSES = ("running", "done", "failed")
CASE_LEAD_STATUSES = ("new", "drafting", "drafted", "dismissed", "failed")
UPLOADER_TYPES = ("customer", "staff", "system")
# draft: the lawyer is writing the preliminary report. issued: the customer sees it and uploads the documents asked for.
# final_generated: the final PDF is made and waits to be printed and signed. signed: the signed scan is uploaded.
REPORT_STATUSES = ("draft", "issued", "final_generated", "signed")
# received is set when the customer files a document under the item's tag; the lawyer then verifies, rejects or waives it.
REPORT_ITEM_STATUSES = ("pending", "received", "verified", "rejected", "waived")
PAYMENT_STATUSES = ("created", "paid", "refund_due", "refunded")
PAYMENT_PROVIDERS = ("razorpay", "test")
PAYMENT_KINDS = ("checkout", "link")
# Case management (case_management.py): the case is the ticket; these add its team, tasks, close-out and fee.
CASE_TASK_STATUSES = ("open", "done", "cancelled")
CASE_TASK_SOURCES = ("manual", "playbook")
CASE_MEMBER_ROLES = ("associate", "paralegal", "reviewer")
CLOSURE_OUTCOMES = ("delivered", "withdrawn", "not_viable", "duplicate", "other")
FEE_STATUSES = ("none", "quoted", "paid", "waived")
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


class VerificationJob(Base):
    __tablename__ = "verification_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','completed','failed','cancelled','stale')", name="ck_verification_job_status"),
        CheckConstraint("phase IN ('queued','extracting','analysing','finalizing','finished')", name="ck_verification_job_phase"),
        UniqueConstraint("service_request_id", "submission_key", name="uq_verification_job_submission"),
        Index("uq_verification_job_active", "service_request_id", unique=True,
            postgresql_where=text("status IN ('queued','running')"), sqlite_where=text("status IN ('queued','running')")),
        Index("ix_verification_job_queue", "status", "created_at"),
        Index("ix_verification_job_case", "service_request_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"))
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    submission_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    request: Mapped[dict] = mapped_column(JSONType, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(Text, default="queued", nullable=False)
    phase: Mapped[str] = mapped_column(Text, default="queued", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("verification_runs.id", ondelete="SET NULL"))
    reason_code: Mapped[str | None] = mapped_column(Text)

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
    token_version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(Text)  # Fernet ciphertext, never a plaintext seed.
    mfa_pending_secret: Mapped[str | None] = mapped_column(Text)
    mfa_pending_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_last_counter: Mapped[int | None] = mapped_column(BigInteger)
    mfa_recovery_hashes: Mapped[list | None] = mapped_column(JSONType)
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

class StaffAuthToken(Base):
    __tablename__ = "staff_auth_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class StaffAuthBucket(Base):
    __tablename__ = "staff_auth_buckets"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)

class ApiRateBucket(Base):
    __tablename__ = "api_rate_buckets"
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)

class WorkerPulse(Base):
    """Latest observations of a logical worker group, shared across API/CLI processes."""
    __tablename__ = "worker_pulses"
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)

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

class CustomerNotificationPreference(Base):
    __tablename__ = "customer_notification_preferences"
    __table_args__ = (CheckConstraint("revision >= 1", name="ck_customer_notification_preferences_revision"),)

    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customer_accounts.id", ondelete="CASCADE"), primary_key=True)
    email: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sms: Mapped[bool] = mapped_column(Boolean, nullable=False)
    whatsapp: Mapped[bool] = mapped_column(Boolean, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

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
    __table_args__ = (CheckConstraint("availability_revision >= 1", name="ck_service_availability_revision"),
        CheckConstraint("description_revision >= 1", name="ck_service_description_revision"),
        CheckConstraint("intake_form_revision >= 1", name="ck_service_intake_form_revision"),
        CheckConstraint("description_override IS NULL OR length(description_override) BETWEEN 10 AND 800", name="ck_service_description_length"))

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    description_override: Mapped[str | None] = mapped_column(Text)
    description_revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    intake_questions: Mapped[list] = mapped_column(JSONType, default=list, server_default=text("'[]'"), nullable=False)
    intake_form_revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
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
    intake_paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    availability_revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)

class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(_check_in("state", ("active", "submitted", "closed", "abandoned")), name="ck_conversations_state"),
        Index("idx_conversations_client_key", "client_key"),
        Index("ix_conversations_retention", "retention_hold", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customer_accounts.id", ondelete="SET NULL", name="fk_conversations_account"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="SET NULL"))
    property_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("properties.id", ondelete="SET NULL"))
    service_type_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_types.id", ondelete="SET NULL"))
    state: Mapped[str] = mapped_column(Text, default="active", nullable=False)
    intake_data: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    consent_notice_version: Mapped[str | None] = mapped_column(Text)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Salted hash of the chat client's address, for rate limiting across API workers. Never the raw IP.
    client_key: Mapped[str | None] = mapped_column(Text)
    retention_hold: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)

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
        Index("idx_requests_status_due", "status", "due_at"),
        CheckConstraint(_check_in("fee_status", FEE_STATUSES), name="ck_service_requests_fee_status"),
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
    # Case management. First response: the first staff action the customer sees (message, status change, assignment).
    first_response_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_pause_seconds: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"), nullable=False)
    closure_outcome: Mapped[str | None] = mapped_column(Text)
    closure_summary: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The fee for the legal work (consultation booking fees stay in payments).
    fee_status: Mapped[str] = mapped_column(Text, default="none", server_default=text("'none'"), nullable=False)
    fee_quote_paise: Mapped[int | None] = mapped_column(Integer)
    fee_paid_paise: Mapped[int | None] = mapped_column(Integer)
    fee_reference: Mapped[str | None] = mapped_column(Text)
    fee_paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fee_note: Mapped[str | None] = mapped_column(Text)

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
    tasks: Mapped[list["CaseTask"]] = relationship(back_populates="service_request", order_by="CaseTask.created_at", lazy="selectin", cascade="all, delete-orphan")
    members: Mapped[list["CaseMember"]] = relationship(order_by="CaseMember.added_at", lazy="selectin", cascade="all, delete-orphan")

    @property
    def active_assignment(self) -> "Assignment | None":
        return next((a for a in reversed(self.assignments) if a.unassigned_at is None), None)

class CaseDeadlineAlert(Base):
    __tablename__ = "case_deadline_alerts"
    __table_args__ = (
        UniqueConstraint("service_request_id", "kind", "target_at", name="uq_case_deadline_alert_target"),
        CheckConstraint(_check_in("kind", ("case_due", "first_response")), name="ck_case_deadline_alert_kind"),
        Index("idx_case_deadline_alert_open", "resolved_at", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    target_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class IntakeDraft(TimestampMixin, Base):
    __tablename__ = "intake_drafts"
    __table_args__ = (
        CheckConstraint(_check_in("status", ("draft", "submitted", "discarded")), name="ck_intake_drafts_status"),
        Index("idx_intake_drafts_account_created", "account_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customer_accounts.id", ondelete="CASCADE"), nullable=False)
    answers: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    service_form_snapshot: Mapped[dict] = mapped_column(JSONType, default=dict, server_default=text("'{}'"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    status: Mapped[str] = mapped_column(Text, default="draft", nullable=False)
    saving_notice_version: Mapped[str] = mapped_column(Text, nullable=False)
    saving_consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="SET NULL"), unique=True)

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

class CaseMember(Base):
    """A staff member helping on a case besides its owner (the active Assignment). Members can open the case."""
    __tablename__ = "case_members"
    __table_args__ = (
        CheckConstraint(_check_in("role", CASE_MEMBER_ROLES), name="ck_case_members_role"),
        Index("idx_case_members_user_active", "user_id", postgresql_where=text("removed_at IS NULL"), sqlite_where=text("removed_at IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined")

class CaseTask(Base):
    """A to-do on a case. Playbook tasks are added and ticked off by case_management.sync as the case moves on."""
    __tablename__ = "case_tasks"
    __table_args__ = (
        CheckConstraint(_check_in("status", CASE_TASK_STATUSES), name="ck_case_tasks_status"),
        CheckConstraint(_check_in("source", CASE_TASK_SOURCES), name="ck_case_tasks_source"),
        Index("idx_case_tasks_request", "service_request_id"),
        Index("idx_case_tasks_assignee_open", "assignee_user_id", "due_at", postgresql_where=text("status = 'open'"), sqlite_where=text("status = 'open'")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="open", nullable=False)
    source: Mapped[str] = mapped_column(Text, default="manual", nullable=False)
    playbook_key: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_user_id], lazy="joined")
    service_request: Mapped["ServiceRequest"] = relationship(back_populates="tasks", lazy="joined")

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
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_detail: Mapped[str | None] = mapped_column(Text)
    access_classification: Mapped[str] = mapped_column(Text, default="confidential", nullable=False)
    # Result of the automatic upload check (app.upload_check): document type, legibility, dates and problems.
    ai_check: Mapped[dict | None] = mapped_column(JSONType)
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

class LawyerTimeOff(Base):
    __tablename__ = "lawyer_time_off"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_lawyer_time_off_range"),
        UniqueConstraint("lawyer_user_id", "submission_key", name="uq_lawyer_time_off_submission"),
        Index("ix_lawyer_time_off_window", "lawyer_user_id", "starts_at", "ends_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    lawyer_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    submission_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))

class LawyerReview(Base):
    """A customer's rating of a consultation they had. One per meeting."""
    __tablename__ = "lawyer_reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_lawyer_reviews_rating"),
        Index("idx_lawyer_reviews_lawyer_created", "lawyer_user_id", "created_at"),
        CheckConstraint("moderation_status IN ('pending','published','hidden') AND revision >= 1", name="ck_lawyer_review_moderation"),
        CheckConstraint("withdrawn_at IS NULL OR moderation_status = 'hidden'", name="ck_lawyer_review_withdrawal"),
        Index("ix_lawyer_review_moderation_queue", "moderation_status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    lawyer_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    meeting_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Shown as written, e.g. "Priya S."
    reviewer_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    moderation_status: Mapped[str] = mapped_column(Text, default="pending", server_default="pending", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def publication_status(self):
        return "withdrawn" if self.withdrawn_at is not None else self.moderation_status

class LawyerReviewDecision(Base):
    __tablename__ = "lawyer_review_decisions"
    __table_args__ = (
        UniqueConstraint("review_id", "revision", name="uq_lawyer_review_decision_revision"),
        CheckConstraint("from_status IN ('pending','published','hidden') AND to_status IN ('published','hidden') AND from_status <> to_status AND revision >= 2", name="ck_lawyer_review_decision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    review_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("lawyer_reviews.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    from_status: Mapped[str] = mapped_column(Text, nullable=False)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
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
        CheckConstraint("refunded_paise >= 0 AND refunded_paise <= amount_paise AND refund_pending_paise >= 0", name="ck_payment_refund_amounts"),
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
    refunded_paise: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"), nullable=False)
    refund_pending_paise: Mapped[int] = mapped_column(BigInteger, default=0, server_default=text("0"), nullable=False)
    refund_review_reason: Mapped[str | None] = mapped_column(Text)

    service_request: Mapped[ServiceRequest] = relationship()

class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (
        UniqueConstraint("provider_refund_id", name="uq_refund_provider_id"),
        CheckConstraint("status IN ('pending','processed','failed')", name="ck_refund_status"),
        CheckConstraint("amount_paise > 0 AND revision >= 1", name="ck_refund_values"),
        Index("ix_refund_provider_payment", "provider_payment_id"),
        Index("ix_refund_payment_status", "payment_id", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("payments.id", ondelete="SET NULL"))
    provider_refund_id: Mapped[str] = mapped_column(Text, nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(Text, nullable=False)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    review_code: Mapped[str | None] = mapped_column(Text)
    internal_note: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(_check_in("channel", ("email", "sms", "whatsapp", "in_app")), name="ck_notifications_channel"),
        CheckConstraint(_check_in("delivery_status", ("queued", "sent", "delivered", "failed", "cancelled")), name="ck_notifications_status"),
        Index("idx_notifications_request", "service_request_id"),
        Index("idx_notifications_due", "delivery_status", "send_after"),
        Index("idx_notifications_account", "account_id", "delivery_status"),
        Index("idx_notifications_support", "support_request_id", "delivery_status"),
        CheckConstraint("(template_key = 'support_reply' AND support_update_revision IS NOT NULL AND support_update_revision >= 1 AND customer_id IS NULL AND user_id IS NULL AND service_request_id IS NULL AND meeting_id IS NULL AND case_alert_id IS NULL) OR (template_key <> 'support_reply' AND account_id IS NULL AND support_request_id IS NULL AND support_update_revision IS NULL)", name="ck_notifications_support_scope"),
        CheckConstraint("(template_key = 'support_deadline_email' AND channel = 'email' AND support_alert_revision IS NOT NULL AND support_alert_revision >= 1 AND customer_id IS NULL AND account_id IS NULL AND support_request_id IS NULL AND support_update_revision IS NULL AND service_request_id IS NULL AND meeting_id IS NULL AND case_alert_id IS NULL) OR (template_key <> 'support_deadline_email' AND support_alert_id IS NULL AND support_alert_revision IS NULL)", name="ck_notifications_support_alert_scope"),
        Index("idx_notifications_support_alert", "support_alert_id", "delivery_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    service_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="SET NULL"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customers.id", ondelete="SET NULL"))
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("customer_accounts.id", ondelete="SET NULL", name="fk_notifications_account"))
    support_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("support_requests.id", ondelete="SET NULL", name="fk_notifications_support"))
    support_update_revision: Mapped[int | None] = mapped_column(Integer)
    support_alert_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("support_deadline_alerts.id", ondelete="SET NULL", name="fk_notifications_support_alert"))
    support_alert_revision: Mapped[int | None] = mapped_column(Integer)
    # Staff recipient (a lawyer's meeting invite, reminder or daily agenda).
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    meeting_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("meetings.id", ondelete="SET NULL"))
    case_alert_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("case_deadline_alerts.id", ondelete="SET NULL", name="fk_notifications_case_alert"), index=True)
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
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    provider_reference: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class PrivacyRequest(TimestampMixin, Base):
    __tablename__ = "privacy_requests"
    __table_args__ = (
        CheckConstraint("kind IN ('access','correction','deletion')", name="ck_privacy_requests_kind"),
        CheckConstraint("status IN ('submitted','in_review','closed','withdrawn')", name="ck_privacy_requests_status"),
        CheckConstraint("resolution IS NULL OR resolution IN ('fulfilled','partial','declined')", name="ck_privacy_requests_resolution"),
        CheckConstraint("revision >= 1", name="ck_privacy_requests_revision"),
        UniqueConstraint("account_id", "submission_key", name="uq_privacy_requests_submission"),
        Index("uq_privacy_requests_open_kind", "account_id", "kind", unique=True,
            postgresql_where=text("status IN ('submitted','in_review')"), sqlite_where=text("status IN ('submitted','in_review')")),
        Index("ix_privacy_requests_queue", "status", "due_at"),
        Index("ix_privacy_requests_account_created", "account_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customer_accounts.id", ondelete="RESTRICT"), nullable=False)
    service_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="SET NULL"))
    submission_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    notice_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="submitted", server_default="submitted", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(Text)
    retention_reason: Mapped[str | None] = mapped_column(Text)
    customer_response: Mapped[str | None] = mapped_column(Text)
    internal_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))

class SupportRequest(TimestampMixin, Base):
    __tablename__ = "support_requests"
    __table_args__ = (
        CheckConstraint("kind IN ('case_update','documents','payment','complaint','other')", name="ck_support_kind"),
        CheckConstraint("status IN ('open','in_progress','waiting_for_customer','resolved')", name="ck_support_status"),
        CheckConstraint("revision >= 1", name="ck_support_revision"),
        CheckConstraint("customer_update_revision >= 0 AND customer_read_revision >= 0 AND customer_read_revision <= customer_update_revision", name="ck_support_unread_replies"),
        UniqueConstraint("account_id", "submission_key", name="uq_support_submission"),
        Index("ix_support_account_created", "account_id", "created_at"),
        Index("ix_support_queue", "status", "reply_due_at"),
        Index("ix_support_owner_queue", "assignee_user_id", "status", "reply_due_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("customer_accounts.id", ondelete="RESTRICT"), nullable=False)
    service_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("service_requests.id", ondelete="SET NULL"))
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL", name="fk_support_request_owner"))
    submission_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="open", server_default="open", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    # Counts only customer-visible staff responses, independently of internal revisions.
    customer_update_revision: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    customer_read_revision: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"), nullable=False)
    reply_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportDeadlineAlert(Base):
    __tablename__ = "support_deadline_alerts"
    __table_args__ = (
        UniqueConstraint("support_request_id", "target_at", name="uq_support_deadline_target"),
        CheckConstraint("revision >= 1", name="ck_support_deadline_revision"),
        Index("ix_support_deadline_active", "resolved_at", "acknowledged_at", "target_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    support_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("support_requests.id", ondelete="CASCADE"), nullable=False)
    target_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"), nullable=False)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportMessage(Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        CheckConstraint("author_type IN ('customer','staff')", name="ck_support_message_author"),
        CheckConstraint("visibility IN ('customer','internal')", name="ck_support_message_visibility"),
        CheckConstraint("author_type = 'staff' OR visibility = 'customer'", name="ck_support_customer_visibility"),
        UniqueConstraint("support_request_id", "submission_key", name="uq_support_message_submission"),
        Index("ix_support_message_thread", "support_request_id", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    support_request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("support_requests.id", ondelete="CASCADE"), nullable=False)
    submission_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    author_type: Mapped[str] = mapped_column(Text, nullable=False)
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    visibility: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SitePolicy(Base):
    __tablename__ = "site_policies"
    __table_args__ = (
        CheckConstraint("kind IN ('privacy','terms','grievance')", name="ck_site_policy_kind"),
        CheckConstraint("revision >= 0 AND version_counter >= 0", name="ck_site_policy_counters"),
        UniqueConstraint("kind", name="uq_site_policy_kind"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version_counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    draft: Mapped[dict | None] = mapped_column(JSONType)
    published_version: Mapped[int | None] = mapped_column(Integer)
    withdraw_reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SitePolicyVersion(Base):
    __tablename__ = "site_policy_versions"
    __table_args__ = (UniqueConstraint("policy_id", "number", name="uq_site_policy_version"),
        CheckConstraint("number >= 1", name="ck_site_policy_version_number"))
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("site_policies.id", ondelete="RESTRICT"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSONType, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))


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
    __table_args__ = (Index("ix_audit_logs_created_id", "created_at", "id"),)

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

event.listen(AuditLog.__table__, "after_create", audit_guard_v1.after_create)
event.listen(AuditLog.__table__, "before_drop", audit_guard_v1.before_drop)


class Post(TimestampMixin, Base):
    """A blog article or case study. Admins write the body in Markdown; the website renders published posts."""
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint(_check_in("post_type", POST_TYPES), name="ck_posts_type"),
        CheckConstraint(_check_in("status", POST_STATUSES), name="ck_posts_status"),
        CheckConstraint(_check_in("origin", POST_ORIGINS), name="ck_posts_origin"),
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
    # "ai" posts were drafted by app.blog_agent; they need a person to confirm the review before the first publish.
    origin: Mapped[str] = mapped_column(Text, default="manual", server_default="manual", nullable=False)
    # Sources (with their stored text), claims with quotes and the code checks. See docs/blog-agent/design.md.
    ai_review: Mapped[dict | None] = mapped_column(JSONType)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    author: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[author_user_id])
    reviewed_by: Mapped[User | None] = relationship(lazy="joined", foreign_keys=[reviewed_by_user_id])

class CaseScanRun(Base):
    """One search for new court rulings by app.blog_agent."""
    __tablename__ = "case_scan_runs"
    __table_args__ = (
        CheckConstraint(_check_in("trigger", CASE_SCAN_TRIGGERS), name="ck_case_scan_runs_trigger"),
        CheckConstraint(_check_in("status", CASE_SCAN_STATUSES), name="ck_case_scan_runs_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="running", nullable=False)
    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model: Mapped[str] = mapped_column(Text, default="", nullable=False)
    usage: Mapped[dict] = mapped_column(JSONType, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

class CaseLead(TimestampMixin, Base):
    """A court ruling or news report found by a scan, waiting for an admin to draft or dismiss it."""
    __tablename__ = "case_leads"
    __table_args__ = (
        CheckConstraint(_check_in("status", CASE_LEAD_STATUSES), name="ck_case_leads_status"),
        Index("idx_case_leads_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("case_scan_runs.id", ondelete="SET NULL"))
    # Normalised (no fragment, no tracking parameters, no trailing slash) so the same page is never stored twice.
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    # Court + case number, lower case without spaces, so a ruling reported by two sites is stored once.
    case_key: Mapped[str | None] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    court: Mapped[str] = mapped_column(Text, default="", nullable=False)
    case_number: Mapped[str] = mapped_column(Text, default="", nullable=False)
    decision_date: Mapped[date | None] = mapped_column(Date)
    source_name: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, default="", nullable=False)
    topics: Mapped[list] = mapped_column(JSONType, default=list, nullable=False)
    relevance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="new", nullable=False)
    post_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("posts.id", ondelete="SET NULL"))
    # Why it was dismissed, or why drafting failed.
    note: Mapped[str | None] = mapped_column(Text)

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
