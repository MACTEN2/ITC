"""Hardcoded IT support ticket scenarios plus their secure verification logic.

Each ticket bundles the static catalog fields persisted into the `Ticket` table
with a `verify(submission) -> VerificationResult` callable used to grade a
learner's code/SQL submission against known-correct expected output. Six
tickets ship in two tiers:

    - 3 learner-facing tickets (`is_admin_only=False`), served by
      `GET/POST /api/tickets*` and rewarded in one of the three skill XP tracks.
    - 3 admin-only tickets (`is_admin_only=True`), served by
      `GET/POST /api/admin/tickets*` and rewarded in `infra_points`.

Three isolated execution strategies are used, all deliberately minimal in privilege:

    - Python submissions run through `_run_python_sandbox`: an `exec()` call scoped
      to an allowlisted subset of builtins and importable modules, with no access to
      `open`, `sys`, `subprocess`, `socket`, `eval`, etc. Execution is bounded by a
      wall-clock timeout via a worker thread. The admin filesystem tickets need
      `os`/`shutil`, which are too dangerous to hand out for real -- those two names
      resolve instead to path-jailed facades (see `_make_jailed_os_shutil`) that
      silently confine every operation to a single throwaway temp directory.
    - Read-only SQL submissions run through `_run_sql_sandbox`: validated to be a
      single SELECT (no DDL/DML, no stacked statements), then executed against a
      throwaway in-memory SQLite database seeded fresh per call.
    - The compliance-audit ticket allows exactly one narrow exception: a single
      UPDATE statement against one named table with a mandatory WHERE clause, run
      through `_run_update_sandbox` against the same kind of throwaway database.

This is a best-effort sandbox appropriate for a learning tool where submissions
come from the app's own users, not a hardened multi-tenant sandbox for arbitrary
untrusted code (a production deployment handling adversarial input would isolate
execution in a subprocess or container instead).
"""

import builtins
import concurrent.futures
import csv
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from sqlalchemy import create_engine, insert, text
from sqlalchemy.orm import Session

from app.models import (
    AccessLog,
    Base,
    EmploymentType,
    LoginStatus,
    MockEmployee,
    ProgressStatus,
    Severity,
    User,
    UserTicketProgress,
)

EXECUTION_TIMEOUT_SECONDS = 5.0


def _now_naive_utc() -> datetime:
    """SQLite has no timezone concept, so all sandbox timestamps are naive UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Shared result / catalog types
# ---------------------------------------------------------------------------


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
    starter_code: str
    logs_context: dict
    reward_field: str  # one of User.networking_xp / automation_xp / database_xp / infra_points
    reward_amount: int
    verify: Callable[[str], VerificationResult]
    validation_criteria: dict = field(default_factory=dict)
    is_admin_only: bool = False


def grade_submission(
    db: Session, user: User, definition: TicketDefinition, submission: str
) -> tuple[VerificationResult, int, float]:
    """Grade `submission`, persist progress, and award the reward exactly once.

    Shared by both `POST /api/tickets/submit` and `POST /api/admin/tickets/submit`
    so the "first successful attempt earns the reward, resubmissions don't farm
    it" rule lives in exactly one place regardless of ticket tier.

    Returns (verification_result, amount_actually_awarded, resolution_time_seconds).
    """
    start = time.perf_counter()
    result = definition.verify(submission)
    resolution_time = round(time.perf_counter() - start, 4)

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

    progress.code_submission = submission
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
# Python sandbox
# ---------------------------------------------------------------------------

_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
    "int", "isinstance", "len", "list", "map", "max", "min", "print",
    "range", "reversed", "round", "set", "sorted", "str", "sum", "tuple",
    "zip", "Exception", "ValueError", "KeyError", "TypeError", "IndexError",
    "StopIteration", "PermissionError", "FileNotFoundError",
)


class SandboxPermissionError(PermissionError):
    """Raised when jailed submission code tries to touch a path outside its sandbox."""


def _make_restricted_importer(
    allowed_modules: set[str], fake_modules: dict[str, object] | None = None
) -> Callable:
    """Build an `__import__` replacement that only permits an explicit allowlist.

    `fake_modules` lets specific module names resolve to a substitute object
    instead of the real module -- used to hand out path-jailed facades for
    `os`/`shutil` on filesystem-touching tickets (see `_make_jailed_os_shutil`)
    so submissions get a familiar API without ever touching the real filesystem
    module.
    """
    real_import = builtins.__import__
    fake_modules = fake_modules or {}

    def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
        top_level = name.split(".")[0]
        if top_level in fake_modules:
            return fake_modules[top_level]
        if top_level not in allowed_modules:
            raise ImportError(f"Import of '{name}' is not permitted in this sandbox.")
        return real_import(name, globals, locals, fromlist, level)

    return _restricted_import


def _run_python_sandbox(
    source: str, allowed_imports: set[str], fake_modules: dict[str, object] | None = None
) -> tuple[bool, dict, str | None]:
    """Execute learner-submitted Python in a restricted namespace.

    Returns (success, resulting_globals, error_message). On failure, error_message
    describes what went wrong (syntax error, runtime exception, or timeout) so it
    can be surfaced back to the learner as actionable feedback.
    """
    safe_builtins = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES}
    safe_builtins["__import__"] = _make_restricted_importer(allowed_imports, fake_modules)
    sandbox_globals: dict = {"__builtins__": safe_builtins}

    def _exec() -> None:
        exec(compile(source, "<submission>", "exec"), sandbox_globals)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(_exec).result(timeout=EXECUTION_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        return False, sandbox_globals, "Execution timed out (possible infinite loop)."
    except SyntaxError as exc:
        return False, sandbox_globals, f"SyntaxError: {exc}"
    except Exception as exc:  # noqa: BLE001 - intentionally broad, surfaced as feedback
        return False, sandbox_globals, f"{type(exc).__name__}: {exc}"

    return True, sandbox_globals, None


def _call_with_timeout(func: Callable, args: tuple, timeout: float = EXECUTION_TIMEOUT_SECONDS):
    """Run `func(*args)` on a worker thread and enforce a wall-clock timeout."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(func, *args).result(timeout=timeout)


