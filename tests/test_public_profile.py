"""Test suite for public user profiles (GET /api/users/{username})."""

from tests.conftest import auth_headers

USERS_URL = "/api/users"
SUBMIT_URL = "/api/tickets/submit"

TICKET_1_CORRECT_ROOT_CAUSE = (
    "The account is locked from repeated failed logons using the old password after the forced reset"
)
TICKET_1_CORRECT_ACTIONS = [
    "Unlock the account in Active Directory",
    "Confirm with the user that they are entering the NEW password, not the old one",
]


def test_public_profile_never_includes_email(client, learner_token):
    response = client.get(f"{USERS_URL}/learner_alice", headers=auth_headers(learner_token))
    assert response.status_code == 200
    assert "email" not in response.json()


def test_public_profile_has_expected_fields(client, learner_token):
    response = client.get(f"{USERS_URL}/learner_alice", headers=auth_headers(learner_token))
    body = response.json()
    assert body["username"] == "learner_alice"
    assert body["current_role"] == "Help Desk Tier 1"
    assert body["networking_xp"] == 0
    assert len(body["badges"]) > 0
    assert all(b["earned"] is False for b in body["badges"])


def test_unknown_username_returns_404(client, learner_token):
    response = client.get(f"{USERS_URL}/nonexistent_user_xyz", headers=auth_headers(learner_token))
    assert response.status_code == 404


def test_public_profile_requires_authentication(client):
    response = client.get(f"{USERS_URL}/learner_alice")
    assert response.status_code == 401


def test_badges_reflect_earned_state(client, learner_token):
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

    response = client.get(f"{USERS_URL}/learner_alice", headers=auth_headers(learner_token))
    earned = [b for b in response.json()["badges"] if b["earned"]]
    assert any(b["id"] == "first_blood" for b in earned)
