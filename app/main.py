"""FastAPI application exposing the ITC (IT Operations and Systems Simulator) API.

On startup, `init_db()` creates every table (idempotent -- this is what makes
`itc_database.db` materialize automatically on first run) and the hardcoded
ticket catalog from `tickets_db.py` is seeded/synced into it. There is no
demo-user auto-seed anymore: accounts are created through real registration
(`POST /api/auth/register`) now that JWT authentication is in place.

Three routers are mounted:

    - app.routes.auth   -> POST /api/auth/register, POST /api/auth/login
    - app.routes.admin  -> GET/POST /api/admin/tickets* (admin-only, see that module)
    - this module       -> GET/POST /api/tickets* (any authenticated user)

Both ticket-catalog/submission endpoints below now require a valid JWT (via
`Depends(get_current_user)`) and act on whichever account that token
identifies -- there is no more client-supplied `user_id` field, which also
closes off the obvious "submit on someone else's behalf" hole.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db, init_db
from app.models import Ticket, User
from app.routes import admin, auth
from app.routes.auth import get_current_user
from app.tickets_db import TICKETS, TICKETS_BY_ID, TicketSubmission, grade_submission

# INFO-level app logs (admin route access, submission audit trail) are silently
# dropped under Python's default root level of WARNING. This makes them actually
# visible in server output, which is the whole point of the admin audit logging
# in app/routes/admin.py.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _seed_ticket_catalog() -> None:
    """Sync every ticket row with the hardcoded catalog: insert if missing,
    overwrite every field if already present.

    `tickets_db.py` is the single source of truth for ticket content -- there's
    no admin UI for editing a ticket's text independently of it -- so treating
    the DB row as anything other than a mirror of the current TICKETS list is
    a bug: an earlier version of this function only inserted missing rows,
    which meant editing a ticket's content in code had *no effect* on an
    existing database until it was deleted by hand. `UserTicketProgress` rows
    (by ticket_id FK) are untouched either way.
    """
    db = SessionLocal()
    try:
        for definition in TICKETS:
            ticket = db.get(Ticket, definition.id)
            if ticket is None:
                ticket = Ticket(id=definition.id)
                db.add(ticket)
            ticket.title = definition.title
            ticket.department = definition.department
            ticket.severity = definition.severity
            ticket.problem_description = definition.problem_description
            ticket.root_cause_options = definition.root_cause_options
            ticket.resolution_options = definition.resolution_options
            ticket.logs_context = definition.logs_context
            ticket.validation_criteria = definition.validation_criteria
            ticket.is_admin_only = definition.is_admin_only
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    _seed_ticket_catalog()
    yield


app = FastAPI(
    title="ITC - IT Operations and Systems Simulator",
    description="Practice entry-level IT support skills by resolving simulated IT tickets.",
    version="3.0.0",
    lifespan=lifespan,
)

# Permissive CORS since this API is consumed by a separate front-end during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class TicketOut(BaseModel):
    """Public shape of a ticket returned to the front-end.

    Only ever carries the multiple-choice *options*, never which one is
    correct -- the answer key lives solely in `tickets_db.py`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    department: str
    severity: str
    problem_description: str
    root_cause_options: list[str]
    resolution_options: list[str]
    logs_context: dict
    validation_criteria: dict


class SubmissionRequest(BaseModel):
    """A learner's filled-out resolution form for one ticket."""

    ticket_id: int = Field(description="ID of the ticket being attempted.")
    root_cause: str = Field(description="The selected root cause (must match one of the ticket's options).")
    resolution_actions: list[str] = Field(
        default_factory=list, description="The selected resolution step(s) (subset of the ticket's options)."
    )
    resolution_notes: str = Field(default="", description="Free-text resolution summary, required to close the ticket.")


class UserXP(BaseModel):
    current_role: str
    networking_xp: int
    automation_xp: int
    database_xp: int


class SubmissionResponse(BaseModel):
    passed: bool
    message: str
    details: list[str]
    xp_awarded: int
    resolution_time: float
    user: UserXP


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/api/tickets", response_model=list[TicketOut])
def list_tickets(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Ticket]:
    """Return every open, learner-tier IT support scenario in the catalog.

    Requires a valid JWT (any account) but nothing else. Admin-only tickets
    are deliberately excluded here -- they only surface via
    `GET /api/admin/tickets`, which additionally requires `is_admin=True`.
    """
    return db.query(Ticket).filter(Ticket.is_admin_only.is_(False)).order_by(Ticket.id).all()


@app.post("/api/tickets/submit", response_model=SubmissionResponse)
def submit_ticket(
    payload: SubmissionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubmissionResponse:
    """Grade the calling user's resolution form and award XP on first success.

    XP is only granted the first time a given user resolves a given ticket
    (see `grade_submission` in `tickets_db.py`), so resubmitting an
    already-correct answer doesn't let a learner farm XP.
    """
    definition = TICKETS_BY_ID.get(payload.ticket_id)
    if definition is None or definition.is_admin_only:
        raise HTTPException(status_code=404, detail=f"Ticket {payload.ticket_id} not found.")

    submission = TicketSubmission(
        root_cause=payload.root_cause,
        resolution_actions=payload.resolution_actions,
        resolution_notes=payload.resolution_notes,
    )
    result, xp_awarded, resolution_time = grade_submission(db, current_user, definition, submission)

    return SubmissionResponse(
        passed=result.passed,
        message=result.message,
        details=result.details,
        xp_awarded=xp_awarded,
        resolution_time=resolution_time,
        user=UserXP(
            current_role=current_user.current_role,
            networking_xp=current_user.networking_xp,
            automation_xp=current_user.automation_xp,
            database_xp=current_user.database_xp,
        ),
    )