# ---------------------------------------------------------------------------
# Filesystem sandbox (path-jailed os/shutil facades for the admin tickets)
# ---------------------------------------------------------------------------


def _resolve_within_jail(path, jail_root: Path) -> Path:
    """Resolve `path` (relative to `jail_root` if not absolute) and enforce containment.

    Raises SandboxPermissionError if the resolved path would land outside
    `jail_root` -- e.g. via a `../../` traversal or an absolute path elsewhere
    on the host -- so a submission can only ever affect the one throwaway
    directory the grader created for it.
    """
    candidate = Path(path)
    resolved = candidate.resolve() if candidate.is_absolute() else (jail_root / candidate).resolve()
    jail_resolved = jail_root.resolve()
    if not resolved.is_relative_to(jail_resolved):
        raise SandboxPermissionError(
            f"Access to '{path}' is outside the sandboxed directory and is not permitted."
        )
    return resolved


def _make_jailed_os_shutil(jail_root: Path) -> tuple[SimpleNamespace, SimpleNamespace]:
    """Build path-jailed facades standing in for the real `os` and `shutil` modules.

    Learner code that does `import os` / `import shutil` receives these objects
    instead of the real modules. Every function that touches the filesystem
    resolves its path argument through `_resolve_within_jail` first, so even a
    malicious or buggy submission can only ever read/write/delete files inside
    the single ephemeral directory the grader set up for that one call -- never
    anywhere else on the host running the ITC server.
    """

    def _safe(path) -> Path:
        return _resolve_within_jail(path, jail_root)

    fake_path = SimpleNamespace(
        exists=lambda p: _safe(p).exists(),
        isfile=lambda p: _safe(p).is_file(),
        isdir=lambda p: _safe(p).is_dir(),
        getsize=lambda p: _safe(p).stat().st_size,
        getmtime=lambda p: _safe(p).stat().st_mtime,
        # Pure string manipulation, no filesystem I/O -- safe to expose as-is.
        join=os.path.join,
        basename=os.path.basename,
        splitext=os.path.splitext,
    )

    fake_os = SimpleNamespace(
        path=fake_path,
        listdir=lambda p=".": os.listdir(_safe(p)),
        remove=lambda p: os.remove(_safe(p)),
    )

    fake_shutil = SimpleNamespace(
        rmtree=lambda p: shutil.rmtree(_safe(p)),
    )

    return fake_os, fake_shutil


# ---------------------------------------------------------------------------
# Read-only SQL sandbox
# ---------------------------------------------------------------------------

_FORBIDDEN_SQL_KEYWORDS = (
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "ATTACH", "DETACH",
    "PRAGMA", "CREATE", "REPLACE", "TRUNCATE", "VACUUM", "EXEC", "GRANT",
)


def _strip_sql_comments(sql: str) -> str:
    """Strip `-- line` and `/* block */` comments for validation purposes only.

    Ticket starter code (and realistic learner submissions) routinely keeps
    explanatory `--` comments above the actual statement. Validating the raw
    string would anchor-fail on that leading comment and reject perfectly
    valid SQL, and would also false-positive the forbidden-keyword scan if a
    comment happened to mention a word like "DROP" in prose. The *original*,
    un-stripped submission is still what actually gets executed -- SQLite
    ignores comments natively, so stripping is purely a validation-time view.
    """
    no_line_comments = re.sub(r"--[^\n]*", "", sql)
    return re.sub(r"/\*.*?\*/", "", no_line_comments, flags=re.DOTALL)


def _validate_select_only(submission: str) -> tuple[bool, str]:
    """Defense-in-depth check that a submission is a single, read-only SELECT.

    This runs *before* the query ever touches the sandbox database, rejecting
    anything that isn't a lone SELECT statement so a submission cannot mutate
    schema/data or chain a second statement after a semicolon.
    """
    cleaned = _strip_sql_comments(submission).strip()
    if not cleaned:
        return False, "Submission is empty."

    body = cleaned[:-1] if cleaned.endswith(";") else cleaned
    if ";" in body:
        return False, "Only a single SQL statement is allowed (no stacked queries)."

    if not re.match(r"^\s*SELECT\b", body, re.IGNORECASE):
        return False, "Only SELECT statements are allowed."

    upper = body.upper()
    for keyword in _FORBIDDEN_SQL_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            return False, f"Forbidden keyword detected: {keyword}"

    return True, ""


def _extract_ip_and_count(row: dict) -> tuple[str | None, float | None]:
    """Pull an IP-looking string and a numeric count out of a result row.

    Written to tolerate any column naming/ordering the learner's SELECT uses,
    as long as it returns the IP address and a failed-attempt count somewhere
    in the row.
    """
    ip_address: str | None = None
    count: float | None = None
    for value in row.values():
        if isinstance(value, str) and re.match(r"^\d{1,3}(\.\d{1,3}){3}$", value):
            ip_address = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            count = value
    return ip_address, count


