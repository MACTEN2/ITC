# ITC — IT Operations and Systems Simulator

A FastAPI backend that lets learners practice entry-level IT skills (Help Desk,
Junior SysAdmin, Junior Database Analyst) by resolving simulated **IT Support
Tickets** — real bugs in Python scripts and SQL queries, graded automatically.
Accounts are real (JWT-authenticated, bcrypt-hashed passwords), and a
separate **Admin dashboard** layers three governance/SysAdmin scenarios on
top, gated behind an `is_admin` flag.

## How it works

1. A learner registers (`POST /api/auth/register`) and logs in
   (`POST /api/auth/login`) to get a JWT access token.
2. They pull the open ticket catalog from `GET /api/tickets` (bearer token
   required). Each ticket ships with a `problem_description`,
   `validation_criteria` (what's being checked), `logs_context` (mock data to
   work against), and `starter_code` that's deliberately broken.
3. They fix it and submit their code/SQL to `POST /api/tickets/submit`.
4. The submission is graded in an isolated sandbox against a black-box
   verifier (the "correct" answer is never shown, only whether the observed
   behavior matches it).
5. On a first-time pass, the learner's XP for the relevant track
   (`networking_xp` / `automation_xp` / `database_xp`) increases and persists.
6. Accounts with `is_admin=True` additionally get `GET/POST /api/admin/tickets*`,
   three higher-stakes SysAdmin scenarios rewarded in a separate `infra_points`
   currency.

## Project structure

```
ITC/
├── app/
│   ├── database.py         # SQLite engine, get_db()/init_db()
│   ├── models.py            # SQLAlchemy models (see Data model below)
│   ├── tickets_db.py         # 6 hardcoded tickets + all sandboxed grading logic
│   ├── main.py                # FastAPI app: CORS, startup seeding, learner ticket routes
│   └── routes/
│       ├── auth.py               # register/login, password hashing, JWT, get_current_user
│       └── admin.py               # admin-only ticket routes, require_admin, audit logging
├── tests/
│   ├── conftest.py           # shared fixtures: client, learner_token, admin_token
│   ├── test_tickets.py        # learner-tier ticket engine
│   ├── test_auth.py            # registration, login, token validation
│   └── test_admin.py            # admin authorization boundary + 3 admin tickets
├── requirements.txt          # Runtime dependencies
├── requirements-dev.txt       # + pytest/httpx for running the test suite
└── itc_database.db              # SQLite file, created on first run (git-ignored)
```

## Data model (`app/models.py`)

| Table | Purpose |
|---|---|
| `User` | Account: `username`, `email`, `hashed_password` (bcrypt), `current_role`, `is_admin`, three XP counters (`networking_xp`, `automation_xp`, `database_xp`), `infra_points` (admin-only currency), `created_at`. |
| `Ticket` | Catalog entry: `title`, `department`, `severity`, `problem_description`, `starter_code`, `logs_context` (JSON), `validation_criteria` (JSON, human-readable grading checklist), `is_admin_only`. |
| `UserTicketProgress` | One row per (user, ticket): `status` (Open/Resolved), `code_submission`, `unlocked_at`, `resolved_at`. |
| `AccessLog` | Sandbox-only table for Ticket 2. Seeded fresh into a throwaway in-memory DB per SQL grading call. |
| `MockEmployee` | Sandbox-only table for Admin Ticket 5. Same throwaway-per-call pattern as `AccessLog`. |

Learner and admin tickets share one `tickets` table, distinguished by
`is_admin_only` — `GET /api/tickets` filters it to `False`, `GET
/api/admin/tickets` filters it to `True`, and both submit endpoints 404 if a
`ticket_id` from the wrong tier is passed in.

## The 6 tickets (`app/tickets_db.py`)

**Learner tier** — `GET/POST /api/tickets*`, any authenticated account:

