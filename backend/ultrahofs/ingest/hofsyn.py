"""Ingest the HOFSyn dataset (CC BY 4.0) into the experimental HOF database."""

from __future__ import annotations

import csv
import re
import shutil
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from rdkit import Chem
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import DataSource, EntryReference, HOFEntry, Property, SynthesisCondition
from ..models.hof import default_evidence
from ..services.molecules import get_or_create_molecule, get_or_create_system, invalidate_indices
from ..services.references import upsert_reference
from .crossref import best_match
from .name2struct import resolve_name
from .parallel import run_parallel
from .rtf_refs import parse_endnote_rtf

HOFSYN = {
    "key": "hofsyn_v2",
    "name": "HOFSyn: structure and synthesis dataset for hydrogen-bonded organic frameworks",
    "version": "v2 (2025-05)",
    "url": "https://doi.org/10.6084/m9.figshare.28856483.v2",
    "license": "CC BY 4.0",
    "attribution": "Wang, T. (2025). HOFSyn. figshare. Dataset. https://doi.org/10.6084/m9.figshare.28856483.v2 "
                   "— used under CC BY 4.0; structures re-processed by UltraHOFs.",
}
KNOWN_NET_TOKENS = ("dia", "sql", "hcb", "pcu", "srs", "pts", "ths", "lon", "kgm", "hxl", "bnn", "sod", "acs",
                    "nbo", "cds", "qtz", "ctn", "bor", "tbo", "pto", "rtl", "flu", "stp", "kgd", "fes", "hms",
                    "sqc", "sqp", "nia", "bcu", "fcu", "tfz", "cdz", "mot")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_cif(base: Path, cif_name: str, alt: str) -> Path | None:
    files = {}
    for p in base.glob("*.cif"):
        files.setdefault(p.stem.lower(), p)
        files.setdefault(_norm(p.stem), p)
    for key in (cif_name.strip().lower(), alt.strip().lower(), _norm(cif_name), _norm(alt)):
        if key in files:
            return files[key]
    return None


def parse_temperature(t: str) -> float | None:
    t = (t or "").strip().lower()
    if not t:
        return None
    if t in ("rt", "r.t.", "room temperature", "室温") or "rt" in t.split():
        return 25.0
    m = re.findall(r"-?\d+(?:\.\d+)?", t)
    if not m:
        return None
    vals = [float(x) for x in m]
    return round(sum(vals) / len(vals), 1)


def parse_time_h(t: str) -> float | None:
    t = (t or "").strip().lower()
    m = re.match(r"(\d+(?:\.\d+)?)\s*(h|hr|hours?|d|days?|min|w|weeks?)?", t)
    if not m:
        return None
    v = float(m.group(1))
    unit = (m.group(2) or "h")[0]
    return round(v * {"h": 1, "d": 24, "m": 1 / 60, "w": 168}.get(unit, 1), 2)


def entry_name(cif_name: str) -> str:
    rest = re.sub(r"^\d+[-_ ]*", "", cif_name.strip())
    rest = re.sub(r"(^|[-_\s])\d{6,7}(?=$|[-_\s])", r"\1", rest).strip("-_ ")
    if not re.search(r"[A-Za-z]", rest):
        return ""
    return rest


def ccdc_numbers(cif_name: str, cif_text: str) -> list[str]:
    nums = set(re.findall(r"(?<!\d)(\d{6,7})(?!\d)", cif_name))
    for m in re.finditer(r"_database_code_depnum_ccdc_archive\s+'?CCDC\s*(\d{6,7})", cif_text):
        nums.add(m.group(1))
    return sorted(nums)