def _run_sql_sandbox(submission: str, seed_rows: list[dict]) -> tuple[list[dict] | None, str | None]:
    """Validate, then execute a SELECT against a fresh in-memory `access_logs` table."""
    is_valid, reason = _validate_select_only(submission)
    if not is_valid:
        return None, reason

    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine, tables=[AccessLog.__table__])
        with Session(engine) as session:
            session.execute(insert(AccessLog), seed_rows)
            session.commit()

        try:
            with engine.connect() as conn:
                rows = [dict(row) for row in conn.execute(text(submission)).mappings().all()]
        except Exception as exc:  # noqa: BLE001 - surfaced as learner feedback
            return None, f"SQL execution failed: {exc}"
    finally:
        engine.dispose()

    return rows, None


# ---------------------------------------------------------------------------
# Single-table UPDATE sandbox (admin compliance-audit ticket only)
# ---------------------------------------------------------------------------

_FORBIDDEN_UPDATE_KEYWORDS = (
    "INSERT", "DELETE", "DROP", "ALTER", "ATTACH", "DETACH",
    "PRAGMA", "CREATE", "REPLACE", "TRUNCATE", "VACUUM", "EXEC", "GRANT",
)


def _validate_update_only(submission: str, allowed_table: str) -> tuple[bool, str]:
    """Defense-in-depth check that a submission is a single, scoped UPDATE.

    Unlike the read-only sandbox, this ticket legitimately needs to mutate data --
    but only ever a single UPDATE against `allowed_table`, and only ever with a
    WHERE clause (an unconditional UPDATE would rewrite every row, which is
    exactly the kind of batch mistake this ticket exists to prevent).
    """
    cleaned = _strip_sql_comments(submission).strip()
    if not cleaned:
        return False, "Submission is empty."

    body = cleaned[:-1] if cleaned.endswith(";") else cleaned
    if ";" in body:
        return False, "Only a single SQL statement is allowed (no stacked queries)."

    if not re.match(rf"^\s*UPDATE\s+{re.escape(allowed_table)}\b", body, re.IGNORECASE):
        return False, f"Only a single UPDATE statement against `{allowed_table}` is allowed."

    if not re.search(r"\bWHERE\b", body, re.IGNORECASE):
        return False, "The UPDATE must include a WHERE clause -- unconditional batch updates are not permitted."

    upper = body.upper()
    for keyword in _FORBIDDEN_UPDATE_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper):
            return False, f"Forbidden keyword detected: {keyword}"

    return True, ""


def _run_update_sandbox(submission: str, seed_rows: list[dict]) -> tuple[list[dict] | None, str | None]:
    """Validate, then execute an UPDATE against a fresh in-memory `mock_employees` table."""
    is_valid, reason = _validate_update_only(submission, allowed_table="mock_employees")
    if not is_valid:
        return None, reason

    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine, tables=[MockEmployee.__table__])
        with Session(engine) as session:
            session.execute(insert(MockEmployee), seed_rows)
            session.commit()

            try:
                session.execute(text(submission))
                session.commit()
            except Exception as exc:  # noqa: BLE001 - surfaced as learner feedback
                return None, f"SQL execution failed: {exc}"

            rows = [dict(row) for row in session.execute(text("SELECT * FROM mock_employees")).mappings().all()]
    finally:
        engine.dispose()

    return rows, None


# ---------------------------------------------------------------------------
# Ticket 1: The User Provisioning Script (Python / csv / json)
# ---------------------------------------------------------------------------

MOCK_ROSTER_CSV = (
    "first_name,last_name,department\n"
    "John,Smith,IT\n"
    "Jane,Doe,HR\n"
    "Maria,Garcia,Finance\n"
    "Wei,Chen,IT\n"
    "Aisha,Khan,Sales\n"
)

_GROUP_MAP = {
    "IT": ["VPN-Access", "Domain-Admins"],
    "HR": ["HR-Portal", "Payroll-ReadOnly"],
    "Finance": ["Finance-Systems", "Payroll-ReadOnly"],
    "Sales": ["CRM-Access"],
}

STARTER_CODE_TICKET_1 = '''"""Fix this script so it correctly provisions new hires from the roster CSV."""
import csv
import json

GROUP_MAP = {
    "IT": ["VPN-Access", "Domain-Admins"],
    "HR": ["HR-Portal", "Payroll-ReadOnly"],
    "Finance": ["Finance-Systems", "Payroll-ReadOnly"],
    "Sales": ["CRM-Access"],
}


def provision_users(csv_data: str) -> list[dict]:
    """Parse the roster CSV and return one record per employee:

        {"first_name": ..., "last_name": ..., "department": ...,
         "email": "first.last@company.com", "groups": [...]}
    """
    reader = csv.reader(csv_data.strip().splitlines())  # BUG: should use DictReader
    records = []
    for row in reader:
        first_name, last_name, department = row[0], row[1], row[2]

        # BUG: the header row is never skipped, and the email is not
        # normalized to lowercase, so bad values leak into the output.
        email = f"{first_name}.{last_name}@COMPANY.com"

        records.append({
            "first_name": first_name,
            "last_name": last_name,
            "department": department,
            "email": email,
            "groups": GROUP_MAP.get(department, ["General-Access"]),
        })
    return records
'''


def _expected_provisioning(csv_data: str) -> list[dict]:
    """Reference implementation used purely for grading, never shown to the learner."""
    reader = csv.DictReader(csv_data.strip().splitlines())
    expected = []
    for row in reader:
        first = row["first_name"].strip()
        last = row["last_name"].strip()
        department = row["department"].strip()
        expected.append({
            "email": f"{first.lower()}.{last.lower()}@company.com",
            "groups": _GROUP_MAP.get(department, ["General-Access"]),
        })
    return expected


