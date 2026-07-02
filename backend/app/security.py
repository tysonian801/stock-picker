from datetime import UTC, datetime, timedelta
from hashlib import pbkdf2_hmac, sha256
from hmac import compare_digest
from secrets import token_urlsafe

from fastapi import Cookie, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import SessionToken, User

SESSION_COOKIE = "stock_picker_session"
CSRF_COOKIE = "stock_picker_csrf"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_ATTEMPTS: dict[str, list[datetime]] = {}


def hash_value(value: str, salt: str | None = None) -> str:
    salt = salt or token_urlsafe(16)
    digest = pbkdf2_hmac("sha256", value.encode(), salt.encode(), 200_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_value(value: str, stored_hash: str) -> bool:
    algorithm, salt, expected = stored_hash.split("$", maxsplit=2)
    if algorithm != "pbkdf2_sha256":
        return False
    actual = pbkdf2_hmac("sha256", value.encode(), salt.encode(), 200_000).hex()
    return compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def ensure_admin_user(db: Session) -> None:
    settings = get_settings()
    admin_email = normalize_login_identifier(settings.admin_email)
    existing = db.scalar(select(User).where(User.email == admin_email))
    if existing:
        return
    db.add(
        User(
            email=admin_email,
            password_hash=hash_value(settings.admin_password.get_secret_value()),
        )
    )
    db.commit()


def normalize_login_identifier(email: str) -> str:
    return email.strip().lower()


def check_login_allowed(identifier: str) -> None:
    now = datetime.now(UTC)
    attempts = [
        attempt
        for attempt in LOGIN_ATTEMPTS.get(identifier, [])
        if now - attempt < LOGIN_WINDOW
    ]
    LOGIN_ATTEMPTS[identifier] = attempts
    if len(attempts) >= MAX_LOGIN_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts",
        )


def record_login_failure(identifier: str) -> None:
    LOGIN_ATTEMPTS.setdefault(identifier, []).append(datetime.now(UTC))


def clear_login_failures(identifier: str) -> None:
    LOGIN_ATTEMPTS.pop(identifier, None)


def create_session(db: Session, user: User, response: Response) -> str:
    session_token = token_urlsafe(32)
    csrf_token = token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=7)
    db.add(
        SessionToken(
            user_id=user.id,
            token_hash=token_hash(session_token),
            csrf_token_hash=token_hash(csrf_token),
            expires_at=expires_at,
        )
    )
    db.commit()
    secure_cookie = get_settings().app_env == "production"
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=secure_cookie,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
    )
    return csrf_token


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(CSRF_COOKIE)


def revoke_session(db: Session, session_cookie: str | None) -> None:
    if not session_cookie:
        return
    session = db.scalar(
        select(SessionToken).where(SessionToken.token_hash == token_hash(session_cookie))
    )
    if not session:
        return
    db.delete(session)
    db.commit()


def require_user(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    session = db.scalar(
        select(SessionToken).where(SessionToken.token_hash == token_hash(session_cookie))
    )
    if not session or as_utc(session.expires_at) <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session invalid")
    return user


def require_csrf(
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    csrf_cookie: str | None = Cookie(default=None, alias=CSRF_COOKIE),
    db: Session = Depends(get_db),
) -> None:
    if not session_cookie or not csrf_cookie or not x_csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token required")
    if not compare_digest(csrf_cookie, x_csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token mismatch")
    session = db.scalar(
        select(SessionToken).where(SessionToken.token_hash == token_hash(session_cookie))
    )
    if not session or not compare_digest(session.csrf_token_hash, token_hash(x_csrf_token)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token invalid")
