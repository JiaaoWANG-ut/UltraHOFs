"""Build the RCSR net cache used by the UltraHOFs crystal builder (run once).

PORMAKE (MIT) ships RCSR topologies; we convert them to a compact JSON so the web app never
has to import PORMAKE at runtime.

    python scripts/build_net_cache.py --workers 8
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "backend" / "ultrahofs" / "data" / "nets" / "rcsr_pormake.json.gz"


def convert(name: str):  # noqa: ANN201
    import warnings

    warnings.filterwarnings("ignore")
    import pormake as pm

    try:
        topo = pm.Database().get_topo(name)
    except Exception as e:  # noqa: BLE001
        return name, None, f"load: {e}"
    try:
        atoms = topo.atoms
        cell = np.array(atoms.cell.array, float)
        node_idx = list(topo.node_indices)
        if len(node_idx) > 200:
            return name, None, "too many nodes"
        pos = atoms.positions
        inv = np.linalg.inv(cell.T)
        frac_all = (inv @ pos.T).T
        node_map = {int(n): k for k, n in enumerate(node_idx)}
        frac = np.array([frac_all[n] % 1.0 for n in node_idx])
        types = [int(topo.node_types[n]) for n in node_idx]
        edges = []
        for e in topo.edge_indices:
            nbs = topo.neighbor_list[e]
            if len(nbs) != 2:
                return name, None, "edge without two neighbours"
            ends = []
            for nb in nbs:
                cart = pos[e] + np.asarray(nb.distance_vector)
                f = inv @ cart
                k = node_map[int(nb.index)]
                img = np.rint(f - frac[k]).astype(int)
                if not np.allclose(f - img, frac[k], atol=1e-3):
                    return name, None, "image mismatch"
                ends.append((k, img))
            (a, sa), (b, sb) = ends
            s = (sb - sa).tolist()
            edges.append([a, b, *s])
        tarr = np.array(types)
        cn = np.zeros(len(frac), int)
        for a, b, *_ in edges:
            cn[a] += 1
            cn[b] += 1
        node_types = []
        local = {}
        for t in sorted(set(types)):
            i = int(np.where(tarr == t)[0][0])
            node_types.append({"type": t, "cn": int(cn[i]), "count": int((tarr == t).sum())})
            vecs = []
            for a, b, s0, s1, s2 in edges:
                v = (frac[b] + np.array([s0, s1, s2]) - frac[a]) @ cell
                if a == i:
                    vecs.append(v)
                if b == i:
                    vecs.append(-v)
            vecs = np.array(vecs)
            local[str(t)] = np.round(vecs / np.linalg.norm(vecs, axis=1)[:, None], 5).tolist()
        bip = len(set(types)) == 2 and all(types[a] != types[b] for a, b, *_ in edges)
        return name, {
            "cell": np.round(cell, 6).tolist(),
            "frac": np.round(frac, 6).tolist(),
            "types": types,
            "edges": edges,
            "spacegroup": str(getattr(topo, "spacegroup", "") or ""),
            "node_types": node_types,
            "local": local,
            "bipartite_types": bip,
        }, ""
    except Exception as e:  # noqa: BLE001
        return name, None, f"convert: {e}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    import pormake as pm

    names = list(pm.Database().topology_list)
    if args.limit:
        names = names[: args.limit]
    t = time.time()
    out, failed = {}, {}
    with Pool(args.workers) as pool:
        for k, (name, d, err) in enumerate(pool.imap_unordered(convert, names, chunksize=8)):
            if d is None:
                failed[name] = err
            else:
                out[name] = d
            if (k + 1) % 200 == 0:
                print(f"{k + 1}/{len(names)} ({time.time() - t:.0f}s)", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wt") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {len(out)} nets to {OUT} ({OUT.stat().st_size / 1e6:.1f} MB); failed {len(failed)}")
    for k, v in list(failed.items())[:10]:
        print("  failed", k, v)
    sys.exit(0)


if __name__ == "__main__":
    main()
