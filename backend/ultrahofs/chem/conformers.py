"""3D conformers, synthon connection points (X) and connection-geometry analysis."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdDistGeom, rdMolDescriptors
from rdkit.Chem import rdForceFieldHelpers as ffh

from .synthons import SYNTHON_BY_KEY, SynthonMatch, find_synthons


@dataclass
class ConformerSet:
    mol: Chem.Mol  # with explicit H and conformers
    conf_ids: list[int]
    energies: list[float]
    forcefield: str

    @property
    def best(self) -> int:
        return self.conf_ids[int(np.argmin(self.energies))] if self.energies else self.conf_ids[0]


def embed_conformers(mol: Chem.Mol, n_confs: int = 6, seed: int = 0x5EED, optimize: bool = True,
                     max_iters: int = 600, threads: int = 4) -> ConformerSet:
    molh = Chem.AddHs(mol)
    params = rdDistGeom.ETKDGv3()
    params.randomSeed = seed
    params.pruneRmsThresh = 0.3
    params.numThreads = threads
    cids = list(rdDistGeom.EmbedMultipleConfs(molh, numConfs=n_confs, params=params))
    if not cids:
        params.useRandomCoords = True
        params.maxIterations = 2000
        cids = list(rdDistGeom.EmbedMultipleConfs(molh, numConfs=max(2, n_confs // 2), params=params))
    if not cids:
        raise ValueError("3D embedding failed")
    energies = [0.0] * len(cids)
    ff_name = "none"
    if optimize:
        if ffh.MMFFHasAllMoleculeParams(molh):
            res = AllChem.MMFFOptimizeMoleculeConfs(molh, numThreads=threads, maxIters=max_iters)
            ff_name = "MMFF94"
        else:
            res = AllChem.UFFOptimizeMoleculeConfs(molh, numThreads=threads, maxIters=max_iters)
            ff_name = "UFF"
        energies = [e for (_c, e) in res]
    return ConformerSet(molh, cids, energies, ff_name)


def _ring_centroid(mol: Chem.Mol, pos: np.ndarray, atom_idx: int) -> np.ndarray | None:
    ri = mol.GetRingInfo()
    for ring in ri.AtomRings():
        if atom_idx in ring:
            return pos[list(ring)].mean(axis=0)
    return None


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else v


def connection_point(mol: Chem.Mol, pos: np.ndarray, m: SynthonMatch) -> np.ndarray | None:
    """Position of the H-bond pairing centre X for a synthon instance (None if unsupported)."""
    frame = connection_frame(mol, pos, m)
    return None if frame is None else frame[0]


def connection_frame(mol: Chem.Mol, pos: np.ndarray, m: SynthonMatch) -> tuple[np.ndarray, np.ndarray] | None:
    """Pairing centre X and the unit pairing direction (pointing from the synthon towards its partner).

    In a well-formed pair the two partners' directions are antiparallel.
    """
    st = SYNTHON_BY_KEY[m.key]
    g = st.geometry
    if g is None:
        return None
    if g[0] == "dimer":
        d = g[1]
        if m.donor is None or m.acceptor is None or m.root is None:
            return None
        D, A, R = pos[m.donor], pos[m.acceptor], pos[m.root]
        M = 0.5 * (D + A)
        v = _unit(A - D)
        w = M - R
        n = w - np.dot(w, v) * v
        if np.linalg.norm(n) < 0.2:
            if not m.attach:
                return None
            n = R - pos[m.attach[0]]
            n = n - np.dot(n, v) * v
        n = _unit(n)
        return M + 0.5 * d * n, n
    if g[0] == "axis":
        _, frm, to, d = g

        def point(tag: str) -> np.ndarray | None:
            if tag == "attach":
                return pos[m.attach[0]] if m.attach else None
            if tag == "attach_mid":
                return pos[list(m.attach)].mean(axis=0) if m.attach else None
            if tag == "root":
                return pos[m.root] if m.root is not None else None
            if tag == "acceptor":
                return pos[m.acceptor] if m.acceptor is not None else None
            if tag == "donor":
                return pos[m.donor] if m.donor is not None else None
            if tag == "ring_centroid":
                ref = m.acceptor if m.acceptor is not None else m.root
                return _ring_centroid(mol, pos, ref) if ref is not None else None
            return None

        p0, p1 = point(frm), point(to)
        if p0 is None or p1 is None:
            return None
        u = _unit(p1 - p0)
        return p1 + d * u, u
    return None


# ---------------- connection geometry classification ----------------

def _ideal_shapes() -> dict[str, np.ndarray]:
    s3 = np.sqrt(3) / 2
    t = 1 / np.sqrt(3)
    return {
        "linear": np.array([[1, 0, 0], [-1, 0, 0]], float),
        "bent": np.array([[1, 0, 0], [np.cos(2.0944), np.sin(2.0944), 0]], float),
        "trigonal_planar": np.array([[1, 0, 0], [-0.5, s3, 0], [-0.5, -s3, 0]], float),
        "t_shaped": np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0]], float),
        "trigonal_pyramidal": _unit_rows(np.array([[1, 0, -0.35], [-0.5, s3, -0.35], [-0.5, -s3, -0.35]])),
        "tetrahedral": np.array([[t, t, t], [t, -t, -t], [-t, t, -t], [-t, -t, t]], float),
        "square_planar": np.array([[1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]], float),
        "rectangular_planar": _unit_rows(np.array([[1, 0.6, 0], [1, -0.6, 0], [-1, 0.6, 0], [-1, -0.6, 0]])),
        "octahedral": np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], float),
        "hexagonal_planar": np.array(
            [[np.cos(k * np.pi / 3), np.sin(k * np.pi / 3), 0] for k in range(6)], float),
        "trigonal_prismatic": _unit_rows(np.array(
            [[np.cos(k * 2 * np.pi / 3), np.sin(k * 2 * np.pi / 3), z] for z in (0.8, -0.8) for k in range(3)])),
    }


def _unit_rows(a: np.ndarray) -> np.ndarray:
    return a / np.linalg.norm(a, axis=1)[:, None]


_SHAPES = None


def kabsch_rmsd(p: np.ndarray, q: np.ndarray, allow_reflection: bool = False) -> tuple[float, np.ndarray]:
    """Optimal rotation R (row vectors: p @ R ≈ q) and RMSD between paired unit-vector sets."""
    h = p.T @ q
    u, _s, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(u @ vt))
    if allow_reflection:
        d = 1.0
    dm = np.diag([1.0, 1.0, d])
    r = u @ dm @ vt
    diff = p @ r - q
    return float(np.sqrt((diff**2).sum() / len(p))), r


_PERMS: dict[int, np.ndarray] = {}


def _perm_array(n: int) -> np.ndarray:
    if n not in _PERMS:
        _PERMS[n] = np.array(list(itertools.permutations(range(n))), dtype=int).reshape(-1, n)
    return _PERMS[n]


def best_match(vectors: np.ndarray, targets: np.ndarray, max_perm_n: int = 7) -> tuple[float, np.ndarray, tuple]:
    """Best assignment + rotation of unit vectors onto target unit vectors (same count)."""
    n = len(vectors)
    if n == 0:
        return 0.0, np.eye(3), ()
    if n <= max_perm_n:
        # all assignments at once: batched Kabsch (same convention as kabsch_rmsd: p @ R ≈ q)
        perms = _perm_array(n)
        tq = targets[perms]
        u, _s, vt = np.linalg.svd(np.einsum("ni,pnj->pij", vectors, tq))
        u[:, :, 2] *= np.sign(np.linalg.det(u @ vt))[:, None]
        r = u @ vt
        diff = np.einsum("ni,pij->pnj", vectors, r) - tq
        rmsd = np.sqrt((diff**2).sum(axis=(1, 2)) / n)
        k = int(np.flatnonzero(rmsd <= rmsd.min() + 1e-9)[0])
        return float(rmsd[k]), r[k], tuple(int(x) for x in perms[k])
    best = (np.inf, np.eye(3), tuple(range(n)))
    for perm in _greedy_perms(vectors, targets):
        rmsd, r = kabsch_rmsd(vectors, targets[list(perm)])
        if rmsd < best[0]:
            best = (rmsd, r, perm)
    return best


def _greedy_perms(vectors: np.ndarray, targets: np.ndarray, n_starts: int = 24):
    from scipy.optimize import linear_sum_assignment
    from scipy.spatial.transform import Rotation

    rng = np.random.default_rng(7)
    for k in range(n_starts):
        rot = np.eye(3) if k == 0 else Rotation.random(random_state=rng.integers(1 << 31)).as_matrix()
        cur = vectors @ rot
        for _ in range(8):
            cost = -cur @ targets.T
            _r, c = linear_sum_assignment(cost)
            perm = tuple(int(x) for x in c)
            _rmsd, rot2 = kabsch_rmsd(vectors, targets[list(perm)])
            cur = vectors @ rot2
        yield perm


def classify_geometry(unit_vectors: np.ndarray) -> tuple[str, float]:
    global _SHAPES
    if _SHAPES is None:
        _SHAPES = _ideal_shapes()
    n = len(unit_vectors)
    if n == 0:
        return "none", 0.0
    if n == 1:
        return "terminal", 0.0
    best_name, best_rmsd = "irregular", np.inf
    for name, ideal in _SHAPES.items():
        if len(ideal) != n:
            continue
        rmsd, _r, _p = best_match(unit_vectors, ideal)
        if rmsd < best_rmsd:
            best_name, best_rmsd = name, rmsd
    if best_rmsd > 0.45:
        best_name = "irregular"
    return best_name, float(best_rmsd)


# ---------------- per-molecule 3D analysis ----------------

@dataclass
class Geometry3D:
    n_confs: int
    forcefield: str
    points: list[dict] = field(default_factory=list)  # per supported synthon: X, r, unit vector
    geometry: str = "none"
    geometry_rmsd: float = 0.0
    min_angle: float | None = None
    divergence: float | None = None  # |sum(u)|/n, 0 = balanced/divergent
    angle_spread: float | None = None  # std of min angle across conformers (deg)
    intramolecular_hb_fraction: float = 0.0
    npr1: float | None = None
    npr2: float | None = None
    pbf: float | None = None
    thickness: float | None = None
    arm_length: float | None = None  # mean centroid→X distance (Å)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["points"] = [
            {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in p.items()} for p in self.points
        ]
        return d


def _intramolecular_hb(mol: Chem.Mol, pos: np.ndarray, synthon_atoms: set[int]) -> bool:
    dm = Chem.GetDistanceMatrix(mol)
    donors_h = []
    for a in mol.GetAtoms():
        if a.GetAtomicNum() == 1:
            nb = a.GetNeighbors()[0]
            if nb.GetAtomicNum() in (7, 8) and nb.GetIdx() in synthon_atoms:
                donors_h.append((a.GetIdx(), nb.GetIdx()))
    acceptors = [a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() in (7, 8)]
    for h, d in donors_h:
        for acc in acceptors:
            if acc == d or dm[d][acc] < 4:
                continue
            r = np.linalg.norm(pos[h] - pos[acc])
            if r < 2.3:
                v1 = pos[d] - pos[h]
                v2 = pos[acc] - pos[h]
                cosang = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
                if np.degrees(np.arccos(np.clip(cosang, -1, 1))) > 120:
                    return True
    return False


def analyze_3d(mol: Chem.Mol, n_confs: int = 6, seed: int = 0x5EED,
               matches: list[SynthonMatch] | None = None) -> Geometry3D:
    cs = embed_conformers(mol, n_confs=n_confs, seed=seed)
    molh = cs.mol
    # Synthon indices refer to the heavy-atom molecule; AddHs keeps heavy atom indices unchanged.
    matches = matches if matches is not None else find_synthons(mol)
    synthon_atoms: set[int] = set()
    for m in matches:
        synthon_atoms |= set(m.atoms)
    heavy = [a.GetIdx() for a in molh.GetAtoms() if a.GetAtomicNum() > 1]

    geo = Geometry3D(n_confs=len(cs.conf_ids), forcefield=cs.forcefield)
    min_angles, ihb = [], 0
    best_points = None
    for cid in cs.conf_ids:
        pos = molh.GetConformer(cid).GetPositions()
        if _intramolecular_hb(molh, pos, synthon_atoms):
            ihb += 1
        pts = []
        for m in matches:
            x = connection_point(molh, pos, m)
            if x is not None:
                pts.append((m, x))
        if len(pts) >= 2:
            c = pos[heavy].mean(axis=0)
            u = np.array([_unit(x - c) for _m, x in pts])
            ang = [np.degrees(np.arccos(np.clip(np.dot(u[i], u[j]), -1, 1)))
                   for i in range(len(u)) for j in range(i + 1, len(u))]
            min_angles.append(min(ang))
        if cid == cs.best:
            best_points = pts
            geo.npr1 = round(rdMolDescriptors.CalcNPR1(molh, confId=cid), 3)
            geo.npr2 = round(rdMolDescriptors.CalcNPR2(molh, confId=cid), 3)
            geo.pbf = round(rdMolDescriptors.CalcPBF(molh, confId=cid), 3)
            hp = pos[heavy] - pos[heavy].mean(axis=0)
            _u, _sv, vt = np.linalg.svd(hp, full_matrices=False)
            proj = hp @ vt[-1]
            geo.thickness = round(float(proj.max() - proj.min()), 2)
    geo.intramolecular_hb_fraction = round(ihb / max(1, len(cs.conf_ids)), 2)
    if best_points:
        pos = molh.GetConformer(cs.best).GetPositions()
        c = pos[heavy].mean(axis=0)
        u = np.array([_unit(x - c) for _m, x in best_points])
        r = [float(np.linalg.norm(x - c)) for _m, x in best_points]
        geo.points = [
            {"type": m.key, "x": x, "r": round(ri, 3), "u": ui}
            for (m, x), ri, ui in zip(best_points, r, u, strict=True)
        ]
        geo.arm_length = round(float(np.mean(r)), 2)
        if len(u) >= 2:
            geo.geometry, geo.geometry_rmsd = classify_geometry(u)
            geo.divergence = round(float(np.linalg.norm(u.sum(axis=0)) / len(u)), 3)
            geo.geometry_rmsd = round(geo.geometry_rmsd, 3)
        else:
            geo.geometry = "terminal" if len(u) == 1 else "none"
    if min_angles:
        geo.min_angle = round(float(np.mean(min_angles)), 1)
        geo.angle_spread = round(float(np.std(min_angles)), 1)
    return geo


def molblock_3d(mol: Chem.Mol, seed: int = 0x5EED) -> str:
    cs = embed_conformers(mol, n_confs=3, seed=seed)
    return Chem.MolToMolBlock(cs.mol, confId=cs.best)
