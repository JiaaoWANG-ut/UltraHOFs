"""Password hashing and JWT tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from .config import get_settings

_ph = PasswordHasher()
ALGO = "HS256"


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def make_token(user_id: int, kind: str = "access") -> str:
    s = get_settings()
    now = datetime.now(UTC)
    exp = now + (timedelta(minutes=s.access_token_minutes) if kind == "access"
                 else timedelta(days=s.refresh_token_days))
    payload = {"sub": str(user_id), "type": kind, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, s.resolved_secret_key(), algorithm=ALGO)


def decode_token(token: str, kind: str = "access") -> int | None:
    try:
        data = jwt.decode(token, get_settings().resolved_secret_key(), algorithms=[ALGO])
    except jwt.PyJWTError:
        return None
    if data.get("type") != kind:
        return None
    try:
        return int(data["sub"])
    except (KeyError, ValueError):
        return None