| # | Title | Skill | XP track | Reward |
|---|---|---|---|---|
| 1 | The User Provisioning Script | Python — `csv` / `json` parsing, buggy email generation | `automation_xp` | 50 |
| 2 | The Account Lockout Audit | SQL — `GROUP BY` / `HAVING` brute-force detection | `database_xp` | 100 |
| 3 | The Firewall Breach | Python — `re` extraction of unauthorized IPs | `networking_xp` | 150 |

**Admin tier** — `GET/POST /api/admin/tickets*`, `is_admin=True` only:

| # | Title | Skill | Reward |
|---|---|---|---|
| 4 | Employee Terminations | Python — `os`/`shutil` (path-jailed): deactivate a profile + sweep a cache dir | 100 `infra_points` |
| 5 | The Security Compliance Audit | SQL `UPDATE` with `WHERE`/`AND`: scoped batch clearance downgrade | 150 `infra_points` |
| 6 | Disk Space Emergency | Python — `os`/`os.path` (path-jailed): rotate logs over 50MB or older than 14 days | 125 `infra_points` |

Each ticket is graded by an independent reference implementation, so **any**
correct approach the learner writes passes — the grader never diffs source
code, only behavior. Grading + XP/points persistence for *both* tiers goes
through one shared function, `grade_submission()` in `tickets_db.py`, so the
"first successful attempt earns the reward, resubmissions don't farm it" rule
lives in exactly one place.

## Authentication & security model

- **Passwords**: hashed with bcrypt via `passlib`, never stored or compared
  as plaintext. Bcrypt salts automatically per call, so hashing the same
  password twice yields two different hashes.
- **Sessions**: stateless JWT (HS256, via `pyjwt`), issued on login, valid for
  60 minutes. `get_current_user` (in `app/routes/auth.py`) is the dependency
  every protected route uses to turn a bearer token into a `User` row.
- **Admin authorization**: `require_admin` (in `app/routes/admin.py`) layers
  on top of `get_current_user` — a bad/missing token is `401`; a valid token
  for a non-admin account is `403`. There is **no API endpoint that grants
  `is_admin`** — it's deliberately only settable at the database level (an
  out-of-band operational action), never through the HTTP surface.
- **Audit logging**: every admin route access (allowed or rejected) and every
  admin submission outcome is logged at INFO/WARNING level with the acting
  username, ticket id, and result.
- **JWT secret**: read from the `ITC_JWT_SECRET_KEY` environment variable. If
  unset, the app falls back to a hardcoded, publicly-known dev secret and
  logs a loud warning on startup — **set this env var before deploying
  anywhere but a local machine.**

### Sandbox security model

Learner/admin code and SQL are untrusted input, so submissions never run with
full interpreter or database privileges. Three isolated execution strategies:

- **Python submissions** (`_run_python_sandbox`) execute via `exec()` with a
  hand-picked allowlist of builtins and an `__import__` override that only
  permits a whitelisted module set per ticket. There is no `open`, `sys`,
  `subprocess`, `eval`, or network access available. Execution runs on a
  worker thread with a 5-second wall-clock timeout.
- **Path-jailed `os`/`shutil`** (`_make_jailed_os_shutil`): Admin Tickets 4
  and 6 genuinely need filesystem access (sweeping a cache directory, rotating
  logs), which is too dangerous to hand out for real. `import os` / `import
  shutil` in those two tickets' sandbox resolve to lightweight facade objects
  instead of the real modules — same function names (`os.path.getsize`,
  `os.remove`, `shutil.rmtree`, ...), but every path argument is resolved and
  checked against a single throwaway `tempfile.TemporaryDirectory()` before
  any real operation runs. A path outside that directory (via `../` traversal
  or an absolute path elsewhere on the host) raises `SandboxPermissionError`
  instead of touching the real filesystem.
- **Read-only SQL** (`_run_sql_sandbox`, Ticket 2): validated as a single
  `SELECT` — no DDL/DML, no stacked statements — then executed against a
  fresh in-memory SQLite database seeded per call.
- **Scoped `UPDATE`** (`_run_update_sandbox`, Admin Ticket 5): the one
  deliberate exception. A single `UPDATE` against one named table
  (`mock_employees`), *mandatory* `WHERE` clause, no other DDL/DML keywords —
  run against the same kind of throwaway in-memory database.

