"""Net (topology) library: RCSR 3D nets (via PORMAKE cache) + built-in 2D layer nets."""

from __future__ import annotations

import gzip
import itertools
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..chem.conformers import best_match

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nets"
RCSR_CACHE = DATA_DIR / "rcsr_pormake.json.gz"

# Nets with experimental HOF precedent (literature / HOFSyn notes); used to prioritise suggestions.
HOF_PRECEDENT = {"dia", "sql", "hcb", "pcu", "srs", "pts", "ths", "lon", "kgm", "hxl", "bnn", "sod",
                 "acs", "nbo", "cds", "qtz", "ctn", "bor", "tbo", "pto", "rtl", "flu", "stp", "kgd", "fes"}


@dataclass
class Net:
    name: str
    dim: int
    cell: np.ndarray  # (3,3) rows are lattice vectors; unit-edge scale
    frac: np.ndarray  # (N,3)
    types: np.ndarray  # (N,)
    edges: list[tuple[int, int, tuple[int, int, int]]]
    source: str = "rcsr"
    spacegroup: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def n_nodes(self) -> int:
        return len(self.frac)

    @property
    def precedent(self) -> bool:
        return self.name.split("@")[0] in HOF_PRECEDENT

    def cart(self) -> np.ndarray:
        return self.frac @ self.cell

    def edge_vector(self, k: int) -> np.ndarray:
        i, j, s = self.edges[k]
        return (self.frac[j] + np.asarray(s) - self.frac[i]) @ self.cell

    def coordination(self) -> np.ndarray:
        cn = np.zeros(self.n_nodes, dtype=int)
        for i, j, _s in self.edges:
            cn[i] += 1
            cn[j] += 1
        return cn

    def incident(self, i: int) -> list[tuple[int, int, np.ndarray]]:
        """(edge index, sign, vector from node i towards neighbour) for node i."""
        out = []
        for k, (a, b, _s) in enumerate(self.edges):
            v = self.edge_vector(k)
            if a == i:
                out.append((k, +1, v))
            if b == i:
                out.append((k, -1, -v))
        return out

    def local_vectors(self, i: int) -> np.ndarray:
        vs = np.array([v for _k, _s, v in self.incident(i)])
        return vs / np.linalg.norm(vs, axis=1)[:, None]

    def unique_cn(self) -> list[int]:
        cn = self.coordination()
        return sorted({int(cn[np.where(self.types == t)[0][0]]) for t in np.unique(self.types)})

    def summary(self) -> dict:
        cn = self.coordination()
        return {
            "name": self.name, "dim": self.dim, "source": self.source, "spacegroup": self.spacegroup,
            "n_nodes": int(self.n_nodes), "n_edges": len(self.edges),
            "node_types": [{"type": int(t), "cn": int(cn[np.where(self.types == t)[0][0]]),
                            "count": int((self.types == t).sum())} for t in np.unique(self.types)],
            "precedent": self.precedent,
        }


def edges_from_distance(cell: np.ndarray, frac: np.ndarray, tol: float = 1.02) -> list:
    """Edges = all node pairs at the minimum inter-node distance (unit-edge 2D/3D nets)."""
    n = len(frac)
    cands = []
    rng = range(-1, 2)
    for i in range(n):
        for j in range(n):
            for s in itertools.product(rng, rng, rng):
                if i == j and s == (0, 0, 0):
                    continue
                d = np.linalg.norm((frac[j] + s - frac[i]) @ cell)
                cands.append((d, i, j, s))
    dmin = min(c[0] for c in cands)
    edges = set()
    for d, i, j, s in cands:
        if d <= dmin * tol:
            key = (i, j, s) if (i, j, s) <= (j, i, tuple(-x for x in s)) else (j, i, tuple(-x for x in s))
            edges.add(key)
    return sorted(edges)


