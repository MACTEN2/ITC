# ITC — IT Operations and Systems Simulator

A FastAPI + Next.js app that lets learners practice entry-level IT skills
(Help Desk, Network Support, Database Administration, SysAdmin) by resolving
simulated **IT Support Tickets**. There is no code or SQL to write anywhere
in this app: every ticket is closed the way a real Help Desk / IT Support
agent actually closes one in a system like ServiceNow or Zendesk — read the
scenario, diagnose the root cause from a fixed list of plausible options,
select the correct resolution action(s) from a checklist, and write a
resolution note before the ticket can close. Accounts are real
(JWT-authenticated, bcrypt-hashed passwords), and a separate **Admin
dashboard** layers three higher-stakes governance/SysAdmin scenarios on top,
gated behind an `is_admin` flag.

## How it works

1. A learner registers (`POST /api/auth/register`) and logs in
   (`POST /api/auth/login`) to get a JWT access token.
2. They pull the open ticket catalog from `GET /api/tickets` (bearer token
   required). Each ticket ships with a `problem_description`, supporting
   `logs_context` (a realistic log/config snippet to read, not to parse
   programmatically), `root_cause_options` (single-select), and
   `resolution_options` (multi-select) — the *options* only, never which
   ones are correct.
3. They fill out the resolution form and submit it to
   `POST /api/tickets/submit`: `{root_cause, resolution_actions,
   resolution_notes}`.
4. Grading is a straightforward, deterministic comparison against the answer
   key in `app/tickets_db.py` (never exposed over the API): the root cause
   must match exactly, the resolution actions must match the correct set
   exactly (missing a required step or picking an unnecessary one both
   fail it), and a non-empty resolution note is mandatory.
5. On a first-time pass, the learner's XP for the relevant track
   (`networking_xp` / `automation_xp` / `database_xp`) increases and persists.
6. Accounts with `is_admin=True` additionally get `GET/POST /api/admin/tickets*`,
   three higher-stakes governance/SysAdmin scenarios rewarded in a separate
   `infra_points` currency.

## Project structure

