"""Test suite for per-user notification preferences and their effect on notify()."""

from tests.conftest import auth_headers

PREFERENCES_URL = "/api/notifications/preferences"
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


def test_defaults_are_both_true_with_no_row_written_yet(client, learner_token):
    response = client.get(PREFERENCES_URL, headers=auth_headers(learner_token))
    assert response.status_code == 200
    body = response.json()
    assert body == {"notify_ticket_resolved": True, "notify_badge_unlocked": True}


def test_disabling_ticket_resolved_suppresses_that_notification(client, learner_token):
    client.patch(PREFERENCES_URL, json={"notify_ticket_resolved": False}, headers=auth_headers(learner_token))

    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    types = [n["type"] for n in client.get(NOTIFICATIONS_URL, headers=auth_headers(learner_token)).json()]
    assert "ticket_resolved" not in types
    assert "badge_unlocked" in types  # independently toggleable, still on


def test_disabling_badge_unlocked_suppresses_only_that_type(client, learner_token):
    client.patch(PREFERENCES_URL, json={"notify_badge_unlocked": False}, headers=auth_headers(learner_token))

    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    types = [n["type"] for n in client.get(NOTIFICATIONS_URL, headers=auth_headers(learner_token)).json()]
    assert "badge_unlocked" not in types
    assert "ticket_resolved" in types


def test_preferences_persist_and_can_be_re_enabled(client, learner_token):
    client.patch(PREFERENCES_URL, json={"notify_ticket_resolved": False}, headers=auth_headers(learner_token))
    client.patch(PREFERENCES_URL, json={"notify_ticket_resolved": True}, headers=auth_headers(learner_token))

    response = client.get(PREFERENCES_URL, headers=auth_headers(learner_token))
    assert response.json()["notify_ticket_resolved"] is True


def test_preferences_require_authentication(client):
    assert client.get(PREFERENCES_URL).status_code == 401
    assert client.patch(PREFERENCES_URL, json={"notify_ticket_resolved": False}).status_code == 401