def _verify_ticket_1(submission: str) -> VerificationResult:
    ok, namespace, error = _run_python_sandbox(submission, allowed_imports={"csv", "json"})
    if not ok:
        return VerificationResult(False, f"Script failed to run: {error}")

    func = namespace.get("provision_users")
    if not callable(func):
        return VerificationResult(
            False, "Expected a `provision_users(csv_data: str) -> list[dict]` function."
        )

    try:
        result = _call_with_timeout(func, (MOCK_ROSTER_CSV,))
    except concurrent.futures.TimeoutError:
        return VerificationResult(False, "provision_users() timed out (possible infinite loop).")
    except Exception as exc:  # noqa: BLE001
        return VerificationResult(False, f"provision_users() raised an error: {exc}")

    if not isinstance(result, list):
        return VerificationResult(False, "provision_users() must return a list.")

    expected = _expected_provisioning(MOCK_ROSTER_CSV)
    details: list[str] = []
    passed = True

    if len(result) != len(expected):
        passed = False
        details.append(f"Expected {len(expected)} provisioning records, got {len(result)}.")

    for exp in expected:
        match = next(
            (r for r in result if isinstance(r, dict) and str(r.get("email", "")).lower() == exp["email"]),
            None,
        )
        if match is None:
            passed = False
            details.append(f"Missing or incorrectly-formatted record for {exp['email']}")
            continue
        got_groups = set(match.get("groups") or [])
        if got_groups != set(exp["groups"]):
            passed = False
            details.append(
                f"{exp['email']}: expected groups {sorted(exp['groups'])}, got {sorted(got_groups)}"
            )

    message = "All employees provisioned correctly." if passed else "Provisioning output did not match expectations."
    return VerificationResult(passed, message, details)


# ---------------------------------------------------------------------------
# Ticket 2: The Account Lockout Audit (SQL / GROUP BY / HAVING)
# ---------------------------------------------------------------------------


def _build_access_log_rows(now: datetime) -> list[dict]:
    """Seed rows for the `access_logs` sandbox table, anchored to `now`.

    Crafted so exactly two IPs exceed 5 failed attempts within the last hour,
    one IP has failures but not enough to trip the threshold, and one IP's
    failures are outside the 1-hour window and must be excluded.
    """
    rows: list[dict] = []

    # 203.0.113.10: 7 failed attempts in the last hour -> should be flagged.
    for minutes_ago in (5, 12, 18, 25, 31, 40, 55):
        rows.append({
            "ip_address": "203.0.113.10", "username": "bsmith",
            "status": LoginStatus.FAILED, "attempt_time": now - timedelta(minutes=minutes_ago),
        })
    # Some successful logins from the same IP that must NOT count toward the total.
    for minutes_ago in (3, 8):
        rows.append({
            "ip_address": "203.0.113.10", "username": "bsmith",
            "status": LoginStatus.SUCCESS, "attempt_time": now - timedelta(minutes=minutes_ago),
        })
    # 198.51.100.23: 6 failed attempts in the last hour -> should be flagged.
    for minutes_ago in (2, 10, 15, 20, 33, 47):
        rows.append({
            "ip_address": "198.51.100.23", "username": "jdoe",
            "status": LoginStatus.FAILED, "attempt_time": now - timedelta(minutes=minutes_ago),
        })
    # 192.0.2.77: only 3 failed attempts -> should NOT be flagged.
    for minutes_ago in (4, 22, 44):
        rows.append({
            "ip_address": "192.0.2.77", "username": "mgarcia",
            "status": LoginStatus.FAILED, "attempt_time": now - timedelta(minutes=minutes_ago),
        })
    # 198.51.100.200: 9 failed attempts, all OUTSIDE the last hour -> should NOT be flagged.
    for minutes_ago in (75, 90, 100, 120, 130, 140, 150, 160, 170):
        rows.append({
            "ip_address": "198.51.100.200", "username": "root",
            "status": LoginStatus.FAILED, "attempt_time": now - timedelta(minutes=minutes_ago),
        })

    return rows


_EXPECTED_LOCKOUT_IPS = {"203.0.113.10", "198.51.100.23"}

STARTER_CODE_TICKET_2 = """-- TODO: Fix this query so it correctly flags brute-force IP addresses.
-- Requirement: any IP address with MORE THAN 5 FAILED login attempts within
-- the last hour must appear in the results, alongside its attempt count.
--
-- Available table: access_logs(id, ip_address, username, status, attempt_time)
--   status is either 'SUCCESS' or 'FAILED'.
--
-- BUG: this draft counts ALL attempts (including successful logins) and
-- applies no time window at all.
SELECT ip_address, COUNT(*) AS failed_attempts
FROM access_logs
GROUP BY ip_address
HAVING COUNT(*) > 5;
"""


def _verify_ticket_2(submission: str) -> VerificationResult:
    now = _now_naive_utc()
    rows, error = _run_sql_sandbox(submission, _build_access_log_rows(now))
    if error is not None:
        return VerificationResult(False, error)

    found_ips: set[str] = set()
    details: list[str] = []
    for row in rows or []:
        ip_address, count = _extract_ip_and_count(row)
        if ip_address is None:
            details.append(f"Row {row} does not contain a recognizable IP address column.")
            continue
        if count is None or count <= 5:
            details.append(f"Row for {ip_address} does not show a failed-attempt count greater than 5.")
            continue
        found_ips.add(ip_address)

    missing = _EXPECTED_LOCKOUT_IPS - found_ips
    extra = found_ips - _EXPECTED_LOCKOUT_IPS
    if missing:
        details.append(f"Missing flagged IP(s): {sorted(missing)}")
    if extra:
        details.append(f"Unexpectedly flagged IP(s): {sorted(extra)}")

    passed = not missing and not extra
    message = (
        "Correctly isolated all brute-force IP addresses."
        if passed
        else "Query results do not match the expected lockout report."
    )
    return VerificationResult(passed, message, details)


