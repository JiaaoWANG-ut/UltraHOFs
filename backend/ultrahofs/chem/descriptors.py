"""2D molecular descriptors relevant to HOF formation."""

from __future__ import annotations

import sys
from functools import lru_cache

from rdkit import Chem, RDConfig
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

from .synthons import SynthonMatch


@lru_cache(maxsize=1)
def _sascorer():
    path = f"{RDConfig.RDContribDir}/SA_Score"
    if path not in sys.path:
        sys.path.append(path)
    try:
        import sascorer  # type: ignore

        return sascorer
    except Exception:  # noqa: BLE001
        return None


def sa_score(mol: Chem.Mol) -> float | None:
    mod = _sascorer()
    if mod is None:
        return None
    try:
        return round(float(mod.calculateScore(mol)), 2)
    except Exception:  # noqa: BLE001
        return None


def _side_atoms(mol: Chem.Mol, start: int, blocked: int) -> set[int]:
    seen = {start}
    stack = [start]
    while stack:
        cur = stack.pop()
        for nb in mol.GetAtomWithIdx(cur).GetNeighbors():
            j = nb.GetIdx()
            if j == blocked and cur == start:
                continue
            if j not in seen:
                seen.add(j)
                stack.append(j)
    return seen


def rotor_analysis(mol: Chem.Mol, synthons: list[SynthonMatch]) -> dict:
    """Classify rotatable bonds: terminal-synthon rotors, aryl torsions, and flexible rotors.

    Only flexible rotors (sp3 chains, ethers, ...) change the overall tecton shape; aryl
    torsions and synthon rotations keep connection directions largely intact.
    """
    synthon_atoms = set()
    for s in synthons:
        synthon_atoms |= set(s.atoms)
    heavy = {a.GetIdx() for a in mol.GetAtoms() if a.GetAtomicNum() > 1}
    terminal = aryl = flexible = 0
    for a, b in mol.GetSubstructMatches(Lipinski.RotatableBondSmarts):
        side_b = _side_atoms(mol, b, a) & heavy
        side_a = _side_atoms(mol, a, b) & heavy
        small = side_b if len(side_b) <= len(side_a) else side_a
        if small and small <= synthon_atoms:
            terminal += 1
            continue
        at_a, at_b = mol.GetAtomWithIdx(a), mol.GetAtomWithIdx(b)

        def _shape_preserving(at: Chem.Atom) -> bool:
            # aromatic / sp / sp2 atoms, or quaternary sp3 hubs (C(Ar)4, Si(Ar)4, adamantyl):
            # rotating about such a bond keeps the connection direction (para axis) intact.
            if at.GetIsAromatic() or at.GetHybridization() in (
                    Chem.HybridizationType.SP, Chem.HybridizationType.SP2):
                return True
            return at.GetDegree() == 4 and at.GetTotalNumHs() == 0

        if (at_a.GetIsAromatic() and _shape_preserving(at_b)) or (
                at_b.GetIsAromatic() and _shape_preserving(at_a)):
            aryl += 1
        else:
            flexible += 1
    return {"terminal_synthon_rotors": terminal, "aryl_torsions": aryl, "flexible_rotors": flexible}


def symmetry_info(mol: Chem.Mol, synthons: list[SynthonMatch]) -> dict:
    ranks = list(Chem.CanonicalRankAtoms(mol, breakTies=False))
    roots = [s.root for s in synthons if s.root is not None]
    classes = {ranks[r] for r in roots}
    n_auto = len(mol.GetSubstructMatches(mol, uniquify=False, maxMatches=5000, useChirality=False))
    return {
        "synthon_equivalence_classes": len(classes),
        "synthons_equivalent": len(roots) > 0 and len(classes) == 1,
        "automorphisms": n_auto,
    }


def basic_descriptors(mol: Chem.Mol) -> dict:
    return {
        "mw": round(Descriptors.MolWt(mol), 2),
        "heavy_atoms": mol.GetNumHeavyAtoms(),
        "formal_charge": Chem.GetFormalCharge(mol),
        "rings": rdMolDescriptors.CalcNumRings(mol),
        "aromatic_rings": rdMolDescriptors.CalcNumAromaticRings(mol),
        "fsp3": round(rdMolDescriptors.CalcFractionCSP3(mol), 3),
        "rotatable_bonds": rdMolDescriptors.CalcNumRotatableBonds(mol),
        "tpsa": round(rdMolDescriptors.CalcTPSA(mol), 1),
        "logp": round(Crippen.MolLogP(mol), 2),
        "hbd": Lipinski.NumHDonors(mol),
        "hba": Lipinski.NumHAcceptors(mol),
        "sa_score": sa_score(mol),
        "formula": rdMolDescriptors.CalcMolFormula(mol),
    }
