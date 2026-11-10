"""Console sign-in: accounts, passwords and sessions.

- Passwords are hashed with scrypt (Python standard library, memory-hard): a leaked database
  does not reveal them.
- Signing in returns a random token; the browser sends it as ``Authorization: Bearer <token>``.
  Only its SHA-256 is stored, so the database cannot be used to sign in either. Tokens expire
  after ``SESSION_HOURS`` and are revoked on sign-out.
- Roles: ``agent`` handles tickets; ``admin`` also manages the team.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, col, delete, func, select

from complaintlens.schemas import as_utc, utcnow
from complaintlens.settings import get_settings
from complaintlens.store import LoginSession, User, new_session

log = logging.getLogger(__name__)
USERNAME = re.compile(r"^[a-z0-9._-]{3,32}$")
MIN_PASSWORD = 8
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    params = "$".join(str(_SCRYPT[k]) for k in ("n", "r", "p"))
    encoded = "$".join(base64.b64encode(b).decode() for b in (salt, digest))
    return f"scrypt${params}${encoded}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, n, r, p, salt, digest = stored.split("$")
        expected = base64.b64decode(digest)
        given = hashlib.scrypt(
            password.encode(),
            salt=base64.b64decode(salt),
            dklen=len(expected),
            n=int(n),
            r=int(r),
            p=int(p),
        )
    except ValueError:
        return False
    return hmac.compare_digest(given, expected)


# Checked when the username does not exist, so a wrong username takes as long as a wrong password.
_DUMMY_HASH = hash_password(secrets.token_hex(8))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(user: User) -> dict[str, object]:
    return {"id": user.id, "username": user.username, "name": user.name, "role": user.role}


def authenticate(session: Session, username: str, password: str) -> User | None:
    user = session.exec(select(User).where(User.username == username.strip().lower())).first()
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    return user if verify_password(password, user.password_hash) else None


def start_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    now = utcnow()
    session.exec(delete(LoginSession).where(col(LoginSession.expires_at) < now))
    session.add(
        LoginSession(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=now + timedelta(hours=get_settings().session_hours),
        )
    )
    session.commit()
    return token


def end_session(session: Session, token: str) -> None:
    session.exec(delete(LoginSession).where(LoginSession.token_hash == _token_hash(token)))
    session.commit()


def user_for_token(token: str | None) -> User | None:
    if not token:
        return None
    with new_session() as s:
        login = s.get(LoginSession, _token_hash(token))
        if login is None or as_utc(login.expires_at) < utcnow():
            return None
        return s.get(User, login.user_id)


def bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return auth.removeprefix("Bearer ").strip() or None


def current_user(request: Request) -> User:
    user = user_for_token(bearer(request))
    if user is None:
        raise HTTPException(401, "sign in required")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role != "admin":
        raise HTTPException(403, "administrators only")
    return user


Admin = Annotated[User, Depends(require_admin)]


def check_new_account(username: str, password: str) -> str:
    username = username.strip().lower()
    if not USERNAME.match(username):
        raise HTTPException(422, "username: 3 to 32 lowercase letters, digits, '.', '_' or '-'")
    check_password(password)
    return username


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise HTTPException(422, f"password: at least {MIN_PASSWORD} characters")


def set_password(session: Session, user: User, password: str) -> None:
    """Change the password and sign the user out everywhere else."""
    user.password_hash = hash_password(password)
    session.add(user)
    session.exec(delete(LoginSession).where(LoginSession.user_id == user.id))
    session.commit()


def ensure_admin() -> None:
    """Create the first administrator if the database has no account yet."""
    settings = get_settings()
    with new_session() as s:
        if s.exec(select(func.count()).select_from(User)).one():
            return
        password = settings.admin_password or "admin"
        if not settings.admin_password:
            log.warning("No ADMIN_PASSWORD set: the console account is admin / admin (local only)")
        s.add(
            User(
                username=settings.admin_username.strip().lower(),
                name="Administrator",
                role="admin",
                password_hash=hash_password(password),
            )
        )
        s.commit()