def _build_logs_context_ticket_2() -> dict:
    now = _now_naive_utc()
    sample = _build_access_log_rows(now)
    return {
        "table": "access_logs",
        "columns": ["id", "ip_address", "username", "status", "attempt_time"],
        "sample_rows": [
            {
                "ip_address": r["ip_address"],
                "username": r["username"],
                "status": r["status"].value,
                "attempt_time": r["attempt_time"].isoformat(),
            }
            for r in sample
        ],
    }


# ---------------------------------------------------------------------------
# Ticket 3: The Firewall Breach (Python / re)
# ---------------------------------------------------------------------------

MOCK_FIREWALL_LOG = (
    "2026-07-02 03:14:07 ALLOW src=10.0.0.15 dst=10.0.0.1 proto=TCP port=443\n"
    "2026-07-02 03:15:22 DENY src=203.0.113.44 dst=10.0.0.1 proto=TCP port=22 reason=unauthorized\n"
    "2026-07-02 03:15:41 DENY src=203.0.113.44 dst=10.0.0.5 proto=TCP port=22 reason=unauthorized\n"
    "2026-07-02 03:16:03 ALLOW src=10.0.0.22 dst=10.0.0.1 proto=UDP port=53\n"
    "2026-07-02 03:16:59 BLOCKED src=198.51.100.9 dst=10.0.0.1 proto=TCP port=3389 reason=unauthorized\n"
    "2026-07-02 03:17:30 DENY src=198.51.100.200 dst=10.0.0.7 proto=TCP port=23 reason=unauthorized\n"
    "2026-07-02 03:18:12 ALLOW src=10.0.0.31 dst=10.0.0.1 proto=TCP port=443\n"
    "2026-07-02 03:19:45 BLOCKED src=203.0.113.44 dst=10.0.0.9 proto=TCP port=22 reason=unauthorized\n"
)

STARTER_CODE_TICKET_3 = '''"""Fix this script so it flags every unauthorized source IP in the firewall log."""
import re


def extract_unauthorized_ips(log_text: str) -> list[str]:
    """Return a sorted list of unique source IPs from DENY/BLOCKED log lines."""
    # BUG: only matches ALLOW lines, which is the exact opposite of what we need.
    pattern = r"ALLOW src=(\\d+\\.\\d+\\.\\d+\\.\\d+)"
    ips = set()
    for match in re.finditer(pattern, log_text):
        ips.add(match.group(1))
    return sorted(ips)
'''


def _expected_unauthorized_ips(log_text: str) -> set[str]:
    pattern = r"(?:DENY|BLOCKED)\s+src=(\d{1,3}(?:\.\d{1,3}){3})"
    return {match.group(1) for match in re.finditer(pattern, log_text)}


def _verify_ticket_3(submission: str) -> VerificationResult:
    ok, namespace, error = _run_python_sandbox(submission, allowed_imports={"re"})
    if not ok:
        return VerificationResult(False, f"Script failed to run: {error}")

    func = namespace.get("extract_unauthorized_ips")
    if not callable(func):
        return VerificationResult(
            False, "Expected an `extract_unauthorized_ips(log_text: str) -> list[str]` function."
        )

    try:
        result = _call_with_timeout(func, (MOCK_FIREWALL_LOG,))
    except concurrent.futures.TimeoutError:
        return VerificationResult(False, "extract_unauthorized_ips() timed out (possible infinite loop).")
    except Exception as exc:  # noqa: BLE001
        return VerificationResult(False, f"extract_unauthorized_ips() raised an error: {exc}")

    if not isinstance(result, list):
        return VerificationResult(False, "extract_unauthorized_ips() must return a list.")

    expected_ips = _expected_unauthorized_ips(MOCK_FIREWALL_LOG)
    got_ips = {str(ip) for ip in result}

    missing = expected_ips - got_ips
    extra = got_ips - expected_ips
    details: list[str] = []
    if missing:
        details.append(f"Missing unauthorized IP(s): {sorted(missing)}")
    if extra:
        details.append(f"Unexpected extra IP(s): {sorted(extra)}")

    passed = not missing and not extra
    message = "All unauthorized IPs correctly identified." if passed else "IP extraction did not match expectations."
    return VerificationResult(passed, message, details)


# ---------------------------------------------------------------------------
# Admin Ticket 1: Employee Terminations (Python / os / shutil, path-jailed)
# ---------------------------------------------------------------------------

MOCK_EMPLOYEE_DIRECTORY = [
    {"user_id": 101, "username": "jsmith", "active": True},
    {"user_id": 102, "username": "mrodriguez", "active": True},
    {"user_id": 103, "username": "achen", "active": True},
]

_OFFBOARD_TARGET_USER_ID = 102

STARTER_CODE_ADMIN_TICKET_1 = '''"""Fix this offboarding script: deactivate the departing employee and sweep their cache."""
import os
import shutil


def offboard_employee(user_id: int, directory: list[dict], cache_path: str) -> list[dict]:
    """Deactivate `user_id` in `directory` and delete their temp cache directory."""
    for record in directory:
        # BUG: comparing against a string, so this never matches the int user_id.
        if record["user_id"] == str(user_id):
            record["active"] = False

    # BUG: the cache directory is never actually swept -- just logged.
    if os.path.exists(cache_path):
        print(f"Would remove {cache_path}")

    return directory
'''


