"""Badge catalog + criteria evaluation for the ITC achievement system.

Mirrors the `tickets_db.py` split: the badge *catalog* (id, name,
description, criteria) lives here in code; `UserBadge` (app/models.py) only
records that a badge_id was earned and when, the same way a `Ticket` row
never stores which option is correct.

Deliberately not hooked into `grade_submission()` itself -- that would
create an import cycle (`tickets_db.py` -> `achievements_db.py` ->
`tickets_db.py`) and mixes two responsibilities that are cleaner kept apart.
Callers (the submit routes in `app/main.py` / `app/routes/admin.py`) call
`evaluate_badges()` themselves right after a passing `grade_submission()`.
"""

import re
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.models import ProgressStatus, User, UserBadge, UserTicketProgress
from app.tickets_db import TICKETS


@dataclass
class BadgeDefinition:
    id: str
    name: str
    description: str
    icon: str
    criteria: Callable[[Session, User], bool]


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _resolved_ticket_ids(db: Session, user: User) -> set[int]:
    rows = (
        db.query(UserTicketProgress.ticket_id)
        .filter(UserTicketProgress.user_id == user.id, UserTicketProgress.status == ProgressStatus.RESOLVED)
        .all()
    )
    return {row[0] for row in rows}


def _first_blood(db: Session, user: User) -> bool:
    return len(_resolved_ticket_ids(db, user)) >= 1


def _century_club(db: Session, user: User) -> bool:
    return (user.networking_xp + user.automation_xp + user.database_xp) >= 500


def _infra_guardian(db: Session, user: User) -> bool:
    admin_ticket_ids = {t.id for t in TICKETS if t.is_admin_only}
    return bool(_resolved_ticket_ids(db, user) & admin_ticket_ids)


def _make_department_criteria(department_ticket_ids: set[int]) -> Callable[[Session, User], bool]:
    def _criteria(db: Session, user: User) -> bool:
        return department_ticket_ids.issubset(_resolved_ticket_ids(db, user))

    return _criteria


_DEPARTMENTS = sorted({t.department for t in TICKETS})

BADGES: list[BadgeDefinition] = [
    BadgeDefinition(
        id="first_blood",
        name="First Blood",
        description="Resolve your first ticket.",
        icon="🎯",
        criteria=_first_blood,
    ),
    BadgeDefinition(
        id="century_club",
        name="Century Club",
        description="Earn 500+ combined XP across all skill tracks.",
        icon="💯",
        criteria=_century_club,
    ),
    BadgeDefinition(
        id="infra_guardian",
        name="Infra Guardian",
        description="Resolve an admin-tier SysAdmin/governance ticket.",
        icon="🛡️",
        criteria=_infra_guardian,
    ),
    *[
        BadgeDefinition(
            id=f"dept_master_{_slugify(department)}",
            name=f"{department} Master",
            description=f"Resolve every ticket in the {department} queue.",
            icon="🏆",
            criteria=_make_department_criteria({t.id for t in TICKETS if t.department == department}),
        )
        for department in _DEPARTMENTS
    ],
]

BADGES_BY_ID: dict[str, BadgeDefinition] = {badge.id: badge for badge in BADGES}


def evaluate_badges(db: Session, user: User) -> list[BadgeDefinition]:
    """Check every badge's criteria for `user`; award (and return) any newly earned ones."""
    already_earned = {row[0] for row in db.query(UserBadge.badge_id).filter(UserBadge.user_id == user.id).all()}

    newly_earned: list[BadgeDefinition] = []
    for badge in BADGES:
        if badge.id in already_earned:
            continue
        if badge.criteria(db, user):
            db.add(UserBadge(user_id=user.id, badge_id=badge.id))
            newly_earned.append(badge)

    if newly_earned:
        db.commit()

    return newly_earned
