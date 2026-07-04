"""Hardcoded IT support ticket scenarios plus their grading logic.

There is no code execution anywhere in this module (or this app). Every
ticket is resolved the way a real Help Desk / IT Support agent actually
closes a ticket in a system like ServiceNow or Zendesk: read the scenario
and supporting context, diagnose the root cause from a fixed list of
plausible options, select the resolution action(s) that actually fix it from
a checklist, and write a short resolution note before closing the case.

Seven tickets ship in two tiers:

    - 4 learner-facing tickets (`is_admin_only=False`), served by
      `GET/POST /api/tickets*` and rewarded in one of the three skill XP tracks:
        1. Employee Locked Out After Password Reset (Help Desk Tier 1)
        2. Persistent Wi-Fi Drops in the East Conference Room (Network Support)
        3. Duplicate Customer Records After CRM Import (Database Administration)
        4. Suspicious Email Reported by Finance (Security Awareness / Help Desk)
    - 3 admin-only tickets (`is_admin_only=True`), served by
      `GET/POST /api/admin/tickets*` and rewarded in `infra_points`:
        5. Employee Offboarding -- Immediate Access Revocation
        6. Compliance Flag: Contractor Access Review
        7. Critical Server Disk Space Emergency

Grading is a single generic mechanism (`_make_selection_verifier`): the
submitted root cause must exactly match the correct one, the submitted
resolution actions must exactly match the correct set (no missing steps, no
unnecessary ones), and a non-empty resolution note is required -- exactly
what a real ticketing system enforces before letting you close a case. The
correct answers live only here in Python, never in the `Ticket` row served
by the API, so `GET /api/tickets` can never leak them.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.models import ProgressStatus, Severity, User, UserTicketProgress


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Shared result / catalog / submission types
# ---------------------------------------------------------------------------


@dataclass
class TicketSubmission:
    """A learner's/admin's filled-out resolution form for one ticket."""

    root_cause: str
    resolution_actions: list[str] = field(default_factory=list)
    resolution_notes: str = ""


@dataclass
class VerificationResult:
    """Outcome of grading a single submission."""

    passed: bool
    message: str
    details: list[str] = field(default_factory=list)


@dataclass
class TicketDefinition:
    """A hardcoded ticket: catalog metadata plus how to grade a submission for it."""

    id: int
    title: str
    department: str
    severity: Severity
    problem_description: str
    root_cause_options: list[str]
    resolution_options: list[str]
    logs_context: dict
    reward_field: str  # one of User.networking_xp / automation_xp / database_xp / infra_points
    reward_amount: int
    verify: Callable[[TicketSubmission], VerificationResult]
    validation_criteria: dict = field(default_factory=dict)
    is_admin_only: bool = False


def _make_selection_verifier(
    correct_root_cause: str, correct_actions: set[str]
) -> Callable[[TicketSubmission], VerificationResult]:
    """Build the grading function for one ticket's resolution form.

    Every ticket is graded identically: exact match on root cause, exact-set
    match on resolution actions (missing a required step or picking an
    unnecessary one both fail it), and a resolution note is mandatory --
    real ticketing systems won't let you close a case with a blank
    resolution field either.
    """

    def _verify(submission: TicketSubmission) -> VerificationResult:
        details: list[str] = []
        passed = True

        if submission.root_cause != correct_root_cause:
            passed = False
            details.append(f"Incorrect root cause. The actual root cause was: '{correct_root_cause}'.")

        got_actions = set(submission.resolution_actions)
        missing = correct_actions - got_actions
        extra = got_actions - correct_actions
        if missing:
            passed = False
            details.append(f"Missing required resolution step(s): {sorted(missing)}")
        if extra:
            passed = False
            details.append(f"Unnecessary or incorrect step(s) selected: {sorted(extra)}")

        if not submission.resolution_notes or not submission.resolution_notes.strip():
            passed = False
            details.append("A resolution summary note is required before a ticket can be closed.")

        message = "Ticket resolved correctly." if passed else "Resolution does not match the correct diagnosis."
        return VerificationResult(passed, message, details)

    return _verify


def grade_submission(
    db: Session, user: User, definition: TicketDefinition, submission: TicketSubmission
) -> tuple[VerificationResult, int, float]:
    """Grade `submission`, persist progress, and award the reward exactly once.

    Shared by both `POST /api/tickets/submit` and `POST /api/admin/tickets/submit`
    so the "first successful attempt earns the reward, resubmissions don't farm
    it" rule lives in exactly one place regardless of ticket tier.

    Returns (verification_result, amount_actually_awarded, resolution_time_seconds).
    Grading itself is instant (a handful of set/string comparisons, no code
    execution), so `resolution_time` mostly reflects negligible processing
    overhead -- it's kept for API/telemetry consistency, not because grading
    is slow.
    """
    start = _utcnow()
    result = definition.verify(submission)
    resolution_time = round((_utcnow() - start).total_seconds(), 4)

    progress = (
        db.query(UserTicketProgress)
        .filter(
            UserTicketProgress.user_id == user.id,
            UserTicketProgress.ticket_id == definition.id,
        )
        .first()
    )
    already_resolved = progress is not None and progress.status == ProgressStatus.RESOLVED

    if progress is None:
        progress = UserTicketProgress(user_id=user.id, ticket_id=definition.id)
        db.add(progress)

    progress.submission_data = {
        "root_cause": submission.root_cause,
        "resolution_actions": submission.resolution_actions,
        "resolution_notes": submission.resolution_notes,
    }
    if result.passed and progress.resolved_at is None:
        progress.status = ProgressStatus.RESOLVED
        progress.resolved_at = _utcnow()

    reward_awarded = 0
    if result.passed and not already_resolved:
        reward_awarded = definition.reward_amount
        setattr(user, definition.reward_field, getattr(user, definition.reward_field) + reward_awarded)

    db.commit()
    db.refresh(user)

    return result, reward_awarded, resolution_time


# ---------------------------------------------------------------------------
# Ticket 1: Employee Locked Out After Password Reset (Help Desk Tier 1)
# ---------------------------------------------------------------------------

_TICKET_1_ROOT_CAUSE_OPTIONS = [
    "Caps Lock was enabled while entering the password",
    "The account is locked from repeated failed logons using the old password after the forced reset",
    "A network outage is preventing domain authentication",
    "The password reset email link expired before the user reset it",
]
_TICKET_1_CORRECT_ROOT_CAUSE = _TICKET_1_ROOT_CAUSE_OPTIONS[1]

_TICKET_1_RESOLUTION_OPTIONS = [
    "Unlock the account in Active Directory",
    "Confirm with the user that they are entering the NEW password, not the old one",
    "Restart the user's workstation",
    "Reinstall the corporate VPN client",
    "Escalate to Network Engineering",
]
_TICKET_1_CORRECT_ACTIONS = {_TICKET_1_RESOLUTION_OPTIONS[0], _TICKET_1_RESOLUTION_OPTIONS[1]}


# ---------------------------------------------------------------------------
# Ticket 2: Persistent Wi-Fi Drops in the East Conference Room (Network Support)
# ---------------------------------------------------------------------------

_TICKET_2_ROOT_CAUSE_OPTIONS = [
    "The access point's firmware is out of date",
    "The access point is overloaded with far more connected devices than it's rated for",
    "There is a company-wide ISP outage",
    "The user's laptop Wi-Fi adapter driver is corrupted",
]
_TICKET_2_CORRECT_ROOT_CAUSE = _TICKET_2_ROOT_CAUSE_OPTIONS[1]

_TICKET_2_RESOLUTION_OPTIONS = [
    "Install a second access point to split the client load",
    "Enable the 5GHz radio so compatible devices can move off the crowded 2.4GHz band",
    "Reboot the user's laptop",
    "Replace the user's Wi-Fi card",
    "Call the ISP to report an outage",
]
_TICKET_2_CORRECT_ACTIONS = {_TICKET_2_RESOLUTION_OPTIONS[0], _TICKET_2_RESOLUTION_OPTIONS[1]}


# ---------------------------------------------------------------------------
# Ticket 3: Duplicate Customer Records After CRM Import (Database Administration)
# ---------------------------------------------------------------------------

_TICKET_3_ROOT_CAUSE_OPTIONS = [
    "The database server ran out of storage space",
    "The nightly bulk import ran with duplicate-checking disabled, inserting new rows for existing customers",
    "A Sales rep manually re-entered every customer by hand",
    "The CRM software license expired",
]
_TICKET_3_CORRECT_ROOT_CAUSE = _TICKET_3_ROOT_CAUSE_OPTIONS[1]

_TICKET_3_RESOLUTION_OPTIONS = [
    "Run the CRM's record de-duplication/merge tool on the affected customers",
    "Re-enable duplicate-checking on the bulk import job going forward",
    "Notify Sales so the duplicate invoices can be corrected",
    "Delete the entire customer table and re-import from scratch",
    "Ignore it since the database isn't out of storage",
]
_TICKET_3_CORRECT_ACTIONS = {
    _TICKET_3_RESOLUTION_OPTIONS[0],
    _TICKET_3_RESOLUTION_OPTIONS[1],
    _TICKET_3_RESOLUTION_OPTIONS[2],
}


# ---------------------------------------------------------------------------
# Ticket 4: Suspicious Email Reported by Finance (Security Awareness / Help Desk)
# ---------------------------------------------------------------------------

_TICKET_4_ROOT_CAUSE_OPTIONS = [
    "A legitimate vendor invoice update",
    "A phishing attempt impersonating a vendor using a lookalike domain",
    "A routine marketing email misfiled as suspicious",
    "An internal IT phishing-simulation test",
]
_TICKET_4_CORRECT_ROOT_CAUSE = _TICKET_4_ROOT_CAUSE_OPTIONS[1]

_TICKET_4_RESOLUTION_OPTIONS = [
    "Quarantine the email and report it to the security team",
    "Advise the employee not to click any links or reply",
    "Block the sender's domain at the email gateway",
    "Forward the employee's real banking details to verify",
    "Tell the employee to reply and ask the sender to confirm",
]
_TICKET_4_CORRECT_ACTIONS = {
    _TICKET_4_RESOLUTION_OPTIONS[0],
    _TICKET_4_RESOLUTION_OPTIONS[1],
    _TICKET_4_RESOLUTION_OPTIONS[2],
}


# ---------------------------------------------------------------------------
# Admin Ticket 5: Employee Offboarding -- Immediate Access Revocation
# ---------------------------------------------------------------------------

_TICKET_5_ROOT_CAUSE_OPTIONS = [
    "Standard resignation with a 2-week notice period",
    "Immediate involuntary termination requiring urgent access lockdown",
    "Employee going on approved parental leave",
    "Internal transfer to a different department",
]
_TICKET_5_CORRECT_ROOT_CAUSE = _TICKET_5_ROOT_CAUSE_OPTIONS[1]

_TICKET_5_RESOLUTION_OPTIONS = [
    "Disable the user's Active Directory account immediately",
    "Revoke all active VPN and remote access sessions",
    "Remote-wipe/lock the company-issued mobile device",
    "Leave the account active until HR confirms in writing",
    "Forward their email to their manager for a 2-week grace period",
]
_TICKET_5_CORRECT_ACTIONS = {
    _TICKET_5_RESOLUTION_OPTIONS[0],
    _TICKET_5_RESOLUTION_OPTIONS[1],
    _TICKET_5_RESOLUTION_OPTIONS[2],
}


# ---------------------------------------------------------------------------
# Admin Ticket 6: Compliance Flag: Contractor Access Review
# ---------------------------------------------------------------------------

_TICKET_6_ROOT_CAUSE_OPTIONS = [
    "Contractors were provisioned using the default standard-employee access template instead of the contractor template",
    "Contractor access naturally expires and no action is needed",
    "This is a false positive from the audit tool",
    "Only one contractor account is actually affected",
]
_TICKET_6_CORRECT_ROOT_CAUSE = _TICKET_6_ROOT_CAUSE_OPTIONS[0]

_TICKET_6_RESOLUTION_OPTIONS = [
    "Downgrade all affected contractor accounts to Tier 1 clearance",
    "Leave full-time staff access unchanged",
    "Document the remediation for the compliance audit trail",
    "Delete all contractor accounts immediately",
    "Grant contractors elevated access to compensate for the disruption",
]
_TICKET_6_CORRECT_ACTIONS = {
    _TICKET_6_RESOLUTION_OPTIONS[0],
    _TICKET_6_RESOLUTION_OPTIONS[1],
    _TICKET_6_RESOLUTION_OPTIONS[2],
}


# ---------------------------------------------------------------------------
# Admin Ticket 7: Critical Server Disk Space Emergency
# ---------------------------------------------------------------------------

_TICKET_7_ROOT_CAUSE_OPTIONS = [
    "Legitimate business growth in data usage",
    "Old log files and temporary files were never cleaned up because log rotation was never configured",
    "A hardware fault reduced the disk's usable capacity",
    "A backup job duplicated data unnecessarily",
]
_TICKET_7_CORRECT_ROOT_CAUSE = _TICKET_7_ROOT_CAUSE_OPTIONS[1]

_TICKET_7_RESOLUTION_OPTIONS = [
    "Purge log files past the retention policy",
    "Remove temporary files left with insecure/world-writable permissions",
    "Configure scheduled log rotation going forward",
    "Delete random user files to free up space",
    "Ignore the alert until the disk fills completely",
]
_TICKET_7_CORRECT_ACTIONS = {
    _TICKET_7_RESOLUTION_OPTIONS[0],
    _TICKET_7_RESOLUTION_OPTIONS[1],
    _TICKET_7_RESOLUTION_OPTIONS[2],
}


# ---------------------------------------------------------------------------
# Ticket catalog
# ---------------------------------------------------------------------------

TICKETS: list[TicketDefinition] = [
    TicketDefinition(
        id=1,
        title="Employee Locked Out After Password Reset",
        department="Help Desk",
        severity=Severity.INCIDENT,
        problem_description=(
            "A sales rep (bsmith) says they can't log into their laptop right "
            "after IT force-reset their password this morning. Their account "
            "now shows as locked out. Diagnose the root cause and select the "
            "correct resolution steps before closing the ticket."
        ),
        root_cause_options=_TICKET_1_ROOT_CAUSE_OPTIONS,
        resolution_options=_TICKET_1_RESOLUTION_OPTIONS,
        logs_context={
            "target_host": "CORP-DC01 (Active Directory Domain Controller)",
            "raw_log": (
                "Account: bsmith\n"
                "Status: LOCKED (bad password count: 6)\n"
                "Last successful logon: 2026-06-30 09:14:02\n"
                "Last failed logon: 2026-07-02 08:41:57\n"
                "Password last set: 2026-07-02 08:30:00 (forced reset by IT)"
            ),
        },
        validation_criteria={
            "checks": [
                "Root cause correctly identifies the post-reset lockout, not a Caps Lock or network issue.",
                "Both the AD unlock AND the password-confirmation step are required -- unlocking alone won't stop it from re-locking.",
                "A resolution note is required before the ticket can be closed.",
            ]
        },
        reward_field="automation_xp",
        reward_amount=100,
        verify=_make_selection_verifier(_TICKET_1_CORRECT_ROOT_CAUSE, _TICKET_1_CORRECT_ACTIONS),
    ),
    TicketDefinition(
        id=2,
        title="Persistent Wi-Fi Drops in the East Conference Room",
        department="Network Operations",
        severity=Severity.LOW,
        problem_description=(
            "Multiple employees report Wi-Fi dropping and slowing down every "
            "time a meeting is held in the East Conference Room. The access "
            "point itself looks healthy. Diagnose the root cause and select "
            "the correct fix."
        ),
        root_cause_options=_TICKET_2_ROOT_CAUSE_OPTIONS,
        resolution_options=_TICKET_2_RESOLUTION_OPTIONS,
        logs_context={
            "target_host": "AP-EAST-03 (East Conference Room Access Point)",
            "raw_log": (
                "Connected clients on AP-EAST-03: 47\n"
                "Recommended max clients per AP: 25\n"
                "Band: 2.4GHz only (5GHz radio disabled)\n"
                "Signal quality: Good\n"
                "Uptime: 214 days (no recent reboot)"
            ),
        },
        validation_criteria={
            "checks": [
                "Root cause correctly identifies AP overload, not firmware/ISP/driver issues.",
                "Both the second-AP and 5GHz-band steps are required -- either alone leaves the room over capacity.",
                "A resolution note is required before the ticket can be closed.",
            ]
        },
        reward_field="networking_xp",
        reward_amount=50,
        verify=_make_selection_verifier(_TICKET_2_CORRECT_ROOT_CAUSE, _TICKET_2_CORRECT_ACTIONS),
    ),
    TicketDefinition(
        id=3,
        title="Duplicate Customer Records After CRM Import",
        department="Database Administration",
        severity=Severity.INCIDENT,
        problem_description=(
            "Sales reports that several customers received duplicate invoices "
            "this week. An audit shows 312 duplicate customer records appeared "
            "in the CRM database right after last night's bulk import. "
            "Diagnose the root cause and select the correct remediation steps."
        ),
        root_cause_options=_TICKET_3_ROOT_CAUSE_OPTIONS,
        resolution_options=_TICKET_3_RESOLUTION_OPTIONS,
        logs_context={
            "target_host": "CRM-DB01 (Customer Relationship Management Database)",
            "raw_log": (
                "Nightly bulk import job: customer_import_2026-07-01.csv (14,203 rows)\n"
                "Duplicate-check setting on import job: DISABLED\n"
                "Resulting duplicate customer records detected: 312\n"
                "Affected department: Sales (duplicate invoices sent to 9 customers)"
            ),
        },
        validation_criteria={
            "checks": [
                "Root cause correctly identifies the disabled duplicate-check on the import job.",
                "All three remediation steps (de-dupe existing records, fix the import job, notify Sales) are required.",
                "A resolution note is required before the ticket can be closed.",
            ]
        },
        reward_field="database_xp",
        reward_amount=100,
        verify=_make_selection_verifier(_TICKET_3_CORRECT_ROOT_CAUSE, _TICKET_3_CORRECT_ACTIONS),
    ),
    TicketDefinition(
        id=4,
        title="Suspicious Email Reported by Finance",
        department="Help Desk",
        severity=Severity.CATASTROPHIC,
        problem_description=(
            "A Finance employee used the 'Report Phishing' button on an email "
            "urgently asking them to update vendor banking details. Diagnose "
            "whether this is a real threat and select the correct response."
        ),
        root_cause_options=_TICKET_4_ROOT_CAUSE_OPTIONS,
        resolution_options=_TICKET_4_RESOLUTION_OPTIONS,
        logs_context={
            "target_host": "Email Security Gateway",
            "raw_log": (
                "Reported by: finance-team@company.com\n"
                "Sender: accounts-payable@compnay-vendor.co (note: misspelled domain)\n"
                'Subject: "URGENT: Updated banking details for invoice #48213"\n'
                "Links detected: 1 (shortened URL, not previously seen)\n"
                "Attachment: none\n"
                "Employee action taken so far: reported via 'Report Phishing' button, "
                "did not click links or reply"
            ),
        },
        validation_criteria={
            "checks": [
                "Root cause correctly identifies phishing via a lookalike domain, not a legitimate request.",
                "All three response steps (quarantine/report, advise the employee, block the domain) are required.",
                "A resolution note is required before the ticket can be closed.",
            ]
        },
        reward_field="automation_xp",
        reward_amount=150,
        verify=_make_selection_verifier(_TICKET_4_CORRECT_ROOT_CAUSE, _TICKET_4_CORRECT_ACTIONS),
    ),
    TicketDefinition(
        id=5,
        title="Employee Offboarding -- Immediate Access Revocation",
        department="SysAdmin",
        severity=Severity.INCIDENT,
        problem_description=(
            "HR has flagged an involuntary termination effective immediately. "
            "Diagnose the correct offboarding priority and select every "
            "access-revocation step required before end of day."
        ),
        root_cause_options=_TICKET_5_ROOT_CAUSE_OPTIONS,
        resolution_options=_TICKET_5_RESOLUTION_OPTIONS,
        logs_context={
            "target_host": "AD-DIR-SVC / MDM Console",
            "raw_log": (
                "Employee: mrodriguez (user_id 102)\n"
                "Termination type: Involuntary, effective immediately\n"
                "HR request received: 2026-07-03 09:00\n"
                "Active sessions: VPN (connected), Corporate email (mobile device enrolled)"
            ),
        },
        validation_criteria={
            "checks": [
                "Root cause correctly identifies an urgent involuntary termination, not a routine departure.",
                "All three revocation steps (AD disable, VPN revoke, device wipe/lock) are required.",
                "A resolution note is required before the ticket can be closed.",
            ]
        },
        reward_field="infra_points",
        reward_amount=100,
        verify=_make_selection_verifier(_TICKET_5_CORRECT_ROOT_CAUSE, _TICKET_5_CORRECT_ACTIONS),
        is_admin_only=True,
    ),
    TicketDefinition(
        id=6,
        title="Compliance Flag: Contractor Access Review",
        department="Security / Governance",
        severity=Severity.CATASTROPHIC,
        problem_description=(
            "An access-governance audit flagged contractor accounts with "
            "clearance far above policy. Diagnose why this happened and "
            "select the correct remediation steps."
        ),
        root_cause_options=_TICKET_6_ROOT_CAUSE_OPTIONS,
        resolution_options=_TICKET_6_RESOLUTION_OPTIONS,
        logs_context={
            "target_host": "IAM Governance Console",
            "raw_log": (
                "Audit finding: 14 contractor accounts in 'External QA' provisioned "
                "at standard employee-tier clearance\n"
                "Policy requirement: Contractors must be capped at Tier 1 clearance\n"
                "Full-time staff in External QA: unaffected by this finding"
            ),
        },
        validation_criteria={
            "checks": [
                "Root cause correctly identifies the wrong provisioning template, not a false positive.",
                "All three remediation steps (downgrade contractors, leave full-time staff alone, document it) are required.",
                "A resolution note is required before the ticket can be closed.",
            ]
        },
        reward_field="infra_points",
        reward_amount=150,
        verify=_make_selection_verifier(_TICKET_6_CORRECT_ROOT_CAUSE, _TICKET_6_CORRECT_ACTIONS),
        is_admin_only=True,
    ),
    TicketDefinition(
        id=7,
        title="Critical Server Disk Space Emergency",
        department="SysAdmin",
        severity=Severity.INCIDENT,
        problem_description=(
            "A primary mail/log server is at 98% disk capacity and throwing "
            "DiskSpaceExhausted alerts. Diagnose the root cause and select "
            "the correct remediation steps to safely reclaim space."
        ),
        root_cause_options=_TICKET_7_ROOT_CAUSE_OPTIONS,
        resolution_options=_TICKET_7_RESOLUTION_OPTIONS,
        logs_context={
            "target_host": "MAIL-LOG-SRV-01 (Primary Mail/Log Server)",
            "raw_log": (
                "Disk usage: 98% (critical threshold: 90%)\n"
                "Largest consumers: /var/log (41GB, oldest entry 210 days), "
                "/tmp (12GB, multiple world-writable files)\n"
                "Recent business growth in mailbox usage: none significant\n"
                "Last scheduled log rotation: never configured"
            ),
        },
        validation_criteria={
            "checks": [
                "Root cause correctly identifies unmanaged log/temp growth, not hardware or backups.",
                "All three remediation steps (purge old logs, remove insecure temp files, configure rotation) are required.",
                "A resolution note is required before the ticket can be closed.",
            ]
        },
        reward_field="infra_points",
        reward_amount=125,
        verify=_make_selection_verifier(_TICKET_7_CORRECT_ROOT_CAUSE, _TICKET_7_CORRECT_ACTIONS),
        is_admin_only=True,
    ),
]

TICKETS_BY_ID: dict[int, TicketDefinition] = {ticket.id: ticket for ticket in TICKETS}
