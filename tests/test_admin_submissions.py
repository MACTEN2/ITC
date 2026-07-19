"""Test suite for the admin-only cross-user submission audit log."""

from tests.conftest import auth_headers, register_and_login

SUBMISSIONS_URL = "/api/admin/submissions"
SUBMIT_URL = "/api/tickets/submit"

TICKET_1_CORRECT_ROOT_CAUSE = (
    "The account is locked from repeated failed logons using the old password after the forced reset"
)
TICKET_1_CORRECT_ACTIONS = [
    "Unlock the account in Active Directory",
    "Confirm with the user that they are entering the NEW password, not the old one",
]


def _submit(client, token, ticket_id=1, root_cause=TICKET_1_CORRECT_ROOT_CAUSE, actions=None, notes="Resolved."):
    return client.post(
        SUBMIT_URL,
        json={
            "ticket_id": ticket_id,
            "root_cause": root_cause,
            "resolution_actions": actions or TICKET_1_CORRECT_ACTIONS,
            "resolution_notes": notes,
        },
        headers=auth_headers(token),
    )


def test_forbidden_for_non_admin(client, learner_token):
    response = client.get(SUBMISSIONS_URL, headers=auth_headers(learner_token))
    assert response.status_code == 403


def test_requires_authentication(client):
    assert client.get(SUBMISSIONS_URL).status_code == 401


def test_shows_submissions_across_multiple_users(client, admin_token, learner_token):
    """Unlike GET /api/history (self-only), this endpoint is cross-user."""
    bob_token = register_and_login(client, "learner_bob")
    _submit(client, learner_token, notes="Alice's note.")
    _submit(client, bob_token, notes="Bob's note.")

    response = client.get(SUBMISSIONS_URL, headers=auth_headers(admin_token))
    assert response.status_code == 200
    usernames = {s["username"] for s in response.json()}
    assert {"learner_alice", "learner_bob"} <= usernames

    alice_entry = next(s for s in response.json() if s["username"] == "learner_alice")
    assert alice_entry["resolution_notes"] == "Alice's note."
    assert alice_entry["root_cause"] == TICKET_1_CORRECT_ROOT_CAUSE


def test_filters_by_user_id_and_status(client, admin_token, learner_token):
    _submit(client, learner_token)

    response = client.get(SUBMISSIONS_URL, params={"status": "Resolved"}, headers=auth_headers(admin_token))
    assert all(s["status"] == "Resolved" for s in response.json())

    response = client.get(SUBMISSIONS_URL, params={"ticket_id": 999}, headers=auth_headers(admin_token))
    assert response.json() == []


def test_pagination_respects_limit(client, admin_token, learner_token):
    _submit(client, learner_token, ticket_id=1)
    _submit(client, learner_token, ticket_id=2, root_cause="wrong", actions=[])

    response = client.get(SUBMISSIONS_URL, params={"limit": 1}, headers=auth_headers(admin_token))
    assert len(response.json()) == 1
