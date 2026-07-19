"""Test suite for the admin-only IT Operations dashboard.

Covers the authorization boundary (401 vs 403 vs 404) and the three admin
scenarios' grading logic (Employee Offboarding / Contractor Access Review /
Disk Space Emergency). Like the learner tier, tickets are resolved by
filling out a diagnostic form (root_cause, resolution_actions,
resolution_notes) -- no code, no SQL, no sandboxing needed anymore.
"""

import pytest

from tests.conftest import auth_headers

ADMIN_TICKETS_URL = "/api/admin/tickets"
ADMIN_SUBMIT_URL = "/api/admin/tickets/submit"
LEARNER_SUBMIT_URL = "/api/tickets/submit"

TICKET_5_CORRECT_ROOT_CAUSE = "Immediate involuntary termination requiring urgent access lockdown"
TICKET_5_CORRECT_ACTIONS = [
    "Disable the user's Active Directory account immediately",
    "Revoke all active VPN and remote access sessions",
    "Remote-wipe/lock the company-issued mobile device",
]

TICKET_6_CORRECT_ROOT_CAUSE = (
    "Contractors were provisioned using the default standard-employee access template instead of the contractor template"
)
TICKET_6_CORRECT_ACTIONS = [
    "Downgrade all affected contractor accounts to Tier 1 clearance",
    "Leave full-time staff access unchanged",
    "Document the remediation for the compliance audit trail",
]

TICKET_7_CORRECT_ROOT_CAUSE = (
    "Old log files and temporary files were never cleaned up because log rotation was never configured"
)
TICKET_7_CORRECT_ACTIONS = [
    "Purge log files past the retention policy",
    "Remove temporary files left with insecure/world-writable permissions",
    "Configure scheduled log rotation going forward",
]

TICKET_11_CORRECT_ROOT_CAUSE = "A critical security patch released 3 weeks ago was never applied to this server"
TICKET_11_CORRECT_ACTIONS = [
    "Apply the missing critical security patch immediately",
    "Verify the patched service restarts cleanly and the vulnerability no longer scans positive",
    "Document the remediation timeline for the compliance audit trail",
]


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


# ---------------------------------------------------------------------------
# Authorization boundary
# ---------------------------------------------------------------------------


def test_admin_tickets_requires_authentication(client):
    response = client.get(ADMIN_TICKETS_URL)
    assert response.status_code == 401


def test_admin_tickets_forbidden_for_non_admin(client, learner_token):
    response = client.get(ADMIN_TICKETS_URL, headers=auth_headers(learner_token))
    assert response.status_code == 403


def test_admin_submit_forbidden_for_non_admin(client, learner_token):
    response = _submit_admin(client, learner_token, 5, "irrelevant", [])
    assert response.status_code == 403


def test_admin_tickets_returns_four_admin_scenarios(client, admin_token):
    response = client.get(ADMIN_TICKETS_URL, headers=auth_headers(admin_token))

    assert response.status_code == 200
    tickets = response.json()
    assert {t["id"] for t in tickets} == {5, 6, 7, 11}
    assert {t["title"] for t in tickets} == {
        "Employee Offboarding -- Immediate Access Revocation",
        "Compliance Flag: Contractor Access Review",
        "Critical Server Disk Space Emergency",
        "Unpatched Critical Vulnerability on Public-Facing Server",
    }


def test_admin_submit_rejects_learner_tier_ticket_id(client, admin_token):
    """Ticket tiers are mutually exclusive, even for an admin account."""
    response = _submit_admin(client, admin_token, 1, "irrelevant", [])
    assert response.status_code == 404


