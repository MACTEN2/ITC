"""Admin-scoped IT Operations routes: high-priority SysAdmin/governance tickets.

Every route here is layered behind `require_admin`, which itself is layered on
top of `get_current_user` (see `app/routes/auth.py`): a request first has to
present a *valid* JWT (else 401), and the account behind that token then has
to have `is_admin=True` (else 403). Both the catalog and the submission
endpoint filter to `Ticket.is_admin_only=True` server-side, so even a crafted
`ticket_id` can never grade a learner-tier ticket through the admin surface
(or vice versa via the learner-tier `/api/tickets*` routes -- see `app/main.py`).

Every access attempt -- successful or rejected -- is logged, since these
routes simulate governance actions (account deactivation, compliance data
changes, infrastructure cleanup) an organization would genuinely want an
audit trail for.

Also home to two read-only admin views: `GET /users` (every account's public
stats) and `GET /submissions` (every learner's past ticket submissions, for
review/moderation). Neither exposes a way to grant `is_admin` over the API --
promoting an account is deliberately DB-only (see the README's security model
section), and `GET /users` stays that way on purpose: it lists accounts, it
never mutates them.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.achievements_db import evaluate_badges
from app.database import get_db
from app.models import ProgressStatus, Ticket, User, UserBadge, UserTicketProgress
from app.notifications import notify
from app.routes.auth import get_current_user
from app.tickets_db import TICKETS_BY_ID, TicketSubmission, grade_submission

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency layered on top of `get_current_user` that also requires `is_admin`.

    A non-admin account with an otherwise-valid token gets a 403 (authenticated,
    but not authorized), never a 401 -- the credentials are fine, the account
    just doesn't have the clearance for this resource.
    """
    if not current_user.is_admin:
        logger.warning(
            "403: non-admin user '%s' (id=%s) attempted to access an admin route.",
            current_user.username,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges are required for this operation.",
        )
    return current_user


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AdminTicketOut(BaseModel):
    """Public shape of an admin ticket -- same idea as the learner TicketOut,
    carrying only the multiple-choice options, never the answer key.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    department: str
    severity: str
    problem_description: str
    root_cause_options: list[str]
    resolution_options: list[str]
    logs_context: dict
    validation_criteria: dict


class AdminSubmissionRequest(BaseModel):
    """An admin's filled-out resolution form for one admin-tier ticket."""

    ticket_id: int = Field(description="ID of the admin ticket being attempted.")
    root_cause: str = Field(description="The selected root cause (must match one of the ticket's options).")
    resolution_actions: list[str] = Field(
        default_factory=list, description="The selected resolution step(s) (subset of the ticket's options)."
    )
    resolution_notes: str = Field(default="", description="Free-text resolution summary, required to close the ticket.")


class AdminUserStats(BaseModel):
    current_role: str
    infra_points: int


class BadgeOut(BaseModel):
    id: str
    name: str
    description: str
    icon: str