def _verify_admin_ticket_1(submission: str) -> VerificationResult:
    with tempfile.TemporaryDirectory(prefix="itc_offboard_", ignore_cleanup_errors=True) as jail_root_str:
        jail_root = Path(jail_root_str)
        cache_dir = jail_root / f"employee_{_OFFBOARD_TARGET_USER_ID}_cache"
        cache_dir.mkdir()
        (cache_dir / "session.tmp").write_text("stale session token")
        (cache_dir / "browser_cache.dat").write_text("cached asset data")

        fake_os, fake_shutil = _make_jailed_os_shutil(jail_root)
        ok, namespace, error = _run_python_sandbox(
            submission,
            allowed_imports={"os", "shutil"},
            fake_modules={"os": fake_os, "shutil": fake_shutil},
        )
        if not ok:
            return VerificationResult(False, f"Script failed to run: {error}")

        func = namespace.get("offboard_employee")
        if not callable(func):
            return VerificationResult(
                False,
                "Expected an `offboard_employee(user_id, directory, cache_path) -> list[dict]` function.",
            )

        directory_copy = [dict(record) for record in MOCK_EMPLOYEE_DIRECTORY]
        try:
            result = _call_with_timeout(func, (_OFFBOARD_TARGET_USER_ID, directory_copy, str(cache_dir)))
        except concurrent.futures.TimeoutError:
            return VerificationResult(False, "offboard_employee() timed out (possible infinite loop).")
        except Exception as exc:  # noqa: BLE001
            return VerificationResult(False, f"offboard_employee() raised an error: {exc}")

        if not isinstance(result, list):
            return VerificationResult(False, "offboard_employee() must return a list of employee records.")

        details: list[str] = []
        passed = True

        record = next(
            (r for r in result if isinstance(r, dict) and r.get("user_id") == _OFFBOARD_TARGET_USER_ID),
            None,
        )
        if record is None:
            passed = False
            details.append(f"Returned directory is missing the record for user_id {_OFFBOARD_TARGET_USER_ID}.")
        elif record.get("active") is not False:
            passed = False
            details.append(f"Employee {_OFFBOARD_TARGET_USER_ID}'s `active` flag was not set to False.")

        for other in result:
            if (
                isinstance(other, dict)
                and other.get("user_id") != _OFFBOARD_TARGET_USER_ID
                and other.get("active") is not True
            ):
                passed = False
                details.append(f"Employee {other.get('user_id')} was modified but should have been left untouched.")

        if cache_dir.exists():
            passed = False
            details.append("The departing employee's temp cache directory still exists -- it was never swept.")

    message = (
        "Offboarding completed: profile deactivated and cache swept."
        if passed
        else "Offboarding did not complete correctly."
    )
    return VerificationResult(passed, message, details)


# ---------------------------------------------------------------------------
# Admin Ticket 2: The Security Compliance Audit (SQL UPDATE / WHERE / AND)
# ---------------------------------------------------------------------------

MOCK_EMPLOYEES_SEED = [
    {
        "first_name": "Alice", "last_name": "Nguyen", "department": "External QA",
        "employment_type": EmploymentType.CONTRACTOR, "clearance_level": "Tier 3",
    },
    {
        "first_name": "Brian", "last_name": "Osei", "department": "External QA",
        "employment_type": EmploymentType.CONTRACTOR, "clearance_level": "Tier 2",
    },
    # Full-time staff in External QA -- must NOT be touched by the downgrade.
    {
        "first_name": "Chen", "last_name": "Wu", "department": "External QA",
        "employment_type": EmploymentType.FULL_TIME, "clearance_level": "Tier 3",
    },
    # Contractor, but in a different department -- must NOT be touched either.
    {
        "first_name": "Dana", "last_name": "Silva", "department": "Engineering",
        "employment_type": EmploymentType.CONTRACTOR, "clearance_level": "Tier 3",
    },
    {
        "first_name": "Evan", "last_name": "Brooks", "department": "Finance",
        "employment_type": EmploymentType.FULL_TIME, "clearance_level": "Tier 2",
    },
]

_EXPECTED_DOWNGRADED = {("Alice", "Nguyen"), ("Brian", "Osei")}

STARTER_CODE_ADMIN_TICKET_2 = """-- TODO: Fix this UPDATE so it downgrades exactly the right employees.
-- Policy: every CONTRACTOR in the 'External QA' department must have their
-- clearance_level set to 'Tier 1'. Full-time staff and contractors in other
-- departments must be left completely untouched.
--
-- Available table: mock_employees(id, first_name, last_name, department,
--                                  employment_type, clearance_level)
--   employment_type is either 'Contractor' or 'Full-Time'.
--
-- BUG: this draft is missing the employment_type condition, so it will
-- downgrade full-time staff in External QA too -- a compliance violation.
UPDATE mock_employees
SET clearance_level = 'Tier 1'
WHERE department = 'External QA';
"""


