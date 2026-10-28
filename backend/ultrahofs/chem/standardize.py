"""Molecule parsing, standardisation and identity keys."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, rdMolDescriptors
from rdkit.Chem.MolStandardize import rdMolStandardize

RDLogger.DisableLog("rdApp.*")

MAX_INPUT_LEN = 20000
MAX_HEAVY_ATOMS = 400


class MoleculeInputError(ValueError):
    pass


def parse_molecule(text: str) -> Chem.Mol:
    """Parse SMILES or a MOL block; raise MoleculeInputError with a readable message."""
    if not text or not text.strip():
        raise MoleculeInputError("empty molecule input")
    if len(text) > MAX_INPUT_LEN:
        raise MoleculeInputError("molecule input too long")
    text = text.strip()
    mol = None
    if "\n" in text and ("V2000" in text or "V3000" in text):
        mol = Chem.MolFromMolBlock(text, sanitize=True, removeHs=True)
    else:
        mol = Chem.MolFromSmiles(text)
    if mol is None:
        raise MoleculeInputError("could not parse molecule (invalid SMILES or MOL block)")
    if mol.GetNumHeavyAtoms() == 0:
        raise MoleculeInputError("molecule has no heavy atoms")
    if mol.GetNumHeavyAtoms() > MAX_HEAVY_ATOMS:
        raise MoleculeInputError(f"molecule too large (> {MAX_HEAVY_ATOMS} heavy atoms)")
    return mol


_normalizer = None
_uncharger = None


def _std_tools():
    global _normalizer, _uncharger
    if _normalizer is None:
        _normalizer = rdMolStandardize.Normalizer()
        _uncharger = rdMolStandardize.Uncharger(canonicalOrder=True)
    return _normalizer, _uncharger


def cleanup(mol: Chem.Mol) -> Chem.Mol:
    """Normalise functional-group representations without changing the protonation state."""
    normalizer, _ = _std_tools()
    m = Chem.Mol(mol)
    m = normalizer.normalize(m)
    Chem.SanitizeMol(m)
    return m


def neutral_parent(mol: Chem.Mol) -> Chem.Mol:
    """Neutralised parent used to match a species across protonation states."""
    _, uncharger = _std_tools()
    m = uncharger.uncharge(Chem.Mol(mol))
    Chem.SanitizeMol(m)
    return m


def split_fragments(mol: Chem.Mol) -> list[Chem.Mol]:
    return list(Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True))


@dataclass
class MolKeys:
    smiles: str
    inchi: str
    inchikey: str
    parent_key: str
    skeleton_key: str
    formula: str
    mw: float
    charge: int
    heavy_atoms: int

    def dict(self) -> dict:
        return asdict(self)


def inchikey_of(mol: Chem.Mol) -> str:
    try:
        key = Chem.MolToInchiKey(mol)
    except Exception:  # noqa: BLE001
        key = ""
    return key or ""


def mol_keys(mol: Chem.Mol) -> MolKeys:
    m = cleanup(mol)
    smiles = Chem.MolToSmiles(m)
    try:
        inchi = Chem.MolToInchi(m) or ""
    except Exception:  # noqa: BLE001
        inchi = ""
    inchikey = inchikey_of(m)
    if not inchikey:
        # Fall back to a deterministic pseudo-key so the row stays unique.
        import hashlib

        inchikey = "NOINCHI-" + hashlib.sha1(smiles.encode()).hexdigest()[:19].upper()
    try:
        parent_key = inchikey_of(neutral_parent(m)) or inchikey
    except Exception:  # noqa: BLE001
        parent_key = inchikey
    return MolKeys(
        smiles=smiles,
        inchi=inchi,
        inchikey=inchikey,
        parent_key=parent_key,
        skeleton_key=parent_key[:14],
        formula=rdMolDescriptors.CalcMolFormula(m),
        mw=round(Descriptors.MolWt(m), 3),
        charge=Chem.GetFormalCharge(m),
        heavy_atoms=m.GetNumHeavyAtoms(),
    )


def canonical_smiles(text_or_mol: str | Chem.Mol) -> str:
    mol = parse_molecule(text_or_mol) if isinstance(text_or_mol, str) else text_or_mol
    return Chem.MolToSmiles(cleanup(mol))