def _net2d(name: str, a: tuple, b: tuple, frac: list) -> Net:
    cell = np.array([a, b, (0.0, 0.0, 1.0)], dtype=float)
    fr = np.array(frac, dtype=float)
    edges = [e for e in edges_from_distance(cell, fr) if e[2][2] == 0]
    return Net(name, 2, cell, fr, np.zeros(len(fr), dtype=int), edges, source="builtin-2d")


@lru_cache(maxsize=1)
def builtin_2d() -> dict[str, Net]:
    s3 = np.sqrt(3.0)
    nets = [
        _net2d("sql", (1, 0, 0), (0, 1, 0), [[0, 0, 0]]),
        _net2d("hcb", (s3, 0, 0), (-s3 / 2, 1.5, 0), [[1 / 3, 2 / 3, 0], [2 / 3, 1 / 3, 0]]),
        _net2d("kgm", (2, 0, 0), (-1, s3, 0), [[0.5, 0, 0], [0, 0.5, 0], [0.5, 0.5, 0]]),
        _net2d("hxl", (1, 0, 0), (-0.5, s3 / 2, 0), [[0, 0, 0]]),
    ]
    return {n.name: n for n in nets}


@lru_cache(maxsize=1)
def _rcsr_raw() -> dict[str, dict]:
    if not RCSR_CACHE.exists():
        return {}
    with gzip.open(RCSR_CACHE, "rt") as f:
        return json.load(f)


def _from_raw(name: str, d: dict) -> Net:
    edges = [(int(e[0]), int(e[1]), (int(e[2]), int(e[3]), int(e[4]))) for e in d["edges"]]
    return Net(name, 3, np.array(d["cell"], float), np.array(d["frac"], float), np.array(d["types"], int),
               edges, source="rcsr", spacegroup=d.get("spacegroup", ""), meta={"local": d.get("local", {})})


@lru_cache(maxsize=4096)
def get_net(name: str) -> Net:
    b2 = builtin_2d()
    if name in b2:
        return b2[name]
    raw = _rcsr_raw()
    if name not in raw:
        raise KeyError(f"unknown net '{name}'")
    return _from_raw(name, raw[name])


def list_nets() -> list[dict]:
    out = [n.summary() for n in builtin_2d().values()]
    for name, d in _rcsr_raw().items():
        out.append({"name": name, "dim": 3, "source": "rcsr", "spacegroup": d.get("spacegroup", ""),
                    "n_nodes": len(d["frac"]), "n_edges": len(d["edges"]),
                    "node_types": d.get("node_types", []), "precedent": name in HOF_PRECEDENT})
    return out


# ---------------- supercells & bipartite colouring ----------------

def supercell(net: Net, P: np.ndarray) -> Net:
    """Integer supercell with rows of P giving new lattice vectors in units of old ones."""
    P = np.asarray(P, dtype=int)
    new_cell = P @ net.cell
    Pinv = np.linalg.inv(P)
    n_rep = int(round(abs(np.linalg.det(P))))
    rng = range(-3, 4)
    pts = []
    for t in itertools.product(rng, rng, rng):
        f = np.asarray(t) @ Pinv
        if np.all(f > -1e-6) and np.all(f < 1 - 1e-6):
            pts.append(np.asarray(t))
    if len(pts) != n_rep:
        raise ValueError("supercell lattice-point enumeration failed")
    new_frac, new_types, origin = [], [], []
    for t in pts:
        for i in range(net.n_nodes):
            new_frac.append(((net.frac[i] + t) @ Pinv) % 1.0)
            new_types.append(net.types[i])
            origin.append((i, t))
    new_frac = np.array(new_frac)
    lookup = {}
    for k, (i, t) in enumerate(origin):
        lookup[(i, tuple(t))] = k

    def locate(i: int, cell_shift: np.ndarray) -> tuple[int, tuple]:
        f = ((net.frac[i] + cell_shift) @ Pinv)
        fl = np.floor(f + 1e-6).astype(int)
        f0 = f - fl
        for k in range(len(new_frac)):
            if origin[k][0] == i and np.allclose(new_frac[k], f0 % 1.0, atol=1e-5):
                return k, tuple(int(x) for x in fl)
        raise ValueError("node mapping failed")

    edges = []
    for k, (i, t) in enumerate(origin):
        for a, b, s in net.edges:
            if a == i:
                j, img = locate(b, t + np.asarray(s))
                edges.append((k, j, img))
    seen = set()
    uniq = []
    for i, j, s in edges:
        key = (i, j, s)
        rkey = (j, i, tuple(-x for x in s))
        if key in seen or rkey in seen:
            continue
        seen.add(key)
        uniq.append((i, j, s))
    if net.dim == 2:
        new_cell[2] = net.cell[2]
    return Net(net.name, net.dim, new_cell, new_frac, np.array(new_types), uniq, net.source, net.spacegroup,
               dict(net.meta, supercell=P.tolist()))


