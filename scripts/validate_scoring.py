"""Scoring validation: experimental HOF tectons vs. a background set of generic organic molecules.

This is a positive–unlabeled style check (background molecules are not proven non-HOFs).
Writes docs/validation/scoring.md and scoring.json.

    python scripts/validate_scoring.py
"""

from __future__ import annotations

import json
import statistics as st
from pathlib import Path

from rdkit import Chem
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "validation"

BACKGROUND = [
    # simple / flexible acids and diacids
    "CC(=O)O", "OC(=O)CC(O)=O", "OC(=O)CCC(O)=O", "OC(=O)CCCCC(O)=O", "OC(=O)CCCCCCCCC(O)=O", "OC(=O)C=CC(O)=O",
    "OC(=O)CC(O)(CC(O)=O)C(O)=O", "OC(=O)CCCN(CCCC(O)=O)CCCC(O)=O", "OC(=O)c1ccccc1", "OC(=O)c1ccccc1C(O)=O",
    "OC(=O)c1cccc(C(O)=O)c1", "OC(=O)c1ccc(cc1)C(O)=O", "OC(=O)CCc1ccccc1", "OC(=O)C(O)C(O)C(O)=O",
    "OC(=O)CCCCCCCC=CCCCCCCCC", "OC(=O)c1ccc(O)cc1", "OC(=O)c1ccncc1", "OC(=O)CN", "CC(N)C(O)=O",
    "NC(CCC(O)=O)C(O)=O", "NC(Cc1ccccc1)C(O)=O", "NCCCCC(N)C(O)=O",
    # drugs / drug-like
    "CC(C)Cc1ccc(C(C)C(O)=O)cc1", "CC(=O)Oc1ccccc1C(O)=O", "CC(=O)Nc1ccc(O)cc1", "COc1ccc2cc(C(C)C(O)=O)ccc2c1",
    "CN1C(=O)CN=C(c2ccccc2)c2cc(Cl)ccc21", "CN1CCC[C@H]1c1cccnc1", "CN1C=NC2=C1C(=O)N(C)C(=O)N2C",
    "OC(=O)Cc1ccccc1Nc1c(Cl)cccc1Cl", "CC(C)NCC(O)COc1cccc2ccccc12", "NC(=O)c1cccnc1", "O=C(O)c1cc(O)c(O)c(O)c1",
    "CC(C)(C)NCC(O)c1ccc(O)c(CO)c1", "Clc1ccc(cc1)C(c1ccccc1)N1CCN(CC1)CCOCC(O)=O", "CC1=C(C(=O)O)N2C(=O)C(NC(=O)Cc3ccccc3)C2SC1",
    "NS(=O)(=O)c1cc(C(O)=O)c(NCc2ccco2)cc1Cl", "OCC(O)CO", "OC[C@H]1OC(O)[C@H](O)[C@@H](O)[C@@H]1O",
    "C(C(C(C(C(CO)O)O)O)O)O", "O=C(N)N", "NC(=O)CCCCC(N)=O", "CC(=O)NCCC(=O)NC", "O=C1NC(=O)C=C1",
    "O=c1[nH]cnc2[nH]cnc12", "Nc1ncnc2[nH]cnc12", "O=C1NC(=O)NC(=O)C1", "c1ccc2[nH]ccc2c1", "c1cn[nH]c1",
    "OCCO", "OCCOCCO", "CCO", "CC(C)O", "c1ccccc1O", "Oc1ccc(O)cc1", "Oc1cccc(O)c1", "OC1CCCCC1",
    # amides / sulfonamides / misc
    "CC(=O)Nc1ccccc1", "O=C(Nc1ccccc1)c1ccccc1", "CS(N)(=O)=O", "NS(=O)(=O)c1ccccc1", "O=C(O)CNC(=O)c1ccccc1",
    "CCCCCCCCCCCCCCCC(=O)O", "CCCCCCCC/C=C\\CCCCCCCC(=O)NCCO", "OC(=O)CCCCCCCCCCCCCCC(O)=O",
    "OC(=O)C1CCC(CC1)C(O)=O", "OC(=O)C1CC1", "OC(=O)C(F)(F)F", "N#Cc1ccccc1", "Clc1ccccc1", "c1ccc(cc1)-c1ccccc1",
    "OC(=O)c1ccc(-c2ccccc2)cc1", "Cc1ccc(cc1)S(O)(=O)=O", "OB(O)c1ccccc1", "OP(O)(=O)c1ccccc1",
    "CC(=O)C(C)=O", "O=C1CCCCC1", "CC(C)=O",
]


