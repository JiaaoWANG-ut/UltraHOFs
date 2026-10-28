"""Crossref client with on-disk cache; citation formatting (ACS, BibTeX, RIS)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from difflib import SequenceMatcher

import httpx

from .. import __version__
from ..config import get_settings

API = "https://api.crossref.org/works"


def _headers() -> dict[str, str]:
    mail = get_settings().crossref_mailto
    ua = f"UltraHOFs/{__version__} (https://ultra-x.example; Ultra-X materials platform)"
    if mail:
        ua = f"UltraHOFs/{__version__} (mailto:{mail})"
    return {"User-Agent": ua}


def _cache_path(key: str):  # noqa: ANN202
    d = get_settings().cache_dir / "crossref"
    d.mkdir(parents=True, exist_ok=True)
    return d / (hashlib.sha1(key.encode()).hexdigest() + ".json")


def _get(url: str, params: dict | None = None, retries: int = 3) -> dict | None:
    key = url + json.dumps(params or {}, sort_keys=True)
    cp = _cache_path(key)
    if cp.exists():
        return json.loads(cp.read_text())
    last = None
    for attempt in range(retries):
        try:
            r = httpx.get(url, params=params, headers=_headers(), timeout=get_settings().http_timeout_s)
            if r.status_code == 404:
                cp.write_text(json.dumps(None))
                return None
            if r.status_code == 429:
                time.sleep(2 + 2 * attempt)
                continue
            r.raise_for_status()
            data = r.json()
            cp.write_text(json.dumps(data))
            return data
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1 + attempt)
    if last:
        raise last
    return None


def normalize_doi(doi: str) -> str:
    doi = doi.strip()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi, flags=re.I)
    return doi.lower().rstrip(".")


def fetch_doi(doi: str) -> dict | None:
    data = _get(f"{API}/{normalize_doi(doi)}")
    return data.get("message") if data else None


def search_bibliographic(text: str, rows: int = 3) -> list[dict]:
    data = _get(API, {"query.bibliographic": text[:500], "rows": rows,
                      "select": "DOI,title,author,container-title,short-container-title,issued,volume,page,score"})
    return data.get("message", {}).get("items", []) if data else []


def best_match(text: str, title_guess: str, year: int | None) -> tuple[str | None, float]:
    """DOI for a free-text citation; accept only confident matches."""
    items = search_bibliographic(text)
    best, best_s = None, 0.0
    for it in items:
        title = (it.get("title") or [""])[0]
        sim = SequenceMatcher(None, title.lower(), title_guess.lower()).ratio() if title_guess else 0
        if not sim and title:
            sim = SequenceMatcher(None, title.lower(), text.lower()[:len(title) + 40]).ratio()
        iy = (it.get("issued", {}).get("date-parts") or [[None]])[0][0]
        year_ok = (year is None) or (iy == year)
        s = sim * (1.0 if year_ok else 0.6)
        if s > best_s:
            best, best_s = it.get("DOI"), s
    return (best.lower() if best and best_s >= 0.6 else None), round(best_s, 3)


def message_to_reference(msg: dict) -> dict:
    from html import unescape

    def clean(s: str) -> str:
        return unescape(re.sub(r"<[^>]+>", "", s or "")).strip()

    authors = [{"given": clean(a.get("given", "")), "family": clean(a.get("family", a.get("name", "")))}
               for a in msg.get("author", [])]
    year = None
    for k in ("published-print", "published-online", "issued", "created"):
        dp = (msg.get(k) or {}).get("date-parts")
        if dp and dp[0] and dp[0][0]:
            year = int(dp[0][0])
            break
    return {
        "doi": normalize_doi(msg.get("DOI", "")),
        "title": clean((msg.get("title") or [""])[0]),
        "authors": authors,
        "journal": clean((msg.get("container-title") or [""])[0]),
        "journal_abbrev": clean((msg.get("short-container-title") or [""])[0]),
        "year": year,
        "volume": msg.get("volume", "") or "",
        "issue": msg.get("issue", "") or "",
        "pages": msg.get("page", "") or msg.get("article-number", "") or "",
        "url": msg.get("URL", "") or f"https://doi.org/{msg.get('DOI', '')}",
        "publisher": msg.get("publisher", "") or "",
    }


# ---------------- formatting ----------------

def _initials(given: str) -> str:
    parts = re.split(r"[\s\-]+", given.strip())
    return " ".join(p[0] + "." for p in parts if p)


def format_acs(ref: dict) -> str:
    authors = ref.get("authors") or []
    names = [f"{a['family']}, {_initials(a.get('given', ''))}".strip(", ") for a in authors]
    if len(names) > 10:
        names = names[:10] + ["et al."]
    auth = "; ".join(names)
    j = ref.get("journal_abbrev") or ref.get("journal") or ""
    parts = [f"{auth} {ref.get('title', '')}." if auth else f"{ref.get('title', '')}."]
    tail = f"*{j}* **{ref.get('year') or ''}**"
    if ref.get("volume"):
        tail += f", *{ref['volume']}*"
    if ref.get("pages"):
        tail += f", {ref['pages']}"
    parts.append(tail + ".")
    if ref.get("doi"):
        parts.append(f"DOI: {ref['doi']}")
    return " ".join(parts)


def bibtex_key(ref: dict) -> str:
    fam = (ref.get("authors") or [{"family": "anon"}])[0].get("family", "anon")
    fam = re.sub(r"[^A-Za-z]", "", fam) or "anon"
    word = re.sub(r"[^A-Za-z]", "", (ref.get("title") or "x").split()[0]) if ref.get("title") else "x"
    return f"{fam}{ref.get('year') or ''}{word}"


def format_bibtex(ref: dict) -> str:
    authors = " and ".join(f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
                           for a in ref.get("authors") or [])
    fields = {
        "title": "{" + (ref.get("title") or "") + "}",
        "author": authors,
        "journal": ref.get("journal") or "",
        "year": str(ref.get("year") or ""),
        "volume": ref.get("volume") or "",
        "number": ref.get("issue") or "",
        "pages": (ref.get("pages") or "").replace("-", "--"),
        "doi": ref.get("doi") or "",
        "url": ref.get("url") or "",
    }
    body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields.items() if v and v != "{}")
    return f"@article{{{bibtex_key(ref)},\n{body}\n}}\n"


def format_ris(ref: dict) -> str:
    lines = ["TY  - JOUR"]
    for a in ref.get("authors") or []:
        lines.append(f"AU  - {a.get('family', '')}, {a.get('given', '')}")
    for tag, key in (("TI", "title"), ("JO", "journal"), ("JA", "journal_abbrev"), ("PY", "year"),
                     ("VL", "volume"), ("IS", "issue"), ("DO", "doi"), ("UR", "url")):
        if ref.get(key):
            lines.append(f"{tag}  - {ref[key]}")
    pages = ref.get("pages") or ""
    if pages:
        sp, _, ep = pages.partition("-")
        lines.append(f"SP  - {sp}")
        if ep:
            lines.append(f"EP  - {ep}")
    lines.append("ER  - ")
    return "\n".join(lines) + "\n"
