"""Topologies, periodic structure building, export, analysis, relaxation and jobs."""

from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
from ase.io import read as ase_read
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..chem.standardize import MoleculeInputError
from ..config import get_settings
from ..crystal.assemble import AssemblyError, recommend_binodal_for_bb, recommend_for_bb
from ..crystal.bb import BuildingBlockError
from ..crystal.export import FORMATS, export
from ..crystal.nets import bipartite_version, get_net, list_nets
from ..db import get_db
from ..jobs.queue import enqueue, job_dict
from ..models import GeneratedStructure, Job, User
from ..relax.engine import engines
from ..services.structures import (
    BuildSpec,
    analyze_porosity,
    build,
    cached_bb,
    save_structure,
    structure_dict,
)
from .deps import current_user

router = APIRouter()


# ---------------- topologies ----------------

@router.get("/topologies", tags=["topologies"])
def topologies(dim: int | None = None, cn: int | None = None, precedent: bool | None = None,
               q: str = "", limit: int = Query(200, le=3000), user: User = Depends(current_user)) -> dict:
    nets = list_nets()
    if dim:
        nets = [n for n in nets if n["dim"] == dim]
    if cn:
        nets = [n for n in nets if any(t["cn"] == cn for t in n["node_types"])]
    if precedent is not None:
        nets = [n for n in nets if n["precedent"] == precedent]
    if q:
        nets = [n for n in nets if q.lower() in n["name"].lower()]
    nets.sort(key=lambda n: (not n["precedent"], n["n_nodes"], n["name"]))
    return {"total": len(nets), "items": nets[:limit]}


@router.get("/topologies/{name}", tags=["topologies"])
def topology_detail(name: str, user: User = Depends(current_user)) -> dict:
    try:
        net = get_net(name)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    rng = range(0, 2) if net.dim == 3 else range(-1, 2)
    zr = range(0, 2) if net.dim == 3 else range(0, 1)
    nodes, edges = [], []
    cell = net.cell
    for t in itertools.product(rng, rng, zr):
        for i in range(net.n_nodes):
            nodes.append({"pos": ((net.frac[i] + t) @ cell).round(4).tolist(), "type": int(net.types[i])})
        for a, b, s in net.edges:
            p1 = (net.frac[a] + t) @ cell
            p2 = (net.frac[b] + np.asarray(s) + t) @ cell
            edges.append([p1.round(4).tolist(), p2.round(4).tolist()])
    d = net.summary()
    d.update({"cell": cell.round(5).tolist(), "nodes": nodes, "edges": edges,
              "bipartite": bipartite_version(net) is not None})
    return d


class SuggestIn(BaseModel):
    smiles: str = Field(min_length=1, max_length=5000)
    partner_smiles: str = ""
    top: int = Field(default=10, ge=1, le=40)


@router.post("/topologies/suggest", tags=["topologies"])
def suggest(body: SuggestIn, user: User = Depends(current_user)) -> dict:
    try:
        a = cached_bb(body.smiles, False)
        if body.partner_smiles:
            b = cached_bb(body.partner_smiles, False)
            if b.k == 2 and a.k > 2:
                return {"mode": "single+edge", "building_blocks": [a.summary(), b.summary()],
                        "nets": recommend_for_bb(a, top=body.top, edge_bb=b)}
            if a.k == 2 and b.k > 2:
                return {"mode": "single+edge", "building_blocks": [b.summary(), a.summary()],
                        "nets": recommend_for_bb(b, top=body.top, edge_bb=a), "swap": True}
            return {"mode": "bipartite" if a.k == b.k else "binodal",
                    "building_blocks": [a.summary(), b.summary()],
                    "nets": recommend_binodal_for_bb(a, b, top=body.top)}
        return {"mode": "single", "building_blocks": [a.summary()], "nets": recommend_for_bb(a, top=body.top)}
    except (BuildingBlockError, MoleculeInputError) as e:
        raise HTTPException(422, str(e)) from e


# ---------------- structures ----------------

class BuildIn(BaseModel):
    net: str
    mode: str = Field(default="single", pattern="^(single|bipartite|binodal)$")
    node: str = ""
    node_a: str = ""
    node_b: str = ""
    edge: str = ""
    stacking: str = Field(default="AA", pattern="^(AA|AB|ABC)$")
    interlayer: float | None = Field(default=None, ge=2.8, le=12.0)
    slip: tuple[float, float] = (0.0, 0.0)
    interpenetration: int = Field(default=1, ge=1, le=6)
    align_synthons: bool = True
    name: str = Field(default="", max_length=200)
    analyze: bool = True
    project_id: int | None = None