```
ITC/
├── app/
│   ├── database.py         # SQLite engine, get_db()/init_db()
│   ├── models.py            # SQLAlchemy models (see Data model below)
│   ├── tickets_db.py         # 7 hardcoded tickets + the grading logic
│   ├── main.py                # FastAPI app: CORS, startup seeding, learner ticket routes
│   └── routes/
│       ├── auth.py               # register/login, password hashing, JWT, get_current_user
│       └── admin.py               # admin-only ticket routes, require_admin, audit logging
├── frontend/                # Next.js (App Router) + Tailwind v4 -- see Frontend section below
│   ├── app/{login,register,dashboard,admin}/page.tsx
│   ├── components/TicketResolutionWorkspace.tsx
│   └── lib/{api.ts,types.ts}
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
| `Ticket` | Catalog entry: `title`, `department`, `severity`, `problem_description`, `root_cause_options` (JSON list), `resolution_options` (JSON list), `logs_context` (JSON), `validation_criteria` (JSON, human-readable grading checklist), `is_admin_only`. |
| `UserTicketProgress` | One row per (user, ticket): `status` (Open/Resolved), `submission_data` (JSON: the learner's last submitted root cause/actions/notes), `unlocked_at`, `resolved_at`. |

Learner and admin tickets share one `tickets` table, distinguished by
`is_admin_only` — `GET /api/tickets` filters it to `False`, `GET
/api/admin/tickets` filters it to `True`, and both submit endpoints 404 if a
`ticket_id` from the wrong tier is passed in. Crucially, `root_cause_options`
and `resolution_options` are the only ticket fields the API ever serializes
— the correct answer for each ticket lives exclusively in Python in
`app/tickets_db.py` and is never sent to the client.

## The 7 tickets (`app/tickets_db.py`)

**Learner tier** — `GET/POST /api/tickets*`, any authenticated account:

| # | Title | Department | Severity | XP track | Reward |
|---|---|---|---|---|---|
| 1 | Employee Locked Out After Password Reset | Help Desk | Incident | `automation_xp` | 100 |
| 2 | Persistent Wi-Fi Drops in the East Conference Room | Network Operations | Low | `networking_xp` | 50 |
| 3 | Duplicate Customer Records After CRM Import | Database Administration | Incident | `database_xp` | 100 |
| 4 | Suspicious Email Reported by Finance | Help Desk | Catastrophic | `automation_xp` | 150 |

**Admin tier** — `GET/POST /api/admin/tickets*`, `is_admin=True` only:

| # | Title | Department | Severity | Reward |
|---|---|---|---|---|
| 5 | Employee Offboarding — Immediate Access Revocation | SysAdmin | Incident | 100 `infra_points` |
| 6 | Compliance Flag: Contractor Access Review | Security / Governance | Catastrophic | 150 `infra_points` |
| 7 | Critical Server Disk Space Emergency | SysAdmin | Incident | 125 `infra_points` |

Every ticket is graded by the exact same generic mechanism
(`_make_selection_verifier` in `tickets_db.py`): exact match on root cause,
exact-set match on resolution actions, and a mandatory resolution note.
Grading + XP/points persistence for *both* tiers goes through one shared
function, `grade_submission()`, so the "first successful attempt earns the
reward, resubmissions don't farm it" rule lives in exactly one place.

Each scenario is deliberately built around a *plausible wrong answer* a
real Tier 1 agent might reach for under time pressure — e.g. Ticket 4's
worst-case wrong move is "forward the employee's real banking details to
verify," which the grader rejects just as firmly as any other incorrect
combination.

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

There is no code-execution sandbox in this app at all — every submission is
a small JSON object (`root_cause`, `resolution_actions`, `resolution_notes`)
graded by plain string/set comparison, so there's no `exec()`, no SQL
execution, and no filesystem access anywhere in the request path.

## API

All routes except `/api/auth/register` and `/api/auth/login` require
`Authorization: Bearer <token>`.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | none | Create an account (JSON body: `username`, `email`, `password`). |
| POST | `/api/auth/login` | none | Form body (`username`, `password`) → `{access_token, token_type}`. |
| GET | `/api/auth/me` | any account | The caller's own profile (used by the frontend's admin gate). |
| GET | `/api/tickets` | any account | Learner-tier ticket catalog. |
| POST | `/api/tickets/submit` | any account | Grade a learner's resolution form, award XP. |
| GET | `/api/admin/tickets` | `is_admin=True` | Admin-tier ticket catalog. |
| POST | `/api/admin/tickets/submit` | `is_admin=True` | Grade an admin's resolution form, award `infra_points`. |

### `POST /api/tickets/submit`
```jsonc
{
  "ticket_id": 2,
  "root_cause": "The access point is overloaded with far more connected devices than it's rated for",
  "resolution_actions": [
    "Install a second access point to split the client load",
    "Enable the 5GHz radio so compatible devices can move off the crowded 2.4GHz band"
  ],
  "resolution_notes": "Added a second AP and enabled 5GHz to spread the load."
}
```
```jsonc
{
  "passed": true,
  "message": "Ticket resolved correctly.",
  "details": [],
  "xp_awarded": 50,
  "resolution_time": 0.0001,
  "user": { "current_role": "Help Desk Tier 1", "networking_xp": 50, "automation_xp": 0, "database_xp": 0 }
}
```
XP/points are only granted the **first** time a user resolves a given ticket
— resubmitting an already-correct answer returns `passed: true` but a `0`
award, so nobody can farm XP by resubmitting.

## Frontend (`frontend/`)

A Next.js (App Router) + Tailwind v4 dark-themed UI, kept in its own
directory since Next.js's own `app/` router would otherwise collide with
the Python `app/` package at the project root.

| Page/Component | Purpose |
|---|---|
| `app/login/page.tsx` | Credential capture -> `POST /api/auth/login` (form-encoded) -> stores the JWT in `localStorage` -> `GET /api/auth/me` -> routes to `/admin` or `/dashboard` by `is_admin`. |
| `app/register/page.tsx` | Account creation -> `POST /api/auth/register` -> immediately logs the new account in and routes it onward, same as the login page. |
| `app/dashboard/page.tsx` | Learner command center: sidebar filters by ticket `department`, a metrics header (current IT Tier + 3 XP bars), and a ticket feed backed live by `GET /api/tickets`. |
| `app/admin/page.tsx` | Admin dashboard: fetches the caller's own profile first and only calls the admin ticket catalog if `is_admin` is true; a non-admin account sees a clean "Access Restricted" panel instead. Includes a simulated (not real) operational log feed. |
| `components/TicketResolutionWorkspace.tsx` | Shared split-screen resolution form: ticket detail (source department, target machine/IP, severity, raw log) on the left; a root-cause radio list, a resolution-actions checklist, and a resolution-notes textarea on the right, wired to `POST /api/tickets/submit` or `/api/admin/tickets/submit` depending on `mode`. |
| `lib/api.ts` / `lib/types.ts` | Typed fetch wrapper (attaches the bearer token automatically) and TypeScript mirrors of every backend response shape. |

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL, defaults to http://127.0.0.1:8000
npm run dev
```

