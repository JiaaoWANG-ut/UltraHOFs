"""Name → structure fallbacks (OPSIN, offline; PubChem, online) with composition checks."""

from __future__ import annotations

import re
from collections import Counter

from rdkit import Chem

from ..chem.standardize import parse_molecule


def clean_name(name: str) -> str:
    name = name.strip().replace("’", "'").replace("′", "'")
    name = re.sub(r"\s+", " ", name)
    return name


def opsin(name: str) -> str | None:
    try:
        import warnings

        from py2opsin import py2opsin

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            smi = py2opsin(clean_name(name))
        if smi and Chem.MolFromSmiles(smi) is not None:
            return smi
    except Exception:  # noqa: BLE001
        return None
    return None


def pubchem(name: str, timeout: float = 15.0) -> str | None:
    from urllib.parse import quote

    import httpx

    try:
        url = ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
               f"{quote(clean_name(name), safe='')}/property/IsomericSMILES/JSON")
        r = httpx.get(url, timeout=timeout)
        if r.status_code != 200:
            return None
        props = r.json().get("PropertyTable", {}).get("Properties", [])
        smi = props[0].get("IsomericSMILES") or props[0].get("SMILES") if props else None
        return smi if smi and Chem.MolFromSmiles(smi) is not None else None
    except Exception:  # noqa: BLE001
        return None


def heavy_formula(smiles: str) -> Counter:
    mol = parse_molecule(smiles)
    return Counter(a.GetSymbol() for a in mol.GetAtoms() if a.GetAtomicNum() > 1)


def resolve_name(name: str, expected_heavy: list[Counter] | None = None, online: bool = False) -> tuple[str | None, str]:
    """Resolve a compound name; if expected compositions are given, require a heavy-atom match."""
    if not name or len(name) < 3:
        return None, ""
    for method, fn in (("opsin", opsin), ("pubchem", pubchem if online else None)):
        if fn is None:
            continue
        smi = fn(name)
        if not smi:
            continue
        if expected_heavy:
            hf = heavy_formula(smi)
            if not any(hf == e for e in expected_heavy):
                continue
        return smi, method
    return None, ""
