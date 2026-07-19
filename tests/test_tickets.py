"""TDD suite for the learner-tier ITC ticket resolution engine.

These tests drive the real HTTP surface (`GET /api/tickets`,
`POST /api/tickets/submit`) as an authenticated learner would, via
FastAPI's `TestClient`. Auth/registration mechanics live in `test_auth.py`;
admin-tier tickets live in `test_admin.py`. Shared fixtures (`client`,
`learner_token`) live in `conftest.py`.

Tickets are resolved by filling out a diagnostic form (root_cause,
resolution_actions, resolution_notes) -- there is no code involved anywhere,
mirroring how a real Help Desk / IT Support agent actually closes a ticket
in a system like ServiceNow or Zendesk. See app/tickets_db.py for the full
catalog and answer keys.
"""

from tests.conftest import auth_headers

SUBMIT_URL = "/api/tickets/submit"
TICKETS_URL = "/api/tickets"

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

TICKET_3_CORRECT_ROOT_CAUSE = (
    "The nightly bulk import ran with duplicate-checking disabled, inserting new rows for existing customers"
)
TICKET_3_CORRECT_ACTIONS = [
    "Run the CRM's record de-duplication/merge tool on the affected customers",
    "Re-enable duplicate-checking on the bulk import job going forward",
    "Notify Sales so the duplicate invoices can be corrected",
]

TICKET_4_CORRECT_ROOT_CAUSE = "A phishing attempt impersonating a vendor using a lookalike domain"
TICKET_4_CORRECT_ACTIONS = [
    "Quarantine the email and report it to the security team",
    "Advise the employee not to click any links or reply",
    "Block the sender's domain at the email gateway",
]

TICKET_8_CORRECT_ROOT_CAUSE = "The VPN client is still using the cached old password instead of the new one"
TICKET_8_CORRECT_ACTIONS = [
    "Clear the saved/cached credentials in the VPN client",
    "Have the employee re-enter and save the new password in the VPN client",
]

TICKET_9_CORRECT_ROOT_CAUSE = (
    "A frequently-queried column has no index, causing full table scans as the table grew"
)
TICKET_9_CORRECT_ACTIONS = [
    "Add an index on the frequently-queried column",
    "Verify query performance improves after the index is added",
    "Document the change for future schema reviews",
]

