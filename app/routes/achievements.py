"""Read-only view of the badge catalog, annotated with a user's own progress."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.achievements_db import BADGES
from app.database import get_db
from app.models import User, UserBadge
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/achievements", tags=["achievements"])


class BadgeOut(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    earned: bool
    earned_at: datetime | None


def annotated_badges(db: Session, user_id: int) -> list[BadgeOut]:
    """Every badge in the catalog, annotated with whether/when `user_id` earned it.

    Shared by this router's own endpoint, the public-profile endpoint
    (`app/routes/users.py`), and the data-export endpoint (`app/routes/export.py`)
    so the annotation logic lives in exactly one place.
    """
    earned_rows = {
        row.badge_id: row.earned_at for row in db.query(UserBadge).filter(UserBadge.user_id == user_id).all()
    }
    return [
        BadgeOut(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            icon=badge.icon,
            earned=badge.id in earned_rows,
            earned_at=earned_rows.get(badge.id),
        )
        for badge in BADGES
    ]


@router.get("", response_model=list[BadgeOut])
def get_achievements(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[BadgeOut]:
    """Every badge in the catalog, annotated with whether/when the caller earned it."""
    return annotated_badges(db, current_user.id)
