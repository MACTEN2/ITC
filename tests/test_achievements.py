"""Test suite for the achievement/badge system.

Badge catalog + criteria live in app/achievements_db.py; evaluation is
triggered from the submit routes right after a passing grade_submission()
(see app/main.py::submit_ticket and app/routes/admin.py::submit_admin_ticket).
"""

from tests.conftest import auth_headers

ACHIEVEMENTS_URL = "/api/achievements"
SUBMIT_URL = "/api/tickets/submit"
ADMIN_SUBMIT_URL = "/api/admin/tickets/submit"

TICKET_1_CORRECT_ROOT_CAUSE = (
    "The account is locked from repeated failed logons using the old password after the forced reset"
)
TICKET_1_CORRECT_ACTIONS = [
    "Unlock the account in Active Directory",
    "Confirm with the user that they are entering the NEW password, not the old one",
]

TICKET_2_CORRECT_ROOT_CAUSE = "The access point is overloaded with far more connected devices than it's rated for"
TICKET_2_CORRECT_ACTIONS = [
    "Install a second access point to split the client load",
    "Enable the 5GHz radio so compatible devices can move off the crowded 2.4GHz band",
]

TICKET_10_CORRECT_ROOT_CAUSE = "A newly added device on the network has a static IP conflicting with the printer's"
TICKET_10_CORRECT_ACTIONS = [
    "Reassign the conflicting device to a non-conflicting static IP",
    "Confirm the printer comes back online after the conflict is resolved",
    "Document the IP assignment to prevent a repeat conflict",
]

TICKET_5_CORRECT_ROOT_CAUSE = "Immediate involuntary termination requiring urgent access lockdown"
TICKET_5_CORRECT_ACTIONS = [
    "Disable the user's Active Directory account immediately",
    "Revoke all active VPN and remote access sessions",
    "Remote-wipe/lock the company-issued mobile device",
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


def _submit_admin(client, token, ticket_id, root_cause, resolution_actions, resolution_notes="Resolved and documented."):
    return client.post(
        ADMIN_SUBMIT_URL,
        json={
            "ticket_id": ticket_id,
            "root_cause": root_cause,
            "resolution_actions": resolution_actions,
            "resolution_notes": resolution_notes,
        },
        headers=auth_headers(token),
    )


def test_achievements_catalog_starts_fully_locked(client, learner_token):
    response = client.get(ACHIEVEMENTS_URL, headers=auth_headers(learner_token))
    assert response.status_code == 200
    badges = response.json()
    assert len(badges) > 0
    assert all(b["earned"] is False and b["earned_at"] is None for b in badges)


def test_first_resolution_unlocks_first_blood_badge(client, learner_token):
    response = _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)
    unlocked_ids = {b["id"] for b in response.json()["badges_unlocked"]}
    assert "first_blood" in unlocked_ids

    achievements = client.get(ACHIEVEMENTS_URL, headers=auth_headers(learner_token)).json()
    first_blood = next(b for b in achievements if b["id"] == "first_blood")
    assert first_blood["earned"] is True
    assert first_blood["earned_at"] is not None


def test_resubmitting_an_already_resolved_ticket_does_not_retrigger_the_unlock(client, learner_token):
    _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)
    second = _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    assert second.json()["badges_unlocked"] == []


def test_department_completion_badge_unlocks_only_after_every_ticket_in_department(client, learner_token):
    first = _submit(client, learner_token, 2, TICKET_2_CORRECT_ROOT_CAUSE, TICKET_2_CORRECT_ACTIONS)
    assert "dept_master_network_operations" not in {b["id"] for b in first.json()["badges_unlocked"]}

    second = _submit(client, learner_token, 10, TICKET_10_CORRECT_ROOT_CAUSE, TICKET_10_CORRECT_ACTIONS)
    assert "dept_master_network_operations" in {b["id"] for b in second.json()["badges_unlocked"]}


def test_resolving_an_admin_ticket_unlocks_infra_guardian_badge(client, admin_token):
    response = _submit_admin(client, admin_token, 5, TICKET_5_CORRECT_ROOT_CAUSE, TICKET_5_CORRECT_ACTIONS)
    unlocked_ids = {b["id"] for b in response.json()["badges_unlocked"]}
    assert "infra_guardian" in unlocked_ids