def analyze_cif_file(path: str, pores: bool = True) -> dict:
    """Worker: CIF → molecules, H-bond network, guest-free porosity. Must be picklable/fork-safe."""
    import gemmi

    from ..analysis.cif_molecules import analyze_structure, read_cif
    from ..analysis.hbond import hbond_network_dimensionality
    from ..analysis.zeopp import analyze_cif, porous_verdict, zeopp_available
    from ..crystal.export import cell_dict, density, write_cif

    text = Path(path).read_text(errors="replace")
    meta = {}
    try:
        doc = gemmi.cif.read_string(text)
        blk = next((b for b in doc if b.find_value("_cell_length_a")), doc.sole_block())
        st = gemmi.make_small_structure_from_block(blk)
        meta["space_group"] = st.spacegroup_hm or (blk.find_value("_symmetry_space_group_name_H-M") or "").strip("'")
        meta["formula"] = (blk.find_value("_chemical_formula_sum") or "").strip("'\"")
    except Exception:  # noqa: BLE001
        pass
    atoms = read_cif(text)
    res = analyze_structure(atoms)
    out = {
        "meta": meta, "n_atoms": len(atoms), "cell": cell_dict(atoms), "density": density(atoms),
        "molecules": [m.to_dict() for m in res.molecules], "issues": res.issues, "confidence": res.confidence,
    }
    unknown = []
    for m in res.molecules:
        if m.role == "unknown":
            idx = m.atom_indices[0]
            syms = [atoms[i].symbol for i in idx]
            unknown.append(dict(Counter(s for s in syms if s != "H")))
    out["unknown_heavy"] = unknown
    fw = res.framework_atoms
    if fw is not None and 0 < len(fw) <= 8000:
        try:
            out["hbond"] = hbond_network_dimensionality(fw)
        except Exception as e:  # noqa: BLE001
            out["issues"].append(f"H-bond analysis failed: {e}")
        cif_fw = write_cif(fw, Path(path).stem + "-framework")
        out["framework_cif"] = cif_fw
        if pores and zeopp_available():
            try:
                pm = analyze_cif(cif_fw)
                pm["verdict"] = porous_verdict(pm)
                out["pore"] = pm
            except Exception as e:  # noqa: BLE001
                out["issues"].append(f"Zeo++ failed: {str(e)[:120]}")
    return out


def _evidence(result: dict) -> dict:
    ev = default_evidence()
    ev["crystal_structure_reported"] = {"value": "yes", "source": "literature",
                                        "note": "Single-crystal structure reported (CIF in HOFSyn)."}
    hb = result.get("hbond")
    if hb:
        d = hb.get("hbond_dimensionality", 0)
        if hb.get("n_hbonds", 0) == 0 and not hb.get("uses_heavy_atom_fallback"):
            ev["extended_hbond_network"] = {"value": "no", "source": "computed",
                                            "note": "No classical N–H/O–H···A H-bonds found between framework "
                                                    "components (may rely on weaker C–H···X contacts)."}
        else:
            ev["extended_hbond_network"] = {
                "value": "yes" if d >= 2 else "no", "source": "computed",
                "note": f"H-bonded network dimensionality {d}D" + (
                    " (heavy-atom contacts used where H atoms are missing)" if hb.get("uses_heavy_atom_fallback") else ""),
            }
    pm = result.get("pore")
    if pm:
        ev["geometric_porosity"] = {
            "value": pm.get("verdict", "unknown"), "source": "computed",
            "note": (f"Guest-free framework: PLD {pm.get('pld_A'):.2f} Å, LCD {pm.get('lcd_A'):.2f} Å, "
                     f"probe {pm.get('probe_radius_A')} Å (Zeo++)."),
        }
    return ev


def _topology_from_notes(*texts: str) -> str:
    for t in texts:
        if not t:
            continue
        for tok in re.findall(r"[a-z]{3}(?:-[a-z])?", t.lower()):
            if tok in KNOWN_NET_TOKENS:
                return tok
    return ""


