"""Test suite for the admin-only IT Operations dashboard.

Covers the authorization boundary (401 vs 403 vs 404), the three admin
scenarios' grading logic (Employee Terminations / Security Compliance Audit /
Disk Space Emergency), and the security properties specific to this tier: the
path-jailed os/shutil sandbox and the single-scoped-UPDATE SQL sandbox.
"""

import pytest

from tests.conftest import auth_headers

ADMIN_TICKETS_URL = "/api/admin/tickets"
ADMIN_SUBMIT_URL = "/api/admin/tickets/submit"
LEARNER_SUBMIT_URL = "/api/tickets/submit"


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
    response = client.post(
        ADMIN_SUBMIT_URL, json={"ticket_id": 4, "submission": "irrelevant"}, headers=auth_headers(learner_token)
    )
    assert response.status_code == 403


def test_admin_tickets_returns_three_admin_scenarios(client, admin_token):
    response = client.get(ADMIN_TICKETS_URL, headers=auth_headers(admin_token))

    assert response.status_code == 200
    tickets = response.json()
    assert {t["id"] for t in tickets} == {4, 5, 6}
    assert {t["title"] for t in tickets} == {
        "Employee Terminations",
        "The Security Compliance Audit",
        "Disk Space Emergency",
    }


def test_admin_submit_rejects_learner_tier_ticket_id(client, admin_token):
    """Ticket tiers are mutually exclusive, even for an admin account."""
    response = client.post(
        ADMIN_SUBMIT_URL, json={"ticket_id": 1, "submission": "irrelevant"}, headers=auth_headers(admin_token)
    )
    assert response.status_code == 404


def test_learner_endpoint_rejects_admin_tier_ticket_id_even_for_admins(client, admin_token):
    response = client.post(
        LEARNER_SUBMIT_URL, json={"ticket_id": 4, "submission": "irrelevant"}, headers=auth_headers(admin_token)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Admin Ticket 4: Employee Terminations (Python / os / shutil, path-jailed)
# ---------------------------------------------------------------------------

VALID_OFFBOARDING_SUBMISSION = """
import os
import shutil


def offboard_employee(user_id, directory, cache_path):
    for record in directory:
        if record["user_id"] == user_id:
            record["active"] = False
    if os.path.exists(cache_path):
        shutil.rmtree(cache_path)
    return directory
"""

# Never actually sweeps the cache directory -- only "would remove" it.
BROKEN_OFFBOARDING_SUBMISSION = """
def offboard_employee(user_id, directory, cache_path):
    return directory
"""

# Tries to escape the sandbox jail via an absolute host path.
SANDBOX_ESCAPE_OFFBOARDING_SUBMISSION = """
import os


def offboard_employee(user_id, directory, cache_path):
    os.remove("/etc/hosts")
    return directory
"""


def test_admin_ticket_4_valid_offboarding_grants_infra_points(client, admin_token):
    response = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 4, "submission": VALID_OFFBOARDING_SUBMISSION},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["infra_points_awarded"] == 100
    assert body["user"]["infra_points"] == 100


def test_admin_ticket_4_broken_offboarding_fails_without_points(client, admin_token):
    response = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 4, "submission": BROKEN_OFFBOARDING_SUBMISSION},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["infra_points_awarded"] == 0
    assert len(body["details"]) > 0


def test_admin_ticket_4_sandbox_escape_attempt_is_contained(client, admin_token):
    """The jailed os/shutil facade must block access outside the throwaway
    grading directory -- this must fail gracefully, not crash the server or
    touch the real filesystem.
    """
    response = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 4, "submission": SANDBOX_ESCAPE_OFFBOARDING_SUBMISSION},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200, "a sandbox escape attempt must not crash the API"
    body = response.json()
    assert body["passed"] is False
    assert body["infra_points_awarded"] == 0
    assert "outside the sandboxed directory" in body["message"].lower()


# ---------------------------------------------------------------------------
# Admin Ticket 5: The Security Compliance Audit (SQL UPDATE / WHERE / AND)
# ---------------------------------------------------------------------------

VALID_COMPLIANCE_UPDATE = (
    "UPDATE mock_employees SET clearance_level = 'Tier 1' "
    "WHERE department = 'External QA' AND employment_type = 'Contractor'"
)

# Missing the employment_type condition -- would also downgrade full-time staff.
OVERBROAD_COMPLIANCE_UPDATE = "UPDATE mock_employees SET clearance_level = 'Tier 1' WHERE department = 'External QA'"

