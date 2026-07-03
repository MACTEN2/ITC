"""Relational database schema for the ITC (IT Operations and Systems Simulator).

Core tables:
    - User: an account (credentials + role) plus accumulated XP per skill track
      and "Infrastructure Stability Points" earned from admin-only tickets.
    - Ticket: a catalog entry describing one hardcoded IT support scenario.
    - UserTicketProgress: the join/history table tracking a user's attempts on a ticket.

Sandbox-only tables (never written through normal application flow -- see
`tickets_db.py`) are seeded fresh into an isolated in-memory database for every
single grading call, so untrusted user-submitted SQL/code can never touch
persistent data:
    - AccessLog: queried by Ticket #2 ("The Account Lockout Audit").
    - MockEmployee: mutated by Admin Ticket #2 ("The Security Compliance Audit").
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Severity(str, enum.Enum):
    """How urgent/impactful a ticket is, mirroring real-world IT ticket triage."""

    LOW = "Low"
    INCIDENT = "Incident"
    CATASTROPHIC = "Catastrophic"


class ProgressStatus(str, enum.Enum):
    """Lifecycle state of a user's attempt at a given ticket."""

    OPEN = "Open"
    RESOLVED = "Resolved"


class LoginStatus(str, enum.Enum):
    """Outcome of a single authentication attempt in the access_logs sandbox table."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class EmploymentType(str, enum.Enum):
    """Staffing category in the mock_employees sandbox table."""

    FULL_TIME = "Full-Time"
    CONTRACTOR = "Contractor"


def _utcnow() -> datetime:
    """Timezone-aware 'now', used as a default factory for timestamp columns."""
    return datetime.now(timezone.utc)


class User(Base):
    """An ITC account: login credentials, role, and accumulated progression."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    # Bcrypt hash (via passlib), never the plaintext password. See app/routes/auth.py.
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Career ladder label, e.g. "Help Desk Tier 1", "Junior SysAdmin", "Junior Database Analyst".
    current_role: Mapped[str] = mapped_column(String(64), default="Help Desk Tier 1", nullable=False)

    # Grants access to the /api/admin/* routes (see app/routes/admin.py). Regular
    # learners default to False and can never self-promote through the API.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # XP tracks, one per skill discipline exercised by the learner-facing tickets.
    networking_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    automation_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    database_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Separate currency earned only from admin-scoped governance/ops tickets.
    infra_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    progress: Mapped[list["UserTicketProgress"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Ticket(Base):
    """A catalog entry describing one hardcoded IT support scenario."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    department: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), nullable=False)
    problem_description: Mapped[str] = mapped_column(Text, nullable=False)

    # Buggy/incomplete code (or a SQL query skeleton) the learner starts from.
    starter_code: Mapped[str] = mapped_column(Text, nullable=False)

    # Arbitrary supporting context (sample logs, CSV rosters, etc.) shown to the learner.
    logs_context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Human-readable description of what the automated grader checks -- shown to the
    # learner so they know the acceptance criteria up front. The grading logic itself
    # lives in code (`tickets_db.py`), not as data, so any correct approach passes;
    # this field documents that logic rather than driving it.
    validation_criteria: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Admin-only tickets are hidden from the standard learner catalog and require
    # `is_admin == True` to view/submit (enforced in app/routes/admin.py).
    is_admin_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    progress: Mapped[list["UserTicketProgress"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )


class UserTicketProgress(Base):
    """Tracks a single user's attempt(s) at resolving a single ticket."""

    __tablename__ = "user_ticket_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), nullable=False, index=True)

    status: Mapped[ProgressStatus] = mapped_column(
        Enum(ProgressStatus), default=ProgressStatus.OPEN, nullable=False
    )
    code_submission: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set the moment a user's first attempt at this ticket is recorded.
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # Set only once the submission passes verification; stays NULL while still Open.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="progress")
    ticket: Mapped["Ticket"] = relationship(back_populates="progress")


class AccessLog(Base):
    """Sandbox-only table representing router/auth access logs for Ticket #2.

    Rows are never written through normal application flow; `tickets_db.py` creates
    this table (via `Base.metadata.create_all`) inside a throwaway in-memory SQLite
    engine and seeds it fresh for every submission so learner SQL runs in isolation.
    """

    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    # `values_callable` makes SQLAlchemy persist the enum's *value* ("FAILED")
    # instead of its default of the member *name* -- both happen to read the
    # same here, but this matters for MockEmployee below and is kept
    # consistent so raw learner-submitted SQL always matches human-readable
    # values, never Python identifier names.
    status: Mapped[LoginStatus] = mapped_column(
        Enum(LoginStatus, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    attempt_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MockEmployee(Base):
    """Sandbox-only table for Admin Ticket #2 ("The Security Compliance Audit").

    Like AccessLog, this is never populated through normal application flow --
    `tickets_db.py` seeds it fresh into a throwaway in-memory SQLite engine for
    every UPDATE submission, so a learner's SQL can never mutate real records.
    """

    __tablename__ = "mock_employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_name: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[str] = mapped_column(String(64), nullable=False)
    # `values_callable` here is not cosmetic: without it SQLAlchemy stores the
    # enum's member *name* ("CONTRACTOR"), so a learner's `WHERE employment_type
    # = 'Contractor'` -- which matches the value shown in the ticket description
    # and in every SELECT result -- would silently match zero rows.
    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(EmploymentType, values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    clearance_level: Mapped[str] = mapped_column(String(16), nullable=False)
