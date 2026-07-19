"""Public (any authenticated user) view of another account's stats + badges.

Deliberately returns a distinct `PublicUserProfile` model rather than reusing
`UserPublic` (app/routes/auth.py) -- `UserPublic` includes `email`, and the
whole point of this endpoint is showing someone's stats without leaking their
contact info. `is_admin` is fine to include since it's already shown per-row
on the leaderboard.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routes.achievements import BadgeOut, annotated_badges
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/users", tags=["users"])


class PublicUserProfile(BaseModel):
    id: int
    username: str
    current_role: str
    is_admin: bool
    networking_xp: int
    automation_xp: int
    database_xp: int
    infra_points: int
    created_at: datetime
    badges: list[BadgeOut]


@router.get("/{username}", response_model=PublicUserProfile)
def get_public_profile(
    username: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> PublicUserProfile:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{username}' not found.")

    return PublicUserProfile(
        id=user.id,
        username=user.username,
        current_role=user.current_role,
        is_admin=user.is_admin,
        networking_xp=user.networking_xp,
        automation_xp=user.automation_xp,
        database_xp=user.database_xp,
        infra_points=user.infra_points,
        created_at=user.created_at,
        badges=annotated_badges(db, user.id),
    )