TICKET_10_CORRECT_ROOT_CAUSE = "A newly added device on the network has a static IP conflicting with the printer's"
TICKET_10_CORRECT_ACTIONS = [
    "Reassign the conflicting device to a non-conflicting static IP",
    "Confirm the printer comes back online after the conflict is resolved",
    "Document the IP assignment to prevent a repeat conflict",
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


# ---------------------------------------------------------------------------
# Catalog sanity
# ---------------------------------------------------------------------------


def test_list_tickets_requires_authentication(client):
    response = client.get(TICKETS_URL)
    assert response.status_code == 401


def test_list_tickets_returns_only_the_seven_learner_scenarios(client, learner_token):
    response = client.get(TICKETS_URL, headers=auth_headers(learner_token))

    assert response.status_code == 200
    tickets = response.json()
    assert len(tickets) == 7
    assert {t["id"] for t in tickets} == {1, 2, 3, 4, 8, 9, 10}
    assert {t["title"] for t in tickets} == {
        "Employee Locked Out After Password Reset",
        "Persistent Wi-Fi Drops in the East Conference Room",
        "Duplicate Customer Records After CRM Import",
        "Suspicious Email Reported by Finance",
        "VPN Connection Fails for Remote Employee After Password Change",
        "Slow Database Query Performance After Table Growth",
        "Shared Printer Offline for Entire Finance Floor",
    }


def test_ticket_options_never_reveal_which_choice_is_correct(client, learner_token):
    """The API must only ever expose the multiple-choice options, never a
    field indicating which one is the answer."""
    response = client.get(TICKETS_URL, headers=auth_headers(learner_token))
    ticket = next(t for t in response.json() if t["id"] == 1)

    assert set(ticket.keys()) == {
        "id", "title", "department", "severity", "problem_description",
        "root_cause_options", "resolution_options", "logs_context", "validation_criteria",
    }
    assert TICKET_1_CORRECT_ROOT_CAUSE in ticket["root_cause_options"]


# ---------------------------------------------------------------------------
# Ticket 1: Employee Locked Out After Password Reset (Help Desk Tier 1)
# ---------------------------------------------------------------------------


def test_ticket_1_correct_resolution_grants_automation_xp(client, learner_token):
    response = _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["details"] == []
    assert body["xp_awarded"] == 100
    assert body["user"]["automation_xp"] == 100
    assert body["user"]["networking_xp"] == 0


def test_ticket_1_wrong_root_cause_fails_without_awarding_xp(client, learner_token):
    response = _submit(
        client, learner_token, 1, "Caps Lock was enabled while entering the password", TICKET_1_CORRECT_ACTIONS
    )

    assert response.status_code == 200, "a wrong-but-valid submission must not error the API"
    body = response.json()
    assert body["passed"] is False
    assert body["xp_awarded"] == 0
    assert body["user"]["automation_xp"] == 0
    assert any("root cause" in detail.lower() for detail in body["details"])


def test_ticket_1_missing_resolution_step_fails(client, learner_token):
    """Unlocking the account alone isn't enough -- it'll just re-lock unless
    the user is also confirmed to be using the new password."""
    response = _submit(
        client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, ["Unlock the account in Active Directory"]
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["xp_awarded"] == 0
    assert any("missing required resolution step" in detail.lower() for detail in body["details"])


def test_ticket_1_extra_unnecessary_action_fails(client, learner_token):
    response = _submit(
        client,
        learner_token,
        1,
        TICKET_1_CORRECT_ROOT_CAUSE,
        [*TICKET_1_CORRECT_ACTIONS, "Escalate to Network Engineering"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert any("unnecessary or incorrect" in detail.lower() for detail in body["details"])


def test_ticket_1_missing_resolution_notes_fails(client, learner_token):
    response = _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS, "")

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert any("resolution summary note is required" in detail.lower() for detail in body["details"])


# ---------------------------------------------------------------------------
# Ticket 2: Persistent Wi-Fi Drops in the East Conference Room (Network Support)
# ---------------------------------------------------------------------------


def test_ticket_2_correct_resolution_grants_networking_xp(client, learner_token):
    response = _submit(client, learner_token, 2, TICKET_2_CORRECT_ROOT_CAUSE, TICKET_2_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["xp_awarded"] == 50
    assert body["user"]["networking_xp"] == 50
    assert body["user"]["automation_xp"] == 0


def test_ticket_2_wrong_root_cause_fails(client, learner_token):
    response = _submit(
        client, learner_token, 2, "The access point's firmware is out of date", TICKET_2_CORRECT_ACTIONS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["xp_awarded"] == 0


# ---------------------------------------------------------------------------
# Ticket 3: Duplicate Customer Records After CRM Import (Database Administration)
# ---------------------------------------------------------------------------


def test_ticket_3_correct_resolution_grants_database_xp(client, learner_token):
    response = _submit(client, learner_token, 3, TICKET_3_CORRECT_ROOT_CAUSE, TICKET_3_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["xp_awarded"] == 100
    assert body["user"]["database_xp"] == 100


def test_ticket_3_partial_resolution_missing_a_step_fails(client, learner_token):
    """Fixing the duplicates without also disabling future duplicate imports
    just means the same problem recurs tomorrow night."""
    response = _submit(
        client,
        learner_token,
        3,
        TICKET_3_CORRECT_ROOT_CAUSE,
        ["Run the CRM's record de-duplication/merge tool on the affected customers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert any("missing required resolution step" in detail.lower() for detail in body["details"])


# ---------------------------------------------------------------------------
# Ticket 4: Suspicious Email Reported by Finance (Security Awareness / Help Desk)
# ---------------------------------------------------------------------------


def test_ticket_4_correct_resolution_grants_automation_xp(client, learner_token):
    response = _submit(client, learner_token, 4, TICKET_4_CORRECT_ROOT_CAUSE, TICKET_4_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["xp_awarded"] == 150
    assert body["user"]["automation_xp"] == 150


def test_ticket_4_treating_it_as_legitimate_is_a_dangerous_wrong_answer(client, learner_token):
    """The single worst possible call here -- forwarding real banking
    details to "verify" -- must fail cleanly, not be treated as valid input."""
    response = _submit(
        client,
        learner_token,
        4,
        "A legitimate vendor invoice update",
        ["Forward the employee's real banking details to verify"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["xp_awarded"] == 0


# ---------------------------------------------------------------------------
# Ticket 8: VPN Connection Fails for Remote Employee After Password Change
# ---------------------------------------------------------------------------


def test_ticket_8_correct_resolution_grants_networking_xp(client, learner_token):
    response = _submit(client, learner_token, 8, TICKET_8_CORRECT_ROOT_CAUSE, TICKET_8_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["xp_awarded"] == 75
    assert body["user"]["networking_xp"] == 75


def test_ticket_8_assuming_server_wide_outage_fails(client, learner_token):
    response = _submit(client, learner_token, 8, "The VPN server is down for everyone", TICKET_8_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["xp_awarded"] == 0


# ---------------------------------------------------------------------------
# Ticket 9: Slow Database Query Performance After Table Growth
# ---------------------------------------------------------------------------


def test_ticket_9_correct_resolution_grants_database_xp(client, learner_token):
    response = _submit(client, learner_token, 9, TICKET_9_CORRECT_ROOT_CAUSE, TICKET_9_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["xp_awarded"] == 100
    assert body["user"]["database_xp"] == 100


def test_ticket_9_blaming_ram_instead_of_missing_index_fails(client, learner_token):
    response = _submit(
        client, learner_token, 9, "The database server needs more RAM", TICKET_9_CORRECT_ACTIONS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["xp_awarded"] == 0


# ---------------------------------------------------------------------------
# Ticket 10: Shared Printer Offline for Entire Finance Floor
# ---------------------------------------------------------------------------


def test_ticket_10_correct_resolution_grants_networking_xp(client, learner_token):
    response = _submit(client, learner_token, 10, TICKET_10_CORRECT_ROOT_CAUSE, TICKET_10_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is True
    assert body["xp_awarded"] == 40
    assert body["user"]["networking_xp"] == 40


def test_ticket_10_blaming_toner_instead_of_ip_conflict_fails(client, learner_token):
    response = _submit(client, learner_token, 10, "The printer is out of toner", TICKET_10_CORRECT_ACTIONS)

    assert response.status_code == 200
    body = response.json()
    assert body["passed"] is False
    assert body["xp_awarded"] == 0


# ---------------------------------------------------------------------------
# Search & filter (GET /api/tickets?department=&severity=&q=)
# ---------------------------------------------------------------------------


def test_list_tickets_filters_by_department(client, learner_token):
    response = client.get(TICKETS_URL, params={"department": "Network Operations"}, headers=auth_headers(learner_token))

    assert response.status_code == 200
    tickets = response.json()
    assert {t["id"] for t in tickets} == {2, 10}


def test_list_tickets_filters_by_severity(client, learner_token):
    response = client.get(TICKETS_URL, params={"severity": "Catastrophic"}, headers=auth_headers(learner_token))

    assert response.status_code == 200
    tickets = response.json()
    assert {t["id"] for t in tickets} == {4}


def test_list_tickets_search_matches_description_case_insensitively(client, learner_token):
    """'Phishing' appears in ticket 4's description ('Report Phishing' button) -- an
    uppercase search term should still match it case-insensitively."""
    response = client.get(TICKETS_URL, params={"q": "PHISHING"}, headers=auth_headers(learner_token))

    assert response.status_code == 200
    tickets = response.json()
    assert {t["id"] for t in tickets} == {4}


def test_list_tickets_search_matches_description_substring(client, learner_token):
    response = client.get(TICKETS_URL, params={"q": "printer"}, headers=auth_headers(learner_token))

    assert response.status_code == 200
    tickets = response.json()
    assert {t["id"] for t in tickets} == {10}


def test_list_tickets_combined_filters_and_together(client, learner_token):
    response = client.get(
        TICKETS_URL,
        params={"department": "Help Desk", "severity": "Incident"},
        headers=auth_headers(learner_token),
    )

    assert response.status_code == 200
    tickets = response.json()
    assert {t["id"] for t in tickets} == {1, 8}


def test_list_tickets_no_matches_returns_empty_list_not_error(client, learner_token):
    response = client.get(TICKETS_URL, params={"department": "Nonexistent Dept"}, headers=auth_headers(learner_token))

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Anti-farming, error paths, and cross-tier boundary enforcement
# ---------------------------------------------------------------------------


def test_resubmission_after_success_does_not_double_award_xp(client, learner_token):
    first = _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)
    second = _submit(client, learner_token, 1, TICKET_1_CORRECT_ROOT_CAUSE, TICKET_1_CORRECT_ACTIONS)

    assert first.json()["xp_awarded"] == 100
    assert second.json()["passed"] is True
    assert second.json()["xp_awarded"] == 0, "resubmitting an already-solved ticket must not farm XP"
    assert second.json()["user"]["automation_xp"] == 100


def test_invalid_ticket_id_returns_404(client, learner_token):
    response = _submit(client, learner_token, 999, "irrelevant", [])
    assert response.status_code == 404


def test_admin_only_ticket_is_not_reachable_via_the_learner_endpoint(client, learner_token):
    """Ticket tiers are mutually exclusive: an admin ticket_id must 404 here,
    even for a submission that would otherwise be graded correctly by
    `/api/admin/tickets/submit`.
    """
    response = _submit(client, learner_token, 5, "irrelevant", [])
    assert response.status_code == 404


def test_submit_without_token_is_rejected(client):
    response = client.post(
        SUBMIT_URL,
        json={"ticket_id": 1, "root_cause": TICKET_1_CORRECT_ROOT_CAUSE, "resolution_actions": TICKET_1_CORRECT_ACTIONS},
    )
    assert response.status_code == 401
