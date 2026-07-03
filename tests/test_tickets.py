"""TDD suite for the learner-tier ITC ticket submission engine.

These tests drive the real HTTP surface (`GET /api/tickets`,
`POST /api/tickets/submit`) as an authenticated learner would, via
FastAPI's `TestClient`. Auth/registration mechanics live in `test_auth.py`;
admin-tier tickets live in `test_admin.py`. Shared fixtures (`client`,
`learner_token`) live in `conftest.py`.
"""

import pytest

from tests.conftest import auth_headers

SUBMIT_URL = "/api/tickets/submit"
TICKETS_URL = "/api/tickets"


# ---------------------------------------------------------------------------
# Fixture submissions
# ---------------------------------------------------------------------------

VALID_TICKET_1_SUBMISSION = '''
import csv
import json

GROUP_MAP = {
    "IT": ["VPN-Access", "Domain-Admins"],
    "HR": ["HR-Portal", "Payroll-ReadOnly"],
    "Finance": ["Finance-Systems", "Payroll-ReadOnly"],
    "Sales": ["CRM-Access"],
}


def provision_users(csv_data):
    reader = csv.DictReader(csv_data.strip().splitlines())
    records = []
    for row in reader:
        first_name = row["first_name"].strip()
        last_name = row["last_name"].strip()
        department = row["department"].strip()
        email = f"{first_name.lower()}.{last_name.lower()}@company.com"
        records.append({
            "first_name": first_name,
            "last_name": last_name,
            "department": department,
            "email": email,
            "groups": GROUP_MAP.get(department, ["General-Access"]),
        })
    return records
'''

# Silently returns nothing for every employee -- wrong output, but does not raise.
BROKEN_TICKET_1_SUBMISSION = "def provision_users(csv_data):\n    return []\n"

VALID_TICKET_2_SUBMISSION = (
    "SELECT ip_address, COUNT(*) AS failed_attempts "
    "FROM access_logs "
    "WHERE status = 'FAILED' AND attempt_time >= datetime('now', '-1 hour') "
    "GROUP BY ip_address "
    "HAVING COUNT(*) > 5"
)

# Attempts to chain a destructive statement after the SELECT.
DESTRUCTIVE_TICKET_2_SUBMISSION = "DROP TABLE access_logs; SELECT 1"

VALID_TICKET_3_SUBMISSION = '''
import re


def extract_unauthorized_ips(log_text):
    pattern = r"(?:DENY|BLOCKED)\\s+src=(\\d{1,3}(?:\\.\\d{1,3}){3})"
    return sorted({m.group(1) for m in re.finditer(pattern, log_text)})
'''


# ---------------------------------------------------------------------------
# Catalog sanity
# ---------------------------------------------------------------------------


def test_list_tickets_requires_authentication(client):
    response = client.get(TICKETS_URL)
    assert response.status_code == 401


def test_list_tickets_returns_only_the_three_learner_scenarios(client, learner_token):
    response = client.get(TICKETS_URL, headers=auth_headers(learner_token))

    assert response.status_code == 200
    tickets = response.json()
    assert len(tickets) == 3
    assert {t["id"] for t in tickets} == {1, 2, 3}
    assert {t["title"] for t in tickets} == {
        "The User Provisioning Script",
        "The Account Lockout Audit",
        "The Firewall Breach",
    }


# ---------------------------------------------------------------------------
# Task 1: The User Provisioning Script (Python / csv / json)
# ---------------------------------------------------------------------------


