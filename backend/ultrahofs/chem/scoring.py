"""Transparent HOF-likeness ranking score.

This is an explainable *ranking* heuristic built from literature design rules for HOF tectons
(directional synthons, >=3 divergent connections, rigidity, symmetry, shapes that frustrate close
packing). It is NOT a calibrated probability that a molecule will crystallise as a porous HOF.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rdkit import Chem

from .conformers import Geometry3D, analyze_3d
from .descriptors import basic_descriptors, rotor_analysis, symmetry_info
from .synthons import STRONG_THRESHOLD, SYNTHON_BY_KEY, SynthonMatch, connection_count, find_synthons

WEIGHTS: dict[str, float] = {
    "connectivity": 0.18,
    "synthon_strength": 0.14,
    "rigidity": 0.16,
    "geometry": 0.14,
    "symmetry": 0.08,
    "shape": 0.08,
    "intramolecular_hb": 0.06,
    "synthesis": 0.06,
    "size": 0.04,
    "precedent": 0.03,
    "solubility": 0.03,
}

LABELS = {
    "connectivity": ("Connectivity", "连接数"),
    "synthon_strength": ("Synthon strength & precedent", "合成子强度与先例"),
    "rigidity": ("Rigidity", "刚性"),
    "geometry": ("Divergent geometry", "发散几何"),
    "symmetry": ("Symmetry", "对称性"),
    "shape": ("Anti-close-packing shape", "防密堆积形状"),
    "intramolecular_hb": ("No intramolecular H-bond", "无分子内氢键"),
    "synthesis": ("Synthetic accessibility", "可合成性"),
    "size": ("Size / interpenetration", "尺寸/穿插"),
    "precedent": ("Similarity to reported HOFs", "与已报道 HOF 相似度"),
    "solubility": ("Solubility proxy", "溶解性代理"),
}

_TRIPTYCENE = Chem.MolFromSmarts("[CX4H1]12c3ccccc3[CX4H1](c3ccccc31)c1ccccc12")


@dataclass
class Component:
    key: str
    score: float
    weight: float
    en: str
    zh: str
    values: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "key": self.key, "label_en": LABELS[self.key][0], "label_zh": LABELS[self.key][1],
            "score": round(self.score, 3), "weight": self.weight,
            "explain_en": self.en, "explain_zh": self.zh, "values": self.values,
        }


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_components(mol: Chem.Mol, synthons: list[SynthonMatch], geo: Geometry3D | None,
                     max_similarity: float | None = None,
                     synthon_prior: dict[str, float] | None = None) -> tuple[list[Component], list[dict]]:
    comps: list[Component] = []
    flags: list[dict] = []
    desc = basic_descriptors(mol)
    rot = rotor_analysis(mol, synthons)
    sym = symmetry_info(mol, synthons)
    n_conn = connection_count(synthons)
    strong = [s for s in synthons if s.type.strength >= STRONG_THRESHOLD]
    charged = [s for s in synthons if s.type.category in ("cation", "anion")]

    # 1. connectivity
    table = {0: 0.0, 1: 0.1, 2: 0.45, 3: 0.9, 4: 1.0, 5: 0.95, 6: 1.0}
    s_conn = table.get(n_conn, 0.85)
    comps.append(Component(
        "connectivity", s_conn, WEIGHTS["connectivity"],
        f"{n_conn} framework-forming synthon(s); >=3 are needed for 2D/3D nets.",
        f"{n_conn} 个成框架合成子；形成 2D/3D 网络通常需要 ≥3 个。", {"n_connect": n_conn}))
    if n_conn == 2:
        flags.append({"level": "warn", "en": "Only 2 connections: forms chains unless combined with a co-tecton.",
                      "zh": "只有 2 个连接点：单独使用多形成链，需要搭配共构筑分子。"})
    if n_conn < 2:
        flags.append({"level": "bad", "en": "Fewer than 2 strong synthons: unlikely to form an extended framework.",
                      "zh": "强合成子少于 2 个：难以形成延伸框架。"})

    # 2. synthon strength + literature prior
    if strong:
        mean_strength = sum(s.type.strength for s in strong) / len(strong)
        prior = 0.0
        if synthon_prior:
            prior = max(synthon_prior.get(s.key, 0.0) for s in strong)
        s_str = 0.75 * mean_strength + 0.25 * prior if synthon_prior else mean_strength
        names = sorted({s.type.name_en for s in strong})
        names_zh = sorted({s.type.name_zh for s in strong})
    else:
        s_str, names, names_zh = 0.0, [], []
    comps.append(Component(
        "synthon_strength", s_str, WEIGHTS["synthon_strength"],
        "Synthons: " + (", ".join(names) or "none") + ".",
        "合成子：" + ("、".join(names_zh) or "无") + "。",
        {"types": [s.key for s in strong]}))
    if charged:
        flags.append({"level": "info", "en": "Charged synthons: design as a two-component charge-assisted system.",
                      "zh": "带电合成子：应按双组分电荷辅助体系设计。"})

    # 3. rigidity
    flex = rot["flexible_rotors"]
    s_rig = {0: 1.0, 1: 0.75, 2: 0.5, 3: 0.3}.get(flex, 0.1)
    s_rig = _clip(s_rig - min(0.15, 0.02 * rot["aryl_torsions"]))
    comps.append(Component(
        "rigidity", s_rig, WEIGHTS["rigidity"],
        f"{flex} flexible rotor(s), {rot['aryl_torsions']} aryl torsion(s) (synthon end-group rotations ignored).",
        f"{flex} 个柔性转子，{rot['aryl_torsions']} 个芳基扭转（不计端基合成子的转动）。", rot))
    if flex >= 2:
        flags.append({"level": "warn", "en": "Flexible linkers may favour dense packing or framework collapse.",
                      "zh": "柔性连接易导致密堆积或骨架坍塌。"})

    # 4. geometry / divergence
    if geo and geo.points and len(geo.points) >= 2:
        s_div = _clip(1 - (geo.divergence or 0) / 0.5)
        s_ang = 1.0 if (geo.min_angle or 0) >= 90 else _clip((geo.min_angle or 0) / 90)
        s_reg = 1.0 if geo.geometry not in ("irregular", "bent", "t_shaped") else 0.5
        s_geo = 0.4 * s_div + 0.3 * s_ang + 0.3 * s_reg
        en = (f"Connection geometry {geo.geometry.replace('_', ' ')} (RMSD {geo.geometry_rmsd}); "
              f"min angle {geo.min_angle}°, divergence {geo.divergence}.")
        zh = (f"连接几何：{geo.geometry}（RMSD {geo.geometry_rmsd}）；最小夹角 {geo.min_angle}°，"
              f"发散度 {geo.divergence}。")
        vals = {"geometry": geo.geometry, "min_angle": geo.min_angle, "divergence": geo.divergence}
        if (geo.min_angle or 180) < 60:
            flags.append({"level": "warn", "en": "Convergent synthons may chelate or self-close.",
                          "zh": "合成子方向会聚，可能自闭合或形成分子内配对。"})
    else:
        s_geo, en, zh, vals = 0.2, "Fewer than 2 geometrically defined connection points.", "可定义几何的连接点少于 2 个。", {}
    comps.append(Component("geometry", s_geo, WEIGHTS["geometry"], en, zh, vals))

    # 5. symmetry
    ncls = sym["synthon_equivalence_classes"]
    s_sym = 1.0 if sym["synthons_equivalent"] else (0.6 if ncls == 2 else 0.3)
    comps.append(Component(
        "symmetry", s_sym, WEIGHTS["symmetry"],
        f"Synthons fall into {ncls} symmetry class(es).", f"合成子分属 {ncls} 个对称等价类。", sym))

    # 6. shape (two routes to porosity: rigid 3D shapes or planar pi-stacked layers)
    has_trip = mol.HasSubstructMatch(_TRIPTYCENE)
    if geo and geo.npr1 is not None:
        planar = ((geo.thickness or 9) < 1.6 or (geo.pbf or 9) < 0.8) and desc["aromatic_rings"] >= 1
        if has_trip:
            s_shape, en, zh = 0.95, "Triptycene-type shape with internal free volume frustrates packing.", "三蝶烯类骨架具有分子内自由体积，阻碍密堆积。"
        elif geo.geometry in ("tetrahedral", "trigonal_prismatic", "octahedral") or geo.npr1 > 0.6:
            s_shape, en, zh = 0.9, "3D shape resists close packing (tetrahedral/globular).", "三维形状（四面体/球形）抵抗密堆积。"
        elif planar:
            s_shape, en, zh = 0.85, "Planar π-system: layered HOF route via π–π stacking (1D channels).", "平面 π 体系：可经 π–π 堆积形成层状 HOF（一维孔道）。"
        elif geo.npr1 < 0.25:
            s_shape, en, zh = 0.35, "Rod-like shape tends to pack densely.", "棒状分子倾向于密堆积。"
        else:
            s_shape, en, zh = 0.6, "Intermediate shape.", "中间形状。"
        vals = {"npr1": geo.npr1, "npr2": geo.npr2, "thickness": geo.thickness, "triptycene": has_trip}
    else:
        s_shape, en, zh, vals = 0.5, "No 3D shape information.", "无三维形状信息。", {}
    comps.append(Component("shape", s_shape, WEIGHTS["shape"], en, zh, vals))

    # 7. intramolecular H-bonds
    ihb = geo.intramolecular_hb_fraction if geo else 0.0
    comps.append(Component(
        "intramolecular_hb", 1 - ihb, WEIGHTS["intramolecular_hb"],
        f"Intramolecular H-bond in {int(ihb * 100)}% of conformers.", f"{int(ihb * 100)}% 构象中存在分子内氢键。",
        {"fraction": ihb}))
    if ihb >= 0.5:
        flags.append({"level": "warn", "en": "Synthons often consumed by intramolecular H-bonds.",
                      "zh": "合成子常被分子内氢键占用。"})

    # 8. synthetic accessibility
    sa = desc["sa_score"]
    s_sa = _clip((8.0 - sa) / 5.0) if sa is not None else 0.5
    comps.append(Component(
        "synthesis", s_sa, WEIGHTS["synthesis"], f"SAscore {sa} (1 easy – 10 hard).", f"SAscore {sa}（1 易 – 10 难）。",
        {"sa_score": sa}))

    # 9. size / interpenetration
    arm = geo.arm_length if geo else None
    if arm is None:
        s_size, en, zh = 0.5, "Unknown arm length.", "臂长未知。"
    elif arm < 3.5:
        s_size, en, zh = 0.5, f"Short arms ({arm} Å): small pores.", f"臂较短（{arm} Å）：孔较小。"
    elif arm <= 10:
        s_size, en, zh = 1.0, f"Arm length {arm} Å.", f"臂长 {arm} Å。"
    elif arm <= 14:
        s_size, en, zh = 0.8, f"Long arms ({arm} Å): interpenetration likely.", f"臂较长（{arm} Å）：可能穿插。"
    else:
        s_size, en, zh = 0.6, f"Very long arms ({arm} Å): high interpenetration risk.", f"臂很长（{arm} Å）：穿插风险高。"
    comps.append(Component("size", s_size, WEIGHTS["size"], en, zh, {"arm_length": arm}))

    # 10. precedent similarity
    if max_similarity is None:
        s_prec, en, zh = 0.3, "No database comparison.", "未与数据库比较。"
    else:
        s_prec = _clip(0.3 + 0.7 * (max_similarity - 0.25) / 0.6)
        en = f"Max Tanimoto to reported HOF tectons: {max_similarity:.2f}."
        zh = f"与已报道 HOF 构筑单元的最大 Tanimoto 相似度：{max_similarity:.2f}。"
    comps.append(Component("precedent", s_prec, WEIGHTS["precedent"], en, zh, {"max_similarity": max_similarity}))

    # 11. solubility proxy
    mw, logp = desc["mw"], desc["logp"]
    s_sol = 1.0 if (mw < 1200 and -2 < logp < 10) else 0.6
    comps.append(Component(
        "solubility", s_sol, WEIGHTS["solubility"], f"MW {mw}, logP {logp}.", f"分子量 {mw}，logP {logp}。",
        {"mw": mw, "logp": logp}))
    return comps, flags


def weighted_sum(comps: list[Component]) -> float:
    wsum = sum(c.weight for c in comps)
    return sum(c.weight * c.score for c in comps) / wsum


def critical_gate(comps: list[Component]) -> float:
    """Connectivity and rigidity are necessary conditions, so they also act multiplicatively."""
    by = {c.key: c.score for c in comps}
    return (0.5 + 0.5 * by.get("connectivity", 0.0)) * (0.6 + 0.4 * by.get("rigidity", 0.0))


def total_score(comps: list[Component]) -> float:
    return round(100 * weighted_sum(comps) * critical_gate(comps), 1)


def band(score: float) -> str:
    return "high" if score >= 75 else ("medium" if score >= 55 else "low")


def score_molecule(mol: Chem.Mol, *, n_confs: int = 6, max_similarity: float | None = None,
                   synthon_prior: dict[str, float] | None = None, with_3d: bool = True) -> dict:
    synthons = find_synthons(mol)
    geo = None
    if with_3d:
        try:
            geo = analyze_3d(mol, n_confs=n_confs, matches=synthons)
        except Exception:  # noqa: BLE001
            geo = None
    comps, flags = score_components(mol, synthons, geo, max_similarity, synthon_prior)
    total = total_score(comps)
    return {
        "score": total,
        "band": band(total),
        "weighted_sum": round(100 * weighted_sum(comps), 1),
        "gate": round(critical_gate(comps), 3),
        "components": [c.to_dict() for c in comps],
        "flags": flags,
        "synthons": [s.to_dict() for s in synthons],
        "n_connect": connection_count(synthons),
        "geometry": geo.to_dict() if geo else None,
        "disclaimer_en": "Ranking heuristic, not a formation probability.",
        "disclaimer_zh": "这是排序分数，不是形成概率。",
    }


def synthon_types_present(synthons: list[SynthonMatch]) -> list[str]:
    return sorted({s.key for s in synthons if s.key in SYNTHON_BY_KEY})
