from __future__ import annotations

from ultrahofs.ingest.crossref import (
    format_acs,
    format_bibtex,
    format_ris,
    message_to_reference,
    normalize_doi,
)
from ultrahofs.ingest.hofsyn import entry_name, parse_temperature, parse_time_h
from ultrahofs.ingest.rtf_refs import parse_endnote_rtf, rtf_to_text

RTF = (r"{\rtf1\ansi{\fonttbl{\f0 Times;}}"
       r"{\listtext 1.\tab}Smith, J. & Lee, K. A porous framework. \i J. Am. Chem. Soc.\i0  \b 130\b0 , 1-5 (2008)."
       r" doi:10.1021/ja000001x\par"
       r"{\listtext 2.\tab}Wang, T. Another HOF paper. Chem. Sci. 12, 3-9 (2021).\par}")

CROSSREF_MSG = {
    "DOI": "10.1021/JA000001X", "title": ["A <i>porous</i> framework"],
    "author": [{"given": "John", "family": "Smith"}, {"given": "Kim", "family": "Lee"}],
    "container-title": ["Journal of the American Chemical Society"], "short-container-title": ["J. Am. Chem. Soc."],
    "published-print": {"date-parts": [[2008, 5, 1]]}, "volume": "130", "issue": "2", "page": "1-5",
    "URL": "https://doi.org/10.1021/ja000001x", "publisher": "ACS",
}


def test_rtf_parsing():
    assert "porous framework" in rtf_to_text(RTF)
    entries = parse_endnote_rtf(RTF)
    assert set(entries) == {1, 2}
    assert entries[1].doi == "10.1021/ja000001x"
    assert entries[1].year == 2008 and entries[2].year == 2021
    assert entries[2].doi is None


def test_crossref_mapping_and_formats():
    ref = message_to_reference(CROSSREF_MSG)
    assert ref["doi"] == "10.1021/ja000001x" and ref["year"] == 2008
    assert ref["title"] == "A porous framework"
    assert "Smith, J." in format_acs(ref)
    bib = format_bibtex(ref)
    assert bib.startswith("@article{Smith2008A") and "pages = {1--5}" in bib
    ris = format_ris(ref)
    assert "TY  - JOUR" in ris and "DO  - 10.1021/ja000001x" in ris


def test_doi_normalisation():
    assert normalize_doi("https://doi.org/10.1039/D0CE00133C") == "10.1039/d0ce00133c"
    assert normalize_doi("doi:10.1021/ja506577g.") == "10.1021/ja506577g"


def test_condition_parsing():
    assert parse_temperature("rt") == 25.0
    assert parse_temperature("90") == 90.0
    assert parse_temperature("") is None
    assert parse_time_h("72h") == 72.0
    assert parse_time_h("3 d") == 72.0


def test_entry_names():
    assert entry_name("10-SOF-7") == "SOF-7"
    assert entry_name("100_1974317_2") == ""
    assert entry_name("113_1984953_HOF-20") == "HOF-20"