def ingest_hofsyn(db: Session, base: Path | None = None, *, workers: int = 8, limit: int | None = None,
                  online: bool = True, pores: bool = True, log: Callable[[str], None] = print) -> dict:
    s = get_settings()
    base = base or (s.data_dir / "raw" / "hofsyn")
    raw_dir = base / "raw_cifs" / "hof_database_cifs"
    rows = list(csv.DictReader(open(base / "HOF_database.csv", encoding="utf-8-sig", errors="replace")))
    if limit:
        rows = rows[:limit]

    ds = db.execute(select(DataSource).where(DataSource.key == HOFSYN["key"])).scalar_one_or_none()
    if ds is None:
        db.add(DataSource(**HOFSYN))
    db.flush()

    # ---- references
    rtf = (base / "HOFSyn EndNote Library.rtf").read_text(encoding="latin-1")
    cites = parse_endnote_rtf(rtf)
    needed = {int(m.group(1)) for r in rows if (m := re.match(r"^(\d+)", r["cif_name"].strip()))}
    ref_ids: dict[int, int] = {}
    for num in sorted(needed):
        rc = cites.get(num)
        if rc is None:
            continue
        doi = rc.doi
        if not doi and online:
            try:
                doi, _score = best_match(rc.text, rc.title_guess, rc.year)
            except Exception:  # noqa: BLE001
                doi = None
        ref = upsert_reference(db, doi=doi, online=online, source="hofsyn",
                               fallback={"title": rc.title_guess, "year": rc.year, "raw_citation": rc.text})
        if not ref.raw_citation:
            ref.raw_citation = rc.text
        ref_ids[num] = ref.id
    db.commit()
    log(f"references: {len(ref_ids)} linked")

    # ---- structures
    items = []
    for k, r in enumerate(rows):
        p = find_cif(raw_dir, r["cif_name"], r.get("cif_name_1", ""))
        items.append((k, str(p) if p else None))
    todo = [(k, p) for k, p in items if p]
    results: dict[int, tuple[str, object]] = {}
    for item, status, res in run_parallel(lambda it: analyze_cif_file(it[1], pores), todo, workers=workers,
                                          timeout=240):
        results[item[0]] = (status, res)
        if len(results) % 50 == 0:
            log(f"analysed {len(results)}/{len(todo)} CIFs")

    cif_dir = s.var_dir / "cif"
    (cif_dir / "raw").mkdir(parents=True, exist_ok=True)
    (cif_dir / "framework").mkdir(parents=True, exist_ok=True)
    stats = Counter()
    for k, r in enumerate(rows):
        cif_name = r["cif_name"].strip()
        exists = db.execute(select(HOFEntry).where(HOFEntry.source_dataset == "HOFSyn v2",
                                                   HOFEntry.source_record == cif_name)).scalar_one_or_none()
        if exists is not None:
            stats["skipped_existing"] += 1
            continue
        path = items[k][1]
        status, res = results.get(k, ("missing", None))
        issues: list[str] = []
        confidence = 0.0
        result: dict = res if (status == "ok" and isinstance(res, dict)) else {}
        if status != "ok":
            issues.append(f"CIF analysis {status}" + (f": {res}" if isinstance(res, str) else ""))
        else:
            issues += result.get("issues", [])
            confidence = result.get("confidence", 0.0)
        monomer_names = [x.strip() for x in (r.get("Monomer1", ""), r.get("Monomer1.1", "")) if x and x.strip()]

        components = []
        for m in result.get("molecules", []):
            if m["role"] not in ("tecton", "co_tecton", "counterion") or not m["smiles"]:
                continue
            mol = Chem.MolFromSmiles(m["smiles"])
            if mol is None:
                continue
            mrow = get_or_create_molecule(db, mol, experimental=m["role"] in ("tecton", "co_tecton"),
                                          provenance={"source": "HOFSyn v2", "method": m["method"]})
            components.append((mrow, m["count"], m["role"]))

        if not any(role == "tecton" for _m, _c, role in components):
            expected = [Counter(u) for u in result.get("unknown_heavy", []) if u]
            for nm in monomer_names:
                smi, method = resolve_name(nm, expected or None, online=False)
                if smi:
                    mol = Chem.MolFromSmiles(smi)
                    mrow = get_or_create_molecule(db, mol, experimental=True, name=nm,
                                                  provenance={"source": "HOFSyn v2", "method": f"{method}-name"})
                    components.append((mrow, 1, "tecton"))
                    issues.append(f"tecton resolved from name via {method}" + (
                        " (composition-checked)" if expected else " (not composition-checked)"))
                    confidence = max(confidence, 0.7 if expected else 0.5)
                    break

        system = None
        if components:
            from functools import reduce
            from math import gcd

            fw_counts = [c for _m, c, role in components if role in ("tecton", "co_tecton")]
            g = reduce(gcd, fw_counts) if fw_counts else 1
            comps = [(m, c / g if role in ("tecton", "co_tecton") else c / g, role) for m, c, role in components]
            system = get_or_create_system(db, comps, name=" + ".join(monomer_names)[:400])
            for m, _c, role in components:
                if role == "tecton" and not m.name and monomer_names:
                    m.name = monomer_names[0][:300]
        else:
            issues.append("no molecular components identified")

        num_m = re.match(r"^(\d+)", cif_name)
        ref_id = ref_ids.get(int(num_m.group(1))) if num_m else None
        cif_text = Path(path).read_text(errors="replace") if path else ""
        meta = result.get("meta", {})
        hb = result.get("hbond") or {}
        status_c = "auto" if (confidence >= 0.8 and system is not None) else "needs_review"
        notes = " | ".join(x.strip() for x in (r.get("备注", ""), r.get("Unnamed: 13", ""),
                                               r.get("Unnamed: 15", "")) if x and x.strip() and x.strip() != "-")
        e = HOFEntry(
            name=entry_name(cif_name) or ("CCDC " + ccdc_numbers(cif_name, cif_text)[0]
                                          if ccdc_numbers(cif_name, cif_text) else cif_name),
            system_id=system.id if system else None,
            ccdc_numbers=ccdc_numbers(cif_name, cif_text),
            formula=meta.get("formula", ""),
            cell=result.get("cell", {}),
            space_group=meta.get("space_group", ""),
            density=result.get("density"),
            topology=_topology_from_notes(r.get("备注", ""), r.get("Unnamed: 13", "")),
            hbond_dimensionality=hb.get("hbond_dimensionality"),
            pore=result.get("pore") or {},
            evidence=_evidence(result) if result else default_evidence(),
            hbond_class=(r.get("氢键类型") or "").strip(),
            application=(r.get("Application") or "").strip(),
            notes=notes,
            source_dataset="HOFSyn v2",
            source_record=cif_name,
            license="Metadata: CC BY 4.0 (HOFSyn); crystal structure: CCDC deposition / original authors",
            curation_status=status_c,
            confidence=round(confidence, 2),
            issues=issues,
        )
        if e.topology:
            e.topology_source = "HOFSyn note"
        db.add(e)
        db.flush()
        if path:
            dst = cif_dir / "raw" / f"{e.id}.cif"
            shutil.copyfile(path, dst)
            e.cif_raw_path = s.rel_var_path(dst)
        if result.get("framework_cif"):
            dst = cif_dir / "framework" / f"{e.id}.cif"
            dst.write_text(result["framework_cif"])
            e.cif_clean_path = s.rel_var_path(dst)
            e.cleaning_log = ["removed solvent/guest molecules: " + ", ".join(
                sorted({m["smiles"] for m in result.get("molecules", []) if m["role"] in ("solvent", "guest")})
            )[:900]]
        solvents = [x.strip() for x in (r.get("Solvent1", ""), r.get("Solvent2", "")) if x and x.strip()]
        e.conditions.append(SynthesisCondition(
            solvents=solvents, temperature=(r.get("Temperature") or "").strip(),
            temperature_c=parse_temperature(r.get("Temperature", "")),
            time_h=parse_time_h(r.get("Reaction time (h) ", "") or r.get("Reaction time (h)", "")),
            additive=(r.get("additive") or "").strip(), method="",
            raw={k2: v for k2, v in r.items() if k2 and v},
        ))
        if e.application:
            e.properties.append(Property(kind="application", text=e.application, reference_id=ref_id))
        if ref_id:
            e.references.append(EntryReference(reference_id=ref_id, role="primary"))
            from ..models import Reference

            ref = db.get(Reference, ref_id)
            e.year = ref.year if ref else None
        stats[status_c] += 1
        if k % 100 == 0:
            db.commit()
    db.commit()
    invalidate_indices()
    log(f"entries: {dict(stats)}")
    return dict(stats)
