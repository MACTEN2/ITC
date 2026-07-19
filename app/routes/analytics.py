"""Admin-only aggregate stats: department breakdowns and a top-line summary.

Backs the `/analytics` admin dashboard page. Unlike the leaderboard (any
authenticated user), this exposes cross-user aggregate data, so every route
here is layered behind `require_admin` -- same authorization pattern as
`app/routes/admin.py`.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ProgressStatus, Ticket, User, UserBadge, UserTicketProgress
from app.routes.admin import require_admin

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class DepartmentStats(BaseModel):
    department: str
    ticket_count: int
    total_attempts: int
    resolved_count: int
    resolution_rate: float
    unique_learners_engaged: int


class AnalyticsSummary(BaseModel):
    total_users: int
    total_tickets_resolved: int
    average_resolution_rate: float
    most_active_department: str | None
    total_badges_unlocked: int


def _department_stats(db: Session) -> list[DepartmentStats]:
    tickets = db.query(Ticket).all()
    progress_rows = db.query(UserTicketProgress).join(Ticket, Ticket.id == UserTicketProgress.ticket_id).all()

    departments = sorted({t.department for t in tickets})
    stats: list[DepartmentStats] = []
    for department in departments:
        dept_ticket_ids = {t.id for t in tickets if t.department == department}
        dept_progress = [p for p in progress_rows if p.ticket_id in dept_ticket_ids]
        resolved = [p for p in dept_progress if p.status == ProgressStatus.RESOLVED]
        total_attempts = len(dept_progress)
        resolved_count = len(resolved)
        stats.append(
            DepartmentStats(
                department=department,
                ticket_count=len(dept_ticket_ids),
                total_attempts=total_attempts,
                resolved_count=resolved_count,
                resolution_rate=round(resolved_count / total_attempts, 4) if total_attempts else 0.0,
                unique_learners_engaged=len({p.user_id for p in dept_progress}),
            )
        )
    return stats


@router.get("/departments", response_model=list[DepartmentStats])
def get_department_stats(
    current_user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[DepartmentStats]:
    return _department_stats(db)


@router.get("/summary", response_model=AnalyticsSummary)
def get_analytics_summary(
    current_user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> AnalyticsSummary:
    total_users = db.query(User).count()
    total_resolved = (
        db.query(UserTicketProgress).filter(UserTicketProgress.status == ProgressStatus.RESOLVED).count()
    )
    total_badges = db.query(UserBadge).count()

    dept_stats = _department_stats(db)
    rates = [d.resolution_rate for d in dept_stats if d.total_attempts > 0]
    average_resolution_rate = round(sum(rates) / len(rates), 4) if rates else 0.0
    most_active = max(dept_stats, key=lambda d: d.total_attempts, default=None)

    return AnalyticsSummary(
        total_users=total_users,
        total_tickets_resolved=total_resolved,
        average_resolution_rate=average_resolution_rate,
        most_active_department=most_active.department if most_active and most_active.total_attempts > 0 else None,
        total_badges_unlocked=total_badges,
    )
