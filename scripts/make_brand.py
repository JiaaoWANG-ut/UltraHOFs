"""Generate UltraHOFs / Ultra-X (知声无界) brand assets as self-contained SVGs.

Lettering is converted to outlines with fontTools (Zhuque Fangsong + Cormorant Garamond, both
SIL OFL 1.1), so the files render identically without installed fonts.

    python scripts/make_brand.py
"""

from __future__ import annotations

import math
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "data" / "raw" / "fonts"
OUT = ROOT / "frontend" / "public" / "brand"

INK = "#111418"
PAPER = "#F6F4EF"
INDIGO = "#1E2A3A"
GOLD = "#B08D57"


class Lettering:
    def __init__(self, path: Path, weight: float | None = None):
        font = TTFont(str(path))
        if weight is not None and "fvar" in font:
            font = instantiateVariableFont(font, {"wght": weight})
        self.font = font
        self.gs = font.getGlyphSet()
        self.cmap = font.getBestCmap()
        self.upm = font["head"].unitsPerEm

    def path(self, text: str, size: float, x: float, y: float, tracking: float = 0.0) -> tuple[str, float]:
        """SVG path data for ``text`` with baseline at (x, y); tracking in em."""
        scale = size / self.upm
        pen = SVGPathPen(self.gs)
        cursor = 0.0
        for ch in text:
            gname = self.cmap.get(ord(ch))
            if gname is None:
                cursor += 0.5 * self.upm
                continue
            glyph = self.gs[gname]
            glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x + cursor * scale, y)))
            cursor += glyph.width + tracking * self.upm
        width = (cursor - tracking * self.upm) * scale
        return pen.getCommands(), width


def hexagon(cx: float, cy: float, r: float, pointy: bool = True) -> list[tuple[float, float]]:
    start = -90 if pointy else 0
    return [(cx + r * math.cos(math.radians(start + 60 * k)), cy + r * math.sin(math.radians(start + 60 * k)))
            for k in range(6)]


