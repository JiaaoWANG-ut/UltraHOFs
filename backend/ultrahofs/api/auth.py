"""Authentication, user administration and projects."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import GeneratedStructure, HOFEntry, Job, Molecule, Project, ProjectItem, User
from ..security import decode_token, hash_password, make_token, verify_password
from .deps import audit, current_user, require_role, user_dict

router = APIRouter()


class LoginIn(BaseModel):
    username: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class MeUpdate(BaseModel):
    display_name: str | None = None
    locale: str | None = Field(default=None, pattern="^(zh-CN|en-US)$")
    password: str | None = Field(default=None, min_length=8)
    current_password: str | None = None


@router.post("/auth/login", tags=["auth"])
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    u = db.execute(select(User).where(User.username == body.username)).scalar_one_or_none()
    if u is None or not u.is_active or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "invalid username or password")
    u.last_login_at = datetime.now(UTC)
    db.commit()
    return {"access_token": make_token(u.id, "access"), "refresh_token": make_token(u.id, "refresh"),
            "token_type": "bearer", "user": user_dict(u)}


@router.post("/auth/demo", tags=["auth"])
def demo_login(db: Session = Depends(get_db)) -> dict:
    """Password-less login as the demo user; only available when the server runs in demo mode."""
    from ..bootstrap import DEMO_USER

    if not get_settings().demo_mode:
        raise HTTPException(404, "Not Found")
    u = db.execute(select(User).where(User.username == DEMO_USER)).scalar_one_or_none()
    if u is None or not u.is_active:
        raise HTTPException(503, "demo user is not set up; run `ultrahofs init-db`")
    u.last_login_at = datetime.now(UTC)
    db.commit()
    return {"access_token": make_token(u.id, "access"), "refresh_token": make_token(u.id, "refresh"),
            "token_type": "bearer", "user": user_dict(u)}


@router.post("/auth/refresh", tags=["auth"])
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> dict:
    uid = decode_token(body.refresh_token, "refresh")
    u = db.get(User, uid) if uid else None
    if u is None or not u.is_active:
        raise HTTPException(401, "invalid refresh token")
    return {"access_token": make_token(u.id, "access"), "token_type": "bearer"}


@router.get("/auth/me", tags=["auth"])
def me(user: User = Depends(current_user)) -> dict:
    return user_dict(user)


@router.patch("/auth/me", tags=["auth"])
def update_me(body: MeUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user.id)
    if body.display_name is not None:
        u.display_name = body.display_name[:200]
    if body.locale:
        u.locale = body.locale
    if body.password:
        if not body.current_password or not verify_password(body.current_password, u.password_hash):
            raise HTTPException(400, "current password is incorrect")
        u.password_hash = hash_password(body.password)
    db.commit()
    return user_dict(u)


# ---------------- user administration ----------------

class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=8)
    role: str = Field(default="member", pattern="^(admin|curator|member)$")
    display_name: str = ""
    email: str | None = None


class UserPatch(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|curator|member)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)
    display_name: str | None = None


@router.get("/users", tags=["users"])
def list_users(admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> list[dict]:
    return [user_dict(u) for u in db.execute(select(User).where(User.org_id == admin.org_id)).scalars()]


@router.post("/users", tags=["users"])
def create_user(body: UserIn, admin: User = Depends(require_role("admin")), db: Session = Depends(get_db)) -> dict:
    if db.execute(select(User).where(User.username == body.username)).scalar_one_or_none():
        raise HTTPException(409, "username already exists")
    u = User(username=body.username, password_hash=hash_password(body.password), role=body.role,
             display_name=body.display_name or body.username, email=body.email or None, org_id=admin.org_id)
    db.add(u)
    db.flush()
    audit(db, admin, "create", "user", u.id, {"username": u.username, "role": u.role})
    db.commit()
    return user_dict(u)


@router.patch("/users/{user_id}", tags=["users"])
def patch_user(user_id: int, body: UserPatch, admin: User = Depends(require_role("admin")),
               db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user_id)
    if u is None or u.org_id != admin.org_id:
        raise HTTPException(404, "user not found")
    changes = body.model_dump(exclude_none=True)
    if "password" in changes:
        u.password_hash = hash_password(changes.pop("password"))
        changes["password"] = "***"
    for k, v in changes.items():
        if k != "password":
            setattr(u, k, v)
    audit(db, admin, "update", "user", u.id, changes)
    db.commit()
    return user_dict(u)


# ---------------- projects ----------------

class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ItemIn(BaseModel):
    item_type: str = Field(pattern="^(molecule|structure|job|hof_entry)$")
    item_id: int
    note: str = ""


def _project(db: Session, pid: int, user: User) -> Project:
    p = db.get(Project, pid)
    if p is None or p.org_id != user.org_id:
        raise HTTPException(404, "project not found")
    return p


def _item_label(db: Session, it: ProjectItem) -> dict:
    label, extra = "", {}
    if it.item_type == "molecule":
        m = db.get(Molecule, it.item_id)
        label, extra = (m.name or m.smiles if m else "?"), ({"smiles": m.smiles} if m else {})
    elif it.item_type == "structure":
        s = db.get(GeneratedStructure, it.item_id)
        label = s.name if s else "?"
    elif it.item_type == "job":
        j = db.get(Job, it.item_id)
        label = f"{j.type} #{j.id} ({j.status})" if j else "?"
    elif it.item_type == "hof_entry":
        e = db.get(HOFEntry, it.item_id)
        label = e.name if e else "?"
    return {"id": it.id, "item_type": it.item_type, "item_id": it.item_id, "note": it.note, "label": label,
            "created_at": it.created_at, **extra}


def project_dict(db: Session, p: Project, items: bool = False) -> dict:
    d = {"id": p.id, "name": p.name, "description": p.description, "owner_id": p.owner_id,
         "created_at": p.created_at, "updated_at": p.updated_at, "n_items": len(p.items)}
    if items:
        d["items"] = [_item_label(db, it) for it in p.items]
    return d


@router.get("/projects", tags=["projects"])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    q = select(Project).where(Project.org_id == user.org_id).order_by(Project.updated_at.desc())
    return [project_dict(db, p) for p in db.execute(q).scalars()]


@router.post("/projects", tags=["projects"])
def create_project(body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    p = Project(org_id=user.org_id, owner_id=user.id, name=body.name, description=body.description)
    db.add(p)
    db.commit()
    return project_dict(db, p, items=True)


@router.get("/projects/{pid}", tags=["projects"])
def get_project(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return project_dict(db, _project(db, pid, user), items=True)


@router.patch("/projects/{pid}", tags=["projects"])
def update_project(pid: int, body: ProjectIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    p = _project(db, pid, user)
    p.name, p.description, p.updated_at = body.name, body.description, datetime.now(UTC)
    db.commit()
    return project_dict(db, p, items=True)


@router.delete("/projects/{pid}", tags=["projects"])
def delete_project(pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    p = _project(db, pid, user)
    if p.owner_id != user.id and user.role != "admin":
        raise HTTPException(403, "only the owner can delete a project")
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/projects/{pid}/items", tags=["projects"])
def add_item(pid: int, body: ItemIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    p = _project(db, pid, user)
    exists = db.execute(select(ProjectItem).where(ProjectItem.project_id == p.id,
                                                  ProjectItem.item_type == body.item_type,
                                                  ProjectItem.item_id == body.item_id)).scalar_one_or_none()
    if exists is None:
        p.items.append(ProjectItem(item_type=body.item_type, item_id=body.item_id, note=body.note))
        p.updated_at = datetime.now(UTC)
        db.commit()
    return project_dict(db, p, items=True)


@router.delete("/projects/{pid}/items/{item_id}", tags=["projects"])
def remove_item(pid: int, item_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    p = _project(db, pid, user)
    it = db.get(ProjectItem, item_id)
    if it is None or it.project_id != p.id:
        raise HTTPException(404, "item not found")
    db.delete(it)
    db.commit()
    db.refresh(p)
    return project_dict(db, p, items=True)
