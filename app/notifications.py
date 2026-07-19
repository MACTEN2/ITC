"""Helper for creating in-app notifications.

Standalone (not under app/routes/) because it's called from multiple call
sites that aren't each other's routers: the learner submit route in
app/main.py, the admin submit route in app/routes/admin.py, and its own
read/list router in app/routes/notifications.py.
"""

from sqlalchemy.orm import Session

from app.models import Notification, NotificationPreference, User

# Maps a notification `type` to the NotificationPreference column that can
# suppress it. A type not in this map is always allowed -- a future
# notification type shouldn't be silently blocked just because no one
# remembered to add a preference toggle for it.
_TYPE_TO_PREFERENCE_FIELD = {
    "ticket_resolved": "notify_ticket_resolved",
    "badge_unlocked": "notify_badge_unlocked",
}


def notify(db: Session, user: User, type: str, message: str) -> Notification | None:
    """Create a notification for `user`, unless they've opted out of `type`.

    Returns None (and creates nothing) when suppressed by preference -- every
    current call site already discards the return value, so this is safe.
    """
    preference_field = _TYPE_TO_PREFERENCE_FIELD.get(type)
    if preference_field is not None:
        preference = db.query(NotificationPreference).filter(NotificationPreference.user_id == user.id).first()
        if preference is not None and not getattr(preference, preference_field):
            return None

    notification = Notification(user_id=user.id, type=type, message=message)
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification
