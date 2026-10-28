"""Molecule registry, experimental precedent lookup and synthon priors."""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

from rdkit import Chem
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..chem.depict import mol_svg
from ..chem.similarity import fp_to_bytes, morgan_fp, registry
from ..chem.standardize import mol_keys, parse_molecule, split_fragments
from ..chem.synthons import connection_count, find_synthons, synthon_summary
from ..models import Component, ComponentSystem, HOFEntry, Molecule

EXPERIMENTAL_INDEX = "experimental_tectons"


def get_or_create_molecule(db: Session, mol: Chem.Mol, *, origin: str = "user", name: str = "",
                           experimental: bool = False, provenance: dict | None = None) -> Molecule:
    keys = mol_keys(mol)
    row = db.execute(select(Molecule).where(Molecule.inchikey == keys.inchikey)).scalar_one_or_none()
    if row is None:
        m = Chem.MolFromSmiles(keys.smiles)
        syn = find_synthons(m)
        row = Molecule(
            smiles=keys.smiles, inchi=keys.inchi, inchikey=keys.inchikey, parent_key=keys.parent_key,
            skeleton_key=keys.skeleton_key, formula=keys.formula, mw=keys.mw, charge=keys.charge,
            heavy_atoms=keys.heavy_atoms, name=name, synthons=synthon_summary(syn),
            n_connect=connection_count(syn), fp=fp_to_bytes(morgan_fp(m)),
            origin="experimental" if experimental else origin,
            is_experimental_tecton=experimental, provenance=provenance or {},
        )
        db.add(row)
        db.flush()
    else:
        if experimental and not row.is_experimental_tecton:
            row.is_experimental_tecton = True
            row.origin = "experimental"
        if name and not row.name:
            row.name = name
    return row


def system_key(components: list[tuple[Molecule, float]]) -> str:
    return "|".join(sorted(f"{m.inchikey}*{round(s, 3):g}" for m, s in components))


def get_or_create_system(db: Session, components: list[tuple[Molecule, float, str]],
                         name: str = "") -> ComponentSystem:
    framework = [(m, s) for m, s, role in components if role in ("tecton", "co_tecton")]
    key = system_key(framework or [(m, s) for m, s, _r in components])
    row = db.execute(select(ComponentSystem).where(ComponentSystem.system_key == key)).scalar_one_or_none()
    if row is None:
        charged = any(m.charge != 0 for m, _s, _r in components)
        row = ComponentSystem(name=name, system_key=key, n_components=len(framework) or len(components),
                              charge_assisted=charged)
        for m, s, role in components:
            row.components.append(Component(molecule_id=m.id, role=role, stoichiometry=s))
        db.add(row)
        db.flush()
    elif name and not row.name:
        row.name = name
    return row


def _load_experimental() -> list[tuple[int, str]]:
    from ..db import SessionLocal

    with SessionLocal() as db:
        rows = db.execute(select(Molecule.id, Molecule.smiles).where(Molecule.is_experimental_tecton.is_(True)))
        return [(r[0], r[1]) for r in rows]


def experimental_index():  # noqa: ANN201
    return registry.get(EXPERIMENTAL_INDEX, _load_experimental)


def invalidate_indices() -> None:
    registry.invalidate()
    synthon_prior.cache_clear()


def entries_for_molecules(db: Session, mol_ids: list[int], limit: int = 20) -> list[HOFEntry]:
    if not mol_ids:
        return []
    q = (select(HOFEntry).join(ComponentSystem, HOFEntry.system_id == ComponentSystem.id)
         .join(Component, Component.system_id == ComponentSystem.id)
         .where(Component.molecule_id.in_(mol_ids))
         .where(HOFEntry.curation_status.in_(("auto", "verified", "needs_review")))
         .distinct().limit(limit))
    return list(db.execute(q).scalars())


