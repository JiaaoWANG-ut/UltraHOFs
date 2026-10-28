"""Periodic covalent bonding and molecule identification."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ase import Atoms
from ase.data import covalent_radii
from ase.neighborlist import neighbor_list


@dataclass
class Bonding:
    i: np.ndarray
    j: np.ndarray
    offsets: np.ndarray  # integer image offsets S: bond i -> j + S
    mol_id: np.ndarray  # molecule index per atom
    image: np.ndarray  # per-atom image offset making each molecule whole (unwrap)
    n_molecules: int

    def unwrapped_positions(self, atoms: Atoms) -> np.ndarray:
        return atoms.positions + self.image @ atoms.cell.array


def covalent_bonds(atoms: Atoms, scale: float = 1.15, max_cutoff: float = 3.0):
    radii = np.array([covalent_radii[z] for z in atoms.numbers]) * scale
    cutoff = min(max_cutoff, 2 * radii.max() + 0.01)
    i, j, d, S = neighbor_list("ijdS", atoms, cutoff)
    keep = (d <= radii[i] + radii[j]) & (d > 0.4)
    # H–H "bonds" only for very short contacts (H2 never occurs in HOFs)
    hh = (atoms.numbers[i] == 1) & (atoms.numbers[j] == 1)
    keep &= ~hh
    return i[keep], j[keep], S[keep], d[keep]


def find_molecules(atoms: Atoms, scale: float = 1.15) -> Bonding:
    """Connected components of the covalent graph, with per-atom unwrapping images."""
    n = len(atoms)
    i, j, S, _d = covalent_bonds(atoms, scale)
    adj: list[list[tuple[int, np.ndarray]]] = [[] for _ in range(n)]
    for a, b, s in zip(i, j, S, strict=True):
        adj[a].append((b, s))
    mol_id = -np.ones(n, dtype=int)
    image = np.zeros((n, 3), dtype=int)
    m = 0
    for start in range(n):
        if mol_id[start] >= 0:
            continue
        mol_id[start] = m
        stack = [start]
        while stack:
            cur = stack.pop()
            for nb, s in adj[cur]:
                if mol_id[nb] < 0:
                    mol_id[nb] = m
                    image[nb] = image[cur] + s
                    stack.append(nb)
        m += 1
    return Bonding(i, j, S, mol_id, image, m)


def molecule_atoms(bonding: Bonding, atoms: Atoms) -> list[tuple[list[int], np.ndarray]]:
    pos = bonding.unwrapped_positions(atoms)
    out = []
    for m in range(bonding.n_molecules):
        idx = np.where(bonding.mol_id == m)[0].tolist()
        out.append((idx, pos[idx]))
    return out


def network_dimensionality(n: int, edges: list[tuple[int, int, np.ndarray]]) -> tuple[int, list[int]]:
    """Dimensionality of a periodic graph (max over components) via cycle-translation rank.

    edges: (i, j, S) meaning node i (cell 0) bonded to node j in cell S.
    Returns (max_dim, per-component dims).
    """
    adj: list[list[tuple[int, np.ndarray]]] = [[] for _ in range(n)]
    for a, b, s in edges:
        s = np.asarray(s, dtype=int)
        adj[a].append((b, s))
        adj[b].append((a, -s))
    seen = np.zeros(n, dtype=bool)
    off = np.zeros((n, 3), dtype=int)
    dims = []
    for start in range(n):
        if seen[start]:
            continue
        seen[start] = True
        stack = [start]
        cycles: list[np.ndarray] = []
        while stack:
            cur = stack.pop()
            for nb, s in adj[cur]:
                target = off[cur] + s
                if not seen[nb]:
                    seen[nb] = True
                    off[nb] = target
                    stack.append(nb)
                else:
                    diff = target - off[nb]
                    if np.any(diff):
                        cycles.append(diff)
        if cycles:
            dims.append(int(np.linalg.matrix_rank(np.array(cycles, dtype=float))))
        else:
            dims.append(0)
    return (max(dims) if dims else 0), dims
