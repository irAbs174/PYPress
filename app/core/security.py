import secrets
from typing import Final

from fastapi import HTTPException, Request, status
from pwdlib import PasswordHash


password_hash: Final[PasswordHash] = PasswordHash.recommended()
CSRF_SESSION_KEY: Final[str] = "csrf_token"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def ensure_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if token is None:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf(request: Request, submitted_token: str | None) -> None:
    expected_token = ensure_csrf_token(request)
    if not submitted_token or not secrets.compare_digest(expected_token, submitted_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token.",
        )
