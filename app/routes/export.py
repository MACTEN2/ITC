"""Self-service data export: the caller's own profile + history + achievements
as one JSON document. Pure composition of three already-tested query paths
(`app/routes/auth.py`'s `UserPublic`, `app/routes/history.py`'s `history_entries`,
`app/routes/achievements.py`'s `annotated_badges`) -- no new business logic.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routes.achievements import BadgeOut, annotated_badges
from app.routes.auth import UserPublic, get_current_user
from app.routes.history import HistoryEntry, history_entries

router = APIRouter(prefix="/api/export", tags=["export"])


class UserDataExport(BaseModel):
    exported_at: datetime
    profile: UserPublic
    history: list[HistoryEntry]
    achievements: list[BadgeOut]


@router.get("", response_model=UserDataExport)
def export_user_data(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserDataExport:
    return UserDataExport(
        exported_at=datetime.now(timezone.utc),
        profile=UserPublic.model_validate(current_user),
        history=history_entries(db, current_user),
        achievements=annotated_badges(db, current_user.id),
    )