def test_task_1_valid_submission_grants_automation_xp(client, learner_token):
    response = client.post(
        SUBMIT_URL, json={"ticket_id": 1, "submission": VALID_TICKET_1_SUBMISSION}, headers=auth_headers(learner_token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["details"] == []
    assert body["xp_awarded"] == 50
    assert body["user"]["automation_xp"] == 50
    # Only the automation track should move.
    assert body["user"]["networking_xp"] == 0
    assert body["user"]["database_xp"] == 0


def test_task_1_broken_submission_fails_without_awarding_xp(client, learner_token):
    response = client.post(
        SUBMIT_URL, json={"ticket_id": 1, "submission": BROKEN_TICKET_1_SUBMISSION}, headers=auth_headers(learner_token)
    )

    assert response.status_code == 200, "a wrong-but-non-crashing script must not error the API"
    body = response.json()
    assert body["passed"] is False
    assert body["xp_awarded"] == 0
    assert body["user"]["automation_xp"] == 0
    assert len(body["details"]) > 0, "learner should get actionable feedback on what's missing"


# ---------------------------------------------------------------------------
# Task 2: The Account Lockout Audit (SQL / GROUP BY / HAVING)
# ---------------------------------------------------------------------------


def test_task_2_valid_sql_query_grants_database_xp(client, learner_token):
    response = client.post(
        SUBMIT_URL, json={"ticket_id": 2, "submission": VALID_TICKET_2_SUBMISSION}, headers=auth_headers(learner_token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["details"] == []
    assert body["xp_awarded"] == 100
    assert body["user"]["database_xp"] == 100
    assert body["user"]["automation_xp"] == 0
    assert body["user"]["networking_xp"] == 0


def test_task_2_rejects_destructive_sql_statement(client, learner_token):
    """Defense-in-depth: a stacked DROP TABLE must never reach the sandbox DB."""
    response = client.post(
        SUBMIT_URL,
        json={"ticket_id": 2, "submission": DESTRUCTIVE_TICKET_2_SUBMISSION},
        headers=auth_headers(learner_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["xp_awarded"] == 0
    assert "single sql statement" in body["message"].lower()

    # The catalog must still be intact -- prove the DROP never executed.
    tickets_response = client.get(TICKETS_URL, headers=auth_headers(learner_token))
    assert len(tickets_response.json()) == 3


# ---------------------------------------------------------------------------
# Task 3: The Firewall Breach (Python / re)
# ---------------------------------------------------------------------------


def test_task_3_valid_regex_script_grants_networking_xp(client, learner_token):
    response = client.post(
        SUBMIT_URL, json={"ticket_id": 3, "submission": VALID_TICKET_3_SUBMISSION}, headers=auth_headers(learner_token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["details"] == []
    assert body["xp_awarded"] == 150
    assert body["user"]["networking_xp"] == 150
    assert body["user"]["automation_xp"] == 0
    assert body["user"]["database_xp"] == 0


# ---------------------------------------------------------------------------
# "Server Downtime Counter-Attack": broken submissions must fail gracefully,
# never take the API down or corrupt XP state.
# ---------------------------------------------------------------------------

_SYNTAX_ERROR_SUBMISSION = "def extract_unauthorized_ips(log_text)\n    return []\n"  # missing colon

_RUNTIME_LOGIC_ERROR_SUBMISSION = (
    "import re\n\n\ndef extract_unauthorized_ips(log_text):\n    return undefined_variable\n"
)

_FORBIDDEN_IMPORT_SUBMISSION = (
    "import os\n\n\ndef extract_unauthorized_ips(log_text):\n    os.system('echo pwned')\n    return []\n"
)


@pytest.mark.parametrize(
    ("broken_submission", "expected_message_snippet"),
    [
        pytest.param(_SYNTAX_ERROR_SUBMISSION, "syntaxerror", id="syntax_error"),
        pytest.param(_RUNTIME_LOGIC_ERROR_SUBMISSION, "raised an error", id="runtime_logic_error"),
        pytest.param(_FORBIDDEN_IMPORT_SUBMISSION, "not permitted", id="sandbox_escape_attempt"),
    ],
)
def test_server_downtime_counter_attack_handles_broken_submissions(
    client, learner_token, broken_submission, expected_message_snippet
):
    """A crashing submission must be absorbed by the sandbox, not the server.

    This is the "Server Downtime Counter-Attack" safety net: syntax errors,
    runtime exceptions, and sandbox-escape attempts must all come back as a
    clean HTTP 200 with `passed=False` and zero XP awarded -- never a 500, and
    never a silent state change.
    """
    response = client.post(
        SUBMIT_URL, json={"ticket_id": 3, "submission": broken_submission}, headers=auth_headers(learner_token)
    )

    assert response.status_code == 200, "the API must stay up even when the submission crashes"
    body = response.json()
    assert body["passed"] is False
    assert body["xp_awarded"] == 0
    assert body["user"]["networking_xp"] == 0
    assert expected_message_snippet in body["message"].lower()


# ---------------------------------------------------------------------------
# Anti-farming, error paths, and cross-tier boundary enforcement
# ---------------------------------------------------------------------------


def test_resubmission_after_success_does_not_double_award_xp(client, learner_token):
    first = client.post(
        SUBMIT_URL, json={"ticket_id": 1, "submission": VALID_TICKET_1_SUBMISSION}, headers=auth_headers(learner_token)
    )
    second = client.post(
        SUBMIT_URL, json={"ticket_id": 1, "submission": VALID_TICKET_1_SUBMISSION}, headers=auth_headers(learner_token)
    )

    assert first.json()["xp_awarded"] == 50
    assert second.json()["passed"] is True
    assert second.json()["xp_awarded"] == 0, "resubmitting an already-solved ticket must not farm XP"
    assert second.json()["user"]["automation_xp"] == 50


def test_invalid_ticket_id_returns_404(client, learner_token):
    response = client.post(
        SUBMIT_URL, json={"ticket_id": 999, "submission": "SELECT 1"}, headers=auth_headers(learner_token)
    )
    assert response.status_code == 404


def test_admin_only_ticket_is_not_reachable_via_the_learner_endpoint(client, learner_token):
    """Ticket tiers are mutually exclusive: an admin ticket_id must 404 here,
    even for a submission that would otherwise be graded correctly by
    `/api/admin/tickets/submit`.
    """
    response = client.post(
        SUBMIT_URL, json={"ticket_id": 4, "submission": "irrelevant"}, headers=auth_headers(learner_token)
    )
    assert response.status_code == 404


def test_submit_without_token_is_rejected(client):
    response = client.post(SUBMIT_URL, json={"ticket_id": 1, "submission": VALID_TICKET_1_SUBMISSION})
    assert response.status_code == 401
