"""Quality checks for assembled (or relaxed) periodic HOF structures."""

from __future__ import annotations

import numpy as np
from ase import Atoms
from ase.neighborlist import neighbor_list

from ..analysis.bonding import find_molecules
from ..analysis.hbond import find_hbonds, hbond_network_dimensionality
from .export import density

POLAR = {7, 8}


def quality_report(atoms: Atoms, expected_dim: int | None = None, mol_index: np.ndarray | None = None) -> dict:
    z = atoms.numbers
    bonding = find_molecules(atoms)
    i, j, d, S = neighbor_list("ijdS", atoms, 3.0)
    # different molecule *instance*: different molecule or same molecule in another periodic image
    same = (bonding.mol_id[i] == bonding.mol_id[j]) & np.all(
        (S - bonding.image[j] + bonding.image[i]) == 0, axis=1)
    inter = ~same & (i < j)
    heavy = z > 1
    hh = inter & heavy[i] & heavy[j]
    polar_pair = np.isin(z[i], list(POLAR)) & np.isin(z[j], list(POLAR))
    clash_heavy = hh & (d < 2.6) & ~(polar_pair & (d >= 2.35))
    h_h = inter & (z[i] == 1) & (z[j] == 1) & (d < 1.6)
    h_heavy = inter & ((z[i] == 1) ^ (z[j] == 1)) & (d < 1.5)
    min_heavy = float(d[hh].min()) if hh.any() else None
    hb = find_hbonds(atoms, bonding)
    net = hbond_network_dimensionality(atoms, bonding, hb)
    n_clash = int(clash_heavy.sum() + h_h.sum() + h_heavy.sum())
    n_mols = int(len(np.unique(mol_index))) if mol_index is not None else bonding.n_molecules
    status, msgs = "ok", []
    if n_clash > 0:
        status = "warning" if n_clash <= max(2, n_mols) else "fail"
        msgs.append(f"{n_clash} intermolecular close contacts")
    covalent_extra = bonding.n_molecules < n_mols
    if covalent_extra:
        status = "fail"
        msgs.append("molecules overlap (spurious covalent contacts)")
    if expected_dim is not None and net["hbond_dimensionality"] < expected_dim:
        status = "warning" if status == "ok" else status
        msgs.append(f"H-bond network is {net['hbond_dimensionality']}D (net is {expected_dim}D)")
    return {
        "status": status,
        "messages": msgs,
        "n_atoms": len(atoms),
        "n_molecules": n_mols,
        "density_g_cm3": density(atoms),
        "min_intermolecular_heavy_A": round(min_heavy, 3) if min_heavy is not None else None,
        "n_close_contacts": n_clash,
        "n_hbonds": net["n_hbonds"],
        "hbonds_per_molecule": round(net["n_hbonds"] / max(1, n_mols), 2),
        "hbond_dimensionality": net["hbond_dimensionality"],
        "covalent_dimensionality": net["covalent_dimensionality"],
    }