def auc(pos: list[float], neg: list[float]) -> float:
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else (0.5 if p == n else 0.0)
    return wins / (len(pos) * len(neg))


def main() -> None:
    from ultrahofs.chem.scoring import score_molecule
    from ultrahofs.chem.synthons import connection_count, find_synthons
    from ultrahofs.db import SessionLocal
    from ultrahofs.models import Molecule

    with SessionLocal() as db:
        rows = [(m.smiles, m.score.get("score"), m.n_connect) for m in
                db.execute(select(Molecule).where(Molecule.is_experimental_tecton.is_(True))).scalars() if m.score]
    pos_all = [s for _smi, s, _n in rows]
    pos_classic = [s for _smi, s, n in rows if n >= 1]
    pos_ge3 = [s for _smi, s, n in rows if n >= 3]
    bg = []
    for smi in BACKGROUND:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            continue
        res = score_molecule(mol, n_confs=4)
        bg.append((smi, res["score"], connection_count(find_synthons(mol))))
    neg_all = [s for _smi, s, _n in bg]
    neg_classic = [s for _smi, s, n in bg if n >= 1]

    def desc(v: list[float]) -> dict:
        v = sorted(v)
        return {"n": len(v), "median": round(st.median(v), 1), "p10": round(v[len(v) // 10], 1),
                "p90": round(v[min(len(v) - 1, 9 * len(v) // 10)], 1)}

    report = {
        "experimental_all": desc(pos_all),
        "experimental_with_classical_synthon": desc(pos_classic),
        "experimental_with_>=3_synthons": desc(pos_ge3),
        "background_all": desc(neg_all),
        "background_with_classical_synthon": desc(neg_classic),
        "auc_all": round(auc(pos_all, neg_all), 3),
        "auc_classical_domain": round(auc(pos_classic, neg_classic), 3),
        "fraction_experimental_without_classical_synthon": round(1 - len(pos_classic) / len(pos_all), 3),
        "top_background": sorted(bg, key=lambda x: -x[1])[:8],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scoring.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    lines = [
        "# HOF-likeness score validation",
        "",
        "Positive–unlabeled check: experimental HOF tectons (HOFSyn-derived, this database) vs. a background set "
        f"of {len(neg_all)} generic organic molecules (acids, amides, drugs, sugars, solvents). Background molecules "
        "are *not* proven non-HOFs, so AUC measures enrichment, not classification accuracy.",
        "",
        "| set | n | median | p10 | p90 |",
        "|---|---|---|---|---|",
    ]
    for k in ("experimental_all", "experimental_with_classical_synthon", "experimental_with_>=3_synthons",
              "background_all", "background_with_classical_synthon"):
        d = report[k]
        lines.append(f"| {k} | {d['n']} | {d['median']} | {d['p10']} | {d['p90']} |")
    lines += [
        "",
        f"* ROC-AUC (all): **{report['auc_all']}**",
        f"* ROC-AUC (molecules with ≥1 classical H-bond synthon — the score's design domain): **{report['auc_classical_domain']}**",
        f"* {100 * report['fraction_experimental_without_classical_synthon']:.0f}% of experimental entries' tectons have no "
        "classical N–H/O–H synthon (porous molecular crystals held by weaker C–H···X contacts are included in HOFSyn); "
        "the score is designed for synthon-driven HOFs and ranks those low by construction.",
        "",
        "Highest-scoring background molecules (expected false positives):",
        "",
    ]
    lines += [f"* `{smi}` — {s:.1f}" for smi, s, _n in report["top_background"]]
    lines += ["", "The score remains a ranking heuristic and is never presented as a formation probability."]
    (OUT / "scoring.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "top_background"}, indent=1))


if __name__ == "__main__":
    main()