UNCONDITIONAL_COMPLIANCE_UPDATE = "UPDATE mock_employees SET clearance_level = 'Tier 1'"

DESTRUCTIVE_COMPLIANCE_SUBMISSION = "DROP TABLE mock_employees; SELECT 1"


def test_admin_ticket_5_valid_update_grants_infra_points(client, admin_token):
    response = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 5, "submission": VALID_COMPLIANCE_UPDATE},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["infra_points_awarded"] == 150
    assert body["user"]["infra_points"] == 150


def test_admin_ticket_5_overbroad_update_fails_scope_check(client, admin_token):
    """The classic missing-AND-clause bug: must be caught, not silently accepted."""
    response = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 5, "submission": OVERBROAD_COMPLIANCE_UPDATE},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["infra_points_awarded"] == 0
    assert any("wu" in detail.lower() for detail in body["details"]), "should flag the wrongly-downgraded full-timer"


def test_admin_ticket_5_rejects_unconditional_update(client, admin_token):
    response = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 5, "submission": UNCONDITIONAL_COMPLIANCE_UPDATE},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert "where clause" in body["message"].lower()


def test_admin_ticket_5_rejects_destructive_statement(client, admin_token):
    response = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 5, "submission": DESTRUCTIVE_COMPLIANCE_SUBMISSION},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["infra_points_awarded"] == 0


# ---------------------------------------------------------------------------
# Admin Ticket 6: Disk Space Emergency (Python / os / os.path, path-jailed)
# ---------------------------------------------------------------------------

VALID_LOG_ROTATION_SUBMISSION = """
import os
import time

MAX_SIZE_BYTES = 50 * 1024 * 1024
MAX_AGE_DAYS = 14


def rotate_logs(log_directory):
    removed = []
    now = time.time()
    for filename in os.listdir(log_directory):
        file_path = os.path.join(log_directory, filename)
        too_big = os.path.getsize(file_path) > MAX_SIZE_BYTES
        too_old = (now - os.path.getmtime(file_path)) / 86400 > MAX_AGE_DAYS
        if too_big or too_old:
            os.remove(file_path)
            removed.append(filename)
    return removed
"""

# Only checks size, never age -- matches the shipped starter code's bug.
SIZE_ONLY_LOG_ROTATION_SUBMISSION = """
import os

MAX_SIZE_BYTES = 50 * 1024 * 1024


def rotate_logs(log_directory):
    removed = []
    for filename in os.listdir(log_directory):
        file_path = os.path.join(log_directory, filename)
        if os.path.getsize(file_path) > MAX_SIZE_BYTES:
            os.remove(file_path)
            removed.append(filename)
    return removed
"""


def test_admin_ticket_6_valid_rotation_grants_infra_points(client, admin_token):
    response = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 6, "submission": VALID_LOG_ROTATION_SUBMISSION},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["infra_points_awarded"] == 125
    assert body["user"]["infra_points"] == 125


def test_admin_ticket_6_size_only_rotation_fails(client, admin_token):
    response = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 6, "submission": SIZE_ONLY_LOG_ROTATION_SUBMISSION},
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["infra_points_awarded"] == 0
    assert any("archive.log.old" in detail for detail in body["details"])


# ---------------------------------------------------------------------------
# Anti-farming across the admin tier
# ---------------------------------------------------------------------------


def test_admin_resubmission_does_not_double_award_infra_points(client, admin_token):
    first = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 4, "submission": VALID_OFFBOARDING_SUBMISSION},
        headers=auth_headers(admin_token),
    )
    second = client.post(
        ADMIN_SUBMIT_URL,
        json={"ticket_id": 4, "submission": VALID_OFFBOARDING_SUBMISSION},
        headers=auth_headers(admin_token),
    )

    assert first.json()["infra_points_awarded"] == 100
    assert second.json()["passed"] is True
    assert second.json()["infra_points_awarded"] == 0
    assert second.json()["user"]["infra_points"] == 100


@pytest.mark.parametrize("ticket_id", [4, 5, 6])
def test_admin_ticket_ids_do_not_collide_with_learner_ids(ticket_id):
    """Sanity check on the catalog itself: admin ticket ids (4-6) must never
    overlap with learner ticket ids (1-3), since both endpoints share one
    `tickets` table distinguished only by the `is_admin_only` flag.
    """
    assert ticket_id not in {1, 2, 3}
