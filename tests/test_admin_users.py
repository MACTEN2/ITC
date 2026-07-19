"""Test suite for the admin-only, view-only user management endpoint."""

from tests.conftest import auth_headers, register_and_login

ADMIN_USERS_URL = "/api/admin/users"
SUBMIT_URL = "/api/tickets/submit"

TICKET_1_CORRECT_ROOT_CAUSE = (
    "The account is locked from repeated failed logons using the old password after the forced reset"
)
TICKET_1_CORRECT_ACTIONS = [
    "Unlock the account in Active Directory",
    "Confirm with the user that they are entering the NEW password, not the old one",
]


def test_forbidden_for_non_admin(client, learner_token):
    response = client.get(ADMIN_USERS_URL, headers=auth_headers(learner_token))
    assert response.status_code == 403


def test_requires_authentication(client):
    response = client.get(ADMIN_USERS_URL)
    assert response.status_code == 401


def test_lists_users_with_expected_fields(client, admin_token, learner_token):
    response = client.get(ADMIN_USERS_URL, headers=auth_headers(admin_token))
    assert response.status_code == 200
    usernames = {u["username"] for u in response.json()}
    assert {"root_admin", "learner_alice"} <= usernames
    admin_entry = next(u for u in response.json() if u["username"] == "root_admin")
    assert admin_entry["is_admin"] is True
    assert "email" in admin_entry  # admin view is allowed to see email, unlike the public profile


def test_q_filters_by_username_or_email(client, admin_token, learner_token):
    register_and_login(client, "learner_bob")

    response = client.get(ADMIN_USERS_URL, params={"q": "bob"}, headers=auth_headers(admin_token))
    usernames = {u["username"] for u in response.json()}
    assert usernames == {"learner_bob"}


def test_aggregate_counts_reflect_actual_state(client, admin_token, learner_token):
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

    response = client.get(ADMIN_USERS_URL, headers=auth_headers(admin_token))
    alice = next(u for u in response.json() if u["username"] == "learner_alice")
    assert alice["resolved_ticket_count"] == 1
    assert alice["badges_earned"] == 1  # first_blood


def test_no_promote_demote_endpoint_exists(client, admin_token, learner_token):
    """Hard constraint: is_admin must never be settable over the API."""
    response = client.patch(f"{ADMIN_USERS_URL}/1", json={"is_admin": True}, headers=auth_headers(admin_token))
    assert response.status_code in (404, 405)
