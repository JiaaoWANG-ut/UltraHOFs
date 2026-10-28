"""Optional Cambridge Structural Database connector (requires a licensed `ccdc` installation).

Only active when the CSD Python API is importable and licensed. Mining results are written to the
curation queue as 'candidate' entries and are never auto-accepted.
"""

from __future__ import annotations


def csd_available() -> tuple[bool, str]:
    try:
        import ccdc  # type: ignore  # noqa: F401
        from ccdc import io  # type: ignore

        reader = io.EntryReader("CSD")
        n = len(reader)
        return True, f"CSD available ({n} entries)"
    except ImportError:
        return False, "CSD Python API (ccdc) is not installed in this environment"
    except Exception as e:  # noqa: BLE001
        return False, f"CSD Python API found but not usable: {str(e)[:200]}"


def entry_by_ccdc(ccdc_number: str) -> dict | None:
    """Look up an entry by CCDC deposition number; returns SMILES and CIF text if available."""
    ok, _ = csd_available()
    if not ok:
        return None
    from ccdc import io, search  # type: ignore

    q = search.TextNumericSearch()
    q.add_ccdc_number(int(ccdc_number))
    hits = q.search()
    if not hits:
        return None
    entry = io.EntryReader("CSD").entry(hits[0].identifier)
    cryst = entry.crystal
    return {"refcode": entry.identifier, "smiles": entry.molecule.smiles or "", "cif": cryst.to_string("cif"),
            "doi": getattr(entry.publication, "doi", None) if entry.publication else None}


def mine_candidates(max_hits: int = 500, min_void_fraction: float = 0.15) -> list[dict]:
    """Organic, metal-free CSD entries with >=3 strong synthons and a guest-accessible void.

    Returns lightweight candidate records for the curation queue.
    """
    ok, _ = csd_available()
    if not ok:
        return []
    from ccdc import io  # type: ignore
    from rdkit import Chem

    from ..chem.synthons import STRONG_THRESHOLD, find_synthons

    out = []
    reader = io.EntryReader("CSD")
    for entry in reader:
        if len(out) >= max_hits:
            break
        try:
            if not entry.is_organic or entry.has_disorder:
                continue
            smi = entry.molecule.smiles
            mol = Chem.MolFromSmiles(smi) if smi else None
            if mol is None:
                continue
            strong = [s for s in find_synthons(mol) if s.type.strength >= STRONG_THRESHOLD]
            if len(strong) < 3:
                continue
            vf = entry.crystal.void_volume() / entry.crystal.cell_volume if hasattr(entry.crystal, "void_volume") else None
            if vf is not None and vf < min_void_fraction:
                continue
            out.append({"refcode": entry.identifier, "smiles": smi, "void_fraction": vf,
                        "doi": getattr(entry.publication, "doi", None) if entry.publication else None})
        except Exception:  # noqa: BLE001
            continue
    return out
