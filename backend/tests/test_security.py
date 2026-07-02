from fastapi import HTTPException

from app.models import SessionToken, User
from app.security import (
    LOGIN_ATTEMPTS,
    MAX_LOGIN_ATTEMPTS,
    check_login_allowed,
    create_session,
    hash_value,
    record_login_failure,
    revoke_session,
    token_hash,
)


def test_revoke_session_deletes_server_side_token(db) -> None:
    user = User(email="admin@example.com", password_hash=hash_value("password"))
    db.add(user)
    db.commit()

    class Response:
        def set_cookie(self, key: str, value: str, **kwargs: object) -> None:
            self.cookies[key] = value

        def __init__(self) -> None:
            self.cookies = {}

    response = Response()
    create_session(db, user, response)
    session_cookie = response.cookies["stock_picker_session"]

    assert db.query(SessionToken).count() == 1

    revoke_session(db, session_cookie)

    assert db.query(SessionToken).count() == 0
    assert not db.query(SessionToken).filter_by(token_hash=token_hash(session_cookie)).first()


def test_login_throttle_blocks_after_repeated_failures() -> None:
    identifier = "admin@example.com"
    LOGIN_ATTEMPTS.clear()

    for _ in range(MAX_LOGIN_ATTEMPTS):
        check_login_allowed(identifier)
        record_login_failure(identifier)

    try:
        check_login_allowed(identifier)
    except HTTPException as exc:
        assert exc.status_code == 429
    else:
        raise AssertionError("Expected login throttle to reject repeated failures")
    finally:
        LOGIN_ATTEMPTS.clear()