def _verify_admin_ticket_2(submission: str) -> VerificationResult:
    rows, error = _run_update_sandbox(submission, MOCK_EMPLOYEES_SEED)
    if error is not None:
        return VerificationResult(False, error)

    details: list[str] = []
    passed = True
    for row in rows or []:
        key = (row["first_name"], row["last_name"])
        should_be_downgraded = key in _EXPECTED_DOWNGRADED
        is_downgraded = row["clearance_level"] == "Tier 1"
        if should_be_downgraded and not is_downgraded:
            passed = False
            details.append(f"{row['first_name']} {row['last_name']} should have been downgraded to Tier 1.")
        elif not should_be_downgraded and is_downgraded:
            passed = False
            details.append(f"{row['first_name']} {row['last_name']} was downgraded but should have been left alone.")

    message = (
        "Compliance downgrade applied to exactly the right contractors."
        if passed
        else "UPDATE did not match the required compliance scope."
    )
    return VerificationResult(passed, message, details)


# ---------------------------------------------------------------------------
# Admin Ticket 3: Disk Space Emergency (Python / os / os.path, path-jailed)
# ---------------------------------------------------------------------------

_LOG_RETENTION_DAYS = 14
_LOG_SIZE_LIMIT_BYTES = 50 * 1024 * 1024  # 50MB

# (filename, size_bytes, age_days, should_be_removed)
_LOG_FILE_SPECS = [
    ("app.log", 1 * 1024 * 1024, 2, False),          # small & recent -> keep
    ("app.log.1", 5 * 1024 * 1024, 10, False),         # small & recent-ish -> keep
    ("app.log.2", 60 * 1024 * 1024, 5, True),           # oversized -> remove
    ("archive.log.old", 2 * 1024 * 1024, 30, True),      # too old -> remove
    ("debug.log", 90 * 1024 * 1024, 20, True),            # oversized AND too old -> remove
    ("current.log", 512 * 1024, 0, False),                 # tiny & brand new -> keep
]

STARTER_CODE_ADMIN_TICKET_3 = '''"""Fix this log-rotation script: free disk space by clearing oversized/stale logs."""
import os
import time

MAX_SIZE_BYTES = 50 * 1024 * 1024  # 50MB
MAX_AGE_DAYS = 14


def rotate_logs(log_directory: str) -> list[str]:
    """Delete any log file over 50MB or older than 14 days; return removed filenames."""
    removed = []
    for filename in os.listdir(log_directory):
        file_path = os.path.join(log_directory, filename)

        # BUG: age is never computed -- only the size condition is checked, so
        # small-but-ancient log files are never rotated out.
        if os.path.getsize(file_path) > MAX_SIZE_BYTES:
            os.remove(file_path)
            removed.append(filename)

    return removed
'''


def _seed_log_directory(log_dir: Path) -> set[str]:
    """Create sparse dummy log files with crafted sizes/ages; return expected removals.

    Files are created via `truncate()` rather than writing real bytes, so even a
    90MB "log file" is created near-instantly as a sparse file.
    """
    now = time.time()
    expected_removed: set[str] = set()
    for filename, size_bytes, age_days, should_remove in _LOG_FILE_SPECS:
        file_path = log_dir / filename
        with open(file_path, "wb") as fh:
            fh.truncate(size_bytes)
        mtime = now - (age_days * 86400)
        os.utime(file_path, (mtime, mtime))
        if should_remove:
            expected_removed.add(filename)
    return expected_removed


def _verify_admin_ticket_3(submission: str) -> VerificationResult:
    with tempfile.TemporaryDirectory(prefix="itc_logrotate_", ignore_cleanup_errors=True) as jail_root_str:
        jail_root = Path(jail_root_str)
        expected_removed = _seed_log_directory(jail_root)

        fake_os, _ = _make_jailed_os_shutil(jail_root)
        ok, namespace, error = _run_python_sandbox(
            submission,
            allowed_imports={"os", "time"},
            fake_modules={"os": fake_os},
        )
        if not ok:
            return VerificationResult(False, f"Script failed to run: {error}")

        func = namespace.get("rotate_logs")
        if not callable(func):
            return VerificationResult(False, "Expected a `rotate_logs(log_directory: str) -> list[str]` function.")

        try:
            result = _call_with_timeout(func, (str(jail_root),))
        except concurrent.futures.TimeoutError:
            return VerificationResult(False, "rotate_logs() timed out (possible infinite loop).")
        except Exception as exc:  # noqa: BLE001
            return VerificationResult(False, f"rotate_logs() raised an error: {exc}")

        if not isinstance(result, list):
            return VerificationResult(False, "rotate_logs() must return a list of removed filenames.")

        got_removed = {str(name) for name in result}
        remaining_on_disk = {p.name for p in jail_root.iterdir()}

        details: list[str] = []
        missing = expected_removed - got_removed
        extra = got_removed - expected_removed
        still_present = expected_removed & remaining_on_disk

        if missing:
            details.append(f"Failed to rotate out: {sorted(missing)}")
        if extra:
            details.append(f"Removed file(s) that should have been kept: {sorted(extra)}")
        if still_present:
            details.append(f"Reported as removed but still on disk: {sorted(still_present)}")

        passed = not missing and not extra and not still_present

    message = (
        "Correctly rotated out all oversized/stale logs."
        if passed
        else "Log rotation did not match the expected cleanup."
    )
    return VerificationResult(passed, message, details)


# ---------------------------------------------------------------------------
# Ticket catalog
# ---------------------------------------------------------------------------