class AdminSubmissionResponse(BaseModel):
    passed: bool
    message: str
    details: list[str]
    infra_points_awarded: int
    resolution_time: float
    user: AdminUserStats
    badges_unlocked: list[BadgeOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/tickets", response_model=list[AdminTicketOut])
def list_admin_tickets(
    current_user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[Ticket]:
    """Return the high-priority SysAdmin/governance ticket queue. Admin-only."""
    logger.info("Admin '%s' (id=%s) listed the admin ticket queue.", current_user.username, current_user.id)
    return db.query(Ticket).filter(Ticket.is_admin_only.is_(True)).order_by(Ticket.id).all()


@router.post("/tickets/submit", response_model=AdminSubmissionResponse)
def submit_admin_ticket(
    payload: AdminSubmissionRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminSubmissionResponse:
    """Grade an admin's resolution form using the same grading pipeline as
    learner tickets, but reward `infra_points` instead of a skill XP track.
    XP/points are only granted on a user's first successful resolution of a
    given ticket (see `grade_submission` in `tickets_db.py`).
    """
    definition = TICKETS_BY_ID.get(payload.ticket_id)
    if definition is None or not definition.is_admin_only:
        logger.warning(
            "Admin '%s' (id=%s) requested unknown/non-admin ticket_id=%s.",
            current_user.username,
            current_user.id,
            payload.ticket_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Admin ticket {payload.ticket_id} not found.",
        )

    submission = TicketSubmission(
        root_cause=payload.root_cause,
        resolution_actions=payload.resolution_actions,
        resolution_notes=payload.resolution_notes,
    )
    result, points_awarded, resolution_time = grade_submission(db, current_user, definition, submission)

    logger.info(
        "Admin '%s' (id=%s) submitted ticket %s (%s): passed=%s points_awarded=%s resolution_time=%.4fs",
        current_user.username,
        current_user.id,
        definition.id,
        definition.title,
        result.passed,
        points_awarded,
        resolution_time,
    )

    newly_unlocked_badges = []
    if result.passed and points_awarded > 0:
        notify(db, current_user, "ticket_resolved", f"Ticket resolved: {definition.title} (+{points_awarded} infra points).")
        newly_unlocked_badges = evaluate_badges(db, current_user)
        for badge in newly_unlocked_badges:
            notify(db, current_user, "badge_unlocked", f"Badge unlocked: {badge.name}.")

    return AdminSubmissionResponse(
        passed=result.passed,
        message=result.message,
        details=result.details,
        infra_points_awarded=points_awarded,
        resolution_time=resolution_time,
        user=AdminUserStats(current_role=current_user.current_role, infra_points=current_user.infra_points),
        badges_unlocked=[
            BadgeOut(id=b.id, name=b.name, description=b.description, icon=b.icon) for b in newly_unlocked_badges
        ],
    )


# ---------------------------------------------------------------------------
# User management (view-only -- see module docstring)
# ---------------------------------------------------------------------------


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    current_role: str
    is_admin: bool
    networking_xp: int
    automation_xp: int
    database_xp: int
    infra_points: int
    created_at: datetime
    resolved_ticket_count: int
    badges_earned: int


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminUserOut]:
    """Every account's public stats, for admin visibility only -- no endpoint
    here (or anywhere) can promote/demote is_admin. See module docstring."""
    query = db.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.username.ilike(like), User.email.ilike(like)))
    users = query.order_by(User.id).offset(offset).limit(limit).all()

    resolved_counts: dict[int, int] = {}
    resolved_user_ids = (
        db.query(UserTicketProgress.user_id).filter(UserTicketProgress.status == ProgressStatus.RESOLVED).all()
    )
    for (user_id,) in resolved_user_ids:
        resolved_counts[user_id] = resolved_counts.get(user_id, 0) + 1

    badge_counts: dict[int, int] = {}
    for (user_id,) in db.query(UserBadge.user_id).all():
        badge_counts[user_id] = badge_counts.get(user_id, 0) + 1

    return [
        AdminUserOut(
            id=user.id,
            username=user.username,
            email=user.email,
            current_role=user.current_role,
            is_admin=user.is_admin,
            networking_xp=user.networking_xp,
            automation_xp=user.automation_xp,
            database_xp=user.database_xp,
            infra_points=user.infra_points,
            created_at=user.created_at,
            resolved_ticket_count=resolved_counts.get(user.id, 0),
            badges_earned=badge_counts.get(user.id, 0),
        )
        for user in users
    ]


# ---------------------------------------------------------------------------
# Submission audit log
# ---------------------------------------------------------------------------


class SubmissionOut(BaseModel):
    user_id: int
    username: str
    ticket_id: int
    ticket_title: str
    department: str
    status: str
    root_cause: str | None
    resolution_actions: list[str]
    resolution_notes: str | None
    unlocked_at: datetime
    resolved_at: datetime | None


@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(
    user_id: int | None = None,
    ticket_id: int | None = None,
    department: str | None = None,
    status: ProgressStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[SubmissionOut]:
    """Every learner's past ticket submissions, across all users -- unlike
    `GET /api/history`, which is scoped to the caller only. For review/moderation."""
    query = (
        db.query(UserTicketProgress, Ticket, User)
        .join(Ticket, Ticket.id == UserTicketProgress.ticket_id)
        .join(User, User.id == UserTicketProgress.user_id)
        .filter(UserTicketProgress.submission_data.is_not(None))
    )
    if user_id is not None:
        query = query.filter(UserTicketProgress.user_id == user_id)
    if ticket_id is not None:
        query = query.filter(UserTicketProgress.ticket_id == ticket_id)
    if department is not None:
        query = query.filter(Ticket.department == department)
    if status is not None:
        query = query.filter(UserTicketProgress.status == status)

    rows = query.order_by(UserTicketProgress.unlocked_at.desc()).offset(offset).limit(limit).all()

    return [
        SubmissionOut(
            user_id=user.id,
            username=user.username,
            ticket_id=ticket.id,
            ticket_title=ticket.title,
            department=ticket.department,
            status=progress.status.value,
            root_cause=(progress.submission_data or {}).get("root_cause"),
            resolution_actions=(progress.submission_data or {}).get("resolution_actions", []),
            resolution_notes=(progress.submission_data or {}).get("resolution_notes"),
            unlocked_at=progress.unlocked_at,
            resolved_at=progress.resolved_at,
        )
        for progress, ticket, user in rows
    ]
