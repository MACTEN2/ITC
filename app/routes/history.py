"""A learner's/admin's own ticket resolution history.

No new model here -- `UserTicketProgress` (see app/models.py) already
records everything a history feed needs (status, unlocked_at, resolved_at,
submission_data); this router just queries it from the caller's own
perspective and joins in ticket metadata + the reward amount from the
`tickets_db.py` catalog (which is never stored on the `Ticket` row itself).
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ProgressStatus, Ticket, User, UserTicketProgress
from app.routes.auth import get_current_user
from app.tickets_db import TICKETS_BY_ID

router = APIRouter(prefix="/api/history", tags=["history"])


class HistoryEntry(BaseModel):
    ticket_id: int
    ticket_title: str
    department: str
    severity: str
    status: str
    unlocked_at: datetime
    resolved_at: datetime | None
    reward_field: str | None
    reward_amount: int | None


def history_entries(
    db: Session, user: User, status: ProgressStatus | None = None, department: str | None = None
) -> list[HistoryEntry]:
    """`user`'s own ticket attempt history, most recent activity first.

    Shared by this router's own endpoint and the data-export endpoint
    (`app/routes/export.py`) so the query/assembly logic lives in one place.
    """
    query = (
        db.query(UserTicketProgress, Ticket)
        .join(Ticket, Ticket.id == UserTicketProgress.ticket_id)
        .filter(UserTicketProgress.user_id == user.id)
    )
    if status is not None:
        query = query.filter(UserTicketProgress.status == status)
    if department is not None:
        query = query.filter(Ticket.department == department)

    rows = query.all()
    rows.sort(key=lambda row: row[0].resolved_at or row[0].unlocked_at, reverse=True)

    entries: list[HistoryEntry] = []
    for progress, ticket in rows:
        definition = TICKETS_BY_ID.get(ticket.id)
        is_resolved = progress.status == ProgressStatus.RESOLVED
        entries.append(
            HistoryEntry(
                ticket_id=ticket.id,
                ticket_title=ticket.title,
                department=ticket.department,
                severity=ticket.severity.value,
                status=progress.status.value,
                unlocked_at=progress.unlocked_at,
                resolved_at=progress.resolved_at,
                reward_field=definition.reward_field if (definition and is_resolved) else None,
                reward_amount=definition.reward_amount if (definition and is_resolved) else None,
            )
        )
    return entries


@router.get("", response_model=list[HistoryEntry])
def get_history(
    status: ProgressStatus | None = None,
    department: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[HistoryEntry]:
    """The caller's own ticket attempt history, most recent activity first."""
    return history_entries(db, current_user, status=status, department=department)
