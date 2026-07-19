"""Test suite for self-service data export (GET /api/export)."""

from tests.conftest import auth_headers

EXPORT_URL = "/api/export"
SUBMIT_URL = "/api/tickets/submit"
HISTORY_URL = "/api/history"
ACHIEVEMENTS_URL = "/api/achievements"

TICKET_1_CORRECT_ROOT_CAUSE = (
    "The account is locked from repeated failed logons using the old password after the forced reset"
)
TICKET_1_CORRECT_ACTIONS = [
    "Unlock the account in Active Directory",
    "Confirm with the user that they are entering the NEW password, not the old one",
]


def test_export_requires_authentication(client):
    assert client.get(EXPORT_URL).status_code == 401


def test_export_matches_standalone_endpoints_after_activity(client, learner_token):
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

    export = client.get(EXPORT_URL, headers=auth_headers(learner_token)).json()
    history = client.get(HISTORY_URL, headers=auth_headers(learner_token)).json()
    achievements = client.get(ACHIEVEMENTS_URL, headers=auth_headers(learner_token)).json()

    assert export["profile"]["username"] == "learner_alice"
    assert export["history"] == history
    assert export["achievements"] == achievements
    assert "exported_at" in export
