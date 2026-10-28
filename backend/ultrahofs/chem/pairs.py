"""Two-component charge-assisted (CAHB) HOF systems: cation tecton + anion tecton."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from math import gcd

from rdkit import Chem

from .conformers import analyze_3d
from .enumerate import _combine, _relabel
from .fragments import ARM_BY_KEY, CORE_BY_KEY, Arm, Core
from .standardize import mol_keys
from .synthons import find_synthons

CATION_FRAGMENTS = {
    "amidinium": "[*:1]C(N)=[NH2+]",
    "guanidinium": "[*:1]NC(N)=[NH2+]",
    "ammonium": "[*:1][NH3+]",
}
ANION_FRAGMENTS = {
    "carboxylate": "[*:1]C(=O)[O-]",
    "sulfonate": "[*:1]S(=O)(=O)[O-]",
    "phosphonate": "[*:1]P(=O)(O)[O-]",
}

# Literature-guided complementarity of charge-assisted synthon pairs (expert prior, 0..1).
COMPLEMENTARITY = {
    ("amidinium", "carboxylate"): (1.00, "R2^2(8) amidinium–carboxylate salt bridge"),
    ("guanidinium", "sulfonate"): (0.95, "guanidinium–sulfonate (GS) quasi-hexagonal sheets"),
    ("amidinium", "sulfonate"): (0.80, "charge-assisted N–H···O=S"),
    ("ammonium", "sulfonate"): (0.80, "ammonium–sulfonate N–H···O networks"),
    ("guanidinium", "carboxylate"): (0.75, "guanidinium–carboxylate R2^2(8)"),
    ("amidinium", "phosphonate"): (0.75, "amidinium–phosphonate"),
    ("ammonium", "carboxylate"): (0.70, "ammonium–carboxylate"),
    ("guanidinium", "phosphonate"): (0.70, "guanidinium–phosphonate"),
    ("ammonium", "phosphonate"): (0.65, "ammonium–phosphonate"),
}

GEOMETRY_NETS = {
    frozenset({"tetrahedral", "linear"}): (1.0, ["dia"], "4-c tetrahedral nodes linked by 2-c linkers → dia"),
    frozenset({"tetrahedral"}): (1.0, ["dia"], "bipartite tetrahedral nodes → dia"),
    frozenset({"trigonal_planar"}): (1.0, ["hcb", "srs"], "bipartite 3-c nodes → hcb (2D) / srs (3D)"),
    frozenset({"trigonal_planar", "linear"}): (0.9, ["hcb", "srs"], "3-c nodes + 2-c linkers → hcb / srs"),
    frozenset({"square_planar"}): (0.95, ["sql"], "bipartite 4-c planar nodes → sql"),
    frozenset({"rectangular_planar"}): (0.9, ["sql", "kgm"], "bipartite 4-c planar nodes → sql/kgm"),
    frozenset({"square_planar", "linear"}): (0.9, ["sql"], "4-c planar nodes + linkers → sql"),
    frozenset({"rectangular_planar", "linear"}): (0.85, ["sql", "kgm"], "4-c planar + linkers → sql/kgm"),
    frozenset({"trigonal_planar", "tetrahedral"}): (0.85, ["ctn", "bor"], "(3,4)-c → ctn / bor"),
    frozenset({"trigonal_planar", "square_planar"}): (0.85, ["tbo", "pto"], "(3,4)-c → tbo / pto"),
    frozenset({"trigonal_planar", "rectangular_planar"}): (0.8, ["tbo", "pto"], "(3,4)-c → tbo / pto"),
    frozenset({"hexagonal_planar", "trigonal_planar"}): (0.75, ["kgd"], "(3,6)-c → kgd"),
    frozenset({"hexagonal_planar", "linear"}): (0.75, ["hxl"], "6-c + linkers → hxl"),
    frozenset({"trigonal_prismatic", "linear"}): (0.7, ["acs"], "6-c trigonal prism + linkers → acs"),
    frozenset({"linear"}): (0.2, [], "2-c + 2-c → chains only"),
}


@dataclass
class IonTecton:
    smiles: str
    core: str
    arm: str
    synthon: str
    n_sites: int
    charge: int
    geometry: str


def build_ion(core: Core, arm: Arm, frag_smiles: str) -> Chem.Mol | None:
    if core.needs_arm and arm.key == "none":
        return None
    pieces = [Chem.MolFromSmiles(core.smiles)]
    for k in range(1, core.n_sites + 1):
        if arm.key == "none":
            pieces.append(_relabel(frag_smiles, {1: k}))
        else:
            pieces.append(_relabel(arm.smiles, {1: k, 2: 100 + k}))
            pieces.append(_relabel(frag_smiles, {1: 100 + k}))
    try:
        mol = Chem.molzip(_combine(pieces))
        Chem.SanitizeMol(mol)
        return Chem.MolFromSmiles(Chem.MolToSmiles(mol))
    except Exception:  # noqa: BLE001
        return None


def stoichiometry(n_cation_charge: int, n_anion_charge: int) -> tuple[int, int]:
    """(cation count, anion count) giving a neutral salt."""
    a, b = abs(n_anion_charge), abs(n_cation_charge)
    g = gcd(a, b) or 1
    return a // g, b // g


def _ion_type(mol: Chem.Mol, sign: int) -> tuple[str | None, int]:
    keys = [m.key for m in find_synthons(mol) if (m.type.charge > 0) == (sign > 0) and m.type.charge != 0]
    if not keys:
        return None, 0
    main = max(set(keys), key=keys.count)
    return main, len(keys)


def evaluate_pair(cation_smiles: str, anion_smiles: str, with_3d: bool = True) -> dict:
    cat = Chem.MolFromSmiles(cation_smiles)
    an = Chem.MolFromSmiles(anion_smiles)
    if cat is None or an is None:
        raise ValueError("invalid SMILES")
    qc, qa = Chem.GetFormalCharge(cat), Chem.GetFormalCharge(an)
    ctype, nc = _ion_type(cat, +1)
    atype, na = _ion_type(an, -1)
    issues = []
    if qc <= 0:
        issues.append("cation tecton has no net positive charge")
    if qa >= 0:
        issues.append("anion tecton has no net negative charge")
    comp, comp_note = COMPLEMENTARITY.get((ctype or "", atype or ""), (0.5, "no well-known motif"))
    geo_c = analyze_3d(cat, n_confs=3).geometry if with_3d else "unknown"
    geo_a = analyze_3d(an, n_confs=3).geometry if with_3d else "unknown"
    key = frozenset({geo_c, geo_a})
    net_score, nets, net_note = GEOMETRY_NETS.get(key, (0.5, [], "no simple binodal net suggested"))
    ratio = stoichiometry(qc, qa) if qc > 0 and qa < 0 else (1, 1)
    score = round(100 * (0.5 * comp + 0.5 * net_score) * (1.0 if not issues else 0.6), 1)
    return {
        "cation": {"smiles": Chem.MolToSmiles(cat), "charge": qc, "synthon": ctype, "n_sites": nc,
                   "geometry": geo_c, "keys": mol_keys(cat).dict()},
        "anion": {"smiles": Chem.MolToSmiles(an), "charge": qa, "synthon": atype, "n_sites": na,
                  "geometry": geo_a, "keys": mol_keys(an).dict()},
        "stoichiometry": {"cation": ratio[0], "anion": ratio[1]},
        "salt_smiles": ".".join([Chem.MolToSmiles(cat)] * ratio[0] + [Chem.MolToSmiles(an)] * ratio[1]),
        "complementarity": {"score": comp, "motif": comp_note},
        "net_compatibility": {"score": net_score, "nets": nets, "note": net_note},
        "score": score,
        "issues": issues,
        "disclaimer_en": "Ranking heuristic for charge-assisted pairs, not a formation probability.",
        "disclaimer_zh": "电荷辅助配对的排序分数，不是形成概率。",
    }


def enumerate_pairs(cation_cores: list[str], anion_cores: list[str], cation_types: list[str],
                    anion_types: list[str], arms: list[str] | None = None, limit: int = 200) -> list[dict]:
    arms = arms or ["none", "phenylene"]
    cations, anions = [], []
    for ck, ak, ct in itertools.product(cation_cores, arms, cation_types):
        m = build_ion(CORE_BY_KEY[ck], ARM_BY_KEY[ak], CATION_FRAGMENTS[ct])
        if m is not None:
            cations.append((Chem.MolToSmiles(m), ck, ak, ct))
    for ck, ak, at in itertools.product(anion_cores, arms, anion_types):
        m = build_ion(CORE_BY_KEY[ck], ARM_BY_KEY[ak], ANION_FRAGMENTS[at])
        if m is not None:
            anions.append((Chem.MolToSmiles(m), ck, ak, at))
    out = []
    seen = set()
    for (cs, cck, cak, ct), (as_, ack, aak, at) in itertools.product(cations, anions):
        if (cs, as_) in seen:
            continue
        seen.add((cs, as_))
        comp, comp_note = COMPLEMENTARITY.get((ct, at), (0.5, "no well-known motif"))
        g1, g2 = CORE_BY_KEY[cck].geometry, CORE_BY_KEY[ack].geometry
        net_score, nets, net_note = GEOMETRY_NETS.get(frozenset({g1, g2}), (0.5, [], "no simple net"))
        qc = Chem.GetFormalCharge(Chem.MolFromSmiles(cs))
        qa = Chem.GetFormalCharge(Chem.MolFromSmiles(as_))
        ratio = stoichiometry(qc, qa)
        out.append({
            "cation": {"smiles": cs, "core": cck, "arm": cak, "synthon": ct, "charge": qc, "geometry": g1},
            "anion": {"smiles": as_, "core": ack, "arm": aak, "synthon": at, "charge": qa, "geometry": g2},
            "stoichiometry": {"cation": ratio[0], "anion": ratio[1]},
            "complementarity": {"score": comp, "motif": comp_note},
            "net_compatibility": {"score": net_score, "nets": nets, "note": net_note},
            "score": round(100 * (0.5 * comp + 0.5 * net_score), 1),
        })
    out.sort(key=lambda d: -d["score"])
    return out[:limit]
