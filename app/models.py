"""Relational database schema for the ITC (IT Operations and Systems Simulator).

Core tables:
    - User: an account (credentials + role) plus accumulated XP per skill track
      and "Infrastructure Stability Points" earned from admin-only tickets.
    - Ticket: a catalog entry describing one hardcoded IT support scenario,
      resolved by picking a root cause and the correct resolution action(s)
      from a fixed multiple-choice list -- there is no code execution
      anywhere in this app. This mirrors how a real Help Desk / IT Support
      ticketing system (ServiceNow, Zendesk, etc.) actually works: an agent
      diagnoses the issue and selects/logs the resolution, they don't write
      and run scripts against production.
    - UserTicketProgress: the join/history table tracking a user's attempts on a ticket.

The *correct* root cause / resolution actions for each ticket live only in
`tickets_db.py` (Python code, never serialized to the API) -- the `Ticket`
row itself only carries the multiple-choice *options* shown to the user, so
`GET /api/tickets` can never leak the answer key.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
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
    """A catalog entry describing one hardcoded IT support scenario.

    Resolved via a fixed multiple-choice "resolution form", not code:
    `root_cause_options` is the single-select list of plausible causes shown
    to the user, `resolution_options` is the multi-select checklist of
    possible actions. Both lists include realistic wrong answers alongside
    the correct one(s) -- the correct answer(s) are not stored here at all,
    only in `tickets_db.py`.
    """

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    department: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), nullable=False)
    problem_description: Mapped[str] = mapped_column(Text, nullable=False)

    # Single-select: plausible root causes, exactly one of which is correct.
    root_cause_options: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Multi-select: plausible resolution actions/steps; some subset is correct.
    resolution_options: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Supporting context shown to the user (sample logs, a config dump, a
    # directory listing, ...) -- read-only reference material, not something
    # the ticket is graded against directly.
    logs_context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Human-readable description of what the grader checks -- shown to the
    # learner so they know the acceptance criteria up front.
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
    # The learner's last submitted resolution form: {"root_cause": ..., "resolution_actions": [...], "resolution_notes": ...}
    submission_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Set the moment a user's first attempt at this ticket is recorded.
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # Set only once the submission passes verification; stays NULL while still Open.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="progress")
    ticket: Mapped["Ticket"] = relationship(back_populates="progress")


class UserBadge(Base):
    """One row per (user, badge) an account has unlocked.

    The badge catalog itself (name/description/criteria) lives in code, in
    `app/achievements_db.py` -- exactly the same split as `Ticket` (DB row,
    no answer key) vs. `tickets_db.py` (the code-defined catalog). This table
    only records *that* a given badge_id was earned and when.
    """

    __tablename__ = "user_badges"
    __table_args__ = (UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    badge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class Notification(Base):
    """An in-app notification for a user (ticket resolved, badge unlocked, ...)."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # Plain string rather than an Enum -- new notification types shouldn't need a migration.
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class NotificationPreference(Base):
    """Per-user opt-out flags for each notification type.

    A separate table (not new columns on `User`) because `Base.metadata.create_all()`
    only issues CREATE TABLE for tables that don't exist yet -- it never ALTERs an
    existing table, and this app has no migration tool. One row per user, created
    lazily on first write; `GET /api/notifications/preferences` synthesizes the
    all-True defaults below if no row exists yet, so there's no need to backfill
    a row for every existing account.
    """

    __tablename__ = "notification_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    notify_ticket_resolved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_badge_unlocked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LoginEvent(Base):
    """One row per successful login, for the user's own 'recent sign-ins' list.

    `ip_address` is `request.client.host` -- the direct TCP peer address as
    FastAPI/Starlette sees it. This app has no reverse proxy in front of it, so
    that's meaningful here; it deliberately does NOT parse `X-Forwarded-For` or
    similar headers, which are client-suppliable and not trustworthy without a
    proxy validating them. `user_agent` is stored raw (no parsing dependency
    exists in this project to turn it into a friendly "Chrome on macOS" label).
    """

    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
