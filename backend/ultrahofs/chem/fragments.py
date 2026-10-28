"""Building-block libraries for HOF tecton generation (core x arm x synthon).

Core SMILES use [*:k] for substitution sites k = 1..n. Symmetry of every core was verified
(all sites canonically equivalent); C3 isomers were cross-checked with OPSIN.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Core:
    key: str
    name_en: str
    name_zh: str
    smiles: str
    n_sites: int
    geometry: str
    fused_pairs: tuple[tuple[int, int], ...] = ()
    needs_arm: bool = False  # direct synthon attachment is chemically unreasonable
    precursor: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Arm:
    key: str
    name_en: str
    name_zh: str
    smiles: str  # [*:1] core side, [*:2] synthon side; "" = direct bond
    length: float  # approximate added length (Å)
    coupling: str
    aromatic: bool = True


@dataclass(frozen=True)
class SynthonFragment:
    key: str  # SynthonType key
    smiles: str  # [*:1] (terminal) or [*:1]...[*:2] (fused)
    fused: bool = False
    ionic_form: str = ""  # charged form used in two-component salts


CORES: tuple[Core, ...] = (
    # ---- 3-connected, trigonal ----
    Core("benzene_135", "Benzene-1,3,5-triyl", "苯-1,3,5-三基", "[*:1]c1cc([*:2])cc([*:3])c1", 3,
         "trigonal_planar", precursor="1,3,5-tribromobenzene", tags=("planar",)),
    Core("triazine", "1,3,5-Triazine-2,4,6-triyl", "1,3,5-三嗪-2,4,6-三基", "[*:1]c1nc([*:2])nc([*:3])n1", 3,
         "trigonal_planar", needs_arm=True, precursor="cyanuric chloride / nitrile trimerisation",
         tags=("planar",)),
    Core("triphenylamine", "Triphenylamine", "三苯胺",
         "N(c1ccc([*:1])cc1)(c1ccc([*:2])cc1)c1ccc([*:3])cc1", 3, "trigonal_planar",
         precursor="tris(4-bromophenyl)amine", tags=("propeller",)),
    Core("triphenylbenzene", "1,3,5-Triphenylbenzene", "1,3,5-三苯基苯",
         "c1(-c2ccc([*:1])cc2)cc(-c2ccc([*:2])cc2)cc(-c2ccc([*:3])cc2)c1", 3, "trigonal_planar",
         precursor="1,3,5-tris(4-bromophenyl)benzene", tags=("planar",)),
    Core("triphenyltriazine", "2,4,6-Triphenyl-1,3,5-triazine", "2,4,6-三苯基-1,3,5-三嗪",
         "c1(-c2ccc([*:1])cc2)nc(-c2ccc([*:2])cc2)nc(-c2ccc([*:3])cc2)n1", 3, "trigonal_planar",
         precursor="2,4,6-tris(4-bromophenyl)-1,3,5-triazine", tags=("planar",)),
    Core("triphenylene_3", "Triphenylene-2,6,10-triyl", "三亚苯-2,6,10-三基",
         "c1cc2c(cc1[*:1])c1ccc([*:2])cc1c1ccc([*:3])cc21", 3, "trigonal_planar",
         precursor="2,6,10-tribromotriphenylene", tags=("planar", "pi")),
    Core("triptycene_3", "Triptycene-2,6,14-triyl", "三蝶烯-2,6,14-三基",
         "C12c3cc([*:1])ccc3C(c3ccc([*:2])cc31)c1ccc([*:3])cc12", 3, "trigonal_planar",
         precursor="2,6,14-tribromotriptycene", tags=("triptycene", "3d")),
    # ---- 4-connected ----
    Core("tpm", "Tetraphenylmethane", "四苯基甲烷",
         "C(c1ccc([*:1])cc1)(c1ccc([*:2])cc1)(c1ccc([*:3])cc1)c1ccc([*:4])cc1", 4, "tetrahedral",
         precursor="tetrakis(4-bromophenyl)methane", tags=("3d",)),
    Core("tps", "Tetraphenylsilane", "四苯基硅烷",
         "[Si](c1ccc([*:1])cc1)(c1ccc([*:2])cc1)(c1ccc([*:3])cc1)c1ccc([*:4])cc1", 4, "tetrahedral",
         precursor="tetrakis(4-bromophenyl)silane", tags=("3d",)),
    Core("adamantane", "Adamantane-1,3,5,7-tetrayl", "金刚烷-1,3,5,7-四基",
         "C1C2([*:1])CC3([*:2])CC1([*:3])CC(C2)([*:4])C3", 4, "tetrahedral",
         precursor="1,3,5,7-tetrabromoadamantane / 1,3,5,7-tetraphenyladamantane", tags=("3d",)),
    Core("spirobifluorene", "9,9'-Spirobifluorene-2,2',7,7'-tetrayl", "9,9'-螺二芴-2,2',7,7'-四基",
         "c1cc2c(cc1[*:1])C1(c3cc([*:2])ccc3-2)c2cc([*:3])ccc2-c2ccc([*:4])cc21", 4, "tetrahedral",
         precursor="2,2',7,7'-tetrabromo-9,9'-spirobifluorene", tags=("3d",)),
    Core("pyrene", "Pyrene-1,3,6,8-tetrayl", "芘-1,3,6,8-四基",
         "[*:1]c1cc([*:2])c2ccc3c([*:3])cc([*:4])c4ccc1c2c34", 4, "rectangular_planar",
         precursor="1,3,6,8-tetrabromopyrene", tags=("planar", "pi")),
    Core("porphyrin", "Porphyrin-5,10,15,20-tetrayl", "卟啉-5,10,15,20-四基",
         "[*:1]c1c2ccc(n2)c([*:2])c2ccc([nH]2)c([*:3])c2ccc(n2)c([*:4])c2ccc1[nH]2", 4, "square_planar",
         needs_arm=True, precursor="pyrrole + 4-substituted benzaldehyde (Adler–Longo / Lindsey)",
         tags=("planar", "pi")),
    Core("tpe", "Tetraphenylethylene", "四苯乙烯",
         "C(c1ccc([*:1])cc1)(c1ccc([*:2])cc1)=C(c1ccc([*:3])cc1)c1ccc([*:4])cc1", 4, "rectangular_planar",
         precursor="tetrakis(4-bromophenyl)ethylene", tags=("propeller",)),
    Core("biphenyl_3355", "Biphenyl-3,3',5,5'-tetrayl", "联苯-3,3',5,5'-四基",
         "[*:1]c1cc([*:2])cc(c1)-c1cc([*:3])cc([*:4])c1", 4, "rectangular_planar",
         precursor="3,3',5,5'-tetrabromobiphenyl", tags=("planar",)),
    Core("benzene_1245", "Benzene-1,2,4,5-tetrayl", "苯-1,2,4,5-四基",
         "c1([*:1])c([*:2])cc([*:3])c([*:4])c1", 4, "rectangular_planar", fused_pairs=((1, 2), (3, 4)),
         precursor="1,2,4,5-tetrabromobenzene / pyromellitic dianhydride", tags=("planar",)),
    Core("naphthalene_1458", "Naphthalene-1,4,5,8-tetrayl", "萘-1,4,5,8-四基",
         "[*:1]c1ccc([*:3])c2c([*:4])ccc([*:2])c12", 4, "rectangular_planar", fused_pairs=((1, 2), (3, 4)),
         precursor="naphthalene-1,4,5,8-tetracarboxylic dianhydride", tags=("planar", "pi")),
    # ---- 6-connected (or 3-connected through fused synthons) ----
    Core("triptycene_6", "Triptycene-2,3,6,7,14,15-hexayl", "三蝶烯-2,3,6,7,14,15-六基",
         "C12c3cc([*:1])c([*:2])cc3C(c3cc([*:3])c([*:4])cc31)c1cc([*:5])c([*:6])cc12", 6,
         "trigonal_prismatic", fused_pairs=((1, 2), (3, 4), (5, 6)),
         precursor="2,3,6,7,14,15-hexaaminotriptycene / hexabromotriptycene", tags=("triptycene", "3d")),
    Core("triphenylene_6", "Triphenylene-2,3,6,7,10,11-hexayl", "三亚苯-2,3,6,7,10,11-六基",
         "[*:1]c1cc2c(cc1[*:2])c1cc([*:3])c([*:4])cc1c1cc([*:5])c([*:6])cc21", 6, "hexagonal_planar",
         fused_pairs=((1, 2), (3, 4), (5, 6)),
         precursor="2,3,6,7,10,11-hexabromo/hexaamino-triphenylene", tags=("planar", "pi")),
    Core("hexaphenylbenzene", "Hexaphenylbenzene", "六苯基苯",
         "c1(-c2ccc([*:1])cc2)c(-c2ccc([*:2])cc2)c(-c2ccc([*:3])cc2)c(-c2ccc([*:4])cc2)"
         "c(-c2ccc([*:5])cc2)c1-c1ccc([*:6])cc1", 6, "hexagonal_planar",
         precursor="Diels–Alder of tetraarylcyclopentadienone + diarylacetylene", tags=("propeller",)),
    # ---- 2-connected (co-tectons / linear partners) ----
    Core("benzene_14", "1,4-Phenylene", "1,4-亚苯基", "[*:1]c1ccc([*:2])cc1", 2, "linear",
         precursor="1,4-dibromobenzene", tags=("linear",)),
    Core("biphenyl_44", "Biphenyl-4,4'-diyl", "联苯-4,4'-二基", "[*:1]c1ccc(cc1)-c1ccc([*:2])cc1", 2, "linear",
         precursor="4,4'-dibromobiphenyl", tags=("linear",)),
    Core("naphthalene_26", "Naphthalene-2,6-diyl", "萘-2,6-二基", "[*:1]c1ccc2cc([*:2])ccc2c1", 2, "linear",
         precursor="2,6-dibromonaphthalene", tags=("linear",)),
    Core("anthracene_910", "Anthracene-9,10-diyl", "蒽-9,10-二基", "[*:1]c1c2ccccc2c([*:2])c2ccccc12", 2,
         "linear", precursor="9,10-dibromoanthracene", tags=("linear", "pi")),
)

ARMS: tuple[Arm, ...] = (
    Arm("none", "Direct bond", "直接相连", "", 0.0, "direct installation on the core"),
    Arm("phenylene", "1,4-Phenylene", "1,4-亚苯基", "[*:1]c1ccc([*:2])cc1", 4.3,
        "Suzuki–Miyaura coupling (core–Br + 4-substituted phenylboronic acid)"),
    Arm("biphenylene", "Biphenyl-4,4'-diyl", "联苯-4,4'-二基", "[*:1]c1ccc(cc1)-c1ccc([*:2])cc1", 8.6,
        "Suzuki–Miyaura coupling with 4'-substituted biphenyl-4-boronic acid"),
    Arm("ethynylene", "Ethynylene", "乙炔撑", "[*:1]C#C[*:2]", 2.6,
        "Sonogashira coupling (core–I/Br + terminal alkyne)"),
    Arm("phenylethynylene", "4-Ethynylphenylene", "4-乙炔基亚苯基", "[*:1]C#Cc1ccc([*:2])cc1", 6.9,
        "Sonogashira coupling with 4-substituted phenylacetylene"),
    Arm("thiophene", "Thiophene-2,5-diyl", "噻吩-2,5-二基", "[*:1]c1ccc([*:2])s1", 3.7,
        "Suzuki/Stille coupling with 5-substituted thiophene-2-boronic ester"),
    Arm("dimethylphenylene", "2,5-Dimethyl-1,4-phenylene", "2,5-二甲基-1,4-亚苯基",
        "[*:1]c1cc(C)c([*:2])cc1C", 4.3, "Suzuki–Miyaura coupling (methyls twist the arm)"),
    Arm("tetrafluorophenylene", "2,3,5,6-Tetrafluoro-1,4-phenylene", "2,3,5,6-四氟-1,4-亚苯基",
        "[*:1]c1c(F)c(F)c([*:2])c(F)c1F", 4.3, "Suzuki–Miyaura or C–H arylation of tetrafluoroarene"),
)

SYNTHON_FRAGMENTS: tuple[SynthonFragment, ...] = (
    SynthonFragment("carboxylic_acid", "[*:1]C(=O)O", ionic_form="[*:1]C(=O)[O-]"),
    SynthonFragment("dat", "[*:1]c1nc(N)nc(N)n1"),
    SynthonFragment("primary_amide", "[*:1]C(N)=O"),
    SynthonFragment("boronic_acid", "[*:1]B(O)O"),
    SynthonFragment("pyrazole", "[*:1]c1cn[nH]c1"),
    SynthonFragment("triazole", "[*:1]c1nc[nH]n1"),
    SynthonFragment("tetrazole", "[*:1]c1nn[nH]n1"),
    SynthonFragment("pyridone", "[*:1]c1ccc(=O)[nH]c1"),
    SynthonFragment("phosphonic_acid", "[*:1]P(=O)(O)O", ionic_form="[*:1]P(=O)(O)[O-]"),
    SynthonFragment("sulfonic_acid", "[*:1]S(=O)(=O)O", ionic_form="[*:1]S(=O)(=O)[O-]"),
    SynthonFragment("amidine", "[*:1]C(=N)N", ionic_form="[*:1]C(N)=[NH2+]"),
    SynthonFragment("urea", "[*:1]NC(N)=O"),
    SynthonFragment("hydroxy", "[*:1]O"),
    SynthonFragment("pyridyl", "[*:1]c1ccncc1"),
    SynthonFragment("nitrile", "[*:1]C#N"),
    SynthonFragment("benzimidazolone", "[*:1]NC(=O)N[*:2]", fused=True),
    SynthonFragment("imide", "[*:1]C(=O)NC(=O)[*:2]", fused=True),
)

CORE_BY_KEY = {c.key: c for c in CORES}
ARM_BY_KEY = {a.key: a for a in ARMS}
FRAG_BY_KEY = {f.key: f for f in SYNTHON_FRAGMENTS}

# Synthons that only make sense on an aromatic carbon (heteroaryl rings, phenols).
AROMATIC_ONLY = {"hydroxy", "pyridone", "boronic_acid"}


def library_dict() -> dict:
    from .synthons import SYNTHON_BY_KEY

    def syn(f: SynthonFragment) -> dict:
        st = SYNTHON_BY_KEY[f.key]
        return {"key": f.key, "smiles": f.smiles, "fused": f.fused, "ionic_form": f.ionic_form,
                "name_en": st.name_en, "name_zh": st.name_zh, "strength": st.strength,
                "builder": st.builder, "category": st.category, "route": st.route}

    return {
        "cores": [c.__dict__ | {"fused_pairs": [list(p) for p in c.fused_pairs], "tags": list(c.tags)}
                  for c in CORES],
        "arms": [a.__dict__ for a in ARMS],
        "synthons": [syn(f) for f in SYNTHON_FRAGMENTS],
    }