def test_learner_endpoint_rejects_admin_tier_ticket_id_even_for_admins(client, admin_token):
    response = client.post(
        LEARNER_SUBMIT_URL,
        json={"ticket_id": 5, "root_cause": "irrelevant", "resolution_actions": []},
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Admin Ticket 5: Employee Offboarding -- Immediate Access Revocation
# ---------------------------------------------------------------------------


def test_admin_ticket_5_correct_resolution_grants_infra_points(client, admin_token):
    response = _submit_admin(client, admin_token, 5, TICKET_5_CORRECT_ROOT_CAUSE, TICKET_5_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["infra_points_awarded"] == 100
    assert body["user"]["infra_points"] == 100


def test_admin_ticket_5_treating_it_as_routine_departure_fails(client, admin_token):
    response = _submit_admin(
        client, admin_token, 5, "Standard resignation with a 2-week notice period", TICKET_5_CORRECT_ACTIONS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["infra_points_awarded"] == 0


def test_admin_ticket_5_missing_a_revocation_step_fails(client, admin_token):
    """Disabling AD but leaving an active VPN session or an unwiped phone is
    still a live access-security hole."""
    response = _submit_admin(
        client, admin_token, 5, TICKET_5_CORRECT_ROOT_CAUSE, ["Disable the user's Active Directory account immediately"]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert any("missing required resolution step" in detail.lower() for detail in body["details"])


# ---------------------------------------------------------------------------
# Admin Ticket 6: Compliance Flag: Contractor Access Review
# ---------------------------------------------------------------------------


def test_admin_ticket_6_correct_resolution_grants_infra_points(client, admin_token):
    response = _submit_admin(client, admin_token, 6, TICKET_6_CORRECT_ROOT_CAUSE, TICKET_6_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["infra_points_awarded"] == 150
    assert body["user"]["infra_points"] == 150


def test_admin_ticket_6_overreacting_by_deleting_accounts_fails(client, admin_token):
    """Deleting contractor accounts instead of downgrading them is a scope
    overreach, not a correct remediation."""
    response = _submit_admin(
        client,
        admin_token,
        6,
        TICKET_6_CORRECT_ROOT_CAUSE,
        ["Delete all contractor accounts immediately", "Document the remediation for the compliance audit trail"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert any("unnecessary or incorrect" in detail.lower() for detail in body["details"])


# ---------------------------------------------------------------------------
# Admin Ticket 7: Critical Server Disk Space Emergency
# ---------------------------------------------------------------------------


def test_admin_ticket_7_correct_resolution_grants_infra_points(client, admin_token):
    response = _submit_admin(client, admin_token, 7, TICKET_7_CORRECT_ROOT_CAUSE, TICKET_7_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["infra_points_awarded"] == 125
    assert body["user"]["infra_points"] == 125


def test_admin_ticket_7_blaming_hardware_instead_of_log_growth_fails(client, admin_token):
    response = _submit_admin(
        client, admin_token, 7, "A hardware fault reduced the disk's usable capacity", TICKET_7_CORRECT_ACTIONS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["infra_points_awarded"] == 0


# ---------------------------------------------------------------------------
# Admin Ticket 11: Unpatched Critical Vulnerability on Public-Facing Server
# ---------------------------------------------------------------------------


def test_admin_ticket_11_correct_resolution_grants_infra_points(client, admin_token):
    response = _submit_admin(client, admin_token, 11, TICKET_11_CORRECT_ROOT_CAUSE, TICKET_11_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["infra_points_awarded"] == 175
    assert body["user"]["infra_points"] == 175


def test_admin_ticket_11_dismissing_as_false_positive_fails(client, admin_token):
    response = _submit_admin(
        client, admin_token, 11, "This is a false positive from the vulnerability scanner", TICKET_11_CORRECT_ACTIONS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["infra_points_awarded"] == 0


# ---------------------------------------------------------------------------
# Anti-farming across the admin tier
# ---------------------------------------------------------------------------


def test_admin_resubmission_does_not_double_award_infra_points(client, admin_token):
    first = _submit_admin(client, admin_token, 5, TICKET_5_CORRECT_ROOT_CAUSE, TICKET_5_CORRECT_ACTIONS)
    second = _submit_admin(client, admin_token, 5, TICKET_5_CORRECT_ROOT_CAUSE, TICKET_5_CORRECT_ACTIONS)

    assert first.json()["infra_points_awarded"] == 100
    assert second.json()["passed"] is True
    assert second.json()["infra_points_awarded"] == 0
    assert second.json()["user"]["infra_points"] == 100


@pytest.mark.parametrize("ticket_id", [5, 6, 7, 11])
def test_admin_ticket_ids_do_not_collide_with_learner_ids(ticket_id):
    """Sanity check on the catalog itself: admin ticket ids must never
    overlap with learner ticket ids.
    """
    assert ticket_id not in {1, 2, 3, 4, 8, 9, 10}
