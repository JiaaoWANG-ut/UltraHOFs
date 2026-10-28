"""Hydrogen-bonding synthon library and detection.

SMARTS atom-map labels mark the roles used downstream:
  :1 attach atom (scaffold atom bonded to the synthon)   :5 second attach atom (fused synthons)
  :2 root (synthon atom bonded to the scaffold)           :3 donor heavy atom    :4 acceptor atom
If :1/:2 are absent the root/attach atoms are found dynamically (ring synthons such as pyridone).

``geometry`` tells the crystal builder where the H-bond pairing centre (connection point X) is:
  ("dimer", d)        centrosymmetric R2^2(n) homodimer; X = M(D,A) + d/2 * n_out
  ("axis", frm, to, d) X = P_to + d * unit(P_to - P_frm)
  None                 not supported by the v1 assembler
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache

from rdkit import Chem


@dataclass(frozen=True)
class SynthonType:
    key: str
    name_en: str
    name_zh: str
    smarts: tuple[str, ...]
    category: str  # neutral | cation | anion | acceptor | weak | fused
    strength: float  # expert prior (0..1) of H-bond strength/directionality for framework formation
    motif: str
    hofsyn_classes: tuple[str, ...] = ()
    geometry: tuple | None = None
    builder: str = "none"  # full | approx | none
    partners: tuple[str, ...] = ()  # complementary synthons for heterosynthons / salts
    route: str = ""
    fused: bool = False
    charge: int = 0


SYNTHON_TYPES: tuple[SynthonType, ...] = (
    # ---------------- fused (use two adjacent core positions) ----------------
    SynthonType(
        "benzimidazolone", "Benzimidazolone", "苯并咪唑酮",
        ("[c:1]1[c:5][nH][c:2](=[O:4])[nH:3]1",),
        "fused", 0.80, "N–H···O=C tapes / R2^2(8) dimers", (),
        ("axis", "attach_mid", "acceptor", 1.45), "approx", (),
        "o-diamine + CDI (or urea) cyclisation", fused=True,
    ),
    SynthonType(
        "imide", "Cyclic imide", "环状酰亚胺",
        ("[#6:1][CX3;R:2](=[OX1:4])[NX3H1;R:3][CX3;R](=[OX1])[#6:5]",),
        "fused", 0.62, "N–H···O=C R2^2(8) dimers / catemers", (),
        ("axis", "attach_mid", "donor", 1.90), "approx", (),
        "anhydride + NH3 / urea (imidisation)", fused=True,
    ),
    # ---------------- charge-assisted ions ----------------
    SynthonType(
        "amidinium", "Amidinium", "脒鎓",
        ("[#6:1]-[CX3:2](=[NX3H2+:3])-[NX3H2:4]",),
        "cation", 0.95, "charge-assisted R2^2(8) with carboxylate/sulfonate", ("carboxylate-amidinium",),
        ("axis", "attach", "root", 1.97), "full", ("carboxylate", "sulfonate", "phosphonate"),
        "nitrile → amidine (Pinner or LiHMDS), protonate", charge=+1,
    ),
    SynthonType(
        "guanidinium", "Guanidinium", "胍鎓",
        ("[#6:1]-[NX3H1]-[CX3:2](=[NX3H2+:3])-[NX3H2:4]", "[NX3H2:3]-[CX3:2](=[NX3H2+])-[NX3H2:4]"),
        "cation", 0.95, "guanidinium–sulfonate (GS) quasi-hexagonal sheets", ("sulfonate-guanidium",),
        None, "none", ("sulfonate", "carboxylate"),
        "amine + cyanamide / S-methylisothiourea; or guanidinium salt", charge=+1,
    ),
    SynthonType(
        "ammonium", "Ammonium", "铵",
        ("[#6:1]-[NX4H3+:3]", "[NX4H4+:3]"),
        "cation", 0.85, "charge-assisted N–H···O to sulfonate/carboxylate", ("sulfonate-ammonium",),
        None, "none", ("sulfonate", "carboxylate"),
        "amine protonation", charge=+1,
    ),
    SynthonType(
        "carboxylate", "Carboxylate", "羧酸根",
        ("[#6:1]-[CX3:2](=[OX1:4])-[OX1-:3]",),
        "anion", 0.92, "charge-assisted R2^2(8) with amidinium", ("carboxylate-amidinium",),
        ("axis", "attach", "root", 1.97), "full", ("amidinium", "guanidinium", "ammonium"),
        "carboxylic acid deprotonation", charge=-1,
    ),
    SynthonType(
        "sulfonate", "Sulfonate", "磺酸根",
        ("[#6:1]-[SX4:2](=[OX1:4])(=[OX1])-[OX1-:3]",),
        "anion", 0.93, "GS sheets / charge-assisted N–H···O", ("sulfonate-guanidium", "sulfonate-ammonium"),
        None, "none", ("guanidinium", "ammonium", "amidinium"),
        "sulfonation (H2SO4/SO3 or ClSO3H)", charge=-1,
    ),
    SynthonType(
        "phosphonate", "Phosphonate", "膦酸根",
        ("[#6:1]-[PX4:2](=[OX1:4])(-[OX1-:3])-[OX1-,OX2H1]",),
        "anion", 0.80, "charge-assisted O–H···O / N–H···O", ("phosphonate",),
        None, "none", ("amidinium", "ammonium"),
        "Arbuzov / Pd-catalysed P–C coupling then hydrolysis", charge=-1,
    ),
    # ---------------- strong neutral synthons ----------------
    SynthonType(
        "dat", "2,4-Diaminotriazine (DAT)", "二氨基三嗪 (DAT)",
        ("[#6:1]-[c:2]1[n][c](-[NX3;H1,H2;!$(NC=O)])[n:4][c](-[NX3;H1,H2;!$(NC=O):3])[n]1",
         "[#7:1]-[c:2]1[n][c](-[NX3;H1,H2;!$(NC=O)])[n:4][c](-[NX3;H1,H2;!$(NC=O):3])[n]1"),
        "neutral", 0.85, "N–H···N R2^2(8) face-to-face / side-by-side", ("dat",),
        ("dimer", 3.00), "approx", (),
        "aryl nitrile + dicyandiamide, KOH (N-substituted: cyanuric chloride + amines)",
    ),
    SynthonType(
        "carboxylic_acid", "Carboxylic acid", "羧酸",
        ("[#6:1]-[CX3:2](=[OX1:4])-[OX2H1:3]",),
        "neutral", 0.85, "O–H···O R2^2(8) homodimer", ("carboxy", "carboxyl-pyridine"),
        ("dimer", 2.64), "full", ("pyridyl", "amidinium"),
        "ester/nitrile hydrolysis; or Suzuki with 4-(methoxycarbonyl)phenylboronic acid then hydrolysis",
    ),
    SynthonType(
        "boronic_acid", "Boronic acid", "硼酸",
        ("[#6:1]-[BX3:2](-[OX2H1:3])-[OX2H1:4]",),
        "neutral", 0.60, "O–H···O R2^2(8) homodimer", (),
        ("dimer", 2.75), "full", (),
        "aryl halide → Miyaura borylation → hydrolysis",
    ),
    SynthonType(
        "phosphonic_acid", "Phosphonic acid", "膦酸",
        ("[#6:1]-[PX4:2](=[OX1:4])(-[OX2H1:3])-[OX2H1]",),
        "neutral", 0.70, "O–H···O=P multiple H-bonds", ("phosphonate",),
        ("dimer", 2.55), "approx", (),
        "Arbuzov / Pd-catalysed P–C coupling then TMSBr dealkylation",
    ),
    SynthonType(
        "sulfonic_acid", "Sulfonic acid", "磺酸",
        ("[#6:1]-[SX4:2](=[OX1:4])(=[OX1])-[OX2H1:3]",),
        "neutral", 0.55, "usually ionised; pairs with bases", (),
        None, "none", ("guanidinium", "ammonium", "amidinium"),
        "sulfonation (H2SO4/SO3 or ClSO3H)",
    ),
    SynthonType(
        "pyridone", "2-Pyridone", "2-吡啶酮",
        ("[OX1:4]=c1[nH:3]cccc1",),
        "neutral", 0.75, "N–H···O=C R2^2(8) homodimer", (),
        ("dimer", 2.80), "full", (),
        "2-methoxypyridine coupling then demethylation (HBr or TMSCl/NaI)",
    ),
    SynthonType(
        "tetrazole", "Tetrazole", "四唑",
        ("[nH:3]1[n:4][n][n][c]1", "[c]1[n][nH:3][n:4][n]1"),
        "neutral", 0.62, "N–H···N chains / dimers", (),
        ("dimer", 2.85), "approx", (),
        "nitrile + NaN3 / ZnBr2 ([3+2] cycloaddition)",
    ),
    SynthonType(
        "triazole", "1,2,4-Triazole", "1,2,4-三唑",
        ("[nH:3]1[n:4][c][n][c]1", "[nH:3]1[c][n][n:4][c]1"),
        "neutral", 0.62, "N–H···N chains / dimers", (),
        ("dimer", 2.90), "approx", (),
        "nitrile + hydrazide condensation",
    ),
    SynthonType(
        "pyrazole", "Pyrazole", "吡唑",
        ("[nH:3]1[n:4][c][c][c]1",),
        "neutral", 0.70, "N–H···N trimers / catemers", ("pyrazolyl trimer",),
        ("dimer", 2.90), "approx", (),
        "Suzuki with 4-pyrazoleboronic acid pinacol ester (Boc/THP-protected)",
    ),
    SynthonType(
        "urea", "Urea", "脲",
        ("[#6:1]-[NX3H1:3]-[CX3:2](=[OX1:4])-[NX3;H1,H2]",),
        "neutral", 0.70, "bifurcated N–H···O tapes", (),
        None, "none", (),
        "amine + isocyanate (or CDI then amine)",
    ),
    SynthonType(
        "amidine", "Amidine", "脒",
        ("[#6:1]-[CX3:2](=[NX2H1:4])-[NX3H2:3]",),
        "neutral", 0.70, "N–H···N R2^2(8) dimer; protonated with acids", ("carboxylate-amidinium",),
        ("dimer", 3.00), "approx", ("carboxylic_acid", "sulfonic_acid"),
        "nitrile → amidine (Pinner or LiHMDS)",
    ),
    SynthonType(
        "primary_amide", "Primary amide", "伯酰胺",
        ("[#6:1]-[CX3:2](=[OX1:4])-[NX3H2:3]",),
        "neutral", 0.65, "N–H···O R2^2(8) dimers + ladders", ("amide",),
        ("dimer", 2.92), "full", (),
        "nitrile partial hydrolysis; or acid chloride + NH3",
    ),
    SynthonType(
        "secondary_amide", "Secondary amide", "仲酰胺",
        ("[#6:1]-[CX3:2](=[OX1:4])-[NX3H1:3]-[#6]",),
        "neutral", 0.55, "N–H···O=C catemers", ("amide",),
        None, "none", (),
        "acid chloride / coupling reagent + amine",
    ),
    SynthonType(
        "imidazole", "Imidazole", "咪唑",
        ("[nH:3]1[c][n:4][c][c]1",),
        "neutral", 0.55, "N–H···N catemers", ("imidazolyl",),
        None, "none", (),
        "Debus–Radziszewski / Suzuki with imidazolyl boronate",
    ),
    # ---------------- weaker / single-role groups ----------------
    SynthonType(
        "silanol", "Silanol", "硅醇",
        ("[Si:2]-[OX2H1:3]",),
        "neutral", 0.60, "Si–O–H···O strongly donating chains / rings", ("hydroxy",),
        ("axis", "root", "donor", 1.40), "approx", (),
        "hydrolysis of alkoxy-/chlorosilanes under mild conditions",
    ),
    SynthonType(
        "hydroxy", "Phenol / hydroxy", "酚羟基",
        ("[c:1]-[OX2H1:2]",),
        "weak", 0.45, "O–H···O / O–H···N chains", ("hydroxy",),
        ("axis", "attach", "root", 1.40), "approx", ("pyridyl",),
        "methyl ether coupling then BBr3 demethylation",
    ),
    SynthonType(
        "alcohol", "Aliphatic alcohol", "醇羟基",
        ("[CX4:1]-[OX2H1:2]",),
        "weak", 0.40, "O–H···O chains (often conformationally flexible)", ("hydroxy",),
        None, "none", (),
        "ester/ketone reduction; Grignard addition",
    ),
    SynthonType(
        "secondary_aryl_amine", "Secondary aryl amine (N–H)", "仲芳胺 (N–H)",
        ("[c:1]-[NX3H1;!$(NC=O);!$(N[#6]=[#7,#8]):2]-[#6]",),
        "weak", 0.35, "weak N–H···N/O donor", ("amine",),
        None, "none", (),
        "Buchwald–Hartwig amination",
    ),
    SynthonType(
        "pyridyl", "Pyridyl (acceptor)", "吡啶基 (受体)",
        ("[nX2;r6;$(n1ccccc1):4]",),
        "acceptor", 0.40, "accepts O–H/N–H (heterosynthon with COOH)", ("pyridyl", "carboxyl-pyridine"),
        ("axis", "ring_centroid", "acceptor", 1.40), "approx", ("carboxylic_acid", "hydroxy"),
        "Suzuki with pyridylboronic acid",
    ),
    SynthonType(
        "amine", "Aryl amine", "芳胺",
        ("[c:1]-[NX3H2;!$(NC=O);!$(Nc(n)n):2]",),
        "weak", 0.35, "N–H···N/O weak donors", ("amine",),
        None, "none", (),
        "nitro reduction / Buchwald–Hartwig amination",
    ),
    SynthonType(
        "nitrile", "Nitrile", "腈",
        ("[#6:1]-[CX2:2]#[NX1:4]",),
        "weak", 0.30, "C–H···N weak acceptor", ("nitrile",),
        ("axis", "root", "acceptor", 1.60), "approx", (),
        "Rosenmund–von Braun or Pd-catalysed cyanation",
    ),
)

SYNTHON_BY_KEY = {s.key: s for s in SYNTHON_TYPES}
STRONG_THRESHOLD = 0.5


@dataclass
class SynthonMatch:
    key: str
    atoms: tuple[int, ...]  # synthon atoms (excluding attach atoms)
    root: int | None
    attach: tuple[int, ...]
    donor: int | None
    acceptor: int | None
    extra: dict = field(default_factory=dict)

    @property
    def type(self) -> SynthonType:
        return SYNTHON_BY_KEY[self.key]

    def to_dict(self) -> dict:
        return {
            "type": self.key,
            "atoms": list(self.atoms),
            "root": self.root,
            "attach": list(self.attach),
            "donor": self.donor,
            "acceptor": self.acceptor,
        }


@cache
def _compiled(smarts: str) -> tuple[Chem.Mol, dict[int, list[int]]]:
    patt = Chem.MolFromSmarts(smarts)
    if patt is None:
        raise ValueError(f"bad SMARTS: {smarts}")
    roles: dict[int, list[int]] = {}
    for a in patt.GetAtoms():
        mn = a.GetAtomMapNum()
        if mn:
            roles.setdefault(mn, []).append(a.GetIdx())
    return patt, roles


def _dynamic_root(mol: Chem.Mol, synthon_atoms: set[int], donor: int | None, acceptor: int | None):
    """Root = synthon atom bonded to a heavy atom outside the synthon (farthest from D/A)."""
    candidates = []
    for idx in synthon_atoms:
        atom = mol.GetAtomWithIdx(idx)
        for nb in atom.GetNeighbors():
            if nb.GetAtomicNum() > 1 and nb.GetIdx() not in synthon_atoms:
                candidates.append((idx, nb.GetIdx()))
    if not candidates:
        return None, ()
    if len(candidates) == 1 or donor is None:
        return candidates[0][0], (candidates[0][1],)
    dm = Chem.GetDistanceMatrix(mol)
    ref = [x for x in (donor, acceptor) if x is not None]
    best = max(candidates, key=lambda c: sum(dm[c[0]][r] for r in ref))
    return best[0], (best[1],)


def find_synthons(mol: Chem.Mol) -> list[SynthonMatch]:
    """Detect synthon instances; each heavy atom belongs to at most one synthon (priority order)."""
    used: set[int] = set()
    found: list[SynthonMatch] = []
    for st in SYNTHON_TYPES:
        for smarts in st.smarts:
            patt, roles = _compiled(smarts)
            for match in mol.GetSubstructMatches(patt, uniquify=True, maxMatches=1000):
                role_atoms = {k: [match[i] for i in v] for k, v in roles.items()}
                attach = tuple(role_atoms.get(1, [])) + tuple(role_atoms.get(5, []))
                atoms = {a for a in match if a not in attach}
                if atoms & used:
                    continue
                donor = role_atoms.get(3, [None])[0]
                acceptor = role_atoms.get(4, [None])[0]
                root = role_atoms.get(2, [None])[0]
                if root is None and not attach:
                    root, attach = _dynamic_root(mol, atoms, donor, acceptor)
                elif root is None:
                    root = next(iter(atoms))
                if root is None and st.category in ("cation", "anion"):
                    root = donor if donor is not None else acceptor
                found.append(SynthonMatch(st.key, tuple(sorted(atoms)), root, attach, donor, acceptor))
                used |= atoms
    return found


def synthon_summary(matches: list[SynthonMatch]) -> list[dict]:
    counts: dict[str, int] = {}
    for m in matches:
        counts[m.key] = counts.get(m.key, 0) + 1
    out = []
    for key, n in sorted(counts.items(), key=lambda kv: -SYNTHON_BY_KEY[kv[0]].strength):
        st = SYNTHON_BY_KEY[key]
        out.append({"type": key, "count": n, "name_en": st.name_en, "name_zh": st.name_zh,
                    "category": st.category, "strength": st.strength})
    return out


def connection_count(matches: list[SynthonMatch]) -> int:
    """Number of framework-forming (strong) synthon instances."""
    return sum(1 for m in matches if m.type.strength >= STRONG_THRESHOLD)


def library_table() -> list[dict]:
    return [
        {
            "key": s.key, "name_en": s.name_en, "name_zh": s.name_zh, "category": s.category,
            "strength": s.strength, "motif": s.motif, "builder": s.builder, "fused": s.fused,
            "charge": s.charge, "partners": list(s.partners), "route": s.route,
            "hofsyn_classes": list(s.hofsyn_classes),
        }
        for s in SYNTHON_TYPES
    ]
