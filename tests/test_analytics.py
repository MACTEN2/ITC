"""Test suite for admin-only aggregate analytics (GET /api/analytics/*)."""

from tests.conftest import auth_headers

DEPARTMENTS_URL = "/api/analytics/departments"
SUMMARY_URL = "/api/analytics/summary"
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


def test_departments_forbidden_for_non_admin(client, learner_token):
    response = client.get(DEPARTMENTS_URL, headers=auth_headers(learner_token))
    assert response.status_code == 403


def test_summary_forbidden_for_non_admin(client, learner_token):
    response = client.get(SUMMARY_URL, headers=auth_headers(learner_token))
    assert response.status_code == 403


def test_department_stats_reflect_the_seeded_catalog(client, admin_token):
    response = client.get(DEPARTMENTS_URL, headers=auth_headers(admin_token))
    assert response.status_code == 200
    departments = {d["department"] for d in response.json()}
    assert "Help Desk" in departments
    assert "Network Operations" in departments
    assert "Database Administration" in departments
    assert "SysAdmin" in departments
    assert "Security / Governance" in departments


def test_department_stats_update_after_a_resolution(client, learner_token, admin_token):
    _resolve_ticket_1(client, learner_token)

    response = client.get(DEPARTMENTS_URL, headers=auth_headers(admin_token))
    help_desk = next(d for d in response.json() if d["department"] == "Help Desk")
    assert help_desk["resolved_count"] == 1
    assert help_desk["total_attempts"] == 1
    assert help_desk["resolution_rate"] == 1.0
    assert help_desk["unique_learners_engaged"] == 1


def test_summary_totals_update_after_resolutions(client, learner_token, admin_token):
    before = client.get(SUMMARY_URL, headers=auth_headers(admin_token)).json()
    _resolve_ticket_1(client, learner_token)
    after = client.get(SUMMARY_URL, headers=auth_headers(admin_token)).json()

    assert after["total_tickets_resolved"] == before["total_tickets_resolved"] + 1
    assert after["total_users"] >= 2
