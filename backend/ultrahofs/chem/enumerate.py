"""Combinatorial tecton assembly: core x arm x synthon, with symmetric substitution."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from rdkit import Chem

from .fragments import ARM_BY_KEY, CORE_BY_KEY, CORES, FRAG_BY_KEY, Arm, Core, SynthonFragment
from .standardize import mol_keys
from .synthons import SYNTHON_BY_KEY, find_synthons

# synthons that must not sit on an sp carbon (ynols, ynamines, alkynylboronic acids are unstable)
_NO_SP_ATTACH = {"hydroxy", "urea", "boronic_acid", "amine", "pyridone"}


def _relabel(smiles: str, mapping: dict[int, int]) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"bad fragment SMILES {smiles}")
    for a in mol.GetAtoms():
        if a.GetAtomicNum() == 0 and a.GetAtomMapNum() in mapping:
            a.SetAtomMapNum(mapping[a.GetAtomMapNum()])
    return mol


def _combine(mols: Iterable[Chem.Mol]) -> Chem.Mol:
    it = iter(mols)
    out = next(it)
    for m in it:
        out = Chem.CombineMols(out, m)
    return out


def assemble(core: Core, arm: Arm, frag: SynthonFragment, smiles_override: str | None = None) -> Chem.Mol | None:
    """Return the assembled tecton or None if the combination is not chemically meaningful."""
    syn_smiles = smiles_override or frag.smiles
    pieces = [Chem.MolFromSmiles(core.smiles)]
    if frag.fused:
        if not core.fused_pairs or arm.key != "none":
            return None
        for a, b in core.fused_pairs:
            pieces.append(_relabel(syn_smiles, {1: a, 2: b}))
    else:
        if core.needs_arm and arm.key == "none":
            return None
        for k in range(1, core.n_sites + 1):
            if arm.key == "none":
                pieces.append(_relabel(syn_smiles, {1: k}))
            else:
                pieces.append(_relabel(arm.smiles, {1: k, 2: 100 + k}))
                pieces.append(_relabel(syn_smiles, {1: 100 + k}))
    try:
        mol = Chem.molzip(_combine(pieces))
        Chem.SanitizeMol(mol)
    except Exception:  # noqa: BLE001
        return None
    if any(a.GetAtomicNum() == 0 for a in mol.GetAtoms()):
        return None
    if not _chemically_sane(mol, frag.key):
        return None
    return Chem.MolFromSmiles(Chem.MolToSmiles(mol))


def _chemically_sane(mol: Chem.Mol, synthon_key: str) -> bool:
    if synthon_key not in _NO_SP_ATTACH and synthon_key != "boronic_acid":
        return True
    for m in find_synthons(mol):
        if m.key != synthon_key:
            continue
        for at in m.attach:
            atom = mol.GetAtomWithIdx(at)
            if atom.GetHybridization() == Chem.HybridizationType.SP:
                return False
            if synthon_key == "boronic_acid" and not atom.GetIsAromatic():
                return False
    return True


@dataclass
class Candidate:
    smiles: str
    core: str
    arm: str
    synthon: str
    keys: dict

    def to_dict(self) -> dict:
        return {"smiles": self.smiles, "core": self.core, "arm": self.arm, "synthon": self.synthon,
                "inchikey": self.keys["inchikey"], "formula": self.keys["formula"], "mw": self.keys["mw"],
                "heavy_atoms": self.keys["heavy_atoms"]}


def enumerate_tectons(core_keys: list[str] | None = None, arm_keys: list[str] | None = None,
                      synthon_keys: list[str] | None = None, *, min_sites: int = 3,
                      max_heavy_atoms: int = 160, limit: int | None = None) -> Iterator[Candidate]:
    cores = [CORE_BY_KEY[k] for k in core_keys] if core_keys else [c for c in CORES if c.n_sites >= min_sites]
    arms = [ARM_BY_KEY[k] for k in arm_keys] if arm_keys else list(ARM_BY_KEY.values())
    frags = [FRAG_BY_KEY[k] for k in synthon_keys] if synthon_keys else list(FRAG_BY_KEY.values())
    seen: set[str] = set()
    n = 0
    for core, arm, frag in itertools.product(cores, arms, frags):
        mol = assemble(core, arm, frag)
        if mol is None or mol.GetNumHeavyAtoms() > max_heavy_atoms:
            continue
        keys = mol_keys(mol).dict()
        if keys["inchikey"] in seen:
            continue
        seen.add(keys["inchikey"])
        yield Candidate(keys["smiles"], core.key, arm.key, frag.key, keys)
        n += 1
        if limit and n >= limit:
            return


def count_combinations(core_keys: list[str] | None, arm_keys: list[str] | None,
                       synthon_keys: list[str] | None, min_sites: int = 3) -> int:
    nc = len(core_keys) if core_keys else sum(1 for c in CORES if c.n_sites >= min_sites)
    na = len(arm_keys) if arm_keys else len(ARM_BY_KEY)
    ns = len(synthon_keys) if synthon_keys else len(FRAG_BY_KEY)
    return nc * na * ns


def route_hint(core_key: str, arm_key: str, synthon_key: str) -> dict:
    core = CORE_BY_KEY[core_key]
    arm = ARM_BY_KEY[arm_key]
    st = SYNTHON_BY_KEY[synthon_key]
    frag = FRAG_BY_KEY.get(synthon_key)
    en: list[str] = []
    zh: list[str] = []
    en.append(f"Core precursor: {core.precursor or core.name_en}.")
    zh.append(f"核心前体：{core.precursor or core.name_zh}。")
    if frag is not None and frag.fused:
        en.append(f"Fused synthon on adjacent positions: {st.route}.")
        zh.append(f"在相邻位点构建稠合合成子：{st.route}。")
    else:
        if arm.key != "none":
            en.append(f"Arms: {arm.coupling}.")
            zh.append(f"连接臂：{arm.coupling}。")
        en.append(f"Synthon installation: {st.route}.")
        zh.append(f"合成子引入：{st.route}。")
    en.append("Template-based suggestion — not an experimentally validated route.")
    zh.append("基于反应模板的提示，并非经过实验验证的路线。")
    return {"en": en, "zh": zh}
