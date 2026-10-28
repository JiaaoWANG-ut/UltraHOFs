"""Parse an EndNote numbered bibliography exported as RTF into citation records."""

from __future__ import annotations

import re
from dataclasses import dataclass

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s;,<>\"]+", re.I)

_DESTINATIONS = {
    "fonttbl", "colortbl", "stylesheet", "info", "pict", "header", "footer", "listtable",
    "listoverridetable", "rsidtbl", "generator", "latentstyles", "datastore", "themedata",
    "colorschememapping", "xmlnstbl", "mmathPr", "pgdsctbl", "pntxta", "pntxtb",
}


def rtf_to_text(rtf: str) -> str:
    """Minimal RTF → text converter (handles groups, destinations, \\'hh and \\uN escapes)."""
    out: list[str] = []
    stack: list[tuple[bool, int]] = []
    ignorable = False
    uc_skip = 1
    curskip = 0
    i = 0
    n = len(rtf)
    while i < n:
        ch = rtf[i]
        if ch == "{":
            stack.append((ignorable, uc_skip))
            i += 1
            continue
        if ch == "}":
            if stack:
                ignorable, uc_skip = stack.pop()
            i += 1
            continue
        if ch == "\\":
            i += 1
            if i >= n:
                break
            c = rtf[i]
            if c in "\\{}":
                if not ignorable:
                    out.append(c)
                i += 1
                continue
            if c == "*":
                ignorable = True
                i += 1
                continue
            if c == "'":
                hexs = rtf[i + 1:i + 3]
                i += 3
                if curskip > 0:
                    curskip -= 1
                    continue
                if not ignorable:
                    try:
                        out.append(bytes.fromhex(hexs).decode("cp1252", errors="replace"))
                    except ValueError:
                        pass
                continue
            if c in "\n\r":
                i += 1
                continue
            m = re.match(r"([a-zA-Z]+)(-?\d+)? ?", rtf[i:])
            if not m:
                i += 1
                continue
            word, arg = m.group(1), m.group(2)
            i += m.end()
            if word in _DESTINATIONS:
                ignorable = True
            elif ignorable:
                continue
            elif word in ("par", "line"):
                out.append("\n")
            elif word == "tab":
                out.append("\t")
            elif word == "uc" and arg:
                uc_skip = int(arg)
            elif word == "u" and arg:
                code = int(arg)
                if code < 0:
                    code += 65536
                out.append(chr(code))
                curskip = uc_skip
            continue
        if ch in "\r\n":
            i += 1
            continue
        if curskip > 0:
            curskip -= 1
            i += 1
            continue
        if not ignorable:
            out.append(ch)
        i += 1
    return "".join(out)


@dataclass
class RawCitation:
    number: int
    text: str
    doi: str | None
    year: int | None
    title_guess: str


def parse_endnote_rtf(rtf: str) -> dict[int, RawCitation]:
    text = rtf_to_text(rtf)
    entries: dict[int, RawCitation] = {}
    current_num: int | None = None
    buf: list[str] = []

    def flush() -> None:
        if current_num is None:
            return
        raw = " ".join(" ".join(buf).split())
        raw = re.sub(r"PDF:\s*<[^>]*>", "", raw).strip()
        doi_m = DOI_RE.search(raw)
        doi = doi_m.group(0).rstrip(".)]") if doi_m else None
        years = re.findall(r"\((19\d\d|20\d\d)\)", raw)
        year = int(years[-1]) if years else None
        title = _guess_title(raw)
        entries[current_num] = RawCitation(current_num, raw, doi.lower() if doi else None, year, title)

    for line in text.split("\n"):
        m = re.match(r"^\s*(\d{1,4})\.\t(.*)$", line)
        if m:
            flush()
            current_num = int(m.group(1))
            buf = [m.group(2)]
        elif current_num is not None:
            buf.append(line)
    flush()
    return entries


def _guess_title(raw: str) -> str:
    # "Authors. Title. Journal Vol, pages (year)." → take the longest sentence-like chunk
    parts = [p.strip() for p in re.split(r"\.\s+", raw) if p.strip()]
    if len(parts) >= 2:
        cand = sorted(parts[1:3], key=len, reverse=True)[0]
        return cand[:300]
    return raw[:200]
