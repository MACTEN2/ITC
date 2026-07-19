"""Authentication: registration, login, and JWT verification.

Security model, at a glance:

    - Passwords are never stored or compared as plaintext. `hash_password()`
      runs them through bcrypt (via passlib), which salts automatically per
      call -- two users with the same password get two different hashes, and
      the salt travels inside the hash string itself so `verify_password()`
      doesn't need it passed separately.
    - Successful login issues a JWT access token (`create_access_token`)
      signed with HS256 and a server-side secret. The token's payload (who
      you are, when it expires) is base64-encoded, *not* encrypted -- anyone
      can read it -- but nobody without the secret key can produce a
      signature the server will accept, so a verified token's claims can be
      trusted.
    - `get_current_user` is the dependency every protected route uses: it
      pulls the `Authorization: Bearer <token>` header (via `oauth2_scheme`),
      verifies the signature and expiry, and loads the corresponding `User`
      row. Any failure -- bad signature, expired token, deleted user -- comes
      back as the same generic 401 so a caller can't distinguish "wrong
      token" from "right token, user since deleted".
"""

import logging
import os
import re
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LoginEvent, Notification, NotificationPreference, User, UserBadge, UserTicketProgress

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWT configuration
# ---------------------------------------------------------------------------

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

_DEV_ONLY_SECRET_KEY = "itc-dev-only-insecure-secret-do-not-use-in-production-3f9a1c7e"
JWT_SECRET_KEY = os.environ.get("ITC_JWT_SECRET_KEY", _DEV_ONLY_SECRET_KEY)
if JWT_SECRET_KEY == _DEV_ONLY_SECRET_KEY:
    logger.warning(
        "ITC_JWT_SECRET_KEY is not set -- using an insecure, publicly-known "
        "development default. Set the ITC_JWT_SECRET_KEY environment variable "
        "to a long random value before deploying this anywhere but a local machine."
    )

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash `password` with bcrypt. Bcrypt salts automatically per call, so
    hashing the same password twice yields two different hashes -- this is
    what defeats rainbow-table attacks. The salt is embedded in the returned
    hash string, so no separate salt storage is needed.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check `plain_password` against a stored bcrypt hash in constant time."""
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT issuing and verification
# ---------------------------------------------------------------------------


def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """Issue a signed JWT whose payload identifies `user_id` and an expiry.

    HS256 is symmetric signing: the same `JWT_SECRET_KEY` both signs and
    verifies, so only this server can mint tokens it will later accept.
    """
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": str(user_id), "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def _decode_access_token(token: str) -> int:
    """Decode and validate a bearer token, returning the embedded user id.

    Any failure -- bad signature, malformed token, or expiry -- collapses
    into the same generic 401 so a caller can't fingerprint which specific
    check failed.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        raise credentials_exception from None

    subject = payload.get("sub")
    if subject is None:
        raise credentials_exception
    try:
        return int(subject)
    except ValueError:
        raise credentials_exception from None


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """FastAPI dependency: decode the bearer token and load the matching User.

    Adding `current_user: User = Depends(get_current_user)` to any route
    signature makes that route require a valid `Authorization: Bearer <token>`
    header -- `oauth2_scheme` extracts it, this function verifies it and
    resolves it to a real account.
    """
    user_id = _decode_access_token(token)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

# Deliberately not using Pydantic's EmailStr here -- it requires the
# `email-validator` package, an extra dependency not in requirements.txt.
# This regex is a pragmatic format check, not full RFC 5322 validation.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, description="Unique login handle.")
    email: str = Field(min_length=5, max_length=255, description="Contact email; must be unique.")
    # Bcrypt silently truncates input beyond 72 bytes, so longer passwords are rejected
    # up front rather than accepted and then quietly weakened.
    password: str = Field(min_length=8, max_length=72, description="Plaintext password (min 8 characters).")

    @field_validator("email")
    @classmethod
    def _validate_email_format(cls, value: str) -> str:
        if not _EMAIL_PATTERN.match(value):
            raise ValueError("Not a valid email address.")
        return value.lower()

    @field_validator("username")
    @classmethod
    def _normalize_username(cls, value: str) -> str:
        return value.strip()


