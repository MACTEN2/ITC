"""Test suite for the in-app notification feed."""

from tests.conftest import auth_headers, register_and_login

NOTIFICATIONS_URL = "/api/notifications"
SUBMIT_URL = "/api/tickets/submit"

TICKET_1_CORRECT_ROOT_CAUSE = (
    "The account is locked from repeated failed logons using the old password after the forced reset"
)
TICKET_1_CORRECT_ACTIONS = [
    "Unlock the account in Active Directory",
    "Confirm with the user that they are entering the NEW password, not the old one",
]


def _submit(client, token, ticket_id, root_cause, resolution_actions, resolution_notes="Resolved and documented."):
    return client.post(
        SUBMIT_URL,
        json={
            "ticket_id": ticket_id,
            "root_cause": root_cause,
            "resolution_actions": resolution_actions,
            "resolution_notes": resolution_notes,
        },
        headers=auth_headers(token),
    )


def test_first_time_resolution_creates_a_ticket_resolved_notification(client, learner_token):
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    response = client.get(NOTIFICATIONS_URL, headers=auth_headers(learner_token))
    assert response.status_code == 200
    types = [n["type"] for n in response.json()]
    assert "ticket_resolved" in types


def test_resubmission_does_not_duplicate_the_ticket_resolved_notification(client, learner_token):
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    response = client.get(NOTIFICATIONS_URL, headers=auth_headers(learner_token))
    types = [n["type"] for n in response.json()]
    assert types.count("ticket_resolved") == 1


def test_badge_unlock_creates_a_badge_unlocked_notification(client, learner_token):
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    response = client.get(NOTIFICATIONS_URL, headers=auth_headers(learner_token))
    types = [n["type"] for n in response.json()]
    assert "badge_unlocked" in types


def test_unread_only_filter_excludes_read_notifications(client, learner_token):
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    all_notifications = client.get(NOTIFICATIONS_URL, headers=auth_headers(learner_token)).json()
    first_id = all_notifications[0]["id"]
    client.patch(f"{NOTIFICATIONS_URL}/{first_id}/read", headers=auth_headers(learner_token))

    unread = client.get(NOTIFICATIONS_URL, params={"unread_only": True}, headers=auth_headers(learner_token)).json()
    assert first_id not in {n["id"] for n in unread}


def test_marking_another_users_notification_read_returns_404(client, learner_token):
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)
    notification_id = client.get(NOTIFICATIONS_URL, headers=auth_headers(learner_token)).json()[0]["id"]

    other_token = register_and_login(client, "learner_other")
    response = client.patch(f"{NOTIFICATIONS_URL}/{notification_id}/read", headers=auth_headers(other_token))
    assert response.status_code == 404


def test_read_all_marks_every_notification_read(client, learner_token):
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    response = client.post(f"{NOTIFICATIONS_URL}/read-all", headers=auth_headers(learner_token))
    assert response.status_code == 204

    all_notifications = client.get(NOTIFICATIONS_URL, headers=auth_headers(learner_token)).json()
    assert all(n["is_read"] for n in all_notifications)


def test_notifications_require_authentication(client):
    response = client.get(NOTIFICATIONS_URL)
    assert response.status_code == 401
