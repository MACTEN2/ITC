"""Test suite for self-service account deletion (DELETE /api/auth/me)."""

from tests.conftest import DEFAULT_PASSWORD, auth_headers

ME_URL = "/api/auth/me"
SUBMIT_URL = "/api/tickets/submit"

TICKET_1_CORRECT_ROOT_CAUSE = (
    "The account is locked from repeated failed logons using the old password after the forced reset"
)
TICKET_1_CORRECT_ACTIONS = [
    "Unlock the account in Active Directory",
    "Confirm with the user that they are entering the NEW password, not the old one",
]


def _delete_account(client, token, password):
    # httpx's Client.delete() doesn't accept a body; DELETE-with-JSON needs .request().
    return client.request(
        "DELETE", ME_URL, json={"current_password": password}, headers=auth_headers(token)
    )


def test_wrong_password_is_rejected_and_account_survives(client, learner_token):
    response = _delete_account(client, learner_token, "totally-wrong")
    assert response.status_code == 400

    me = client.get(ME_URL, headers=auth_headers(learner_token))
    assert me.status_code == 200


def test_correct_password_deletes_account_and_invalidates_the_old_token(client, learner_token):
    response = _delete_account(client, learner_token, DEFAULT_PASSWORD)
    assert response.status_code == 204

    me = client.get(ME_URL, headers=auth_headers(learner_token))
    assert me.status_code == 401

    login = client.post("/api/auth/login", data={"username": "learner_alice", "password": DEFAULT_PASSWORD})
    assert login.status_code == 401


def test_deletion_leaves_no_orphaned_rows_in_any_child_table(client, learner_token):
    """Resolve a ticket first so progress/badge/notification rows all exist,
    then confirm deletion actually cleans up every child table -- not just
    that the User row itself disappears without error."""
    client.post(
        SUBMIT_URL,
        json={
            "ticket_id": 1,
            "root_cause": TICKET_1_CORRECT_ROOT_CAUSE,
            "resolution_actions": TICKET_1_CORRECT_ACTIONS,
            "resolution_notes": "Resolved and documented.",
        },
        headers=auth_headers(learner_token),
    )
    client.patch(
        "/api/notifications/preferences", json={"notify_ticket_resolved": False}, headers=auth_headers(learner_token)
    )

    from app.database import SessionLocal
    from app.models import LoginEvent, Notification, NotificationPreference, User, UserBadge, UserTicketProgress

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "learner_alice").first()
        user_id = user.id
    finally:
        db.close()

    response = _delete_account(client, learner_token, DEFAULT_PASSWORD)
    assert response.status_code == 204

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.id == user_id).first() is None
        assert db.query(UserTicketProgress).filter(UserTicketProgress.user_id == user_id).count() == 0
        assert db.query(UserBadge).filter(UserBadge.user_id == user_id).count() == 0
        assert db.query(Notification).filter(Notification.user_id == user_id).count() == 0
        assert db.query(NotificationPreference).filter(NotificationPreference.user_id == user_id).count() == 0
        assert db.query(LoginEvent).filter(LoginEvent.user_id == user_id).count() == 0
    finally:
        db.close()


def test_deletion_requires_authentication(client):
    response = client.request("DELETE", ME_URL, json={"current_password": DEFAULT_PASSWORD})
    assert response.status_code == 401
