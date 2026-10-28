"""Reference (citation) management."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ingest.crossref import (
    fetch_doi,
    format_acs,
    format_bibtex,
    format_ris,
    message_to_reference,
    normalize_doi,
)
from ..models import Reference


def reference_dict(r: Reference) -> dict:
    data = {
        "id": r.id, "doi": r.doi, "title": r.title, "authors": r.authors or [], "journal": r.journal,
        "journal_abbrev": r.journal_abbrev, "year": r.year, "volume": r.volume, "issue": r.issue,
        "pages": r.pages, "url": r.url or (f"https://doi.org/{r.doi}" if r.doi else ""),
        "publisher": r.publisher, "source": r.source, "raw_citation": r.raw_citation,
    }
    data["acs"] = format_acs(data)
    return data


def export_reference(r: Reference, fmt: str) -> str:
    d = reference_dict(r)
    if fmt == "bibtex":
        return format_bibtex(d)
    if fmt == "ris":
        return format_ris(d)
    return d["acs"]


def upsert_reference(db: Session, *, doi: str | None, fallback: dict | None = None, online: bool = True,
                     source: str = "manual") -> Reference:
    """Create/update a reference; with a DOI and network access, metadata comes from Crossref."""
    doi_n = normalize_doi(doi) if doi else None
    row = None
    if doi_n:
        row = db.execute(select(Reference).where(Reference.doi == doi_n)).scalar_one_or_none()
    if row is not None and row.source == "crossref":
        return row
    meta = None
    if doi_n and online:
        try:
            msg = fetch_doi(doi_n)
            meta = message_to_reference(msg) if msg else None
        except Exception:  # noqa: BLE001
            meta = None
    if row is None:
        row = Reference(doi=doi_n)
        db.add(row)
    if meta:
        for k, v in meta.items():
            setattr(row, k, v)
        row.source = "crossref"
    elif fallback:
        for k, v in fallback.items():
            if hasattr(row, k) and v not in (None, ""):
                setattr(row, k, v)
        row.source = source
    db.flush()
    return row
