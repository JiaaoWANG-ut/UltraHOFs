"""2D depictions (SVG) in the UltraHOFs house style."""

from __future__ import annotations

from functools import lru_cache

from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

from .synthons import find_synthons

rdDepictor.SetPreferCoordGen(True)

INK = (0.067, 0.078, 0.094)
GOLD = (0.69, 0.553, 0.341)
PALETTE = {
    0: (0.5, 0.5, 0.5),
    1: (0.35, 0.38, 0.42),
    5: (0.55, 0.40, 0.25),
    6: INK,
    7: (0.16, 0.30, 0.58),
    8: (0.70, 0.22, 0.20),
    9: (0.20, 0.50, 0.35),
    14: (0.45, 0.40, 0.30),
    15: (0.75, 0.45, 0.10),
    16: (0.70, 0.60, 0.10),
    17: (0.20, 0.50, 0.35),
    35: (0.50, 0.25, 0.20),
}


@lru_cache(maxsize=4096)
def mol_svg(smiles: str, width: int = 320, height: int = 240, highlight: bool = True) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return ""
    rdDepictor.Compute2DCoords(mol)
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    opts = drawer.drawOptions()
    opts.clearBackground = False
    opts.bondLineWidth = 1.4
    opts.padding = 0.08
    opts.additionalAtomLabelPadding = 0.12
    opts.setAtomPalette(PALETTE)
    opts.highlightRadius = 0.32
    opts.fillHighlights = True
    atoms: list[int] = []
    colors: dict[int, tuple] = {}
    bonds: list[int] = []
    bcolors: dict[int, tuple] = {}
    if highlight:
        for m in find_synthons(mol):
            if m.type.strength < 0.5:
                continue
            for a in m.atoms:
                atoms.append(a)
                colors[a] = (*GOLD, 0.35)
            aset = set(m.atoms)
            for b in mol.GetBonds():
                if b.GetBeginAtomIdx() in aset and b.GetEndAtomIdx() in aset:
                    bonds.append(b.GetIdx())
                    bcolors[b.GetIdx()] = (*GOLD, 0.35)
    rdMolDraw2D.PrepareAndDrawMolecule(
        drawer, mol, highlightAtoms=atoms, highlightAtomColors=colors,
        highlightBonds=bonds, highlightBondColors=bcolors,
    )
    drawer.FinishDrawing()
    svg = drawer.GetDrawingText()
    return svg.replace("<?xml version='1.0' encoding='iso-8859-1'?>\n", "")