def pts(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def symbol_lattice(ink: str = INK, gold: str = GOLD) -> str:
    """A: hexagonal H-bond lattice crossed by an X whose arms continue as dashed H-bonds (无界)."""
    hexv = hexagon(60, 60, 38)
    d = 0.7071
    inner = 24
    outer0, outer1 = 31, 54
    arms = [(1, 1), (-1, 1), (1, -1), (-1, -1)]
    solid = "".join(
        f'<line x1="{60 - inner * d * sx:.2f}" y1="{60 - inner * d * sy:.2f}" x2="{60 + inner * d * sx:.2f}" '
        f'y2="{60 + inner * d * sy:.2f}"/>' for sx, sy in arms[:2])
    dashed = "".join(
        f'<line x1="{60 + outer0 * d * sx:.2f}" y1="{60 + outer0 * d * sy:.2f}" '
        f'x2="{60 + outer1 * d * sx:.2f}" y2="{60 + outer1 * d * sy:.2f}"/>' for sx, sy in arms)
    nodes = "".join(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.7"/>' for x, y in hexv)
    return (
        f'<g fill="none" stroke="{ink}" stroke-width="1.5" stroke-linejoin="round">'
        f'<polygon points="{pts(hexv)}"/></g>'
        f'<g stroke="{gold}" stroke-width="3.4" stroke-linecap="round">{solid}</g>'
        f'<g stroke="{gold}" stroke-width="1.6" stroke-linecap="round" stroke-dasharray="0.1 4.2">{dashed}</g>'
        f'<g fill="{ink}">{nodes}<circle cx="60" cy="60" r="3.8"/></g>'
    )


def symbol_wave(ink: str = INK, gold: str = GOLD) -> str:
    """B: sound waves (知声) resolving into a hexagonal framework node (无界)."""
    arcs = []
    for r, op in ((11, 1.0), (19, 0.72), (27, 0.45)):
        a0, a1 = math.radians(-42), math.radians(42)
        x0, y0 = 20 + r * math.cos(a0), 60 + r * math.sin(a0)
        x1, y1 = 20 + r * math.cos(a1), 60 + r * math.sin(a1)
        arcs.append(f'<path d="M{x0:.2f},{y0:.2f} A{r},{r} 0 0 1 {x1:.2f},{y1:.2f}" stroke-opacity="{op}"/>')
    hexv = hexagon(78, 60, 25, pointy=False)
    nodes = "".join(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.4"/>' for x, y in hexv)
    x = 9.5
    return (
        f'<circle cx="20" cy="60" r="3.2" fill="{gold}"/>'
        f'<g fill="none" stroke="{gold}" stroke-width="2.2" stroke-linecap="round">{"".join(arcs)}</g>'
        f'<g fill="none" stroke="{ink}" stroke-width="1.5" stroke-linejoin="round"><polygon points="{pts(hexv)}"/></g>'
        f'<g stroke="{ink}" stroke-width="2.6" stroke-linecap="round">'
        f'<line x1="{78 - x}" y1="{60 - x}" x2="{78 + x}" y2="{60 + x}"/>'
        f'<line x1="{78 + x}" y1="{60 - x}" x2="{78 - x}" y2="{60 + x}"/></g>'
        f'<g fill="{ink}">{nodes}</g>'
    )


def symbol_seal(serif: Lettering, ink: str = INK, gold: str = GOLD) -> str:
    """C: a seal — serif X within a ring of six H-bond nodes."""
    ring = hexagon(60, 60, 47)
    beads = "".join(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.5"/>' for x, y in ring)
    d, w = serif.path("X", 74, 0, 0)
    xg, _ = serif.path("X", 74, 60 - w / 2, 86)
    return (
        f'<circle cx="60" cy="60" r="47" fill="none" stroke="{gold}" stroke-width="1.2"/>'
        f'<circle cx="60" cy="60" r="41" fill="none" stroke="{gold}" stroke-width="0.5" stroke-opacity="0.6"/>'
        f'<g fill="{ink}">{beads}</g><path d="{xg}" fill="{ink}"/>'
    )


def svg(content: str, w: float, h: float, bg: str | None = None, title: str = "Ultra-X") -> str:
    rect = f'<rect width="{w}" height="{h}" rx="{min(w, h) * 0.12:.1f}" fill="{bg}"/>' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {h:.1f}" width="{w:.0f}" height="{h:.0f}" '
            f'role="img" aria-label="{title}"><title>{title}</title>{rect}{content}</svg>\n')


def lockup(symbol: str, fang: Lettering, serif: Lettering, ink: str = INK, gold: str = GOLD) -> str:
    zh, zw = fang.path("知声无界", 46, 156, 64, tracking=0.08)
    en, ew = serif.path("ULTRA-X", 25, 158, 100, tracking=0.32)
    width = 156 + max(zw, ew) + 24
    body = (f'<g transform="translate(6,0)">{symbol}</g>'
            f'<line x1="138" y1="26" x2="138" y2="94" stroke="{gold}" stroke-width="1"/>'
            f'<path d="{zh}" fill="{ink}"/><path d="{en}" fill="{ink}"/>')
    return svg(body, width, 120, title="知声无界 Ultra-X")


def product_lockup(symbol: str, fang: Lettering, serif: Lettering, ink: str = INK, gold: str = GOLD) -> str:
    name, nw = serif.path("UltraHOFs", 50, 140, 70, tracking=0.02)
    sub, sw = fang.path("知声无界 · 氢键有机框架设计平台", 17, 142, 100, tracking=0.12)
    width = 140 + max(nw, sw) + 20
    body = (f'<g transform="translate(4,0)">{symbol}</g>'
            f'<path d="{name}" fill="{ink}"/><path d="{sub}" fill="{gold}"/>')
    return svg(body, width, 120, title="UltraHOFs")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fang = Lettering(FONTS / "zhuque" / "ZhuqueFangsong-Regular.ttf")
    serif = Lettering(FONTS / "CormorantGaramond-wght.ttf", weight=600)
    symbols = {"lattice": symbol_lattice(), "wave": symbol_wave(), "seal": symbol_seal(serif)}
    symbols_dark = {"lattice": symbol_lattice(PAPER, GOLD), "wave": symbol_wave(PAPER, GOLD),
                    "seal": symbol_seal(serif, PAPER, GOLD)}
    for k, s in symbols.items():
        (OUT / f"symbol-{k}.svg").write_text(svg(s, 120, 120))
        (OUT / f"symbol-{k}-dark.svg").write_text(svg(symbols_dark[k], 120, 120, bg=INDIGO))
        (OUT / f"lockup-{k}.svg").write_text(lockup(s, fang, serif))
        (OUT / f"product-{k}.svg").write_text(product_lockup(s, fang, serif))
    (OUT / "favicon.svg").write_text(svg(symbol_lattice(), 120, 120, bg=PAPER))
    names = {"lattice": ("A · 晶格之 X", "Hexagonal H-bond lattice crossed by an X; dashed arms = boundless network"),
             "wave": ("B · 声波晶格", "Sound waves (知声) resolving into a framework node (无界)"),
             "seal": ("C · 印章", "Serif X within a ring of six H-bond nodes — a classic seal")}
    cards = "".join(
        f'<section><h2>{names[k][0]}</h2><p>{names[k][1]}</p><div class="row">'
        f'<img src="symbol-{k}.svg" width="120"><img src="symbol-{k}-dark.svg" width="120">'
        f'<img src="lockup-{k}.svg" height="120"></div><div class="row"><img src="product-{k}.svg" height="96"></div>'
        f'</section>' for k in symbols)
    (OUT / "brand-preview.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Ultra-X brand preview</title><style>"
        f"body{{background:{PAPER};color:{INK};font-family:serif;padding:40px;max-width:1100px;margin:auto}}"
        "section{border-top:1px solid #d8d2c4;padding:28px 0}.row{display:flex;gap:28px;align-items:center;"
        "margin:14px 0}.sw{display:inline-block;width:110px;height:64px;margin-right:12px;padding:8px;"
        "color:#fff;font:12px monospace}</style><h1>知声无界 · Ultra-X — 品牌方案</h1>"
        f'<p><span class=sw style="background:{INK}">墨黑 {INK}</span>'
        f'<span class=sw style="background:{PAPER};color:{INK};border:1px solid #ccc">宣纸白 {PAPER}</span>'
        f'<span class=sw style="background:{INDIGO}">黛蓝 {INDIGO}</span>'
        f'<span class=sw style="background:{GOLD}">香槟金 {GOLD}</span></p>' + cards)
    print("brand assets written to", OUT)


if __name__ == "__main__":
    main()
