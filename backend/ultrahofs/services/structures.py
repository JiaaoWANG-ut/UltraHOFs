"""Structure building, persistence and analysis services."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from ase import Atoms
from sqlalchemy.orm import Session

from ..analysis.zeopp import analyze_cif, porous_verdict, zeopp_available
from ..config import get_settings
from ..crystal.assemble import AssemblyError, BuildOptions, LayerOptions, arrange_nodes, assemble
from ..crystal.bb import BuildingBlock, build_bb
from ..crystal.export import cell_dict, density, write_cif
from ..crystal.nets import get_net
from ..crystal.qc import quality_report
from ..models import GeneratedStructure


@lru_cache(maxsize=256)
def cached_bb(smiles: str, planar: bool) -> BuildingBlock:
    return build_bb(smiles, planar=planar)


@dataclass
class BuildSpec:
    net: str
    mode: str = "single"  # single | bipartite | binodal
    node: str = ""  # SMILES (single)
    node_a: str = ""  # SMILES (bipartite/binodal), e.g. cation
    node_b: str = ""  # SMILES (bipartite/binodal), e.g. anion
    edge: str = ""  # optional 2-connected linker SMILES (single mode)
    stacking: str = "AA"
    interlayer: float | None = None
    slip: tuple[float, float] = (0.0, 0.0)
    interpenetration: int = 1
    align_synthons: bool = True
    planar: bool | None = None
    name: str = ""
    extra: dict = field(default_factory=dict)


def build(spec: BuildSpec) -> dict:
    net = get_net(spec.net)
    planar = (net.dim == 2) if spec.planar is None else spec.planar
    edge_bb = cached_bb(spec.edge, False) if spec.edge else None
    if spec.mode == "single":
        if not spec.node:
            raise AssemblyError("node building block (SMILES) is required")
        bb = cached_bb(spec.node, planar)
        net, node_bbs = arrange_nodes(net, "single", bb)
        bbs = {"node": bb}
    elif spec.mode in ("bipartite", "binodal"):
        if not spec.node_a or not spec.node_b:
            raise AssemblyError("two building blocks (SMILES) are required")
        a, b = cached_bb(spec.node_a, planar), cached_bb(spec.node_b, planar)
        net, node_bbs = arrange_nodes(net, spec.mode, a, b)
        bbs = {"node_a": a, "node_b": b}
    else:
        raise AssemblyError(f"unknown mode {spec.mode}")
    if edge_bb is not None:
        bbs["edge"] = edge_bb
    opts = BuildOptions(align_synthons=spec.align_synthons, interpenetration=spec.interpenetration,
                        layer=LayerOptions(spec.stacking, spec.interlayer, tuple(spec.slip)), edge_bb=edge_bb)
    out = assemble(net, node_bbs, opts)
    atoms = out.to_ase()
    if len(atoms) > get_settings().max_build_atoms:
        raise AssemblyError(f"structure has {len(atoms)} atoms (limit {get_settings().max_build_atoms})")
    qc = quality_report(atoms, expected_dim=net.dim, mol_index=out.mol_index)
    angle = out.info.get("synthon_angle_max")
    if angle is not None and angle > 30.0:
        qc["messages"].append(f"paired synthons deviate {angle}° from head-on pairing; another net may suit better")
        if qc["status"] == "ok":
            qc["status"] = "warning"
    return {"atoms": atoms, "info": out.info, "qc": qc, "dim": net.dim,
            "building_blocks": {k: v.summary() for k, v in bbs.items()}}


def analyze_porosity(atoms: Atoms) -> dict:
    if not zeopp_available():
        raise RuntimeError("Zeo++ not available")
    pm = analyze_cif(write_cif(atoms, "zeopp"))
    pm["verdict"] = porous_verdict(pm)
    return pm


def save_structure(db: Session, *, owner_id: int, org_id: int, name: str, atoms: Atoms, components: list,
                   topology: str, dimensionality: int, options: dict, qc: dict, analysis: dict,
                   relax: dict | None = None, parent_id: int | None = None, status: str = "built") -> GeneratedStructure:
    st = GeneratedStructure(
        owner_id=owner_id, org_id=org_id, name=name or f"{topology} structure", components=components,
        topology=topology, dimensionality=dimensionality, options=options, cell=cell_dict(atoms),
        formula=atoms.get_chemical_formula(mode="hill"), n_atoms=len(atoms), density=density(atoms),
        qc=qc, analysis=analysis, relax=relax or {}, parent_id=parent_id, status=status,
    )
    db.add(st)
    db.flush()
    s = get_settings()
    d = s.var_dir / "structures"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{st.id}.cif"
    path.write_text(write_cif(atoms, st.name))
    st.cif_path = s.rel_var_path(path)
    return st


def structure_dict(st: GeneratedStructure, with_cif: bool = False) -> dict:
    d = {
        "id": st.id, "name": st.name, "components": st.components, "topology": st.topology,
        "dimensionality": st.dimensionality, "options": st.options, "cell": st.cell, "formula": st.formula,
        "n_atoms": st.n_atoms, "density": st.density, "qc": st.qc, "analysis": st.analysis,
        "relax": st.relax, "parent_id": st.parent_id, "status": st.status, "created_at": st.created_at,
        "owner_id": st.owner_id,
    }
    if with_cif and st.cif_path:
        try:
            d["cif"] = get_settings().var_path(st.cif_path).read_text()
        except OSError:
            d["cif"] = ""
    return d