The client-side auth gate on `/dashboard` and `/admin` (checking `is_admin`,
redirecting to `/login`) is a UX convenience only — the real authorization
boundary is always server-side (`require_admin` in `app/routes/admin.py`).

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
seeds/syncs the 7-ticket catalog into it. There's no demo-user auto-seed —
register a real account (via `POST /api/auth/register` or the frontend's
`/register` page). To test the admin dashboard locally, promote an account
directly in the DB:

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

49 tests across 3 files, all driving the real HTTP API via FastAPI's
`TestClient` (shared fixtures in `conftest.py`: `client`, `learner_token`,
`admin_token`). Coverage includes:

- **test_tickets.py** — the learner-tier engine: correct resolutions per
  ticket, wrong root causes, missing/extra resolution steps, missing
  resolution notes, the "no answer key leaks over the API" check, anti-farming,
  cross-tier boundary enforcement, and the `401`-without-a-token path.
- **test_auth.py** — registration (duplicate username/email, invalid email,
  short password), login (success, wrong password, unknown user), protected
  routes (missing/malformed token), and that bcrypt salts independently per hash.
- **test_admin.py** — the `401` → `403` → `404` authorization ladder, all
  three admin tickets' grading logic (correct resolution, wrong root cause,
  missing/extra steps), and anti-farming for `infra_points`.

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
- **Ticket content edits never reached an existing database.** `_seed_ticket_catalog()`
  only inserted a `Ticket` row if its id was missing, so replacing a ticket's
  content in `tickets_db.py` had *no effect* on an already-running instance's
  database until the file was deleted by hand. **Fix:** seeding now syncs
  every field on every startup — `tickets_db.py` is the single source of
  truth, there's no admin UI for editing ticket content independently, so
  the DB row should always mirror it exactly.

*(Earlier iterations of this app used a code/SQL-execution sandbox — a
restricted `exec()` for Python submissions, path-jailed `os`/`shutil`
facades, and a scoped SQL `UPDATE`/`SELECT` sandbox. That entire subsystem
and the bugs specific to it, e.g. SQL comment-stripping and SQLAlchemy
`Enum` name-vs-value storage, were removed along with it when the app moved
to the no-code resolution-form model above.)*

## Design notes / known limitations

- **No self-service admin promotion.** `is_admin` is only settable directly
  in the database — by design, not an oversight. There is intentionally no
  "become admin" request path.
- **No partial credit.** A resolution form either matches the answer key
  exactly (root cause + full resolution-action set + a non-empty note) or it
  doesn't — there's no scoring for "close enough."
- Grading correctness is verified against a **fixed answer key** baked into
  `tickets_db.py`, not configurable per-request — this keeps every
  submission reproducible and graded identically for every learner.
- The JWT dev-secret fallback is intentionally loud (a startup warning) rather
  than silent, but it's still a fallback — there's no hard failure that
  prevents running with it in a real deployment. Ops discipline (setting
  `ITC_JWT_SECRET_KEY`) is required, not enforced.
- Email format validation is a pragmatic regex (`app/routes/auth.py`), not
  full RFC 5322 validation — deliberately avoiding a dependency on
  `email-validator`, which isn't in `requirements.txt`.