def _components(body: BuildIn) -> list[dict]:
    comps = []
    for role, smi in (("node", body.node), ("node_a", body.node_a), ("node_b", body.node_b), ("edge", body.edge)):
        if smi:
            comps.append({"role": role, "smiles": smi})
    return comps


@router.post("/structures/build", tags=["structures"])
def build_structure(body: BuildIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    spec = BuildSpec(net=body.net, mode=body.mode, node=body.node, node_a=body.node_a, node_b=body.node_b,
                     edge=body.edge, stacking=body.stacking, interlayer=body.interlayer, slip=tuple(body.slip),
                     interpenetration=body.interpenetration, align_synthons=body.align_synthons)
    try:
        res = build(spec)
    except KeyError as e:
        raise HTTPException(404, f"unknown net: {e}") from e
    except (AssemblyError, BuildingBlockError, MoleculeInputError) as e:
        raise HTTPException(422, str(e)) from e
    atoms = res["atoms"]
    analysis = {"qc": res["qc"], "build_info": res["info"], "building_blocks": res["building_blocks"]}
    if body.analyze and len(atoms) <= 4000:
        try:
            analysis["pore"] = analyze_porosity(atoms)
        except Exception as e:  # noqa: BLE001
            analysis["pore_error"] = str(e)[:200]
    name = body.name or f"{body.net}-{body.mode}"
    st = save_structure(db, owner_id=user.id, org_id=user.org_id, name=name, atoms=atoms,
                        components=_components(body), topology=body.net, dimensionality=res["dim"],
                        options=body.model_dump(exclude={"name", "analyze", "project_id"}), qc=res["qc"],
                        analysis=analysis)
    if body.project_id:
        from ..models import Project, ProjectItem

        p = db.get(Project, body.project_id)
        if p is not None and p.org_id == user.org_id:
            p.items.append(ProjectItem(item_type="structure", item_id=st.id))
    db.commit()
    return structure_dict(st, with_cif=True)


def _own(db: Session, sid: int, user: User) -> GeneratedStructure:
    st = db.get(GeneratedStructure, sid)
    if st is None or st.org_id != user.org_id:
        raise HTTPException(404, "structure not found")
    return st


@router.get("/structures", tags=["structures"])
def list_structures(mine: bool = True, page: int = 1, size: int = Query(30, le=200),
                    user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    stmt = select(GeneratedStructure).where(GeneratedStructure.org_id == user.org_id)
    if mine:
        stmt = stmt.where(GeneratedStructure.owner_id == user.id)
    rows = list(db.execute(stmt.order_by(GeneratedStructure.id.desc())).scalars())
    return {"total": len(rows), "items": [structure_dict(s) for s in rows[(page - 1) * size: page * size]]}


@router.get("/structures/{sid}", tags=["structures"])
def get_structure(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return structure_dict(_own(db, sid, user), with_cif=True)


@router.delete("/structures/{sid}", tags=["structures"])
def delete_structure(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    st = _own(db, sid, user)
    if st.owner_id != user.id and user.role != "admin":
        raise HTTPException(403, "only the owner can delete")
    for child in db.execute(select(GeneratedStructure).where(GeneratedStructure.parent_id == st.id)).scalars():
        child.parent_id = None
    s = get_settings()
    if st.cif_path:
        s.var_path(st.cif_path).unlink(missing_ok=True)
    traj = s.var_path((st.relax or {}).get("trajectory_path"))
    if traj is not None:
        traj.unlink(missing_ok=True)
    db.delete(st)
    db.commit()
    return {"ok": True}


@router.get("/structures/{sid}/export", tags=["structures"])
def export_structure(sid: int, format: str = Query("cif"), user: User = Depends(current_user),
                     db: Session = Depends(get_db)) -> Response:
    if format not in FORMATS:
        raise HTTPException(422, f"format must be one of {list(FORMATS)}")
    st = _own(db, sid, user)
    atoms = ase_read(get_settings().var_path(st.cif_path), format="cif")
    text = export(atoms, format, st.name)
    label, mime, ext = FORMATS[format]
    fname = f"{st.name or 'structure'}".replace(" ", "_").replace("/", "_")[:60]
    if format == "poscar":
        fname = "POSCAR_" + fname
    return PlainTextResponse(text, media_type=mime,
                             headers={"Content-Disposition": f'attachment; filename="{fname}.{ext}"'})


@router.get("/structures/{sid}/trajectory", tags=["structures"])
def trajectory(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    st = _own(db, sid, user)
    p = get_settings().var_path((st.relax or {}).get("trajectory_path"))
    if p is None or not p.exists():
        raise HTTPException(404, "no trajectory")
    return PlainTextResponse(p.read_text(), media_type="chemical/x-xyz",
                             headers={"Content-Disposition": f'attachment; filename="relax_{st.id}.xyz"'})


@router.post("/structures/{sid}/analyze", tags=["structures"])
def analyze_structure(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    from ..crystal.qc import quality_report

    st = _own(db, sid, user)
    atoms = ase_read(get_settings().var_path(st.cif_path), format="cif")
    qc = quality_report(atoms, expected_dim=st.dimensionality)
    analysis = dict(st.analysis or {}, qc=qc)
    try:
        analysis["pore"] = analyze_porosity(atoms)
    except Exception as e:  # noqa: BLE001
        analysis["pore_error"] = str(e)[:200]
    st.qc, st.analysis = qc, analysis
    db.commit()
    return structure_dict(st, with_cif=False)


class RelaxIn(BaseModel):
    engine: str = Field(default="mace_off24", pattern="^(mace_off24)$")
    fmax_atoms: float = Field(default=0.05, gt=0.001, le=1.0)
    fmax_cell: float = Field(default=0.02, gt=0.001, le=1.0)
    steps_atoms: int = Field(default=400, ge=10, le=5000)
    steps_cell: int = Field(default=800, ge=0, le=10000)
    cell_relax: bool = True


@router.post("/structures/{sid}/relax", tags=["structures"])
def relax_structure(sid: int, body: RelaxIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    st = _own(db, sid, user)
    if st.n_atoms > get_settings().max_relax_atoms:
        raise HTTPException(422, f"structure has {st.n_atoms} atoms; relaxation limit is "
                                 f"{get_settings().max_relax_atoms} on this server")
    job = enqueue(db, user, "relax", dict(body.model_dump(), structure_id=st.id))
    db.commit()
    return job_dict(job)


@router.get("/relax/engines", tags=["structures"])
def relax_engines(user: User = Depends(current_user)) -> list[dict]:
    return engines()


# ---------------- jobs ----------------

def _job(db: Session, jid: int, user: User) -> Job:
    j = db.get(Job, jid)
    if j is None or j.org_id != user.org_id or (j.owner_id != user.id and user.role != "admin"):
        raise HTTPException(404, "job not found")
    return j


@router.get("/jobs", tags=["jobs"])
def list_jobs(status: str = "", page: int = 1, size: int = Query(50, le=200), user: User = Depends(current_user),
              db: Session = Depends(get_db)) -> dict:
    stmt = select(Job).where(Job.org_id == user.org_id)
    if user.role != "admin":
        stmt = stmt.where(Job.owner_id == user.id)
    if status:
        stmt = stmt.where(Job.status == status)
    rows = list(db.execute(stmt.order_by(Job.id.desc())).scalars())
    items = []
    for j in rows[(page - 1) * size: page * size]:
        d = job_dict(j)
        if j.type == "generate_batch" and isinstance(d.get("result"), dict):
            d["result"] = {"n": d["result"].get("n")}
        items.append(d)
    return {"total": len(rows), "items": items}


@router.get("/jobs/{jid}", tags=["jobs"])
def get_job(jid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return job_dict(_job(db, jid, user))


@router.post("/jobs/{jid}/cancel", tags=["jobs"])
def cancel_job(jid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    j = _job(db, jid, user)
    if j.status == "queued":
        j.status = "cancelled"
    elif j.status == "running":
        j.cancel_requested = True
    db.commit()
    return job_dict(j)


@router.get("/jobs/{jid}/log", tags=["jobs"])
def job_log(jid: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    j = _job(db, jid, user)
    if not j.log_path or not Path(j.log_path).exists():
        return PlainTextResponse("")
    return PlainTextResponse(Path(j.log_path).read_text()[-20000:])
