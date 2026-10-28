"""First-run setup and portable data bundles ("seeds").

* ``bootstrap()`` — run once before the API/worker start: copies the bundled data into an empty
  installation, creates the tables and the first administrator (plus the ``demo`` user in demo mode).
* ``export_seed()`` — writes the experimental HOF database (no accounts, jobs or user structures) and its
  CIF files into a directory that ``ULTRAHOFS_SEED_DIR`` can point to.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from . import __version__
from .config import get_settings

SEED_DB = "ultrahofs.db"
SEED_MANIFEST = "manifest.json"
DEMO_USER = "demo"
DEFAULT_ORG = "Ultra-X"

Log = Callable[[str], None]


def sqlite_file() -> Path | None:
    url = make_url(get_settings().resolved_database_url())
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    return Path(url.database)


def _is_empty_installation(db_file: Path) -> bool:
    if not db_file.exists() or db_file.stat().st_size == 0:
        return True
    con = sqlite3.connect(db_file)
    try:
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        n_entries = con.execute("select count(*) from hof_entries").fetchone()[0] if "hof_entries" in tables else 0
        n_users = con.execute("select count(*) from users").fetchone()[0] if "users" in tables else 0
        return n_entries == 0 and n_users == 0
    finally:
        con.close()


def load_seed(seed_dir: Path | None = None, log: Log = print) -> bool:
    """Copy a seed into this installation if (and only if) it has no data and no users yet."""
    s = get_settings()
    seed = seed_dir or s.seed_dir
    if not seed:
        return False
    seed_dir = Path(seed)
    if not (seed_dir / SEED_DB).exists():
        log(f"seed: {seed_dir / SEED_DB} not found; starting without bundled data")
        return False
    db_file = sqlite_file()
    if db_file is None:
        log("seed: only SQLite installations can be seeded automatically; skipped")
        return False
    if not _is_empty_installation(db_file):
        return False
    from . import db as dbmod

    if dbmod._engine is not None:
        dbmod._engine.dispose()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("-wal", "-shm", "-journal"):
        Path(f"{db_file}{suffix}").unlink(missing_ok=True)
    tmp = db_file.with_suffix(".seed-tmp")
    shutil.copyfile(seed_dir / SEED_DB, tmp)
    os.replace(tmp, db_file)
    for sub in sorted(p for p in seed_dir.iterdir() if p.is_dir()):
        shutil.copytree(sub, s.var_dir / sub.name, dirs_exist_ok=True)
    manifest = seed_dir / SEED_MANIFEST
    info = json.loads(manifest.read_text()) if manifest.exists() else {}
    log(f"seed: loaded {info.get('entries', '?')} HOF entries from {seed_dir}")
    return True


def ensure_users(log: Log = print) -> dict:
    """Create the first administrator in an installation without users, and the demo user in demo mode."""
    from .db import session_scope
    from .models import Org, User
    from .security import hash_password

    s = get_settings()
    out: dict = {}
    with session_scope() as db:
        org = db.execute(select(Org).order_by(Org.id)).scalars().first()
        if org is None:
            org = Org(name=DEFAULT_ORG)
            db.add(org)
            db.flush()
        if db.execute(select(func.count(User.id))).scalar_one() == 0:
            pw = s.admin_password or secrets.token_urlsafe(12)
            db.add(User(username="admin", org_id=org.id, display_name="Administrator", role="admin",
                        password_hash=hash_password(pw)))
            out["admin_created"] = True
            if s.admin_password:
                log("created administrator 'admin' (password from ULTRAHOFS_ADMIN_PASSWORD)")
            else:
                f = s.var_dir / "initial_admin_password.txt"
                f.write_text(pw + "\n")
                f.chmod(0o600)
                bar = "=" * 64
                log(f"{bar}\n UltraHOFs administrator account created\n   username: admin\n   password: {pw}\n"
                    f"   (also saved to {f}; change it after the first login)\n{bar}")
        if s.demo_mode and db.execute(select(User).where(User.username == DEMO_USER)).scalar_one_or_none() is None:
            db.add(User(username=DEMO_USER, org_id=org.id, display_name="Demo", role="admin",
                        password_hash=hash_password(secrets.token_urlsafe(32))))
            out["demo_created"] = True
    if s.demo_mode:
        log("DEMO MODE: password-less demo login is enabled; never expose this server publicly")
    return out


def bootstrap(log: Log = print) -> dict:
    loaded = load_seed(log=log)
    from .db import init_db

    init_db()
    return {"seed_loaded": loaded, **ensure_users(log=log)}


# ---------------------------------------------------------------- seed export

# embedded reflection/refinement files (hkl, fab, res, …) are large and not needed for structure display
_DIFFRACTION_TAG = re.compile(
    r"^_(?:shelxl?_(?:res|hkl|fab|fcf|ins)_(?:file|checksum)|iucr_refine_(?:instructions|reflections|fcf)_details)"
    r"(?=\s|$)", re.IGNORECASE)


def strip_diffraction_data(text: str) -> str:
    """Remove embedded SHELX reflection/result files from a CIF, leaving everything else unchanged."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        m = _DIFFRACTION_TAG.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        has_value = bool(lines[i][m.end():].strip())
        i += 1
        if not has_value and i < len(lines):
            if lines[i].startswith(";"):  # semicolon-delimited text field
                i += 1
                while i < len(lines) and not lines[i].startswith(";"):
                    i += 1
                i += 1
            elif lines[i].strip() and not lines[i].lstrip().startswith(("_", "loop_", "data_", "#")):
                i += 1
    return "".join(out)


