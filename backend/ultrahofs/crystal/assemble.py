"""HOF assembler: place building blocks on net vertices with H-bond-aware scaling."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np
from ase import Atoms
from ase.neighborlist import neighbor_list

from ..chem.conformers import best_match
from .bb import BuildingBlock
from .nets import Net, bipartite_version, get_net, recommend, recommend_binodal


class AssemblyError(ValueError):
    pass


@dataclass
class LayerOptions:
    stacking: str = "AA"  # AA | AB | ABC
    interlayer: float | None = None  # Å, None = automatic
    slip: tuple[float, float] = (0.0, 0.0)  # Å offset along a, b (AA stacking)
    shift: tuple[float, float] | None = None  # fractional in-plane shift for AB / ABC


@dataclass
class BuildOptions:
    align_synthons: bool = True
    interpenetration: int = 1
    layer: LayerOptions = field(default_factory=LayerOptions)
    edge_bb: BuildingBlock | None = None


@dataclass
class Assembled:
    cell: np.ndarray
    symbols: list[str]
    positions: np.ndarray
    mol_index: np.ndarray
    bb_index: np.ndarray
    info: dict

    def to_ase(self) -> Atoms:
        return Atoms(self.symbols, positions=self.positions, cell=self.cell, pbc=True)


def _rotate(points: np.ndarray, origin: np.ndarray, axis: np.ndarray, theta: float) -> np.ndarray:
    k = axis / np.linalg.norm(axis)
    p = points - origin
    c, s = np.cos(theta), np.sin(theta)
    rot = p * c + np.cross(k, p) * s + np.outer(p @ k, k) * (1 - c)
    return rot + origin


@dataclass
class _Site:
    """A placed connection: global atom indices and image shift for one end of an edge."""

    node: int
    group: np.ndarray
    axis: tuple[int, int] | None
    donors_h: np.ndarray
    acceptors: np.ndarray
    shift: np.ndarray


def _align_pair(pos: np.ndarray, heavy: np.ndarray, sa: _Site, sb: _Site, cell: np.ndarray) -> float:
    """Rotate the two synthon groups of an edge about their single bonds to form D–H···A pairs."""
    if sa.axis is None and sb.axis is None:
        return 0.0
    ga, gb = sa.group, sb.group
    ia = {g: k for k, g in enumerate(ga)}
    ib = {g: k for k, g in enumerate(gb)}
    don_a = np.array([ia[h] for h in sa.donors_h], dtype=int)
    acc_a = np.array([ia[x] for x in sa.acceptors], dtype=int)
    don_b = np.array([ib[h] for h in sb.donors_h], dtype=int)
    acc_b = np.array([ib[x] for x in sb.acceptors], dtype=int)
    # minimum allowed contact per atom pair (heavy–heavy 2.45, H–heavy 1.55, H–H 1.9 Å); a pose with the
    # two O–H/N–H groups facing each other scores like a real dimer on H···A alone, so H contacts must count
    hv_a = np.array([heavy[g] for g in ga])
    hv_b = np.array([heavy[g] for g in gb])
    n_heavy = hv_a[:, None].astype(int) + hv_b[None, :].astype(int)
    d_min = np.where(n_heavy == 2, 2.45, np.where(n_heavy == 1, 1.55, 1.9))
    shift_a = sa.shift @ cell
    shift_b = sb.shift @ cell
    base_a = pos[ga] + shift_a
    base_b = pos[gb] + shift_b

    def rotated(base: np.ndarray, site: _Site, th: float, shift: np.ndarray) -> np.ndarray:
        if site.axis is None or th == 0.0:
            return base
        o = pos[site.axis[0]] + shift
        return _rotate(base, o, pos[site.axis[1]] - pos[site.axis[0]], th)

    def hb_term(p_d: np.ndarray, d_idx: np.ndarray, p_a: np.ndarray, a_idx: np.ndarray) -> float:
        if not len(d_idx) or not len(a_idx):
            return 0.0
        d = np.linalg.norm(p_d[d_idx][:, None, :] - p_a[a_idx][None, :, :], axis=2)
        return float(np.exp(-(((d - 1.75) / 0.35) ** 2)).max(axis=1).sum())

    def score(pa: np.ndarray, pb: np.ndarray) -> float:
        s = hb_term(pa, don_a, pb, acc_b) + hb_term(pb, don_b, pa, acc_a)
        d = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=2)
        return s - 2.0 * float(np.clip(d_min - d, 0, None).sum())

    grid_a = np.radians(np.arange(0, 360, 30)) if sa.axis else np.array([0.0])
    grid_b = np.radians(np.arange(0, 360, 30)) if sb.axis else np.array([0.0])
    best = (-np.inf, 0.0, 0.0)
    for ta, tb in itertools.product(grid_a, grid_b):
        s = score(rotated(base_a, sa, ta, shift_a), rotated(base_b, sb, tb, shift_b))
        if s > best[0]:
            best = (s, ta, tb)
    fine = np.radians(np.arange(-20, 21, 5))
    _s0, ta0, tb0 = best
    for da, db in itertools.product(fine if sa.axis else [0.0], fine if sb.axis else [0.0]):
        ta, tb = ta0 + da, tb0 + db
        s = score(rotated(base_a, sa, ta, shift_a), rotated(base_b, sb, tb, shift_b))
        if s > best[0]:
            best = (s, ta, tb)
    s, ta, tb = best
    if sa.axis is not None and ta != 0.0:
        pos[ga] = _rotate(pos[ga], pos[sa.axis[0]], pos[sa.axis[1]] - pos[sa.axis[0]], ta)
    if sb.axis is not None and tb != 0.0:
        pos[gb] = _rotate(pos[gb], pos[sb.axis[0]], pos[sb.axis[1]] - pos[sb.axis[0]], tb)
    return s


def _orient(net: Net, node_bbs: list[BuildingBlock], centres: np.ndarray, cell: np.ndarray):
    """Best rotation + connection→edge assignment for every node given current geometry."""
    rots, fit = [], []
    end_assign: dict[tuple[int, int], tuple[int, int]] = {}
    for i in range(net.n_nodes):
        inc = []
        for k, (a, b, sh) in enumerate(net.edges):
            v = centres[b] + np.asarray(sh) @ cell - centres[a]
            if a == i:
                inc.append((k, +1, v))
            if b == i:
                inc.append((k, -1, -v))
        targets = np.array([v / np.linalg.norm(v) for _k, _sg, v in inc])
        bb = node_bbs[i]
        rmsd, R, perm = best_match(bb.unit, targets)
        fit.append(rmsd)
        rots.append(R)
        for m in range(bb.k):
            k, sign, _v = inc[perm[m]]
            end_assign[(k, 0 if sign > 0 else 1)] = (i, m)
    return rots, fit, end_assign


def _refine_embedding(net: Net, node_bbs: list[BuildingBlock], centres: np.ndarray, cell: np.ndarray,
                      rots: list[np.ndarray], end_assign: dict, edge_len: float,
                      reg: float = 1e-3) -> tuple[np.ndarray, np.ndarray]:
    """Joint least squares for node positions and cell so that paired X points coincide."""
    n = net.n_nodes
    dims = 2 if net.dim == 2 else 3
    nu = n * dims + dims * dims
    rows, rhs = [], []
    for k, (a, b, sh) in enumerate(net.edges):
        ia, ma = end_assign[(k, 0)]
        ib, mb = end_assign[(k, 1)]
        wa = node_bbs[ia].conn[ma] @ rots[ia]
        wb = node_bbs[ib].conn[mb] @ rots[ib]
        target = -(wb - wa)
        if edge_len > 0:
            cur = centres[b] + np.asarray(sh) @ cell + wb - centres[a] - wa
            target = target + edge_len * cur / max(np.linalg.norm(cur), 1e-9)
        s = np.asarray(sh, dtype=float)[:dims]
        for d in range(dims):
            row = np.zeros(nu)
            row[b * dims + d] += 1.0
            row[a * dims + d] -= 1.0
            for e in range(dims):
                row[n * dims + e * dims + d] += s[e]
            rows.append(row)
            rhs.append(target[d])
    # weak regularisation towards the current geometry fixes gauge freedom
    for i in range(n):
        for d in range(dims):
            row = np.zeros(nu)
            row[i * dims + d] = reg
            rows.append(row)
            rhs.append(reg * centres[i][d])
    for e in range(dims):
        for d in range(dims):
            row = np.zeros(nu)
            row[n * dims + e * dims + d] = reg
            rows.append(row)
            rhs.append(reg * cell[e][d])
    sol, *_ = np.linalg.lstsq(np.array(rows), np.array(rhs), rcond=None)
    new_c = centres.copy()
    new_cell = cell.copy()
    new_c[:, :dims] = sol[: n * dims].reshape(n, dims)
    new_cell[:dims, :dims] = sol[n * dims:].reshape(dims, dims)
    if abs(np.linalg.det(new_cell)) < 1e-6 * abs(np.linalg.det(cell)):
        return centres, cell
    return new_c, new_cell


def _embed(net: Net, node_bbs: list[BuildingBlock], edge_len: float, refine: bool = True):
    """Scale the net, orient every node and refine node positions + cell so paired X points coincide."""
    e_len = np.array([np.linalg.norm(net.edge_vector(k)) for k in range(len(net.edges))])
    target = np.array([node_bbs[i].radius + node_bbs[j].radius + edge_len for i, j, _s in net.edges])
    s = float((e_len * target).sum() / (e_len**2).sum())
    cell = net.cell.copy()
    if net.dim == 2:
        cell[:2] *= s
        cell[2] = [0.0, 0.0, 1.0]
    else:
        cell *= s
    centres = net.frac @ cell
    rots, fit, end_assign = _orient(net, node_bbs, centres, cell)
    if refine:
        for _it in range(4):
            centres, cell = _refine_embedding(net, node_bbs, centres, cell, rots, end_assign, edge_len)
            rots, fit, end_assign = _orient(net, node_bbs, centres, cell)
    return s, cell, centres, rots, fit, end_assign


def _angle(u: np.ndarray, v: np.ndarray) -> float:
    return float(np.degrees(np.arccos(np.clip(np.dot(u, v), -1.0, 1.0))))


def _edge_geometry(net: Net, node_bbs: list[BuildingBlock], centres: np.ndarray, cell: np.ndarray,
                   rots: list[np.ndarray], end_assign: dict, edge_len: float) -> tuple[list[float], list[float]]:
    """Per-edge X-point mismatch (Å) and deviation of paired synthons from head-on pairing (degrees).

    Without an edge linker the two pairing directions should be antiparallel; with a linker each
    should point along the linker axis.
    """
    mismatch, angles = [], []
    for k, (_a, _b, sh) in enumerate(net.edges):
        ia, ma = end_assign[(k, 0)]
        ib, mb = end_assign[(k, 1)]
        xa = centres[ia] + node_bbs[ia].conn[ma] @ rots[ia]
        xb = centres[ib] + node_bbs[ib].conn[mb] @ rots[ib] + np.asarray(sh) @ cell
        mismatch.append(float(np.linalg.norm(xa - xb)) if edge_len == 0
                        else float(abs(np.linalg.norm(xb - xa) - edge_len)))
        da, db = node_bbs[ia].conn_dir, node_bbs[ib].conn_dir
        if da is None or db is None:
            continue
        va, vb = da[ma] @ rots[ia], db[mb] @ rots[ib]
        if edge_len == 0:
            angles.append(_angle(va, -vb))
        else:
            e = (xb - xa) / max(float(np.linalg.norm(xb - xa)), 1e-9)
            angles += [_angle(va, e), _angle(vb, -e)]
    return mismatch, angles


def _node_separation(net: Net, node_bbs: list[BuildingBlock], centres: np.ndarray, cell: np.ndarray) -> float:
    """Closest approach of any two node centres (periodic) relative to the mean bonded distance."""
    rng = (-1, 0, 1)
    shifts = np.array([t for t in itertools.product(rng, rng, rng if net.dim == 3 else (0,))], float) @ cell
    diff = centres[:, None, None, :] - centres[None, :, None, :] - shifts[None, None, :, :]
    dist = np.linalg.norm(diff, axis=3)
    n = len(centres)
    zero = int(np.flatnonzero(np.all(np.abs(shifts) < 1e-9, axis=1))[0])
    dist[np.arange(n), np.arange(n), zero] = np.inf
    bonded = np.mean([node_bbs[i].radius + node_bbs[j].radius for i, j, _s in net.edges])
    return float(dist.min() / max(bonded, 1e-6))


def synthon_fit(net: Net, node_bbs: list[BuildingBlock], edge_bb: BuildingBlock | None = None) -> dict:
    """Cheap net/building-block compatibility check (embedding only, no atoms placed)."""
    edge_len = float(np.linalg.norm(edge_bb.conn[0] - edge_bb.conn[1])) if edge_bb is not None else 0.0
    _s, cell, centres, rots, fit, end_assign = _embed(net, node_bbs, edge_len)
    mismatch, angles = _edge_geometry(net, node_bbs, centres, cell, rots, end_assign, edge_len)
    return {"x_mismatch_max": round(max(mismatch), 3) if mismatch else 0.0,
            "synthon_angle_max": round(max(angles), 1) if angles else None,
            "node_fit_rmsd_max": round(float(max(fit)), 3),
            "node_sep_ratio": round(_node_separation(net, node_bbs, centres, cell), 3)}


# paired synthons tolerate some bending and X points some strain before a net becomes implausible;
# node centres much closer than bonded neighbours mean overlapping molecules
ANGLE_TOLERANCE = 15.0
MISMATCH_TOLERANCE = 0.3
NODE_SEP_MIN = 0.7


def fit_penalty(fit: dict) -> float:
    ang = fit.get("synthon_angle_max") or 0.0
    return (0.005 * max(0.0, ang - ANGLE_TOLERANCE)
            + 0.1 * max(0.0, fit["x_mismatch_max"] - MISMATCH_TOLERANCE)
            + 0.5 * max(0.0, NODE_SEP_MIN - fit.get("node_sep_ratio", 1.0)))


def arrange_nodes(net: Net, mode: str, a: BuildingBlock,
                  b: BuildingBlock | None = None) -> tuple[Net, list[BuildingBlock]]:
    """Building block for every node of ``net`` (bipartite mode returns the 2-coloured supercell net)."""
    if mode == "single":
        return net, [a] * net.n_nodes
    if b is None:
        raise AssemblyError(f"{mode} mode needs two building blocks")
    if mode == "bipartite":
        if a.k != b.k:
            raise AssemblyError("bipartite mode needs two building blocks with the same connectivity")
        bv = bipartite_version(net)
        if bv is None:
            raise AssemblyError(f"net {net.name} is not 2-colourable in a small supercell")
        net2, col = bv
        return net2, [a if c == 0 else b for c in col]
    if mode == "binodal":
        cn = net.coordination()
        if len(np.unique(net.types)) != 2:
            raise AssemblyError("binodal mode needs a net with exactly two node types")
        node_bbs = [a if cn[i] == a.k else b for i in range(net.n_nodes)]
        if any(node_bbs[i].k != cn[i] for i in range(net.n_nodes)):
            raise AssemblyError("building-block connectivities do not match the net's node types")
        return net, node_bbs
    raise AssemblyError(f"unknown mode {mode}")


def rerank(recs: list[dict], a: BuildingBlock, b: BuildingBlock | None = None,
           edge_bb: BuildingBlock | None = None, top: int = 12) -> list[dict]:
    """Re-rank direction-based net recommendations with an actual embedding: nets where the paired
    synthons cannot meet head-on or the connection points cannot close are demoted."""
    for r in recs:
        try:
            net, nodes = arrange_nodes(get_net(r["net"]), r.get("mode", "single"), a, b)
            f = synthon_fit(net, nodes, edge_bb)
        except (AssemblyError, KeyError, ValueError, np.linalg.LinAlgError):
            continue
        r["x_mismatch"] = f["x_mismatch_max"]
        r["synthon_angle"] = f["synthon_angle_max"]
        r["node_fit"] = f["node_fit_rmsd_max"]
        r["node_sep"] = f["node_sep_ratio"]
        # the refined embedding may shear the cell, so its node fit replaces the ideal-net direction RMSD
        r["rank"] = r["rank"] - r["rmsd"] + f["node_fit_rmsd_max"] + fit_penalty(f)
        r["fit_ok"] = fit_penalty(f) == 0.0
    recs.sort(key=lambda r: r["rank"])
    return recs[:top]


def recommend_for_bb(bb: BuildingBlock, *, top: int = 12, edge_bb: BuildingBlock | None = None,
                     **kw) -> list[dict]:
    """Single-node-type net recommendations for a building block, checked by embedding."""
    return rerank(recommend(bb.unit, top=max(2 * top, 16), **kw), bb, edge_bb=edge_bb, top=top)


def recommend_binodal_for_bb(a: BuildingBlock, b: BuildingBlock, *, top: int = 10, **kw) -> list[dict]:
    return rerank(recommend_binodal(a.unit, b.unit, top=max(2 * top, 16), **kw), a, b, top=top)


def assemble(net: Net, node_bbs: list[BuildingBlock], opts: BuildOptions | None = None,
             refine: bool = True) -> Assembled:
    opts = opts or BuildOptions()
    n = net.n_nodes
    if len(node_bbs) != n:
        raise AssemblyError("one building block per net node is required")
    cn = net.coordination()
    for i in range(n):
        if node_bbs[i].k != cn[i]:
            raise AssemblyError(f"node {i} has CN {cn[i]} but building block has {node_bbs[i].k} connections")
    ebb = opts.edge_bb
    edge_len = float(np.linalg.norm(ebb.conn[0] - ebb.conn[1])) if ebb is not None else 0.0
    if ebb is not None and ebb.k != 2:
        raise AssemblyError("edge building block must have exactly 2 connections")

    s, cell, centres, rots, fit, end_assign = _embed(net, node_bbs, edge_len, refine)

    pos_list, sym_list, mol_idx = [], [], []
    offsets = []
    natoms = 0
    for i in range(n):
        bb = node_bbs[i]
        offsets.append(natoms)
        pos_list.append(centres[i] + bb.coords @ rots[i])
        sym_list += bb.symbols
        mol_idx += [i] * len(bb.symbols)
        natoms += len(bb.symbols)

    mismatch, angles = _edge_geometry(net, node_bbs, centres, cell, rots, end_assign, edge_len)

    pos = np.vstack(pos_list)
    symbols = list(sym_list)
    mol_index = np.array(mol_idx)
    heavy = np.array([sym != "H" for sym in symbols])

    def site(node: int, m: int, shift: np.ndarray) -> _Site:
        c = node_bbs[node].connections[m]
        off = offsets[node]
        return _Site(node, np.array(c.group) + off,
                     (c.axis[0] + off, c.axis[1] + off) if c.axis else None,
                     np.array(c.donors_h, dtype=int) + off, np.array(c.acceptors, dtype=int) + off,
                     np.asarray(shift, dtype=float))

    # 3) optional 2-connected edge linkers
    pairs: list[tuple[_Site, _Site]] = []
    next_mol = n
    if ebb is not None:
        extra_pos, extra_sym, extra_mol = [], [], []
        for k, (_a, _b, sh) in enumerate(net.edges):
            ia, ma = end_assign[(k, 0)]
            ib, mb = end_assign[(k, 1)]
            xa = centres[ia] + node_bbs[ia].conn[ma] @ rots[ia]
            xb = centres[ib] + node_bbs[ib].conn[mb] @ rots[ib] + np.asarray(sh) @ cell
            d = xb - xa
            e = d / np.linalg.norm(d)
            mid = 0.5 * (xa + xb)
            _r, R, perm = best_match(ebb.unit, np.array([-e, e]))
            best_c, best_q = None, -np.inf
            for th in np.radians(np.arange(0, 360, 30)):
                c = _rotate(ebb.coords @ R + mid, mid, e, th)
                hv = np.array([sy != "H" for sy in ebb.symbols])
                near = np.linalg.norm(pos[heavy] - mid, axis=1) < 12
                if near.any():
                    dd = np.linalg.norm(c[hv][:, None, :] - pos[heavy][near][None, :, :], axis=2).min()
                else:
                    dd = 9.0
                if dd > best_q:
                    best_q, best_c = dd, c
            off = natoms + sum(len(p) for p in extra_pos)
            extra_pos.append(best_c)
            extra_sym += ebb.symbols
            extra_mol += [next_mol] * len(ebb.symbols)
            next_mol += 1
            # pair sites: node a conn ↔ linker end facing a; linker other end ↔ node b conn
            m_to_a = int(np.argmax([np.dot(ebb.unit[m] @ R, -e) for m in range(2)]))
            m_to_b = 1 - m_to_a
            for m_link, (node, m_node, shift) in ((m_to_a, (ia, ma, np.zeros(3))), (m_to_b, (ib, mb, np.asarray(sh)))):
                c = ebb.connections[m_link]
                ls = _Site(-1, np.array(c.group) + off, (c.axis[0] + off, c.axis[1] + off) if c.axis else None,
                           np.array(c.donors_h, dtype=int) + off, np.array(c.acceptors, dtype=int) + off,
                           np.zeros(3))
                pairs.append((site(node, m_node, shift), ls))
        pos = np.vstack([pos] + extra_pos)
        symbols += extra_sym
        mol_index = np.concatenate([mol_index, np.array(extra_mol)])
        heavy = np.array([sym != "H" for sym in symbols])
    else:
        for k, (_a, _b, sh) in enumerate(net.edges):
            ia, ma = end_assign[(k, 0)]
            ib, mb = end_assign[(k, 1)]
            pairs.append((site(ia, ma, np.zeros(3)), site(ib, mb, np.asarray(sh))))

    # 4) synthon torsion alignment
    pair_scores = []
    if opts.align_synthons:
        for sa, sb in pairs:
            pair_scores.append(_align_pair(pos, heavy, sa, sb, cell))

    info = {
        "net": net.name, "net_dim": net.dim, "scale": round(s, 4),
        "node_fit_rmsd_max": round(float(max(fit)), 3), "node_fit_rmsd_mean": round(float(np.mean(fit)), 3),
        "x_mismatch_max": round(float(max(mismatch)), 3) if mismatch else 0.0,
        "x_mismatch_mean": round(float(np.mean(mismatch)), 3) if mismatch else 0.0,
        "synthon_angle_max": round(float(max(angles)), 1) if angles else None,
        "synthon_angle_mean": round(float(np.mean(angles)), 1) if angles else None,
        "n_edges": len(net.edges), "n_nodes": n, "edge_linker": ebb is not None,
        "synthon_pair_score_mean": round(float(np.mean(pair_scores)), 3) if pair_scores else None,
    }
    bb_ids = np.array([0] * len(symbols))
    out = Assembled(cell, symbols, pos, mol_index, bb_ids, info)
    if net.dim == 2:
        out = stack_layers(out, opts.layer, net.name)
    if opts.interpenetration > 1:
        if net.dim == 2:
            raise AssemblyError("interpenetration is only supported for 3D nets")
        out = interpenetrate(out, opts.interpenetration)
    return out


def default_shift(net_name: str) -> tuple[float, float]:
    return (0.5, 0.5) if net_name.startswith("sql") else (1 / 3, 2 / 3)


def stack_layers(layer: Assembled, lo: LayerOptions, net_name: str) -> Assembled:
    pos = layer.positions.copy()
    heavy = np.array([s != "H" for s in layer.symbols])
    pos[:, 2] -= pos[heavy, 2].mean()
    zext = float(pos[heavy, 2].max() - pos[heavy, 2].min())
    # twisted aryl arms put H atoms well outside the heavy-atom slab: keep H···H ≥ 2.4 Å between layers
    zext_all = float(pos[:, 2].max() - pos[:, 2].min())
    d = lo.interlayer if lo.interlayer else max(3.4, zext + 3.2, zext_all + 2.4)
    a, b = layer.cell[0], layer.cell[1]
    ahat, bhat = a / np.linalg.norm(a), b / np.linalg.norm(b)
    mode = lo.stacking.upper()
    n_layers = {"AA": 1, "AB": 2, "ABC": 3}.get(mode)
    if n_layers is None:
        raise AssemblyError(f"unknown stacking '{lo.stacking}'")
    shift = np.array(lo.shift if lo.shift else default_shift(net_name))
    if mode == "AA":
        c = lo.slip[0] * ahat + lo.slip[1] * bhat + np.array([0.0, 0.0, d])
        cell = np.array([a, b, c])
        return Assembled(cell, layer.symbols, pos, layer.mol_index, layer.bb_index,
                         dict(layer.info, stacking="AA", interlayer=round(d, 3), slip=list(lo.slip),
                              layer_thickness=round(zext, 3)))
    cell = np.array([a, b, [0.0, 0.0, n_layers * d]])
    all_pos, syms, mols, bbs = [], [], [], []
    nmol = int(layer.mol_index.max()) + 1
    for L in range(n_layers):
        t = (L * shift[0]) * a + (L * shift[1]) * b + np.array([0.0, 0.0, L * d])
        all_pos.append(pos + t)
        syms += layer.symbols
        mols.append(layer.mol_index + L * nmol)
        bbs.append(layer.bb_index)
    return Assembled(cell, syms, np.vstack(all_pos), np.concatenate(mols), np.concatenate(bbs),
                     dict(layer.info, stacking=mode, interlayer=round(d, 3), shift=shift.tolist(),
                          layer_thickness=round(zext, 3)))


def _min_intercopy_distance(base: Atoms, copies: list[np.ndarray], cutoff: float = 4.0) -> float:
    n = len(base)
    allpos = np.vstack([base.positions] + copies)
    sym = list(base.get_chemical_symbols()) * (1 + len(copies))
    at = Atoms(sym, positions=allpos, cell=base.cell, pbc=True)
    heavy = np.array([s != "H" for s in sym])
    i, j, d = neighbor_list("ijd", at, cutoff)
    mask = heavy[i] & heavy[j] & ((i // n) != (j // n))
    return float(d[mask].min()) if mask.any() else cutoff


def interpenetrate(fw: Assembled, n: int) -> Assembled:
    if n < 2:
        return fw
    if n > 6:
        raise AssemblyError("interpenetration degree must be <= 6")
    base = fw.to_ase()
    cands = [np.array(t) / n for t in itertools.product(range(n), repeat=3) if any(t)]
    node_c = np.array([fw.positions[fw.mol_index == m].mean(axis=0) for m in np.unique(fw.mol_index)])

    def centre_sep(t: np.ndarray) -> float:
        best = np.inf
        for m in range(1, n):
            shifted = node_c + (m * t) @ fw.cell
            diff = shifted[:, None, :] - node_c[None, :, :]
            frac = diff @ np.linalg.inv(fw.cell)
            frac -= np.rint(frac)
            best = min(best, float(np.linalg.norm(frac @ fw.cell, axis=2).min()))
        return best

    ranked = sorted(cands, key=lambda t: -centre_sep(t))[:6]
    best_t, best_d = None, -1.0
    for t in ranked:
        copies = [fw.positions + (m * t) @ fw.cell for m in range(1, n)]
        d = _min_intercopy_distance(base, copies)
        if d > best_d:
            best_t, best_d = t, d
    assert best_t is not None
    nmol = int(fw.mol_index.max()) + 1
    pos = np.vstack([fw.positions] + [fw.positions + (m * best_t) @ fw.cell for m in range(1, n)])
    mols = np.concatenate([fw.mol_index + m * nmol for m in range(n)])
    return Assembled(fw.cell, fw.symbols * n, pos, mols, np.concatenate([fw.bb_index] * n),
                     dict(fw.info, interpenetration=n, interpenetration_vector=best_t.round(4).tolist(),
                          interpenetration_min_distance=round(best_d, 3)))
