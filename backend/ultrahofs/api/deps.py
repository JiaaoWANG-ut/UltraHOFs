"""Shared API dependencies: DB session, current user, role checks, audit."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog, User
from ..security import decode_token

bearer = HTTPBearer(auto_error=False)


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    if cred is None or cred.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    uid = decode_token(cred.credentials, "access")
    user = db.get(User, uid) if uid else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    return user


def require_role(*roles: str) -> Callable[[User], User]:
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient permissions")
        return user

    return dep


def audit(db: Session, user: User | None, action: str, entity_type: str, entity_id: int | None,
          diff: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, action=action, entity_type=entity_type,
                    entity_id=entity_id, diff=diff or {}))


def user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "email": u.email, "display_name": u.display_name,
            "role": u.role, "locale": u.locale, "org_id": u.org_id, "is_active": u.is_active,
            "org": u.org.name if u.org else None}
