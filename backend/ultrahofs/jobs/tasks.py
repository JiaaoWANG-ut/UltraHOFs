"""Job implementations. Each task receives (job_id, params, ctx) and returns a result dict."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..config import get_settings
from ..db import session_scope


class TaskContext:
    def __init__(self, progress: Callable[[float, str], None], should_stop: Callable[[], bool], log_path: Path):
        self.progress = progress
        self.should_stop = should_stop
        self.log_path = log_path

    def log(self, msg: str) -> None:
        with open(self.log_path, "a") as f:
            f.write(msg.rstrip() + "\n")


def task_relax(job_id: int, params: dict, ctx: TaskContext) -> dict:
    from ase.io import read

    from ..crystal.export import cell_dict, density, write_cif
    from ..crystal.qc import quality_report
    from ..models import GeneratedStructure
    from ..relax.engine import frames_to_extxyz, relax
    from ..services.structures import analyze_porosity, save_structure

    with session_scope() as db:
        src = db.get(GeneratedStructure, params["structure_id"])
        if src is None:
            raise ValueError("structure not found")
        cif_path, name, owner_id, org_id = src.cif_path, src.name, src.owner_id, src.org_id
        dim = src.dimensionality
        components, topology = src.components, src.topology
    atoms = read(cif_path, format="cif")
    ctx.log(f"relaxing {name}: {len(atoms)} atoms with {params.get('engine', 'mace_off24')}")
    res = relax(atoms, engine=params.get("engine", "mace_off24"), fmax_atoms=params.get("fmax_atoms", 0.05),
                fmax_cell=params.get("fmax_cell", 0.02), steps_atoms=params.get("steps_atoms", 400),
                steps_cell=params.get("steps_cell", 800), cell_relax=params.get("cell_relax", True),
                progress=ctx.progress, should_stop=ctx.should_stop)
    out = res.pop("atoms")
    frames = res.pop("frames")
    qc = quality_report(out, expected_dim=dim)
    analysis = {"qc": qc}
    try:
        analysis["pore"] = analyze_porosity(out)
    except Exception as e:  # noqa: BLE001
        analysis["pore_error"] = str(e)[:200]
    with session_scope() as db:
        parent = db.get(GeneratedStructure, params["structure_id"])
        before_pore = (parent.analysis or {}).get("pore") or {}
        after_vf = (analysis.get("pore") or {}).get("void_fraction_geometric")
        before_vf = before_pore.get("void_fraction_geometric")
        collapsed = res["volume_change_pct"] < -30 or (
            before_vf and after_vf is not None and after_vf < 0.5 * before_vf)
        res["collapse_flag"] = bool(collapsed)
        res["n_molecules"] = qc["n_molecules"]
        res["energy_per_molecule_eV"] = round(res["energy_final_eV"] / max(1, qc["n_molecules"]), 5)
        st = save_structure(
            db, owner_id=owner_id, org_id=org_id, name=f"{name} (relaxed)", atoms=out,
            components=components, topology=topology, dimensionality=dim,
            options={"relaxed_from": params["structure_id"]}, qc=qc, analysis=analysis,
            relax=res, parent_id=params["structure_id"], status="relaxed",
        )
        traj = Path(st.cif_path).with_suffix(".traj.xyz")
        traj.write_text(frames_to_extxyz(frames))
        st.relax = dict(res, trajectory_path=str(traj), cell_before=cell_dict(atoms), cell_after=cell_dict(out),
                        density_before=density(atoms), density_after=density(out))
        new_id = st.id
    ctx.log(f"done: ΔE = {res['energy_change_eV']} eV, ΔV = {res['volume_change_pct']}%")
    return {"structure_id": new_id, **{k: v for k, v in res.items() if k != "citation"},
            "cif_preview": write_cif(out, name)[:200]}


def task_generate_batch(job_id: int, params: dict, ctx: TaskContext) -> dict:
    from rdkit import Chem

    from ..chem.enumerate import enumerate_tectons, route_hint
    from ..chem.scoring import score_molecule
    from ..services.molecules import experimental_index, get_or_create_molecule, synthon_prior

    cands = list(enumerate_tectons(params.get("cores") or None, params.get("arms") or None,
                                   params.get("synthons") or None, min_sites=params.get("min_sites", 3),
                                   max_heavy_atoms=params.get("max_heavy_atoms", 160),
                                   limit=params.get("limit", 2000)))
    idx = experimental_index()
    prior = synthon_prior()
    out = []
    for k, c in enumerate(cands):
        if ctx.should_stop():
            raise RuntimeError("cancelled")
        mol = Chem.MolFromSmiles(c.smiles)
        sc = score_molecule(mol, n_confs=params.get("n_confs", 4), max_similarity=idx.max_similarity(mol),
                            synthon_prior=prior)
        with session_scope() as db:
            m = get_or_create_molecule(db, mol, origin="generated",
                                       provenance={"core": c.core, "arm": c.arm, "synthon": c.synthon,
                                                   "job": job_id})
            if not m.score:
                m.score = {k2: sc[k2] for k2 in ("score", "band", "weighted_sum", "gate", "components", "flags",
                                                "n_connect", "geometry")}
            mid = m.id
        out.append({"molecule_id": mid, "smiles": c.smiles, "core": c.core, "arm": c.arm, "synthon": c.synthon,
                    "score": sc["score"], "band": sc["band"], "route": route_hint(c.core, c.arm, c.synthon)})
        if k % 5 == 0:
            ctx.progress((k + 1) / max(1, len(cands)), f"scored {k + 1}/{len(cands)}")
    out.sort(key=lambda d: -d["score"])
    return {"n": len(out), "candidates": out}


def task_analyze(job_id: int, params: dict, ctx: TaskContext) -> dict:
    from ase.io import read

    from ..crystal.qc import quality_report
    from ..models import GeneratedStructure
    from ..services.structures import analyze_porosity

    with session_scope() as db:
        st = db.get(GeneratedStructure, params["structure_id"])
        path, dim = st.cif_path, st.dimensionality
    atoms = read(path, format="cif")
    qc = quality_report(atoms, expected_dim=dim)
    pore = analyze_porosity(atoms)
    with session_scope() as db:
        st = db.get(GeneratedStructure, params["structure_id"])
        st.qc = qc
        st.analysis = dict(st.analysis or {}, pore=pore, qc=qc)
    return {"structure_id": params["structure_id"], "qc": qc, "pore": pore}


TASKS: dict[str, Callable[[int, dict, TaskContext], dict]] = {
    "relax": task_relax,
    "generate_batch": task_generate_batch,
    "analyze": task_analyze,
}


def job_dir(job_id: int) -> Path:
    d = get_settings().var_dir / "jobs" / str(job_id)
    d.mkdir(parents=True, exist_ok=True)
    return d