TICKETS: list[TicketDefinition] = [
    TicketDefinition(
        id=1,
        title="The User Provisioning Script",
        department="Help Desk",
        severity=Severity.LOW,
        problem_description=(
            "HR just handed you a CSV export of this week's new hires. The onboarding "
            "script that's supposed to generate company email addresses and assign "
            "each new hire to the right access groups is throwing bad data: emails "
            "aren't formatted correctly and a bogus record keeps showing up in the "
            "output. Fix `provision_users()` so every new hire is provisioned correctly."
        ),
        starter_code=STARTER_CODE_TICKET_1,
        logs_context={"sample_roster_csv": MOCK_ROSTER_CSV, "group_map": _GROUP_MAP},
        validation_criteria={
            "checks": [
                "Returns exactly one record per employee row (header excluded).",
                "email == firstname.lastname@company.com, all lowercase.",
                "groups exactly match the department -> access-group mapping.",
            ]
        },
        reward_field="automation_xp",
        reward_amount=50,
        verify=_verify_ticket_1,
    ),
    TicketDefinition(
        id=2,
        title="The Account Lockout Audit",
        department="Security / SysAdmin",
        severity=Severity.INCIDENT,
        problem_description=(
            "Multiple help desk tickets are coming in about locked-out accounts. "
            "Security suspects a brute-force attempt and needs a report of every "
            "source IP address with more than 5 failed login attempts in the last "
            "hour, pulled from the `access_logs` table. Fix the SQL query below."
        ),
        starter_code=STARTER_CODE_TICKET_2,
        logs_context=_build_logs_context_ticket_2(),
        validation_criteria={
            "checks": [
                "Only FAILED attempts count (SUCCESS logins are excluded).",
                "Only attempts within the last hour count.",
                "Only IPs with a count strictly greater than 5 are returned.",
            ]
        },
        reward_field="database_xp",
        reward_amount=100,
        verify=_verify_ticket_2,
    ),
    TicketDefinition(
        id=3,
        title="The Firewall Breach",
        department="Network Operations",
        severity=Severity.CATASTROPHIC,
        problem_description=(
            "The edge router has been logging a wave of rejected connections and "
            "the on-call network engineer needs a fast triage list. Fix "
            "`extract_unauthorized_ips()` so it correctly pulls every source IP "
            "behind a DENY or BLOCKED entry out of the raw firewall log."
        ),
        starter_code=STARTER_CODE_TICKET_3,
        logs_context={"sample_firewall_log": MOCK_FIREWALL_LOG},
        validation_criteria={
            "checks": [
                "Every DENY/BLOCKED source IP is present, with no duplicates required.",
                "No ALLOW-line IPs are included.",
            ]
        },
        reward_field="networking_xp",
        reward_amount=150,
        verify=_verify_ticket_3,
    ),
    TicketDefinition(
        id=4,
        title="Employee Terminations",
        department="SysAdmin",
        severity=Severity.INCIDENT,
        problem_description=(
            "An employee has left the company under urgent conditions and Legal "
            "wants their access cut immediately. Fix `offboard_employee()` so it "
            "correctly deactivates the departing employee's directory profile and "
            "sweeps every file out of their temporary cache directory -- leaving "
            "everyone else's profile and files completely untouched."
        ),
        starter_code=STARTER_CODE_ADMIN_TICKET_1,
        logs_context={"mock_directory": MOCK_EMPLOYEE_DIRECTORY, "target_user_id": _OFFBOARD_TARGET_USER_ID},
        validation_criteria={
            "checks": [
                "The target employee's `active` flag is set to exactly False.",
                "No other employee record is modified.",
                "The employee's temp cache directory no longer exists on disk afterward.",
            ]
        },
        reward_field="infra_points",
        reward_amount=100,
        verify=_verify_admin_ticket_1,
        is_admin_only=True,
    ),
    TicketDefinition(
        id=5,
        title="The Security Compliance Audit",
        department="Security / Governance",
        severity=Severity.CATASTROPHIC,
        problem_description=(
            "A new corporate compliance policy requires every contractor in the "
            "'External QA' department to have their clearance downgraded to Tier 1 "
            "immediately. Fix the UPDATE statement below so it hits exactly those "
            "records -- full-time staff and contractors elsewhere must not change."
        ),
        starter_code=STARTER_CODE_ADMIN_TICKET_2,
        logs_context={"mock_employees": MOCK_EMPLOYEES_SEED},
        validation_criteria={
            "checks": [
                "Exactly the contractors in External QA end up at clearance_level 'Tier 1'.",
                "Full-time staff in External QA are left unchanged.",
                "Contractors outside External QA are left unchanged.",
            ]
        },
        reward_field="infra_points",
        reward_amount=150,
        verify=_verify_admin_ticket_2,
        is_admin_only=True,
    ),
    TicketDefinition(
        id=6,
        title="Disk Space Emergency",
        department="SysAdmin",
        severity=Severity.INCIDENT,
        problem_description=(
            "A critical Linux application server is hitting 98% disk capacity. "
            "Fix `rotate_logs()` so it clears out any log file larger than 50MB "
            "OR older than 14 days, and returns the list of filenames it removed, "
            "so the on-call engineer can confirm exactly what was reclaimed."
        ),
        starter_code=STARTER_CODE_ADMIN_TICKET_3,
        logs_context={
            "log_directory_preview": [
                {"filename": name, "size_bytes": size, "age_days": age}
                for name, size, age, _ in _LOG_FILE_SPECS
            ]
        },
        validation_criteria={
            "checks": [
                "Every file over 50MB is removed, regardless of age.",
                "Every file older than 14 days is removed, regardless of size.",
                "Files that are neither oversized nor stale are left in place.",
                "The returned filename list matches what's actually gone from disk.",
            ]
        },
        reward_field="infra_points",
        reward_amount=125,
        verify=_verify_admin_ticket_3,
        is_admin_only=True,
    ),
]

TICKETS_BY_ID: dict[int, TicketDefinition] = {ticket.id: ticket for ticket in TICKETS}
