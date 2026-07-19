"""In-app notification feed: list, mark-one-read, mark-all-read."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Notification, NotificationPreference, User
from app.routes.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    message: str
    is_read: bool
    created_at: datetime


class NotificationPreferencesOut(BaseModel):
    notify_ticket_resolved: bool
    notify_badge_unlocked: bool


class NotificationPreferencesUpdate(BaseModel):
    notify_ticket_resolved: bool | None = None
    notify_badge_unlocked: bool | None = None


@router.get("/preferences", response_model=NotificationPreferencesOut)
def get_notification_preferences(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> NotificationPreferencesOut:
    """The caller's notification preferences, defaulting to all-True if no
    row has been written yet (no need to backfill one per account)."""
    preference = db.query(NotificationPreference).filter(NotificationPreference.user_id == current_user.id).first()
    if preference is None:
        return NotificationPreferencesOut(notify_ticket_resolved=True, notify_badge_unlocked=True)
    return NotificationPreferencesOut(
        notify_ticket_resolved=preference.notify_ticket_resolved,
        notify_badge_unlocked=preference.notify_badge_unlocked,
    )


@router.patch("/preferences", response_model=NotificationPreferencesOut)
def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPreferencesOut:
    preference = db.query(NotificationPreference).filter(NotificationPreference.user_id == current_user.id).first()
    if preference is None:
        preference = NotificationPreference(user_id=current_user.id)
        db.add(preference)

    if payload.notify_ticket_resolved is not None:
        preference.notify_ticket_resolved = payload.notify_ticket_resolved
    if payload.notify_badge_unlocked is not None:
        preference.notify_badge_unlocked = payload.notify_badge_unlocked

    db.commit()
    db.refresh(preference)
    return NotificationPreferencesOut(
        notify_ticket_resolved=preference.notify_ticket_resolved,
        notify_badge_unlocked=preference.notify_badge_unlocked,
    )


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Notification]:
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    return query.order_by(Notification.created_at.desc()).limit(limit).all()


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Notification:
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found.")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    db.query(Notification).filter(
        Notification.user_id == current_user.id, Notification.is_read.is_(False)
    ).update({"is_read": True})
    db.commit()
