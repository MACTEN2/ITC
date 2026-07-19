"""Test suite for the learner ticket history feed (GET /api/history)."""

from tests.conftest import auth_headers

HISTORY_URL = "/api/history"
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


def test_history_is_empty_for_a_fresh_user(client, learner_token):
    response = client.get(HISTORY_URL, headers=auth_headers(learner_token))
    assert response.status_code == 200
    assert response.json() == []


def test_resolved_ticket_produces_a_resolved_history_entry_with_reward_fields(client, learner_token):
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    response = client.get(HISTORY_URL, headers=auth_headers(learner_token))
    assert response.status_code == 200
    entries = response.json()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["ticket_id"] == 1
    assert entry["status"] == "Resolved"
    assert entry["resolved_at"] is not None
    assert entry["reward_field"] == "automation_xp"
    assert entry["reward_amount"] == 100


def test_unresolved_attempt_shows_open_status_with_null_resolved_at(client, learner_token):
    _submit(client, learner_token, 1, "Caps Lock was enabled while entering the password", TICKET_1_CORRECT_ACTIONS)

    response = client.get(HISTORY_URL, headers=auth_headers(learner_token))
    entries = response.json()
    assert len(entries) == 1
    assert entries[0]["status"] == "Open"
    assert entries[0]["resolved_at"] is None
    assert entries[0]["reward_field"] is None


def test_history_department_filter(client, learner_token):
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)
    _submit(
        client,
        learner_token,
        2,
        "The access point is overloaded with far more connected devices than it's rated for",
        [
            "Install a second access point to split the client load",
            "Enable the 5GHz radio so compatible devices can move off the crowded 2.4GHz band",
        ],
    )

    response = client.get(HISTORY_URL, params={"department": "Help Desk"}, headers=auth_headers(learner_token))
    entries = response.json()
    assert {e["ticket_id"] for e in entries} == {1}


def test_history_status_filter(client, learner_token):
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)
    _submit(client, learner_token, 2, "wrong", [])

    response = client.get(HISTORY_URL, params={"status": "Resolved"}, headers=auth_headers(learner_token))
    entries = response.json()
    assert {e["ticket_id"] for e in entries} == {1}


def test_history_requires_authentication(client):
    response = client.get(HISTORY_URL)
    assert response.status_code == 401