class UserPublic(BaseModel):
    """Everything about a User that's safe to hand back over the API -- never
    includes `hashed_password`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    current_role: str
    is_admin: bool
    networking_xp: int
    automation_xp: int
    database_xp: int
    infra_points: int
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class AccountDeleteRequest(BaseModel):
    current_password: str = Field(description="Required to confirm permanent account deletion.")


class ProfileUpdateRequest(BaseModel):
    """Fields a user may self-edit. Username is deliberately not included --
    it stays immutable to avoid churn (and because other rows don't
    reference it as a stable foreign key)."""

    email: str | None = Field(default=None, min_length=5, max_length=255)
    current_password: str | None = Field(default=None, description="Required when setting new_password.")
    new_password: str | None = Field(default=None, min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def _validate_email_format(cls, value: str | None) -> str | None:
        if value is not None and not _EMAIL_PATTERN.match(value):
            raise ValueError("Not a valid email address.")
        return value.lower() if value else value


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> User:
    """Create a new account with 0 starting XP/points across every track."""
    existing = (
        db.query(User)
        .filter(or_(User.username == payload.username, User.email == payload.email))
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with that username or email already exists.",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        # current_role/is_admin/*_xp/infra_points all take their column defaults (0 / False).
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> TokenResponse:
    """Validate credentials and issue a JWT access token.

    Accepts OAuth2 password-flow form fields (`username`, `password`) rather
    than JSON -- this is what lets Swagger UI's built-in "Authorize" button
    log in directly against this endpoint.
    """
    user = db.query(User).filter(User.username == form_data.username).first()

    # Deliberately identical error for "no such user" and "wrong password" --
    # distinguishing them would let an attacker enumerate valid usernames.
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    db.add(
        LoginEvent(
            user_id=user.id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    )
    db.commit()

    access_token = create_access_token(user_id=user.id)
    return TokenResponse(access_token=access_token)


@router.get("/login-activity", response_model=list[LoginEventOut])
def get_login_activity(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LoginEvent]:
    """The caller's own recent sign-ins, most recent first."""
    return (
        db.query(LoginEvent)
        .filter(LoginEvent.user_id == current_user.id)
        .order_by(LoginEvent.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/me", response_model=UserPublic)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated caller's own profile.

    A login response only ever returns a bearer token, not the account it
    belongs to -- clients (e.g. the frontend's admin-gate check) need this
    endpoint to resolve "who am I, and am I an admin" from that token.
    """
    return current_user


@router.patch("/me", response_model=UserPublic)
def update_current_user(
    payload: ProfileUpdateRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> User:
    """Self-service profile edit: email and/or password change.

    Changing the password requires the correct `current_password` -- knowing
    a valid session token isn't sufficient on its own, the same way most
    real account-settings pages re-prompt for the current password.
    """
    if payload.email is None and payload.new_password is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update were provided.")

    if payload.email is not None and payload.email != current_user.email:
        existing = db.query(User).filter(User.email == payload.email, User.id != current_user.id).first()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That email is already in use.")
        current_user.email = payload.email

    if payload.new_password is not None:
        if not payload.current_password or not verify_password(payload.current_password, current_user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
        current_user.hashed_password = hash_password(payload.new_password)

    db.commit()
    db.refresh(current_user)
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_user(
    payload: AccountDeleteRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    """Permanently delete the caller's own account and every row referencing it.

    Requires the current password, same re-confirmation pattern as changing it.
    `UserTicketProgress` already cascades via its `User.progress` relationship,
    but `UserBadge`/`Notification`/`NotificationPreference`/`LoginEvent` do not
    have a `relationship()`/cascade defined on `User` at all, and this SQLite
    database has no `PRAGMA foreign_keys=ON` to catch a missed one -- it would
    just silently leave orphaned rows. Bulk-delete every child table explicitly
    (including the one that *would* cascade anyway) so the full set is visible
    in one place and isn't split between "manual" and "trust the ORM".
    """
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")

    user_id = current_user.id
    db.query(UserTicketProgress).filter(UserTicketProgress.user_id == user_id).delete()
    db.query(UserBadge).filter(UserBadge.user_id == user_id).delete()
    db.query(Notification).filter(Notification.user_id == user_id).delete()
    db.query(NotificationPreference).filter(NotificationPreference.user_id == user_id).delete()
    db.query(LoginEvent).filter(LoginEvent.user_id == user_id).delete()
    db.delete(current_user)
    db.commit()