def entry_brief(e: HOFEntry) -> dict:
    refs = [er.reference for er in e.references if er.reference is not None]
    r = refs[0] if refs else None
    return {
        "id": e.id, "name": e.name, "ccdc_numbers": e.ccdc_numbers, "year": e.year,
        "topology": e.topology, "hbond_class": e.hbond_class, "curation_status": e.curation_status,
        "reference": None if r is None else {
            "id": r.id, "doi": r.doi, "title": r.title, "journal": r.journal_abbrev or r.journal,
            "year": r.year, "authors": [a.get("family", "") for a in (r.authors or [])][:3],
        },
    }


def precedent_lookup(db: Session, mol: Chem.Mol, top_k: int = 5) -> dict:
    """Has this molecule (or its skeleton / a close analogue) been crystallised as an HOF?"""
    frags = split_fragments(mol)
    keys = [mol_keys(f) for f in frags]
    exact_ids, parent_ids, skeleton_ids = set(), set(), set()
    for k in keys:
        q = (select(Molecule.id, Molecule.inchikey, Molecule.parent_key, Molecule.skeleton_key)
             .where((Molecule.inchikey == k.inchikey) | (Molecule.parent_key == k.parent_key)
                    | (Molecule.skeleton_key == k.skeleton_key))
             .where(Molecule.is_experimental_tecton.is_(True)))
        for row in db.execute(q):
            if row[1] == k.inchikey:
                exact_ids.add(row[0])
            elif row[2] == k.parent_key:
                parent_ids.add(row[0])
            else:
                skeleton_ids.add(row[0])
    exact = entries_for_molecules(db, list(exact_ids))
    parent = entries_for_molecules(db, list(parent_ids - exact_ids))
    skeleton = entries_for_molecules(db, list(skeleton_ids - exact_ids - parent_ids))
    idx = experimental_index()
    largest = max(frags, key=lambda m: m.GetNumHeavyAtoms())
    sims = idx.similar(largest, top_k=top_k * 3)
    similar = []
    seen = exact_ids | parent_ids
    for mid, s in sims:
        if mid in seen:
            continue
        m = db.get(Molecule, mid)
        ents = entries_for_molecules(db, [mid], limit=3)
        similar.append({"molecule_id": mid, "smiles": m.smiles if m else "", "similarity": s,
                        "entries": [entry_brief(e) for e in ents]})
        if len(similar) >= top_k:
            break
    status = "exact" if exact else ("same_parent" if parent else ("same_skeleton" if skeleton else
                                                                 ("analogues" if similar else "none")))
    return {
        "status": status,
        "exact": [entry_brief(e) for e in exact],
        "same_parent": [entry_brief(e) for e in parent],
        "same_skeleton": [entry_brief(e) for e in skeleton],
        "similar": similar,
        "max_similarity": sims[0][1] if sims else None,
        "n_indexed": len(idx),
    }


@lru_cache(maxsize=1)
def synthon_prior() -> dict[str, float]:
    """Relative frequency of each synthon type among experimental tectons (normalised to max=1)."""
    from ..db import SessionLocal

    with SessionLocal() as db:
        rows = db.execute(select(Molecule.synthons).where(Molecule.is_experimental_tecton.is_(True))).all()
    counts: Counter = Counter()
    for (syn,) in rows:
        for s in syn or []:
            counts[s["type"]] += 1
    if not counts:
        return {}
    top = max(counts.values())
    return {k: round(v / top, 3) for k, v in counts.items()}


def molecule_dict(m: Molecule, with_svg: bool = True) -> dict:
    return {
        "id": m.id, "smiles": m.smiles, "inchikey": m.inchikey, "formula": m.formula, "mw": m.mw,
        "charge": m.charge, "name": m.name, "synthons": m.synthons, "n_connect": m.n_connect,
        "origin": m.origin, "is_experimental_tecton": m.is_experimental_tecton,
        "score": (m.score or {}).get("score"), "band": (m.score or {}).get("band"),
        "svg": mol_svg(m.smiles) if with_svg else None,
    }


def count_molecules(db: Session) -> dict:
    total = db.execute(select(func.count(Molecule.id))).scalar_one()
    exp = db.execute(select(func.count(Molecule.id)).where(Molecule.is_experimental_tecton.is_(True))).scalar_one()
    return {"total": total, "experimental_tectons": exp}


def parse_input(text: str) -> Chem.Mol:
    return parse_molecule(text)
