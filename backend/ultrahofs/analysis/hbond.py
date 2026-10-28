"""Hydrogen-bond detection and H-bonded network dimensionality in periodic structures."""

from __future__ import annotations

import numpy as np
from ase import Atoms
from ase.neighborlist import neighbor_list

from .bonding import Bonding, find_molecules, network_dimensionality

DONOR_Z = {7, 8}
ACCEPTOR_Z = {7, 8, 9, 17, 35, 53}
# element-specific H···A and D···A limits (Å); halide anions form longer charge-assisted H-bonds
H_A_MAX = {7: 2.6, 8: 2.6, 9: 2.5, 17: 2.95, 35: 3.05, 53: 3.25}
D_A_MAX = {7: 3.3, 8: 3.3, 9: 3.2, 17: 3.7, 35: 3.85, 53: 4.05}


def _coordination(atoms: Atoms, bonding: Bonding) -> np.ndarray:
    cn = np.zeros(len(atoms), dtype=int)
    for a in bonding.i:
        cn[a] += 1
    return cn


def find_hbonds(atoms: Atoms, bonding: Bonding | None = None, h_a_max: float = 2.6,
                angle_min: float = 120.0, da_max: float = 3.3, heavy_fallback: bool = True) -> dict:
    """Return explicit (D–H···A) and heavy-atom-only (D···A, when H is missing) H-bonds."""
    bonding = bonding or find_molecules(atoms)
    z = atoms.numbers
    cell = atoms.cell.array
    cn = _coordination(atoms, bonding)
    # donor H: H covalently bonded to N/O
    h_parent: dict[int, tuple[int, np.ndarray]] = {}
    for a, b, s in zip(bonding.i, bonding.j, bonding.offsets, strict=True):
        if z[a] == 1 and z[b] in DONOR_Z:
            h_parent[a] = (b, s)
    acceptor_ok = np.array([(zz in ACCEPTOR_Z) and not (zz == 7 and cn[k] >= 4) for k, zz in enumerate(z)])

    explicit = []
    if h_parent:
        i, j, D, d = neighbor_list("ijDd", atoms, max(h_a_max, 3.25))
        for h, acc, vec, dist in zip(i, j, D, d, strict=True):
            if h not in h_parent or not acceptor_ok[acc]:
                continue
            if dist > H_A_MAX.get(int(z[acc]), h_a_max):
                continue
            donor, s_hd = h_parent[h]
            if acc == donor:
                continue
            p_h = atoms.positions[h]
            p_d = atoms.positions[donor] + s_hd @ cell
            p_a = p_h + vec
            v1, v2 = p_d - p_h, p_a - p_h
            cosang = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
            ang = float(np.degrees(np.arccos(np.clip(cosang, -1, 1))))
            da = float(np.linalg.norm(p_a - p_d))
            if ang < angle_min or da > D_A_MAX.get(int(z[acc]), da_max):
                continue
            # image offset of acceptor relative to donor cell
            frac = np.linalg.solve(cell.T, (p_a - atoms.positions[acc]))
            s_acc = np.rint(frac).astype(int)
            # same molecule instance <=> same mol_id and same translation of the unwrapped molecule
            t_d = np.asarray(s_hd) - bonding.image[donor]
            t_a = s_acc - bonding.image[acc]
            same_instance = bool(bonding.mol_id[donor] == bonding.mol_id[acc] and np.array_equal(t_d, t_a))
            explicit.append({
                "donor": int(donor), "h": int(h), "acceptor": int(acc), "S": s_acc.tolist(),
                "S_donor": np.asarray(s_hd).tolist(),
                "h_a": round(float(dist), 3), "d_a": round(da, 3), "angle": round(ang, 1),
                "intermolecular": not same_instance,
            })

    heavy = []
    if heavy_fallback:
        donors_with_h = {pd for pd, _s in h_parent.values()}
        has_any_polar_h = len(donors_with_h) > 0
        i, j, d, S = neighbor_list("ijdS", atoms, 3.1)
        for a, b, dist, s in zip(i, j, d, S, strict=True):
            if a >= b or z[a] not in DONOR_Z or z[b] not in DONOR_Z:
                continue
            t_a = -bonding.image[a]
            t_b = s - bonding.image[b]
            if bonding.mol_id[a] == bonding.mol_id[b] and np.array_equal(t_a, t_b):
                continue
            if dist < 2.4:
                continue
            # Only use heavy-atom contacts where H atoms appear to be missing
            if has_any_polar_h and (a in donors_with_h or b in donors_with_h):
                continue
            heavy.append({"a": int(a), "b": int(b), "S": s.tolist(), "d": round(float(dist), 3)})
    return {"explicit": explicit, "heavy_atom": heavy, "n_polar_h": len(h_parent)}


def hbond_network_dimensionality(atoms: Atoms, bonding: Bonding | None = None,
                                 hbonds: dict | None = None) -> dict:
    """Dimensionality of the covalent + H-bond periodic graph (0D molecules ... 3D framework)."""
    bonding = bonding or find_molecules(atoms)
    hbonds = hbonds or find_hbonds(atoms, bonding)
    n = len(atoms)
    edges = [(int(a), int(b), s) for a, b, s in zip(bonding.i, bonding.j, bonding.offsets, strict=True) if a < b
             or (a == b)]
    cov_dim, _ = network_dimensionality(n, edges)
    hb_edges = list(edges)
    for hb in hbonds["explicit"]:
        s = np.asarray(hb["S"]) - np.asarray(hb["S_donor"])
        hb_edges.append((hb["donor"], hb["acceptor"], s))
    for hb in hbonds["heavy_atom"]:
        hb_edges.append((hb["a"], hb["b"], np.asarray(hb["S"])))
    hb_dim, comp_dims = network_dimensionality(n, hb_edges)
    n_inter = sum(1 for hb in hbonds["explicit"] if hb["intermolecular"])
    return {
        "covalent_dimensionality": cov_dim,
        "hbond_dimensionality": hb_dim,
        "n_hbonds": n_inter,
        "n_heavy_atom_contacts": len(hbonds["heavy_atom"]),
        "uses_heavy_atom_fallback": bool(hbonds["heavy_atom"]),
        "component_dims": sorted(set(comp_dims), reverse=True)[:5],
    }
