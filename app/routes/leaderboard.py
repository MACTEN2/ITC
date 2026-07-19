"""Cross-user ranking by XP track or infra_points.

Any authenticated user can view the leaderboard (it's meant to be
motivating/competitive among learners), unlike the analytics router which is
admin-only aggregate data. Ranking is computed in Python rather than a SQL
`ORDER BY`/window function -- this app's expected user count is small, and
the codebase already favors simple, explicit Python over cleverness
elsewhere (see grade_submission/evaluate_badges).
"""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/leaderboard", tags=["leaderboard"])

Track = Literal["total", "networking", "automation", "database", "infra_points"]

_TRACK_FIELDS: dict[Track, tuple[str, ...]] = {
    "total": ("networking_xp", "automation_xp", "database_xp"),
    "networking": ("networking_xp",),
    "automation": ("automation_xp",),
    "database": ("database_xp",),
    "infra_points": ("infra_points",),
}


def _track_value(user: User, track: Track) -> int:
    return sum(getattr(user, field) for field in _TRACK_FIELDS[track])


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    username: str
    current_role: str
    value: int
    is_admin: bool


class RankInfo(BaseModel):
    rank: int
    value: int


class LeaderboardResponse(BaseModel):
    track: Track
    entries: list[LeaderboardEntry]
    your_rank: RankInfo | None


@router.get("", response_model=LeaderboardResponse)
def get_leaderboard(
    track: Track = "total",
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaderboardResponse:
    """Rank every user by `track`, descending. Includes the caller's own rank
    even if it falls outside the top `limit`."""
    users = db.query(User).all()
    ranked = sorted(users, key=lambda u: _track_value(u, track), reverse=True)

    entries = [
        LeaderboardEntry(
            rank=idx + 1,
            user_id=user.id,
            username=user.username,
            current_role=user.current_role,
            value=_track_value(user, track),
            is_admin=user.is_admin,
        )
        for idx, user in enumerate(ranked)
    ]

    your_rank = next((RankInfo(rank=e.rank, value=e.value) for e in entries if e.user_id == current_user.id), None)

    return LeaderboardResponse(track=track, entries=entries[:limit], your_rank=your_rank)
