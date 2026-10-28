"""Builder robustness benchmark on experimental HOF tectons.

For each experimental tecton with >=3 builder-supported synthons, build it on its top recommended
net and record success, QC status, H-bond dimensionality and timing. Writes docs/validation/builder.md.

    python scripts/validate_builder.py [--limit 80]
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "validation"


def _build(smiles: str, net_name: str) -> dict:
    from ultrahofs.services.structures import BuildSpec, build

    res = build(BuildSpec(net=net_name, node=smiles))
    qc, info = res["qc"], res["info"]
    return {"net": net_name, "dim": res["dim"], "qc": qc["status"], "hbond_dim": qc["hbond_dimensionality"],
            "hb_per_mol": qc["hbonds_per_molecule"], "contacts": qc["n_close_contacts"],
            "x_mismatch": info["x_mismatch_max"], "synthon_angle": info.get("synthon_angle_max"),
            "n_atoms": len(res["atoms"])}


def run_one(smiles: str) -> dict:
    """Build on the top net of the embedding-checked ranking and, if different, of the direction-only ranking."""
    from ultrahofs.crystal.assemble import recommend_for_bb
    from ultrahofs.crystal.nets import recommend
    from ultrahofs.services.structures import cached_bb

    t0 = time.time()
    bb = cached_bb(smiles, False)
    recs = recommend_for_bb(bb, top=3)
    if not recs:
        return {"status": "no_net", "k": bb.k, "geometry": bb.geometry}
    res = _build(smiles, recs[0]["net"])
    res.update(status="built", k=bb.k, geometry=bb.geometry, seconds=round(time.time() - t0, 2))
    static_net = recommend(bb.unit, top=1)[0]["net"]
    res["static"] = res.copy() if static_net == res["net"] else _build(smiles, static_net)
    res["static"].pop("static", None)
    return res


def write_report(summary: dict) -> None:
    q, q0 = summary["qc"], summary["qc_direction_only_ranking"]
    no_net = summary["n_tectons"] - summary["built"]
    nets = ", ".join(f"{k} {v}" for k, v in summary["nets"].items())
    lines = [
        "# Builder robustness benchmark",
        "",
        f"Experimental HOFSyn tectons with ≥3 builder-supported synthons (≤120 heavy atoms): "
        f"**{summary['n_tectons']}**. Each is built on its top-ranked net with default options "
        f"(AA stacking for layers, no interpenetration, no relaxation) through the same service the API uses. "
        f"Run `python scripts/validate_builder.py` to reproduce (`--report-only` rewrites this page from "
        f"`builder.json`, which holds the per-tecton results).",
        "",
        "| ranking | ok | warning | fail |",
        "|---|---|---|---|",
        f"| embedding-checked (default) | {q.get('ok', 0)} | {q.get('warning', 0)} | {q.get('fail', 0)} |",
        f"| direction-only | {q0.get('ok', 0)} | {q0.get('warning', 0)} | {q0.get('fail', 0)} |",
        "",
        f"* built: **{summary['built']} / {summary['n_tectons']}**"
        + (f" ({no_net} without a net of matching connectivity)" if no_net else "")
        + f"; the embedding check changed the top net for {summary['top_net_changed_by_embedding_check']} tectons",
        f"* H-bond network dimensionality ≥ net dimensionality: **{summary['hbond_dim_matches_net']} / {summary['built']}**",
        f"* medians: build time {summary['median_seconds']} s, max connection mismatch "
        f"{summary['median_x_mismatch']} Å, max synthon pairing angle {summary['median_synthon_angle']}°",
        f"* nets used: {nets}",
        "",
        "## What the checks mean",
        "",
        "* **fail**: more intermolecular close contacts (heavy atoms < 2.6 Å, H···H < 1.6 Å, H···heavy < 1.5 Å) "
        "than max(2, number of molecules), or overlapping molecules. **warning**: fewer such contacts, an H-bond "
        "network of lower dimensionality than the net, or paired synthons more than 30° from head-on. All "
        "models are unrelaxed; MACE-OFF24 relaxation usually resolves warnings.",
        "* **Direction-only ranking** compares connection directions with each net's ideal vertex geometry. "
        "**Embedding-checked ranking** (default in the UI and API) also embeds the top candidates and penalises "
        "nets in which paired synthons cannot meet head-on (angle > 15°), connection points do not close "
        "(> 0.3 Å) or molecules would overlap.",
        "* An earlier assembler version scored 23 ok / 26 warning / 30 fail on this set (direction-only ranking). "
        "Its torsion search ignored hydrogen contacts, so it could leave carboxylic-acid or DAT pairs with their "
        "O–H/N–H groups facing each other (H···H ≈ 0.8 Å). Its automatic interlayer spacing also ignored the "
        "hydrogens of twisted aryl arms.",
        "* Remaining failures are mostly irregular or flexible tectons (no net closes without strain), tectons "
        "with mixed synthons of very different reach (e.g. COOH + pyridyl), and single-component salts that "
        "need counter-ions. The benchmark tests construction robustness, not whether the experimental polymorph "
        "is reproduced (experimental HOFs are often interpenetrated or solvated).",
    ]
    (OUT / "builder.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--report-only", action="store_true", help="rewrite builder.md from builder.json")
    args = ap.parse_args()
    if args.report_only:
        write_report(json.loads((OUT / "builder.json").read_text())["summary"])
        return
    from ultrahofs.chem.synthons import SYNTHON_BY_KEY
    from ultrahofs.db import SessionLocal
    from ultrahofs.ingest.parallel import run_parallel
    from ultrahofs.models import Molecule

    with SessionLocal() as db:
        mols = [m for m in db.execute(select(Molecule).where(Molecule.is_experimental_tecton.is_(True))).scalars()]
    todo = []
    for m in mols:
        supported = sum(s["count"] for s in (m.synthons or [])
                        if SYNTHON_BY_KEY.get(s["type"]) and SYNTHON_BY_KEY[s["type"]].geometry is not None)
        if supported >= 3 and m.heavy_atoms <= 120:
            todo.append(m.smiles)
    todo = todo[: args.limit]
    results = []
    for smi, status, res in run_parallel(run_one, todo, workers=8, timeout=180):
        if status == "ok":
            results.append(dict(res, smiles=smi))
        else:
            results.append({"status": status, "smiles": smi, "error": str(res)[:200]})
    built = [r for r in results if r["status"] == "built"]

    def median(vals: list) -> float | None:
        vals = sorted(v for v in vals if v is not None)
        return vals[len(vals) // 2] if vals else None

    summary = {
        "n_tectons": len(results),
        "built": len(built),
        "statuses": dict(Counter(r["status"] for r in results)),
        "qc": dict(Counter(r["qc"] for r in built)),
        "qc_direction_only_ranking": dict(Counter(r["static"]["qc"] for r in built)),
        "top_net_changed_by_embedding_check": sum(1 for r in built if r["static"]["net"] != r["net"]),
        "nets": dict(Counter(r["net"] for r in built).most_common(12)),
        "hbond_dim_matches_net": sum(1 for r in built if r["hbond_dim"] >= r["dim"]),
        "median_seconds": median([r["seconds"] for r in built]),
        "median_x_mismatch": median([r["x_mismatch"] for r in built]),
        "median_synthon_angle": median([r["synthon_angle"] for r in built]),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "builder.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2))
    write_report(summary)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