def two_coloring(net: Net) -> np.ndarray | None:
    color = -np.ones(net.n_nodes, dtype=int)
    adj: list[list[int]] = [[] for _ in range(net.n_nodes)]
    for i, j, _s in net.edges:
        if i == j:
            return None
        adj[i].append(j)
        adj[j].append(i)
    for start in range(net.n_nodes):
        if color[start] >= 0:
            continue
        color[start] = 0
        stack = [start]
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if color[v] < 0:
                    color[v] = 1 - color[u]
                    stack.append(v)
                elif color[v] == color[u]:
                    return None
    return color


_SUPERCELLS_3D = [np.eye(3, dtype=int), np.diag([2, 1, 1]), np.diag([1, 2, 1]), np.diag([1, 1, 2]),
                  np.array([[0, 1, 1], [1, 0, 1], [1, 1, 0]]), np.array([[1, 1, 0], [1, -1, 0], [0, 0, 1]]),
                  np.array([[1, 0, 1], [0, 1, 0], [1, 0, -1]]), np.array([[1, 0, 0], [0, 1, 1], [0, 1, -1]]),
                  np.diag([2, 2, 1]), np.diag([2, 1, 2]), np.diag([1, 2, 2]), np.diag([2, 2, 2])]
_SUPERCELLS_2D = [np.eye(3, dtype=int), np.array([[1, 1, 0], [1, -1, 0], [0, 0, 1]]), np.diag([2, 1, 1]),
                  np.diag([1, 2, 1]), np.diag([2, 2, 1])]


def bipartite_version(net: Net) -> tuple[Net, np.ndarray] | None:
    """Smallest supercell (from a short list) in which the net is 2-colourable."""
    for P in (_SUPERCELLS_2D if net.dim == 2 else _SUPERCELLS_3D):
        try:
            sc = net if np.array_equal(P, np.eye(3, dtype=int)) else supercell(net, P)
        except ValueError:
            continue
        col = two_coloring(sc)
        if col is not None:
            return sc, col
    return None


# ---------------- recommendation ----------------

def _local_by_type(net: Net) -> dict[int, np.ndarray]:
    loc = net.meta.get("local") if net.meta else None
    if loc:
        return {int(t): np.array(v, float) for t, v in loc.items()}
    out = {}
    for t in np.unique(net.types):
        i = int(np.where(net.types == t)[0][0])
        out[int(t)] = net.local_vectors(i)
    return out


