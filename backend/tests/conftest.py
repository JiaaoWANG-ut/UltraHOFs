"""Test configuration: isolated var directory + database for every test session."""

from __future__ import annotations

import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="ultrahofs_test_")
os.environ["ULTRAHOFS_VAR_DIR"] = _TMP
os.environ["ULTRAHOFS_DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["ULTRAHOFS_SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TMA = "OC(=O)c1cc(C(O)=O)cc(C(O)=O)c1"
ATC = "OC(=O)C12CC3(C(O)=O)CC(C(O)=O)(C1)CC(C(O)=O)(C3)C2"
TTBI = "O=c1[nH]c2cc3c(cc2[nH]1)C1c2cc4[nH]c(=O)[nH]c4cc2C3c2cc3[nH]c(=O)[nH]c3cc21"
MTB = "OC(=O)c1ccc(C(c2ccc(C(O)=O)cc2)(c2ccc(C(O)=O)cc2)c2ccc(C(O)=O)cc2)cc1"


@pytest.fixture(scope="session")
def client() -> TestClient:
    from ultrahofs.db import init_db
    from ultrahofs.main import app

    init_db()
    with TestClient(app) as c:
        yield c


def _make_user(username: str, role: str) -> None:
    from sqlalchemy import select

    from ultrahofs.db import session_scope
    from ultrahofs.models import Org, User
    from ultrahofs.security import hash_password

    with session_scope() as db:
        org = db.execute(select(Org).where(Org.name == "Ultra-X")).scalar_one_or_none()
        if org is None:
            org = Org(name="Ultra-X")
            db.add(org)
            db.flush()
        if db.execute(select(User).where(User.username == username)).scalar_one_or_none() is None:
            db.add(User(username=username, org_id=org.id, password_hash=hash_password("password123"), role=role))


@pytest.fixture(scope="session")
def admin_headers(client: TestClient) -> dict:
    _make_user("admin", "admin")
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def member_headers(client: TestClient) -> dict:
    _make_user("member", "member")
    r = client.post("/api/v1/auth/login", json={"username": "member", "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
