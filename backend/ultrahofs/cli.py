"""Command-line interface: ``ultrahofs <command>``."""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select


def cmd_init_db(_args: argparse.Namespace) -> None:
    from .db import init_db

    init_db()
    print("database initialised")


def cmd_create_user(args: argparse.Namespace) -> None:
    from .db import init_db, session_scope
    from .models import Org, User
    from .security import hash_password

    init_db()
    pw = args.password or getpass.getpass("password: ")
    if len(pw) < 8:
        sys.exit("password must be at least 8 characters")
    with session_scope() as db:
        org = db.execute(select(Org).where(Org.name == args.org)).scalar_one_or_none()
        if org is None:
            org = Org(name=args.org)
            db.add(org)
            db.flush()
        u = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()
        if u is None:
            u = User(username=args.username, org_id=org.id, display_name=args.display_name or args.username,
                     password_hash=hash_password(pw), role=args.role, email=args.email or None)
            db.add(u)
            print(f"created {args.role} '{args.username}' in org '{args.org}'")
        else:
            u.password_hash = hash_password(pw)
            u.role = args.role
            print(f"updated '{args.username}'")


def cmd_ingest_hofsyn(args: argparse.Namespace) -> None:
    from .db import SessionLocal, init_db
    from .ingest.hofsyn import ingest_hofsyn

    init_db()
    with SessionLocal() as db:
        ingest_hofsyn(db, workers=args.workers, limit=args.limit, online=not args.offline,
                      pores=not args.no_pores)


def _score_one(item: tuple[int, str]) -> dict:
    from rdkit import Chem

    from .chem.descriptors import basic_descriptors
    from .chem.scoring import score_molecule
    from .chem.synthons import connection_count, find_synthons, synthon_summary

    mid, smi = item
    mol = Chem.MolFromSmiles(smi)
    res = score_molecule(mol, n_confs=6)
    syn = find_synthons(mol)
    return {"id": mid, "score": res, "descriptors": basic_descriptors(mol),
            "synthons": synthon_summary(syn), "n_connect": connection_count(syn)}


def cmd_score(args: argparse.Namespace) -> None:
    from .db import SessionLocal, init_db
    from .ingest.parallel import run_parallel
    from .models import Molecule
    from .services.molecules import invalidate_indices

    init_db()
    with SessionLocal() as db:
        q = select(Molecule.id, Molecule.smiles)
        if args.experimental:
            q = q.where(Molecule.is_experimental_tecton.is_(True))
        items = [(r[0], r[1]) for r in db.execute(q)]
    if not args.force:
        with SessionLocal() as db:
            have = {m.id for m in db.execute(select(Molecule)).scalars() if m.score}
        items = [it for it in items if it[0] not in have]
    print(f"scoring {len(items)} molecules")
    done = 0
    with SessionLocal() as db:
        for item, status, res in run_parallel(_score_one, items, workers=args.workers, timeout=180):
            if status != "ok":
                continue
            m = db.get(Molecule, item[0])
            sc = res["score"]
            m.score = {k: sc[k] for k in ("score", "band", "weighted_sum", "gate", "components", "flags",
                                         "n_connect", "geometry")}
            m.descriptors = res["descriptors"]
            m.synthons = res["synthons"]
            m.n_connect = res["n_connect"]
            done += 1
            if done % 50 == 0:
                db.commit()
                print(f"  {done}/{len(items)}")
        db.commit()
    invalidate_indices()
    print(f"scored {done}")


def cmd_worker(args: argparse.Namespace) -> None:
    from .jobs.worker import run_worker

    run_worker(once=args.once)


def cmd_run_job(args: argparse.Namespace) -> None:
    from .jobs.worker import run_job_inline

    run_job_inline(args.job_id)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("ultrahofs.main:app", host=args.host, port=args.port, reload=args.reload,
                log_level="info")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="ultrahofs", description="UltraHOFs platform CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db").set_defaults(func=cmd_init_db)
    u = sub.add_parser("create-user")
    u.add_argument("--username", required=True)
    u.add_argument("--password")
    u.add_argument("--role", default="member", choices=["admin", "curator", "member"])
    u.add_argument("--org", default="Ultra-X")
    u.add_argument("--email")
    u.add_argument("--display-name")
    u.set_defaults(func=cmd_create_user)
    h = sub.add_parser("ingest-hofsyn")
    h.add_argument("--workers", type=int, default=8)
    h.add_argument("--limit", type=int)
    h.add_argument("--offline", action="store_true", help="do not call Crossref")
    h.add_argument("--no-pores", action="store_true", help="skip Zeo++")
    h.set_defaults(func=cmd_ingest_hofsyn)
    s = sub.add_parser("score-molecules")
    s.add_argument("--experimental", action="store_true")
    s.add_argument("--force", action="store_true")
    s.add_argument("--workers", type=int, default=8)
    s.set_defaults(func=cmd_score)
    w = sub.add_parser("worker")
    w.add_argument("--once", action="store_true")
    w.set_defaults(func=cmd_worker)
    rj = sub.add_parser("run-job", help="execute one queued job in this process (Slurm batch scripts)")
    rj.add_argument("job_id", type=int)
    rj.set_defaults(func=cmd_run_job)
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--reload", action="store_true")
    sv.set_defaults(func=cmd_serve)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