def recommend(conn_unit: np.ndarray, *, max_rmsd: float = 0.35, top: int = 12, include_2d: bool = True,
              include_3d: bool = True, max_nodes: int = 64, planar: bool | None = None) -> list[dict]:
    """Rank single-node-type nets by fit of the building block's connection directions.

    Planar building blocks get a bonus on 2D layer nets (they stack into channels), 3D blocks on 3D nets.
    """
    k = len(conn_unit)
    if planar is None and k >= 3:
        sv = np.linalg.svd(conn_unit - conn_unit.mean(axis=0), compute_uv=False)
        planar = bool(sv[-1] < 0.15 * sv[0])
    results = []
    cands: list[tuple[str, Net | None, dict | None]] = []
    if include_2d:
        cands += [(n.name, n, None) for n in builtin_2d().values()]
    if include_3d:
        cands += [(name, None, d) for name, d in _rcsr_raw().items()]
    for name, net, raw in cands:
        if raw is not None:
            if len(raw.get("node_types", [])) == 0:
                continue
            if any(nt["cn"] != k for nt in raw["node_types"]) or len(raw["frac"]) > max_nodes:
                continue
            local = {int(t): np.array(v, float) for t, v in raw["local"].items()}
            dim = 3
        else:
            if any(c != k for c in net.unique_cn()):
                continue
            local = _local_by_type(net)
            dim = 2
        worst = 0.0
        for vecs in local.values():
            rmsd, _r, _p = best_match(conn_unit, vecs)
            worst = max(worst, rmsd)
        if worst <= max_rmsd:
            n_nodes = len(raw["frac"]) if raw is not None else net.n_nodes
            precedent = name in HOF_PRECEDENT
            dim_term = (-0.05 if dim == 2 else 0.0) if planar else (0.05 if dim == 2 else 0.0)
            rank = worst - (0.08 if precedent else 0) + 0.002 * n_nodes + dim_term
            results.append({"net": name, "dim": dim, "rmsd": round(worst, 3), "n_nodes": n_nodes,
                            "precedent": precedent, "rank": rank})
    results.sort(key=lambda r: r["rank"])
    return results[:top]


def recommend_binodal(conn_a: np.ndarray, conn_b: np.ndarray, *, max_rmsd: float = 0.4, top: int = 10,
                      max_nodes: int = 64) -> list[dict]:
    """Nets for two different building blocks (A–B edges only)."""
    ka, kb = len(conn_a), len(conn_b)
    results = []
    if ka == kb:
        for name in list(builtin_2d()) + list(_rcsr_raw()):
            try:
                net = get_net(name)
            except KeyError:
                continue
            if net.n_nodes > max_nodes or any(c != ka for c in net.unique_cn()):
                continue
            local = _local_by_type(net)
            worst = 0.0
            for vecs in local.values():
                worst = max(worst, best_match(conn_a, vecs)[0], best_match(conn_b, vecs)[0])
            if worst > max_rmsd:
                continue
            if bipartite_version(net) is None:
                continue
            results.append({"net": name, "dim": net.dim, "rmsd": round(worst, 3), "mode": "bipartite",
                            "precedent": net.precedent, "n_nodes": net.n_nodes,
                            "rank": worst - (0.08 if net.precedent else 0) + 0.002 * net.n_nodes})
    else:
        for name, d in _rcsr_raw().items():
            nts = d.get("node_types", [])
            if len(nts) != 2 or sorted(nt["cn"] for nt in nts) != sorted([ka, kb]):
                continue
            if len(d["frac"]) > max_nodes or not d.get("bipartite_types"):
                continue
            local = {int(t): np.array(v, float) for t, v in d["local"].items()}
            ta = [int(nt["type"]) for nt in nts if nt["cn"] == ka][0]
            tb = [int(nt["type"]) for nt in nts if nt["cn"] == kb][0]
            worst = max(best_match(conn_a, local[ta])[0], best_match(conn_b, local[tb])[0])
            if worst > max_rmsd:
                continue
            prec = name in HOF_PRECEDENT
            results.append({"net": name, "dim": 3, "rmsd": round(worst, 3), "mode": "binodal",
                            "type_a": ta, "type_b": tb, "precedent": prec, "n_nodes": len(d["frac"]),
                            "rank": worst - (0.08 if prec else 0) + 0.002 * len(d["frac"])})
    results.sort(key=lambda r: r["rank"])
    return results[:top]
