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
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Ticket, User
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


class AdminSubmissionResponse(BaseModel):
    passed: bool
    message: str
    details: list[str]
    infra_points_awarded: int
    resolution_time: float
    user: AdminUserStats


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

    return AdminSubmissionResponse(
        passed=result.passed,
        message=result.message,
        details=result.details,
        infra_points_awarded=points_awarded,
        resolution_time=resolution_time,
        user=AdminUserStats(current_role=current_user.current_role, infra_points=current_user.infra_points),
    )
