"""Building blocks: tecton 3D geometry + connection points at H-bond pairing centres."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import rdForceFieldHelpers as ffh

from ..chem.conformers import classify_geometry, connection_frame, embed_conformers
from ..chem.standardize import parse_molecule
from ..chem.synthons import SYNTHON_BY_KEY, SynthonMatch, find_synthons


class BuildingBlockError(ValueError):
    pass


@dataclass
class Connection:
    synthon: str
    builder: str  # full | approx
    group: list[int]  # atoms rotated during synthon torsion alignment (incl. H)
    axis: tuple[int, int] | None  # (attach, root) atom indices, None if not rotatable
    donors_h: list[int]
    acceptors: list[int]


@dataclass
class BuildingBlock:
    smiles: str
    symbols: list[str]
    coords: np.ndarray  # (N,3) relative to centre
    conn: np.ndarray  # (k,3) X positions relative to centre
    connections: list[Connection]
    charge: int
    geometry: str
    geometry_rmsd: float
    conformer_energy: float | None = None
    notes: list[str] = field(default_factory=list)
    mol: Chem.Mol | None = None
    conn_dir: np.ndarray | None = None  # (k,3) unit pairing directions (partner's is antiparallel)

    @property
    def k(self) -> int:
        return len(self.conn)

    @property
    def unit(self) -> np.ndarray:
        return self.conn / np.linalg.norm(self.conn, axis=1)[:, None]

    @property
    def radius(self) -> float:
        return float(np.linalg.norm(self.conn, axis=1).mean())

    def summary(self) -> dict:
        return {
            "smiles": self.smiles, "n_atoms": len(self.symbols), "k": self.k, "charge": self.charge,
            "geometry": self.geometry, "geometry_rmsd": round(self.geometry_rmsd, 3),
            "radius": round(self.radius, 3),
            "connections": [{"synthon": c.synthon, "builder": c.builder, "rotatable": c.axis is not None}
                            for c in self.connections],
            "notes": self.notes,
        }


def _rotatable(mol: Chem.Mol, attach: int, root: int) -> bool:
    b = mol.GetBondBetweenAtoms(attach, root)
    return b is not None and b.GetBondType() == Chem.BondType.SINGLE and not b.IsInRing()


def _connection(molh: Chem.Mol, m: SynthonMatch) -> Connection:
    st = SYNTHON_BY_KEY[m.key]
    group = set(m.atoms)
    for a in list(m.atoms):
        for nb in molh.GetAtomWithIdx(a).GetNeighbors():
            if nb.GetAtomicNum() == 1:
                group.add(nb.GetIdx())
    donors_h = [h for h in group if molh.GetAtomWithIdx(h).GetAtomicNum() == 1
                and molh.GetAtomWithIdx(h).GetNeighbors()[0].GetAtomicNum() in (7, 8)]
    acceptors = [a for a in m.atoms if molh.GetAtomWithIdx(a).GetAtomicNum() in (7, 8)]
    axis = None
    if len(m.attach) == 1 and m.root is not None and _rotatable(molh, m.attach[0], m.root):
        axis = (m.attach[0], m.root)
    return Connection(m.key, st.builder, sorted(group), axis, donors_h, acceptors)


def planarize(molh: Chem.Mol, conf_id: int, max_displ: float = 0.25, iters: int = 400) -> None:
    """Pull heavy atoms onto their best-fit plane, then relax with position restraints."""
    conf = molh.GetConformer(conf_id)
    pos = conf.GetPositions()
    heavy = [a.GetIdx() for a in molh.GetAtoms() if a.GetAtomicNum() > 1]
    c = pos[heavy].mean(axis=0)
    _u, _s, vt = np.linalg.svd(pos[heavy] - c)
    n = vt[-1]
    proj = pos - np.outer((pos - c) @ n, n)
    for i in range(molh.GetNumAtoms()):
        conf.SetAtomPosition(i, proj[i].tolist())
    if ffh.MMFFHasAllMoleculeParams(molh):
        props = AllChem.MMFFGetMoleculeProperties(molh)
        ff = AllChem.MMFFGetMoleculeForceField(molh, props, confId=conf_id)
    else:
        ff = AllChem.UFFGetMoleculeForceField(molh, confId=conf_id)
    for i in heavy:
        if hasattr(ff, "MMFFAddPositionConstraint"):
            ff.MMFFAddPositionConstraint(i, max_displ, 100.0)
        else:
            ff.UFFAddPositionConstraint(i, max_displ, 100.0)
    ff.Minimize(maxIts=iters)


def build_bb(smiles_or_mol: str | Chem.Mol, *, n_confs: int = 16, seed: int = 0x5EED,
             planar: bool = False, allow_approx: bool = True) -> BuildingBlock:
    """Build a building block from a tecton.

    The conformer is chosen to best match an ideal connection polyhedron (and, for ``planar``,
    to be as flat as possible, which suits 2D layer nets); geometry is never forced.
    """
    from rdkit.Chem import rdMolDescriptors

    mol = parse_molecule(smiles_or_mol) if isinstance(smiles_or_mol, str) else smiles_or_mol
    matches = [m for m in find_synthons(mol) if SYNTHON_BY_KEY[m.key].geometry is not None]
    if not allow_approx:
        matches = [m for m in matches if SYNTHON_BY_KEY[m.key].builder == "full"]
    if not matches:
        raise BuildingBlockError("no synthon supported by the assembler (e.g. COOH, DAT, pyridone, amide, "
                                 "boronic acid, amidinium/carboxylate)")
    cs = embed_conformers(mol, n_confs=n_confs, seed=seed)
    molh = cs.mol
    best = None
    emin = min(cs.energies) if cs.energies else 0.0
    for cid, energy in zip(cs.conf_ids, cs.energies, strict=True):
        pos = molh.GetConformer(cid).GetPositions()
        frames = [connection_frame(molh, pos, m) for m in matches]
        if any(f is None for f in frames):
            continue
        xs = np.array([f[0] for f in frames])
        dirs = np.array([f[1] for f in frames])
        centre = xs.mean(axis=0) if len(xs) > 1 else pos.mean(axis=0)
        u = xs - centre
        u = u / np.linalg.norm(u, axis=1)[:, None]
        geo, rmsd = classify_geometry(u) if len(u) >= 2 else ("terminal", 0.0)
        key = rmsd + 0.002 * (energy - emin)
        if planar:
            key += 0.05 * rdMolDescriptors.CalcPBF(molh, confId=cid)
        if best is None or key < best[0]:
            best = (key, cid, xs, dirs, centre, geo, rmsd, energy)
    if best is None:
        raise BuildingBlockError("could not place connection points")
    _k, cid, xs, dirs, centre, geo, rmsd, energy = best
    pos = molh.GetConformer(cid).GetPositions()
    notes = []
    approx = sorted({m.key for m in matches if SYNTHON_BY_KEY[m.key].builder == "approx"})
    if approx:
        notes.append("approximate pairing geometry for: " + ", ".join(approx))
    keep_conf = Chem.Mol(molh, False, cid)
    return BuildingBlock(
        smiles=Chem.MolToSmiles(mol),
        symbols=[a.GetSymbol() for a in molh.GetAtoms()],
        coords=pos - centre,
        conn=xs - centre,
        connections=[_connection(molh, m) for m in matches],
        charge=Chem.GetFormalCharge(mol),
        geometry=geo,
        geometry_rmsd=float(rmsd),
        conformer_energy=float(energy) if energy is not None else None,
        notes=notes,
        mol=keep_conf,
        conn_dir=dirs,
    )