Both SQL validators strip `--`/`/* */` comments before pattern-matching (see
[Fixed issues](#fixed-issues) — the un-stripped version rejected the ticket's
own starter code).

This is a best-effort sandbox appropriate for a learning tool where
submissions come from the app's own authenticated users — not a hardened
multi-tenant sandbox for adversarial public input (a production deployment
handling that would isolate execution in a subprocess or container instead).

## API

All routes except `/api/auth/*` require `Authorization: Bearer <token>`.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | none | Create an account (JSON body: `username`, `email`, `password`). |
| POST | `/api/auth/login` | none | Form body (`username`, `password`) → `{access_token, token_type}`. |
| GET | `/api/tickets` | any account | Learner-tier ticket catalog. |
| POST | `/api/tickets/submit` | any account | Grade a learner submission, award XP. |
| GET | `/api/admin/tickets` | `is_admin=True` | Admin-tier ticket catalog. |
| POST | `/api/admin/tickets/submit` | `is_admin=True` | Grade an admin submission, award `infra_points`. |

### `POST /api/tickets/submit`
```jsonc
{
  "ticket_id": 2,
  "submission": "SELECT ip_address, COUNT(*) ..."
}
```
```jsonc
{
  "passed": true,
  "message": "Correctly isolated all brute-force IP addresses.",
  "details": [],
  "xp_awarded": 100,
  "resolution_time": 0.0072,
  "user": { "current_role": "Help Desk Tier 1", "networking_xp": 0, "automation_xp": 50, "database_xp": 100 }
}
```
XP/points are only granted the **first** time a user resolves a given ticket —
resubmitting an already-correct answer returns `passed: true` but a `0`
award, so nobody can farm XP by resubmitting.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> **Note on `bcrypt`**: `requirements.txt` pins `bcrypt==4.0.1`. `passlib`
> (last released 2020) probes an internal `bcrypt.__about__` attribute that
> `bcrypt>=4.1` removed, which otherwise breaks every hash/verify call with a
> spurious `"password cannot be longer than 72 bytes"` error.

## Running the app

```bash
export ITC_JWT_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"  # production: set this to something stable
uvicorn app.main:app --reload
```

On startup the app creates `itc_database.db` (if it doesn't exist) and
seeds/syncs the 6-ticket catalog into it. There's no demo-user auto-seed
anymore — register a real account. To test the admin dashboard locally,
promote an account directly in the DB:

```bash
sqlite3 itc_database.db "UPDATE users SET is_admin = 1 WHERE username = 'your_username';"
```

Interactive API docs: `http://127.0.0.1:8000/docs` (Swagger UI's "Authorize"
button works directly against `/api/auth/login`).

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

45 tests across 3 files, all driving the real HTTP API via FastAPI's
`TestClient` (shared fixtures in `conftest.py`: `client`, `learner_token`,
`admin_token`). Coverage includes:

- **test_tickets.py** — the learner-tier engine: valid/broken submissions per
  ticket, the "Server Downtime Counter-Attack" safety net (syntax errors,
  runtime exceptions, sandbox-escape attempts must all come back as a clean
  `200`/`passed: false`, never a `500`), SQL injection rejection, anti-farming,
  cross-tier boundary enforcement, and the `401`-without-a-token path.
- **test_auth.py** — registration (duplicate username/email, invalid email,
  short password), login (success, wrong password, unknown user), protected
  routes (missing/malformed token), and that bcrypt salts independently per hash.
- **test_admin.py** — the `401` → `403` → `404` authorization ladder, all
  three admin tickets' grading logic (valid, buggy, and the missing-`AND`-clause
  compliance bug specifically), the path-jailed filesystem sandbox's escape
  prevention, the scoped-`UPDATE` sandbox's rejection of unconditional/destructive
  statements, and anti-farming for `infra_points`.

Each test runs against a freshly reset SQLite database (`conftest.py`
disposes the engine and deletes `itc_database.db` before/after every test),
so results are deterministic regardless of run order, how many times the
suite has run before, or which directory you run `pytest` from.

> **Note:** the installed `starlette` version prefers a package named
> `httpx2` for `TestClient`, falling back to the well-known `httpx` (used
> here) with a harmless deprecation warning.

## Fixed issues

- **`passlib` + modern `bcrypt` incompatibility.** `passlib` 1.7.4 (its last
  release) probes an internal `bcrypt.__about__` attribute that `bcrypt>=4.1`
  removed, breaking every hash/verify call. **Fix:** pinned `bcrypt==4.0.1` in
  `requirements.txt`, the newest release `passlib`'s version-sniffing still
  works against.
- **SQLAlchemy `Enum` stores the member *name*, not the *value*, by default.**
  `Enum(EmploymentType)` was persisting `"CONTRACTOR"` (the Python identifier)
  instead of `"Contractor"` (the human-readable value shown in the ticket and
  in every `SELECT` result). A learner's `WHERE employment_type = 'Contractor'`
  — the only value they'd ever see — would have silently matched zero rows.
  Caught by writing a throwaway reproduction script before shipping the
  compliance-audit ticket, not by a test. **Fix:** `values_callable=lambda
  enum_cls: [e.value for e in enum_cls]` on both `AccessLog.status` and
  `MockEmployee.employment_type`.
- **SQL validators rejected the tickets' own starter code.** `_validate_select_only`
  / `_validate_update_only` anchored `^\s*SELECT\b` / `^\s*UPDATE\b` at the very
  start of the submission. Both ship with explanatory `-- comment` lines above
  the actual statement (entirely normal SQL style), which made the anchor fail
  and reject perfectly valid SQL with a confusing "Only a SELECT statement..."
  error — including the ticket's *own* starter code, caught by feeding it
  through the verifier directly before shipping. **Fix:** both validators now
  strip `--`/`/* */` comments before pattern-matching (the *original*,
  un-stripped submission is still what actually executes).
- **INFO-level audit logs were silently dropped.** `app/routes/admin.py`'s
  `logger.info(...)` calls (the audit trail this feature explicitly asks for)
  never appeared in server output, because Python's root logger defaults to
  `WARNING` and nothing configured it otherwise. Caught by grepping the live
  server log for expected audit lines and finding them missing. **Fix:**
  `logging.basicConfig(level=logging.INFO, ...)` in `app/main.py`.
- **Test suite failed 7/11 when run from inside `tests/`** (pre-auth version
  of this app). `app/database.py` built the SQLite URL as the cwd-relative
  `sqlite:///./itc.db`, so launching from a different directory silently
  read/wrote a different file than the test fixture was resetting, leaking XP
  across tests. **Fix:** the DB path is built from `Path(__file__)`, always
  resolving to the same project-root file regardless of working directory.

## Design notes / known limitations

- **No self-service admin promotion.** `is_admin` is only settable directly
  in the database — by design, not an oversight. There is intentionally no
  "become admin" request path.
- Grading correctness is verified against **crafted mock data** baked into
  `tickets_db.py`, not user-provided fixtures — this keeps every submission
  reproducible and graded identically for every learner.
  - Admin Tickets 4 and 6's filesystem fixtures are created as **sparse
    files** (`truncate()` rather than writing real bytes), so even a
    simulated 90MB log file is created near-instantly with negligible real
    disk usage.
- The Python sandbox uses `ThreadPoolExecutor.result(timeout=...)` for the
  wall-clock limit; Python cannot forcibly kill a running thread, so a
  submission that ignores the timeout will keep consuming a worker thread in
  the background even after the request returns an error to the caller.
- The JWT dev-secret fallback is intentionally loud (a startup warning) rather
  than silent, but it's still a fallback — there's no hard failure that
  prevents running with it in a real deployment. Ops discipline (setting
  `ITC_JWT_SECRET_KEY`) is required, not enforced.
- Email format validation is a pragmatic regex (`app/routes/auth.py`), not
  full RFC 5322 validation — deliberately avoiding a dependency on
  `email-validator`, which isn't in `requirements.txt`.
