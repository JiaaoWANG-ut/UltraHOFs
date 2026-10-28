"""Experimental HOF database: search, detail, citations, CIF access, statistics and curation."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from rdkit import Chem
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from ..chem.depict import mol_svg
from ..chem.standardize import MoleculeInputError, parse_molecule
from ..config import get_settings
from ..db import get_db
from ..models import (
    Component,
    ComponentSystem,
    EntryReference,
    HOFEntry,
    Molecule,
    Property,
    Reference,
    SynthesisCondition,
    User,
)
from ..models.hof import CURATION_STATUSES, EVIDENCE_LABELS, EVIDENCE_VALUES, default_evidence
from ..services.molecules import (
    experimental_index,
    get_or_create_molecule,
    get_or_create_system,
    invalidate_indices,
)
from ..services.references import export_reference, reference_dict, upsert_reference
from .deps import audit, current_user, require_role

router = APIRouter()
VISIBLE = ("auto", "verified", "needs_review")


def _tectons(e: HOFEntry) -> list[Component]:
    if e.system is None:
        return []
    comps = sorted(e.system.components, key=lambda c: (c.role != "tecton", -c.molecule.heavy_atoms))
    return [c for c in comps if c.role in ("tecton", "co_tecton")]


def entry_summary(e: HOFEntry) -> dict:
    tect = _tectons(e)
    refs = [er.reference for er in e.references if er.reference]
    r = refs[0] if refs else None
    return {
        "id": e.id, "name": e.name, "year": e.year, "ccdc_numbers": e.ccdc_numbers,
        "hbond_class": e.hbond_class, "topology": e.topology, "space_group": e.space_group,
        "hbond_dimensionality": e.hbond_dimensionality, "density": e.density,
        "pld": (e.pore or {}).get("pld_A"), "lcd": (e.pore or {}).get("lcd_A"),
        "asa_m2_g": (e.pore or {}).get("asa_m2_g"),
        "curation_status": e.curation_status, "confidence": e.confidence,
        "evidence": {k: (e.evidence or {}).get(k, {}).get("value", "unknown") for k in EVIDENCE_LABELS},
        "components": [{"molecule_id": c.molecule_id, "smiles": c.molecule.smiles, "role": c.role,
                        "stoichiometry": c.stoichiometry} for c in tect],
        "svg": mol_svg(tect[0].molecule.smiles, 260, 190) if tect else "",
        "reference": None if r is None else {"id": r.id, "doi": r.doi, "journal": r.journal_abbrev or r.journal,
                                             "year": r.year, "title": r.title,
                                             "first_author": (r.authors or [{}])[0].get("family", "")
                                             if r.authors else ""},
    }


def entry_detail(e: HOFEntry, user: User | None) -> dict:
    d = entry_summary(e)
    comps = e.system.components if e.system else []
    d.update({
        "formula": e.formula, "cell": e.cell, "csd_refcodes": e.csd_refcodes, "pore": e.pore,
        "evidence": e.evidence, "interpenetration": e.interpenetration, "topology_source": e.topology_source,
        "application": e.application, "notes": e.notes, "issues": e.issues, "source_dataset": e.source_dataset,
        "source_record": e.source_record, "license": e.license, "cleaning_log": e.cleaning_log,
        "has_raw_cif": bool(e.cif_raw_path), "has_framework_cif": bool(e.cif_clean_path),
        "created_at": e.created_at, "updated_at": e.updated_at,
        "all_components": [{
            "molecule_id": c.molecule_id, "smiles": c.molecule.smiles, "role": c.role,
            "stoichiometry": c.stoichiometry, "formula": c.molecule.formula, "charge": c.molecule.charge,
            "name": c.molecule.name, "synthons": c.molecule.synthons, "svg": mol_svg(c.molecule.smiles),
            "score": (c.molecule.score or {}).get("score"), "band": (c.molecule.score or {}).get("band"),
        } for c in comps],
        "conditions": [{"solvents": c.solvents, "temperature": c.temperature, "temperature_c": c.temperature_c,
                        "time_h": c.time_h, "additive": c.additive, "method": c.method} for c in e.conditions],
        "properties": [{"id": p.id, "kind": p.kind, "value": p.value, "unit": p.unit, "text": p.text,
                        "conditions": p.conditions, "reference_id": p.reference_id} for p in e.properties],
        "references": [dict(reference_dict(er.reference), role=er.role) for er in e.references if er.reference],
        "ccdc_links": [f"https://www.ccdc.cam.ac.uk/structures/Search?Ccdcid={n}" for n in e.ccdc_numbers],
    })
    return d


@router.get("/hofs", tags=["hofs"])
def list_hofs(q: str = "", synthon: str = "", topology: str = "", status: str = "", hbond_class: str = "",
              year_min: int | None = None, year_max: int | None = None, dim: int | None = None,
              porous: str = "", charged: bool | None = None, sort: str = "year_desc",
              page: int = Query(1, ge=1), size: int = Query(24, ge=1, le=200),
              user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    stmt = select(HOFEntry)
    statuses = [status] if status else (list(VISIBLE) if user.role in ("admin", "curator") else ["auto", "verified"])
    stmt = stmt.where(HOFEntry.curation_status.in_(statuses))
    if q:
        like = f"%{q.strip()}%"
        ref_ids = select(EntryReference.entry_id).join(Reference, Reference.id == EntryReference.reference_id).where(
            or_(Reference.doi.ilike(like), Reference.title.ilike(like), Reference.raw_citation.ilike(like)))
        mol_entries = (select(HOFEntry.id).join(Component, Component.system_id == HOFEntry.system_id)
                       .join(Molecule, Molecule.id == Component.molecule_id).where(Molecule.name.ilike(like)))
        stmt = stmt.where(or_(HOFEntry.name.ilike(like), cast(HOFEntry.ccdc_numbers, String).ilike(like),
                              HOFEntry.application.ilike(like), HOFEntry.id.in_(ref_ids),
                              HOFEntry.id.in_(mol_entries)))
    if topology:
        stmt = stmt.where(HOFEntry.topology == topology)
    if hbond_class:
        stmt = stmt.where(HOFEntry.hbond_class.ilike(f"%{hbond_class}%"))
    if year_min:
        stmt = stmt.where(HOFEntry.year >= year_min)
    if year_max:
        stmt = stmt.where(HOFEntry.year <= year_max)
    if dim is not None:
        stmt = stmt.where(HOFEntry.hbond_dimensionality >= dim)
    if synthon:
        mids = select(Molecule.id).where(cast(Molecule.synthons, String).ilike(f'%"{synthon}"%'))
        stmt = stmt.where(HOFEntry.system_id.in_(select(Component.system_id).where(Component.molecule_id.in_(mids))))
    if charged is not None:
        stmt = stmt.where(HOFEntry.system_id.in_(
            select(ComponentSystem.id).where(ComponentSystem.charge_assisted.is_(charged))))
    rows = list(db.execute(stmt).scalars())
    if porous in ("yes", "no"):
        rows = [e for e in rows if (e.evidence or {}).get("geometric_porosity", {}).get("value") == porous]
    key = {
        "year_desc": lambda e: (-(e.year or 0), e.id), "year_asc": lambda e: (e.year or 9999, e.id),
        "name": lambda e: (e.name.lower(), e.id), "pld_desc": lambda e: (-((e.pore or {}).get("pld_A") or 0), e.id),
    }.get(sort, lambda e: e.id)
    rows.sort(key=key)
    total = len(rows)
    page_rows = rows[(page - 1) * size: page * size]
    return {"total": total, "page": page, "size": size, "items": [entry_summary(e) for e in page_rows]}


class StructureQuery(BaseModel):
    query: str = Field(min_length=1, max_length=5000)
    mode: str = Field(default="substructure", pattern="^(substructure|similarity|exact)$")
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    limit: int = Field(default=50, ge=1, le=500)


@router.post("/hofs/search/structure", tags=["hofs"])
def structure_search(body: StructureQuery, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    idx = experimental_index()
    if body.mode == "substructure":
        patt = Chem.MolFromSmarts(body.query) or Chem.MolFromSmiles(body.query)
        if patt is None:
            raise HTTPException(422, "invalid SMILES/SMARTS query")
        hits = [(mid, None) for mid in idx.substructure(patt, limit=2000)]
    else:
        try:
            mol = parse_molecule(body.query)
        except MoleculeInputError as e:
            raise HTTPException(422, str(e)) from e
        thr = 0.999 if body.mode == "exact" else body.threshold
        hits = idx.similar(mol, top_k=2000, threshold=thr)
    sim_of = {mid: s for mid, s in hits}
    if not hits:
        return {"total": 0, "items": []}
    stmt = (select(HOFEntry, Component.molecule_id).join(Component, Component.system_id == HOFEntry.system_id)
            .where(Component.molecule_id.in_(list(sim_of))).where(HOFEntry.curation_status.in_(VISIBLE)))
    seen, items = set(), []
    for e, mid in db.execute(stmt):
        if e.id in seen:
            continue
        seen.add(e.id)
        d = entry_summary(e)
        d["similarity"] = sim_of.get(mid)
        d["matched_molecule_id"] = mid
        items.append(d)
    items.sort(key=lambda d: -(d["similarity"] or 0) if body.mode != "substructure" else -(d["year"] or 0))
    return {"total": len(items), "items": items[: body.limit]}


@router.get("/hofs/stats", tags=["hofs"])
def hof_stats(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = list(db.execute(select(HOFEntry).where(HOFEntry.curation_status.in_(VISIBLE))).scalars())
    by_class = Counter((e.hbond_class or "unknown").strip().lower() for e in rows)
    by_year = Counter(e.year for e in rows if e.year)
    by_topo = Counter(e.topology for e in rows if e.topology)
    by_dim = Counter(e.hbond_dimensionality for e in rows if e.hbond_dimensionality is not None)
    by_status = Counter(e.curation_status for e in rows)
    porous = Counter((e.evidence or {}).get("geometric_porosity", {}).get("value", "unknown") for e in rows)
    plds = [round((e.pore or {}).get("pld_A"), 1) for e in rows if (e.pore or {}).get("pld_A") is not None]
    n_refs = db.execute(select(func.count(func.distinct(EntryReference.reference_id)))).scalar_one()
    n_tect = db.execute(select(func.count(Molecule.id)).where(Molecule.is_experimental_tecton.is_(True))).scalar_one()
    syn = Counter()
    for (s,) in db.execute(select(Molecule.synthons).where(Molecule.is_experimental_tecton.is_(True))):
        for x in s or []:
            syn[x["type"]] += 1
    return {
        "n_entries": len(rows), "n_references": n_refs, "n_tectons": n_tect,
        "by_hbond_class": by_class.most_common(20), "by_year": sorted(by_year.items()),
        "by_topology": by_topo.most_common(20), "by_dimensionality": sorted(by_dim.items()),
        "by_status": dict(by_status), "porosity": dict(porous), "pld_values": plds,
        "synthons": syn.most_common(20),
    }


@router.get("/hofs/{entry_id}", tags=["hofs"])
def get_hof(entry_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    e = db.get(HOFEntry, entry_id)
    if e is None:
        raise HTTPException(404, "entry not found")
    return entry_detail(e, user)


@router.get("/hofs/{entry_id}/cif", tags=["hofs"])
def get_cif(entry_id: int, kind: str = Query("framework", pattern="^(raw|framework|display)$"), download: bool = False,
            user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    e = db.get(HOFEntry, entry_id)
    if e is None:
        raise HTTPException(404, "entry not found")
    if kind == "display":
        text = _display_cif(e)
    else:
        path = e.cif_raw_path if kind == "raw" else (e.cif_clean_path or e.cif_raw_path)
        if not path or not Path(path).exists():
            raise HTTPException(404, "no CIF stored for this entry")
        text = Path(path).read_text(errors="replace")
    headers = {}
    if download:
        fname = f"{e.name or 'hof'}_{kind}.cif".replace(" ", "_").replace("/", "_")
        headers["Content-Disposition"] = f'attachment; filename="{fname}"'
    return PlainTextResponse(text, media_type="chemical/x-cif", headers=headers)


def _display_cif(e: HOFEntry) -> str:
    """Clean P1 CIF for the 3D viewer (guest-free framework if available, else normalised raw CIF)."""
    if e.cif_clean_path and Path(e.cif_clean_path).exists():
        return Path(e.cif_clean_path).read_text(errors="replace")
    if not e.cif_raw_path or not Path(e.cif_raw_path).exists():
        raise HTTPException(404, "no CIF stored for this entry")
    cache = get_settings().var_dir / "cif" / "display" / f"{e.id}.cif"
    if cache.exists():
        return cache.read_text()
    from ..analysis.cif_molecules import read_cif
    from ..crystal.export import write_cif

    try:
        atoms = read_cif(Path(e.cif_raw_path).read_text(errors="replace"))
        text = write_cif(atoms, f"entry-{e.id}")
    except Exception as ex:  # noqa: BLE001
        # some dataset files are not CIFs (e.g. Mol2 saved as .cif); use HOFSyn's processed P1 CIF instead
        processed = _processed_hofsyn_cif(e)
        if processed is None:
            raise HTTPException(422, f"CIF could not be normalised for display: {str(ex)[:200] or type(ex).__name__}") from ex
        text = processed.read_text(errors="replace")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text)
    return text


def _processed_hofsyn_cif(e: HOFEntry) -> Path | None:
    if e.source_dataset != "HOFSyn v2" or not e.source_record:
        return None
    from ..ingest.hofsyn import find_cif

    base = get_settings().data_dir / "raw" / "hofsyn" / "processed_cifs" / "hof_database_cifs_raw"
    return find_cif(base, e.source_record, "") if base.exists() else None


@router.get("/references/{ref_id}", tags=["references"])
def get_reference(ref_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    r = db.get(Reference, ref_id)
    if r is None:
        raise HTTPException(404, "reference not found")
    d = reference_dict(r)
    d["entries"] = [{"id": er.entry_id} for er in db.execute(
        select(EntryReference).where(EntryReference.reference_id == r.id)).scalars()]
    return d


@router.get("/references/{ref_id}/export", tags=["references"])
def export_ref(ref_id: int, format: str = Query("bibtex", pattern="^(bibtex|ris|acs)$"),
               user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    r = db.get(Reference, ref_id)
    if r is None:
        raise HTTPException(404, "reference not found")
    ext = {"bibtex": "bib", "ris": "ris", "acs": "txt"}[format]
    return PlainTextResponse(export_reference(r, format), headers={
        "Content-Disposition": f'attachment; filename="ultrahofs_ref_{r.id}.{ext}"'})


# ---------------- curation ----------------

class EntryPatch(BaseModel):
    name: str | None = None
    topology: str | None = None
    interpenetration: int | None = None
    curation_status: str | None = None
    notes: str | None = None
    application: str | None = None
    evidence: dict[str, dict] | None = None
    ccdc_numbers: list[str] | None = None


@router.get("/curation/queue", tags=["curation"])
def curation_queue(status: str = "needs_review", page: int = 1, size: int = 50,
                   user: User = Depends(require_role("admin", "curator")), db: Session = Depends(get_db)) -> dict:
    stmt = select(HOFEntry).where(HOFEntry.curation_status == status).order_by(HOFEntry.confidence, HOFEntry.id)
    rows = list(db.execute(stmt).scalars())
    out = []
    for e in rows[(page - 1) * size: page * size]:
        d = entry_summary(e)
        d["issues"] = e.issues
        out.append(d)
    return {"total": len(rows), "items": out}


@router.patch("/hofs/{entry_id}", tags=["curation"])
def patch_entry(entry_id: int, body: EntryPatch, user: User = Depends(require_role("admin", "curator")),
                db: Session = Depends(get_db)) -> dict:
    e = db.get(HOFEntry, entry_id)
    if e is None:
        raise HTTPException(404, "entry not found")
    changes = body.model_dump(exclude_none=True)
    if "curation_status" in changes and changes["curation_status"] not in CURATION_STATUSES:
        raise HTTPException(422, "invalid curation status")
    if "evidence" in changes:
        ev = dict(e.evidence or default_evidence())
        for k, v in changes["evidence"].items():
            if k not in EVIDENCE_LABELS or v.get("value") not in EVIDENCE_VALUES:
                raise HTTPException(422, f"invalid evidence label {k}")
            ev[k] = {"value": v["value"], "source": "curated", "note": v.get("note", "")[:500]}
        changes["evidence"] = ev
    before = {k: getattr(e, k) for k in changes}
    for k, v in changes.items():
        setattr(e, k, v)
    e.updated_at = datetime.now(UTC)
    audit(db, user, "update", "hof_entry", e.id, {"before": {k: str(v)[:300] for k, v in before.items()},
                                                  "after": {k: str(v)[:300] for k, v in changes.items()}})
    db.commit()
    invalidate_indices()
    return entry_detail(e, user)


class DoiIn(BaseModel):
    doi: str = Field(min_length=6, max_length=200)


@router.post("/curation/references/from-doi", tags=["curation"])
def reference_from_doi(body: DoiIn, user: User = Depends(require_role("admin", "curator")),
                       db: Session = Depends(get_db)) -> dict:
    r = upsert_reference(db, doi=body.doi, online=True)
    if r.source != "crossref":
        db.rollback()
        raise HTTPException(404, "DOI not found in Crossref")
    audit(db, user, "create", "reference", r.id, {"doi": r.doi})
    db.commit()
    return reference_dict(r)


class ComponentIn(BaseModel):
    smiles: str
    role: str = Field(default="tecton", pattern="^(tecton|co_tecton|counterion|template)$")
    stoichiometry: float = Field(default=1.0, gt=0)
    name: str = ""


class NewEntryIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    doi: str | None = None
    ccdc_numbers: list[str] = []
    components: list[ComponentIn] = Field(min_length=1)
    topology: str = ""
    hbond_class: str = ""
    solvents: list[str] = []
    temperature: str = ""
    time_h: float | None = None
    additive: str = ""
    method: str = ""
    application: str = ""
    notes: str = ""
    bet_m2_g: float | None = None
    evidence: dict[str, dict] = {}
    curation_status: str = Field(default="verified", pattern="^(verified|needs_review|candidate)$")


@router.post("/curation/entries", tags=["curation"])
def create_entry(body: NewEntryIn, user: User = Depends(require_role("admin", "curator")),
                 db: Session = Depends(get_db)) -> dict:
    comps = []
    for c in body.components:
        try:
            mol = parse_molecule(c.smiles)
        except MoleculeInputError as ex:
            raise HTTPException(422, f"component '{c.smiles}': {ex}") from ex
        m = get_or_create_molecule(db, mol, experimental=c.role in ("tecton", "co_tecton"), name=c.name,
                                   provenance={"source": "manual curation", "user": user.username})
        comps.append((m, c.stoichiometry, c.role))
    system = get_or_create_system(db, comps, name=" + ".join(c.name for c in body.components if c.name))
    ev = default_evidence()
    ev["crystal_structure_reported"] = {"value": "yes", "source": "curated", "note": "Entered by curator."}
    for k, v in body.evidence.items():
        if k in EVIDENCE_LABELS and v.get("value") in EVIDENCE_VALUES:
            ev[k] = {"value": v["value"], "source": "curated", "note": v.get("note", "")}
    e = HOFEntry(name=body.name, system_id=system.id, ccdc_numbers=body.ccdc_numbers, topology=body.topology,
                 topology_source="curated" if body.topology else "", hbond_class=body.hbond_class,
                 application=body.application, notes=body.notes, evidence=ev, source_dataset="UltraHOFs curation",
                 source_record=user.username, license="curated metadata", curation_status=body.curation_status,
                 confidence=1.0, created_by=user.id)
    db.add(e)
    db.flush()
    e.conditions.append(SynthesisCondition(solvents=body.solvents, temperature=body.temperature,
                                           time_h=body.time_h, additive=body.additive, method=body.method))
    if body.doi:
        r = upsert_reference(db, doi=body.doi, online=True)
        e.references.append(EntryReference(reference_id=r.id, role="primary"))
        e.year = r.year
    if body.bet_m2_g is not None:
        e.properties.append(Property(kind="bet", value=body.bet_m2_g, unit="m2/g"))
    if body.application:
        e.properties.append(Property(kind="application", text=body.application))
    audit(db, user, "create", "hof_entry", e.id, {"name": e.name, "doi": body.doi})
    db.commit()
    invalidate_indices()
    return entry_detail(e, user)


@router.post("/curation/entries/{entry_id}/cif", tags=["curation"])
async def upload_cif(entry_id: int, file: UploadFile = File(...), analyze: bool = Form(True),
                     user: User = Depends(require_role("admin", "curator")), db: Session = Depends(get_db)) -> dict:
    e = db.get(HOFEntry, entry_id)
    if e is None:
        raise HTTPException(404, "entry not found")
    data = await file.read()
    if len(data) > 20_000_000:
        raise HTTPException(413, "CIF too large")
    d = get_settings().var_dir / "cif" / "raw"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{e.id}.cif"
    path.write_bytes(data)
    e.cif_raw_path = str(path)
    msg = "stored"
    if analyze:
        from ..ingest.hofsyn import _evidence, analyze_cif_file

        try:
            res = analyze_cif_file(str(path), pores=True)
            e.cell = res.get("cell", {})
            e.density = res.get("density")
            e.space_group = res.get("meta", {}).get("space_group", "")
            e.formula = res.get("meta", {}).get("formula", "")
            e.hbond_dimensionality = (res.get("hbond") or {}).get("hbond_dimensionality")
            e.pore = res.get("pore") or {}
            ev = dict(e.evidence or default_evidence())
            computed = _evidence(res)
            for k in ("extended_hbond_network", "geometric_porosity"):
                if ev.get(k, {}).get("source") != "curated":
                    ev[k] = computed[k]
            e.evidence = ev
            if res.get("framework_cif"):
                fp = get_settings().var_dir / "cif" / "framework" / f"{e.id}.cif"
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(res["framework_cif"])
                e.cif_clean_path = str(fp)
            msg = "stored and analysed"
        except Exception as ex:  # noqa: BLE001
            msg = f"stored; analysis failed: {str(ex)[:200]}"
    audit(db, user, "upload_cif", "hof_entry", e.id, {"filename": file.filename, "result": msg})
    db.commit()
    return {"ok": True, "message": msg, "entry": entry_detail(e, user)}


@router.get("/curation/csd/status", tags=["curation"])
def csd_status(user: User = Depends(require_role("admin", "curator"))) -> dict:
    from ..ingest.csd import csd_available

    ok, detail = csd_available()
    return {"available": ok, "detail": detail}
