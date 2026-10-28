"""Molecule design: evaluation, generation, two-component pairs, libraries and depiction."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from rdkit import Chem
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..chem.conformers import molblock_3d
from ..chem.depict import mol_svg
from ..chem.enumerate import count_combinations, enumerate_tectons, route_hint
from ..chem.fragments import ARM_BY_KEY, CORE_BY_KEY, FRAG_BY_KEY, library_dict
from ..chem.pairs import ANION_FRAGMENTS, CATION_FRAGMENTS, enumerate_pairs, evaluate_pair
from ..chem.scoring import score_molecule
from ..chem.standardize import MoleculeInputError, mol_keys, parse_molecule
from ..chem.synthons import library_table
from ..config import get_settings
from ..db import get_db
from ..jobs.queue import enqueue, job_dict
from ..models import Molecule, User
from ..services.molecules import (
    experimental_index,
    get_or_create_molecule,
    molecule_dict,
    precedent_lookup,
    synthon_prior,
)
from .deps import current_user

router = APIRouter()


def _parse(text: str) -> Chem.Mol:
    try:
        return parse_molecule(text)
    except MoleculeInputError as e:
        raise HTTPException(422, str(e)) from e


class EvaluateIn(BaseModel):
    input: str = Field(min_length=1, max_length=20000, description="SMILES or MOL block")
    n_confs: int = Field(default=8, ge=1, le=30)
    suggest_nets: bool = True
    save: bool = True


def suggest_nets_for(smiles: str, top: int = 8) -> dict:
    from ..crystal.assemble import recommend_for_bb
    from ..crystal.bb import BuildingBlockError
    from ..services.structures import cached_bb

    try:
        bb = cached_bb(smiles, False)
    except BuildingBlockError as e:
        return {"available": False, "reason": str(e), "nets": []}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"3D building block failed: {e}", "nets": []}
    if bb.k < 2:
        return {"available": False, "reason": "fewer than 2 supported connection points", "nets": []}
    return {"available": True, "building_block": bb.summary(), "nets": recommend_for_bb(bb, top=top)}


@router.post("/molecules/evaluate", tags=["design"])
def evaluate(body: EvaluateIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    mol = _parse(body.input)
    frags = Chem.GetMolFrags(mol, asMols=True)
    main = max(frags, key=lambda m: m.GetNumHeavyAtoms())
    idx = experimental_index()
    sc = score_molecule(main, n_confs=body.n_confs, max_similarity=idx.max_similarity(main),
                        synthon_prior=synthon_prior())
    prec = precedent_lookup(db, mol)
    keys = mol_keys(main)
    mol_id = None
    if body.save:
        m = get_or_create_molecule(db, main, origin="user", provenance={"user": user.username})
        if not m.score:
            m.score = {k: sc[k] for k in ("score", "band", "weighted_sum", "gate", "components", "flags",
                                         "n_connect", "geometry")}
        db.commit()
        mol_id = m.id
    return {
        "molecule_id": mol_id, "smiles": keys.smiles, "keys": keys.dict(), "svg": mol_svg(keys.smiles, 420, 300),
        "n_fragments": len(frags), "score": sc, "precedent": prec,
        "nets": suggest_nets_for(keys.smiles) if body.suggest_nets else None,
        "percentile": score_percentile(db, sc["score"]),
    }


def score_percentile(db: Session, score: float) -> float | None:
    vals = []
    for (s,) in db.execute(select(Molecule.score).where(Molecule.is_experimental_tecton.is_(True))):
        if s and s.get("score") is not None:
            vals.append(s["score"])
    if len(vals) < 10:
        return None
    return round(100 * sum(1 for v in vals if v <= score) / len(vals), 1)


class GenerateIn(BaseModel):
    cores: list[str] = []
    arms: list[str] = []
    synthons: list[str] = []
    min_sites: int = Field(default=3, ge=2, le=6)
    max_heavy_atoms: int = Field(default=160, ge=10, le=400)
    limit: int = Field(default=200, ge=1, le=5000)
    with_3d: bool = True
    as_job: bool = False


@router.post("/molecules/generate", tags=["design"])
def generate(body: GenerateIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    for k in body.cores:
        if k not in CORE_BY_KEY:
            raise HTTPException(422, f"unknown core {k}")
    for k in body.arms:
        if k not in ARM_BY_KEY:
            raise HTTPException(422, f"unknown arm {k}")
    for k in body.synthons:
        if k not in FRAG_BY_KEY:
            raise HTTPException(422, f"unknown synthon {k}")
    n_comb = count_combinations(body.cores or None, body.arms or None, body.synthons or None, body.min_sites)
    s = get_settings()
    if body.as_job or min(n_comb, body.limit) > s.max_generate_sync:
        job = enqueue(db, user, "generate_batch", body.model_dump())
        db.commit()
        return {"mode": "job", "job": job_dict(job), "n_combinations": n_comb}
    idx = experimental_index()
    prior = synthon_prior()
    out = []
    for c in enumerate_tectons(body.cores or None, body.arms or None, body.synthons or None,
                               min_sites=body.min_sites, max_heavy_atoms=body.max_heavy_atoms, limit=body.limit):
        mol = Chem.MolFromSmiles(c.smiles)
        sc = score_molecule(mol, n_confs=2 if body.with_3d else 1, max_similarity=idx.max_similarity(mol),
                            synthon_prior=prior, with_3d=body.with_3d)
        m = get_or_create_molecule(db, mol, origin="generated",
                                   provenance={"core": c.core, "arm": c.arm, "synthon": c.synthon})
        if not m.score and body.with_3d:
            m.score = {k: sc[k] for k in ("score", "band", "weighted_sum", "gate", "components", "flags",
                                         "n_connect", "geometry")}
        precedent = "exact" if m.is_experimental_tecton else None
        out.append({
            "molecule_id": m.id, "smiles": c.smiles, "core": c.core, "arm": c.arm, "synthon": c.synthon,
            "formula": c.keys["formula"], "mw": c.keys["mw"], "score": sc["score"], "band": sc["band"],
            "components": sc["components"], "flags": sc["flags"], "n_connect": sc["n_connect"],
            "geometry": (sc.get("geometry") or {}).get("geometry"), "precedent": precedent,
            "route": route_hint(c.core, c.arm, c.synthon), "svg": mol_svg(c.smiles, 240, 180),
        })
    db.commit()
    out.sort(key=lambda d: -d["score"])
    return {"mode": "sync", "n_combinations": n_comb, "n": len(out), "candidates": out}


@router.get("/molecules/{mol_id}", tags=["design"])
def get_molecule(mol_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    m = db.get(Molecule, mol_id)
    if m is None:
        raise HTTPException(404, "molecule not found")
    d = molecule_dict(m)
    d.update({"score_detail": m.score, "descriptors": m.descriptors, "provenance": m.provenance,
              "precedent": precedent_lookup(db, Chem.MolFromSmiles(m.smiles))})
    prov = m.provenance or {}
    if {"core", "arm", "synthon"} <= set(prov):
        d["route"] = route_hint(prov["core"], prov["arm"], prov["synthon"])
    return d


@router.get("/molecules/{mol_id}/molblock", tags=["design"])
def molecule_3d(mol_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    m = db.get(Molecule, mol_id)
    if m is None:
        raise HTTPException(404, "molecule not found")
    try:
        return Response(molblock_3d(Chem.MolFromSmiles(m.smiles)), media_type="chemical/x-mdl-molfile")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"3D embedding failed: {e}") from e


class DepictIn(BaseModel):
    input: str = Field(min_length=1, max_length=20000)
    width: int = Field(default=320, ge=80, le=1200)
    height: int = Field(default=240, ge=60, le=900)


@router.post("/molecules/depict", tags=["design"])
def depict(body: DepictIn, user: User = Depends(current_user)) -> dict:
    mol = _parse(body.input)
    smi = Chem.MolToSmiles(mol)
    k = mol_keys(mol)
    return {"smiles": smi, "svg": mol_svg(smi, body.width, body.height), "formula": k.formula, "mw": k.mw,
            "charge": k.charge}


@router.post("/molecules/molblock", tags=["design"])
def to_molblock(body: DepictIn, user: User = Depends(current_user)) -> dict:
    mol = _parse(body.input)
    try:
        return {"molblock": molblock_3d(mol)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"3D embedding failed: {e}") from e


@router.get("/libraries", tags=["design"])
def libraries(user: User = Depends(current_user)) -> dict:
    d = library_dict()
    d["synthon_types"] = library_table()
    d["cation_fragments"] = list(CATION_FRAGMENTS)
    d["anion_fragments"] = list(ANION_FRAGMENTS)
    return d


class PairIn(BaseModel):
    cation: str = Field(min_length=1, max_length=5000)
    anion: str = Field(min_length=1, max_length=5000)


@router.post("/pairs/evaluate", tags=["design"])
def pair_evaluate(body: PairIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    _parse(body.cation)
    _parse(body.anion)
    try:
        res = evaluate_pair(body.cation, body.anion)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    res["cation"]["svg"] = mol_svg(res["cation"]["smiles"], 300, 220)
    res["anion"]["svg"] = mol_svg(res["anion"]["smiles"], 300, 220)
    res["precedent"] = {
        "cation": precedent_lookup(db, Chem.MolFromSmiles(res["cation"]["smiles"]))["status"],
        "anion": precedent_lookup(db, Chem.MolFromSmiles(res["anion"]["smiles"]))["status"],
    }
    return res


class PairGenIn(BaseModel):
    cation_cores: list[str] = Field(min_length=1)
    anion_cores: list[str] = Field(min_length=1)
    cation_types: list[str] = ["amidinium"]
    anion_types: list[str] = ["carboxylate"]
    arms: list[str] = ["none", "phenylene"]
    limit: int = Field(default=100, ge=1, le=500)


@router.post("/pairs/generate", tags=["design"])
def pair_generate(body: PairGenIn, user: User = Depends(current_user)) -> dict:
    for k in body.cation_cores + body.anion_cores:
        if k not in CORE_BY_KEY:
            raise HTTPException(422, f"unknown core {k}")
    for k in body.cation_types:
        if k not in CATION_FRAGMENTS:
            raise HTTPException(422, f"unknown cation synthon {k}")
    for k in body.anion_types:
        if k not in ANION_FRAGMENTS:
            raise HTTPException(422, f"unknown anion synthon {k}")
    for k in body.arms:
        if k not in ARM_BY_KEY:
            raise HTTPException(422, f"unknown arm {k}")
    pairs = enumerate_pairs(body.cation_cores, body.anion_cores, body.cation_types, body.anion_types,
                            body.arms, body.limit)
    for p in pairs:
        p["cation"]["svg"] = mol_svg(p["cation"]["smiles"], 220, 160)
        p["anion"]["svg"] = mol_svg(p["anion"]["smiles"], 220, 160)
    return {"n": len(pairs), "pairs": pairs}
