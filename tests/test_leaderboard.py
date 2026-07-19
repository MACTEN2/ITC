"""Test suite for the cross-user leaderboard (GET /api/leaderboard)."""

from tests.conftest import auth_headers, register_and_login

LEADERBOARD_URL = "/api/leaderboard"
SUBMIT_URL = "/api/tickets/submit"

TICKET_1_CORRECT_ROOT_CAUSE = (
    "The account is locked from repeated failed logons using the old password after the forced reset"
)
TICKET_1_CORRECT_ACTIONS = [
    "Unlock the account in Active Directory",
    "Confirm with the user that they are entering the NEW password, not the old one",
]


def _resolve_ticket_1(client, token):
    return client.post(
        SUBMIT_URL,
        json={
            "ticket_id": 1,
            "root_cause": TICKET_1_CORRECT_ROOT_CAUSE,
            "resolution_actions": TICKET_1_CORRECT_ACTIONS,
            "resolution_notes": "Resolved and documented.",
        },
        headers=auth_headers(token),
    )


def test_leaderboard_requires_authentication(client):
    response = client.get(LEADERBOARD_URL)
    assert response.status_code == 401


def test_leaderboard_orders_entries_descending_by_total_track(client, learner_token):
    bob_token = register_and_login(client, "learner_bob")
    _resolve_ticket_1(client, bob_token)  # bob: +100 automation_xp, alice: 0

    response = client.get(LEADERBOARD_URL, headers=auth_headers(learner_token))
    assert response.status_code == 200
    body = response.json()

    entries = body["entries"]
    bob_entry = next(e for e in entries if e["username"] == "learner_bob")
    alice_entry = next(e for e in entries if e["username"] == "learner_alice")
    assert bob_entry["rank"] < alice_entry["rank"]
    assert bob_entry["value"] == 100
    assert alice_entry["value"] == 0


def test_your_rank_reflects_caller_even_when_outside_limit(client, learner_token):
    for i in range(5):
        register_and_login(client, f"learner_padding_{i}")

    response = client.get(LEADERBOARD_URL, params={"limit": 1}, headers=auth_headers(learner_token))
    body = response.json()

    assert len(body["entries"]) == 1
    assert body["your_rank"] is not None
    assert body["your_rank"]["value"] == 0


def test_leaderboard_track_selects_the_right_field(client, learner_token):
    _resolve_ticket_1(client, learner_token)  # automation_xp track, not networking

    response = client.get(LEADERBOARD_URL, params={"track": "networking"}, headers=auth_headers(learner_token))
    body = response.json()
    alice_entry = next(e for e in body["entries"] if e["username"] == "learner_alice")
    assert alice_entry["value"] == 0

    response = client.get(LEADERBOARD_URL, params={"track": "automation"}, headers=auth_headers(learner_token))
    body = response.json()
    alice_entry = next(e for e in body["entries"] if e["username"] == "learner_alice")
    assert alice_entry["value"] == 100