def export_seed(out_dir: Path, *, strip: bool = True, log: Log = print) -> dict:
    """Write the experimental database (without accounts, jobs or user data) and its CIFs to ``out_dir``."""
    from fastapi import HTTPException

    from .api.hofs import _display_cif, display_cache_path
    from .db import SessionLocal
    from .models import HOFEntry

    s = get_settings()
    src = sqlite_file()
    if src is None or not src.exists():
        raise RuntimeError("export-seed needs a SQLite installation")
    out_dir = Path(out_dir)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(f"{out_dir} is not empty")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) display CIFs for entries without a guest-free framework, so the bundle never needs the raw dataset
    display_failed = []
    with SessionLocal() as db:
        for e in db.execute(select(HOFEntry).where(HOFEntry.cif_clean_path == "")).scalars():
            try:
                _display_cif(e)
            except HTTPException:
                display_failed.append(e.id)

    # 2) consistent copy of the database
    dst_db = out_dir / SEED_DB
    with sqlite3.connect(src) as a, sqlite3.connect(dst_db) as b:
        a.backup(b)

    con = sqlite3.connect(dst_db)
    con.execute("PRAGMA foreign_keys=OFF")
    for t in ("project_items", "projects", "jobs", "generated_structures", "audit_log"):
        con.execute(f"DELETE FROM {t}")
    con.execute("UPDATE hof_entries SET created_by = NULL")
    con.execute("DELETE FROM users")
    con.execute("DELETE FROM molecules WHERE is_experimental_tecton = 0 AND id NOT IN "
                "(SELECT molecule_id FROM components)")

    # 3) CIF files with portable relative paths
    stats = {"raw": 0, "framework": 0, "display": 0, "bytes_before": 0, "bytes_after": 0, "missing": 0}
    for sub in ("raw", "framework", "display"):
        (out_dir / "cif" / sub).mkdir(parents=True, exist_ok=True)

    def copy(path_value: str, sub: str, entry_id: int) -> str:
        p = s.var_path(path_value)
        if p is None or not p.exists():
            stats["missing"] += 1
            return ""
        text = p.read_bytes().decode("latin-1")  # byte-exact round trip for any encoding
        stats["bytes_before"] += len(text)
        if strip and sub == "raw":
            text = strip_diffraction_data(text)
        stats["bytes_after"] += len(text)
        rel = f"cif/{sub}/{entry_id}.cif"
        (out_dir / rel).write_bytes(text.encode("latin-1"))
        stats[sub] += 1
        return rel

    rows = con.execute("SELECT id, cif_raw_path, cif_clean_path FROM hof_entries").fetchall()
    for eid, raw, clean in rows:
        new_raw = copy(raw, "raw", eid) if raw else ""
        new_clean = copy(clean, "framework", eid) if clean else ""
        con.execute("UPDATE hof_entries SET cif_raw_path = ?, cif_clean_path = ? WHERE id = ?",
                    (new_raw, new_clean, eid))
        cache = display_cache_path(eid)
        if not clean and cache.exists():
            shutil.copyfile(cache, out_dir / "cif" / "display" / f"{eid}.cif")
            stats["display"] += 1
    con.commit()
    counts = {
        "entries": con.execute("SELECT count(*) FROM hof_entries").fetchone()[0],
        "references": con.execute('SELECT count(*) FROM "references"').fetchone()[0],
        "molecules": con.execute("SELECT count(*) FROM molecules").fetchone()[0],
        "experimental_tectons": con.execute(
            "SELECT count(*) FROM molecules WHERE is_experimental_tecton = 1").fetchone()[0],
    }
    sources = [dict(zip(("name", "version", "url", "license", "attribution"), r, strict=True)) for r in con.execute(
        "SELECT name, version, url, license, attribution FROM data_sources")]
    con.close()
    con = sqlite3.connect(dst_db)
    con.execute("VACUUM")
    con.close()

    manifest = {
        "format": 1, "app_version": __version__, "created": datetime.now(UTC).isoformat(timespec="seconds"),
        **counts, "cif_files": {k: stats[k] for k in ("raw", "framework", "display")},
        "diffraction_data_removed": strip, "display_failed": display_failed, "sources": sources,
        "license": "CC BY 4.0 (database and structures derived from HOFSyn)",
    }
    (out_dir / SEED_MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    (out_dir / "ATTRIBUTION.md").write_text(_attribution(manifest))
    log(f"seed: {counts['entries']} entries, {stats['raw']} raw / {stats['framework']} framework / "
        f"{stats['display']} display CIFs; raw+framework text {stats['bytes_before'] / 1e6:.0f} MB → "
        f"{stats['bytes_after'] / 1e6:.0f} MB; {stats['missing']} missing files")
    return manifest


def _attribution(m: dict) -> str:
    src = "\n".join(f"- {x['attribution'] or x['name']} ({x['license']}, {x['url']})" for x in m["sources"])
    return f"""# UltraHOFs experimental HOF database — data bundle v{m['app_version']}

{m['entries']} experimental HOF entries, {m['references']} references and {m['molecules']} molecules
({m['experimental_tectons']} experimental tectons).

## Sources

{src}

Bibliographic metadata were completed with Crossref (CC0). Crystal structures originate from the depositions
cited in each entry (CCDC numbers); please cite the original publications when you use them.

## Changes made by UltraHOFs

- CIFs re-parsed (major disorder component kept); molecules, roles (tecton / co-tecton / counter-ion /
  solvent) and SMILES assigned automatically; entries with problems are flagged `needs_review`.
- Guest-free framework CIFs and P1 display CIFs were generated; pore metrics computed with Zeo++.
- Embedded SHELX reflection and result files (`_shelx_hkl_file`, `_shelx_fab_file`, `_shelx_res_file`, …)
  were removed from the raw CIFs to reduce the download size; all structural data are unchanged.
- Explainable HOF-likeness scores and synthon annotations were added.

## Licence

This data bundle is distributed under the Creative Commons Attribution 4.0 International licence
(CC BY 4.0, https://creativecommons.org/licenses/by/4.0/), the licence of its main source.
"""
