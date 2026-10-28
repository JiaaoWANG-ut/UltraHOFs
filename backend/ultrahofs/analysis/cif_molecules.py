"""CIF → periodic structure → unique molecules → RDKit SMILES with role assignment."""

from __future__ import annotations

import io
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import reduce

import networkx as nx
import numpy as np
from ase import Atoms
from ase.io import read as ase_read
from rdkit import Chem
from rdkit.Chem import rdDetermineBonds
from rdkit.Chem.MolStandardize import rdMolStandardize

from ..chem.standardize import mol_keys
from ..chem.synthons import STRONG_THRESHOLD, find_synthons
from .bonding import find_molecules

SOLVENT_SMILES = [
    "O", "CO", "CCO", "CCCO", "CC(C)O", "CCCCO", "OCCO", "CN(C)C=O", "CC(=O)N(C)C", "CS(C)=O", "CC(C)=O",
    "CC#N", "C1CCOC1", "C1COCCO1", "ClC(Cl)Cl", "ClCCl", "ClCCCl", "ClC(Cl)(Cl)Cl", "c1ccccc1", "Cc1ccccc1",
    "Clc1ccccc1", "Clc1ccccc1Cl", "O=[N+]([O-])c1ccccc1", "CN1CCCC1=O", "CCOC(C)=O", "CCCCCC", "CCOCC",
    "C1CCCCC1", "Cc1cc(C)cc(C)c1", "Cc1ccccc1C", "Cc1ccc(C)cc1", "COc1ccccc1", "C[N+](=O)[O-]", "OC=O",
    "CC(=O)O", "c1ccncc1", "CN", "N", "ClC=C(Cl)Cl", "FC(F)(F)c1ccccc1", "Brc1ccccc1", "Ic1ccccc1",
    "C1CC1", "CCCCCCC", "CC(C)(C)OC", "COCCOC", "OCC(O)CO", "CC(O)C",
]
_SOLVENT_KEYS: set[str] | None = None


def solvent_keys() -> set[str]:
    global _SOLVENT_KEYS
    if _SOLVENT_KEYS is None:
        _SOLVENT_KEYS = set()
        for s in SOLVENT_SMILES:
            m = Chem.MolFromSmiles(s)
            if m is not None:
                _SOLVENT_KEYS.add(Chem.MolToInchiKey(m)[:14])
    return _SOLVENT_KEYS


@dataclass
class MoleculeRecord:
    smiles: str
    keys: dict
    count: int
    charge: int
    role: str
    n_atoms: int
    heavy_atoms: int
    has_h: bool
    method: str
    n_strong_synthons: int
    atom_indices: list[list[int]] = field(default_factory=list)  # per instance

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "atom_indices"}
        return d


@dataclass
class CifAnalysis:
    atoms: Atoms
    molecules: list[MoleculeRecord]
    issues: list[str]
    confidence: float
    framework_atoms: Atoms | None = None

    @property
    def framework_molecules(self) -> list[MoleculeRecord]:
        return [m for m in self.molecules if m.role in ("tecton", "co_tecton", "counterion")]


def read_cif(text: str) -> Atoms:
    """Read a CIF keeping only the major disorder component (gemmi), falling back to ASE."""
    try:
        atoms = _read_cif_gemmi(text)
        if len(atoms):
            return dedupe_overlaps(atoms)
    except Exception:  # noqa: BLE001
        pass
    atoms = ase_read(io.StringIO(text), format="cif")
    occ = atoms.info.get("occupancy")
    if occ:
        keep = [i for i in range(len(atoms)) if max(occ.get(i, {"x": 1.0}).values()) >= 0.5]
        atoms = atoms[keep]
    return dedupe_overlaps(atoms)


def _read_cif_gemmi(text: str) -> Atoms:
    import gemmi

    doc = gemmi.cif.read_string(text)
    block = None
    for b in doc:
        if b.find_value("_cell_length_a") is not None and (b.find_loop("_atom_site_fract_x") or
                                                            b.find_loop("_atom_site_label")):
            block = b
            break
    if block is None:
        block = doc.sole_block()
    st = gemmi.make_small_structure_from_block(block)
    keep = {
        s.label for s in st.sites
        if (s.disorder_group in (0, 1, -1)) and (s.occ >= 0.5 or s.disorder_group in (1, -1))
    }
    sites = [s for s in st.get_all_unit_cell_sites() if s.label in keep]
    c = st.cell
    return Atoms(
        [s.element.name for s in sites],
        scaled_positions=[[s.fract.x % 1.0, s.fract.y % 1.0, s.fract.z % 1.0] for s in sites],
        cell=[c.a, c.b, c.c, c.alpha, c.beta, c.gamma], pbc=True,
    )


def dedupe_overlaps(atoms: Atoms, tol: float = 0.6) -> Atoms:
    from ase.neighborlist import neighbor_list

    if len(atoms) == 0:
        return atoms
    i, j = neighbor_list("ij", atoms, tol)
    drop = set()
    for a, b in zip(i, j, strict=True):
        if a < b and a not in drop:
            drop.add(b)
    if not drop:
        return atoms
    return atoms[[k for k in range(len(atoms)) if k not in drop]]


def _graph_hash(symbols: list[str], idx: list[int], bonding) -> str:  # noqa: ANN001
    g = nx.Graph()
    local = {a: k for k, a in enumerate(idx)}
    for k, a in enumerate(idx):
        g.add_node(k, el=symbols[a])
    for a, b in zip(bonding.i, bonding.j, strict=True):
        if a in local and b in local and a < b:
            g.add_edge(local[a], local[b])
    return nx.weisfeiler_lehman_graph_hash(g, node_attr="el", iterations=4)


_CHARGES = [0, 1, -1, 2, -2, 3, -3, 4, -4, 6, -6]
MAX_BOND_ORDER_ITERS = 50_000
XYZ2MOL_MAX_ATOMS = 60

_VALENCE = {1: 1, 5: 3, 6: 4, 7: 3, 8: 2, 9: 1, 14: 4, 15: 3, 16: 2, 17: 1, 34: 2, 35: 1, 53: 1}


def assign_bond_orders(mol: Chem.Mol) -> Chem.Mol | None:
    """Bond orders + formal charges from connectivity with explicit H (polynomial time).

    Valence deficits are satisfied by S/P=O, nitro groups and triple bonds first, then a maximum
    cardinality matching on deficit-1 atoms (Edmonds); leftovers become formal charges.
    """
    n = mol.GetNumAtoms()
    z = [a.GetAtomicNum() for a in mol.GetAtoms()]
    if any(x not in _VALENCE for x in z):
        return None
    nbrs = [[nb.GetIdx() for nb in mol.GetAtomWithIdx(i).GetNeighbors()] for i in range(n)]
    deg = [len(x) for x in nbrs]
    charge = [0] * n
    target = []
    for i in range(n):
        v = _VALENCE[z[i]]
        if z[i] == 7 and deg[i] == 4:
            v, charge[i] = 4, +1
        elif z[i] == 5 and deg[i] == 4:
            v, charge[i] = 4, -1
        elif z[i] == 15 and deg[i] >= 4:
            v = 5
        elif z[i] == 16 and deg[i] >= 3:
            v = 6 if deg[i] == 4 else 4
        target.append(v)
    deficit = [target[i] - deg[i] for i in range(n)]
    if any(d < 0 for d in deficit):
        return None
    order: dict[tuple[int, int], int] = {}

    def setb(i: int, j: int, o: int) -> None:
        order[(min(i, j), max(i, j))] = o

    terminal_o = [[j for j in nbrs[i] if z[j] == 8 and deg[j] == 1] for i in range(n)]
    for i in range(n):  # sulfonyl / phosphoryl
        if z[i] in (15, 16) and deficit[i] > 0:
            for j in terminal_o[i]:
                if deficit[i] > 0 and deficit[j] == 1:
                    setb(i, j, 2)
                    deficit[i] -= 1
                    deficit[j] -= 1
    for i in range(n):  # nitro
        if z[i] == 7 and deg[i] == 3 and len(terminal_o[i]) >= 2 and deficit[i] == 0:
            o1, o2 = terminal_o[i][:2]
            setb(i, o1, 2)
            deficit[o1] = 0
            charge[i] = +1
            charge[o2] = -1
            deficit[o2] = 0
    for b in mol.GetBonds():  # triple bonds
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        if deficit[i] >= 2 and deficit[j] >= 2:
            setb(i, j, 3)
            deficit[i] -= 2
            deficit[j] -= 2
    if any(d >= 2 for d in deficit):
        return None
    g = nx.Graph()
    for b in mol.GetBonds():
        i, j = b.GetBeginAtomIdx(), b.GetEndAtomIdx()
        if deficit[i] == 1 and deficit[j] == 1 and (min(i, j), max(i, j)) not in order:
            g.add_edge(i, j)
    for i, j in nx.max_weight_matching(g, maxcardinality=True):
        setb(i, j, 2)
        deficit[i] -= 1
        deficit[j] -= 1
    for i in range(n):
        if deficit[i] != 1:
            continue
        if z[i] in (8, 16) and deg[i] == 1:
            charge[i] = -1
        elif z[i] == 7 and deg[i] == 2:
            charge[i] = -1
        elif z[i] == 6:
            partner = next((j for j in nbrs[i] if z[j] == 7 and deg[j] == 3 and deficit[j] == 0
                            and charge[j] == 0 and (min(i, j), max(i, j)) not in order), None)
            if partner is None:
                return None
            setb(i, partner, 2)
            charge[partner] = +1
        else:
            return None
        deficit[i] = 0
    rw = Chem.RWMol(mol)
    for b in rw.GetBonds():
        o = order.get((min(b.GetBeginAtomIdx(), b.GetEndAtomIdx()), max(b.GetBeginAtomIdx(), b.GetEndAtomIdx())), 1)
        b.SetBondType({1: Chem.BondType.SINGLE, 2: Chem.BondType.DOUBLE, 3: Chem.BondType.TRIPLE}[o])
    for i, a in enumerate(rw.GetAtoms()):
        a.SetFormalCharge(charge[i])
        a.SetNoImplicit(True)
        a.SetNumExplicitHs(0)
    try:
        out = rw.GetMol()
        Chem.SanitizeMol(out)
        return Chem.RemoveHs(out)
    except Exception:  # noqa: BLE001
        return None


def perceive(symbols: list[str], pos: np.ndarray) -> tuple[Chem.Mol | None, int, str]:
    xyz = f"{len(symbols)}\n\n" + "\n".join(
        f"{s} {p[0]:.5f} {p[1]:.5f} {p[2]:.5f}" for s, p in zip(symbols, pos, strict=True))
    base = Chem.MolFromXYZBlock(xyz)
    if base is None:
        return None, 0, "xyz-parse-failed"
    if len(symbols) == 1:
        m = Chem.RWMol(base).GetMol()
        el = symbols[0]
        q = {"Na": 1, "K": 1, "Li": 1, "Cs": 1, "Rb": 1, "Cl": -1, "Br": -1, "I": -1, "F": -1}.get(el, 0)
        if q:
            m.GetAtomWithIdx(0).SetFormalCharge(q)
            m.GetAtomWithIdx(0).SetNoImplicit(True)
            Chem.SanitizeMol(m)
        return m, q, "single-atom"
    try:
        rdDetermineBonds.DetermineConnectivity(base)
    except Exception:  # noqa: BLE001
        return None, 0, "connectivity-failed"
    fast = assign_bond_orders(base)
    if fast is not None:
        return fast, Chem.GetFormalCharge(fast), "valence-matching"
    if len(symbols) > XYZ2MOL_MAX_ATOMS:
        return None, 0, "bond-order-failed"
    for q in _CHARGES:
        m = Chem.Mol(base)
        try:
            rdDetermineBonds.DetermineBondOrders(m, charge=q, embedChiral=False,
                                                 maxIterations=MAX_BOND_ORDER_ITERS)
            Chem.SanitizeMol(m)
            if any(a.GetNumRadicalElectrons() for a in m.GetAtoms()):
                continue
            return Chem.RemoveHs(m), q, "xyz2mol"
        except Exception:  # noqa: BLE001
            continue
    return None, 0, "bond-order-failed"


def analyze_structure(atoms: Atoms, max_atoms: int = 12000) -> CifAnalysis:
    issues: list[str] = []
    if len(atoms) > max_atoms:
        raise ValueError(f"structure too large ({len(atoms)} atoms)")
    symbols = atoms.get_chemical_symbols()
    has_h_global = "H" in symbols
    if not has_h_global:
        issues.append("no hydrogen atoms in CIF")
    bonding = find_molecules(atoms)
    pos = bonding.unwrapped_positions(atoms)
    groups: dict[str, list[list[int]]] = defaultdict(list)
    for m in range(bonding.n_molecules):
        idx = np.where(bonding.mol_id == m)[0].tolist()
        groups[_graph_hash(symbols, idx, bonding)].append(idx)

    records: list[MoleculeRecord] = []
    for _h, instances in groups.items():
        idx = instances[0]
        syms = [symbols[i] for i in idx]
        mol, q, method = perceive(syms, pos[idx])
        if mol is None:
            records.append(MoleculeRecord("", {}, len(instances), 0, "unknown", len(idx),
                                          sum(1 for s in syms if s != "H"), "H" in syms, method, 0, instances))
            if sum(1 for s in syms if s != "H") > 3:
                issues.append(f"could not perceive bonds for a {len(idx)}-atom molecule")
            continue
        n_strong = sum(1 for s in find_synthons(mol) if s.type.strength >= STRONG_THRESHOLD)
        records.append(MoleculeRecord(Chem.MolToSmiles(mol), mol_keys(mol).dict(), len(instances), q, "",
                                      len(idx), mol.GetNumHeavyAtoms(), "H" in syms, method, n_strong, instances))

    total_q = sum(r.charge * r.count for r in records)
    if total_q != 0:
        issues.append(f"cell charge {total_q:+d}: likely missing H atoms or counter-ions; neutralised")
        uncharger = rdMolStandardize.Uncharger(canonicalOrder=True)
        for r in records:
            if r.smiles and r.charge != 0:
                m = uncharger.uncharge(Chem.MolFromSmiles(r.smiles))
                r.smiles = Chem.MolToSmiles(m)
                r.keys = mol_keys(m).dict()
                r.charge = Chem.GetFormalCharge(m)
                r.method += "+neutralised"

    _assign_roles(records)
    framework_idx = sorted(i for r in records if r.role in ("tecton", "co_tecton", "counterion")
                           for inst in r.atom_indices for i in inst)
    framework = atoms[framework_idx] if framework_idx else None
    tectons = [r for r in records if r.role == "tecton"]
    conf = 1.0
    if not tectons:
        issues.append("no framework-forming tecton identified")
        conf = 0.3
    if not has_h_global:
        conf = min(conf, 0.4)
    if any(r.role == "unknown" and r.heavy_atoms > 3 for r in records):
        conf = min(conf, 0.5)
    if total_q != 0:
        conf = min(conf, 0.6)
    if any(not r.has_h and r.heavy_atoms > 3 for r in tectons):
        conf = min(conf, 0.5)
    return CifAnalysis(atoms, records, issues, conf, framework)


def _assign_roles(records: list[MoleculeRecord]) -> None:
    skeys = solvent_keys()
    known = [r for r in records if r.smiles]
    largest = max((r.heavy_atoms for r in known), default=0)
    for r in records:
        if not r.smiles:
            r.role = "unknown"
            continue
        sk = r.keys.get("inchikey", "")[:14]
        pk = r.keys.get("parent_key", "")[:14]
        if r.charge != 0:
            r.role = "co_tecton" if r.n_strong_synthons >= 1 and r.heavy_atoms >= 4 else "counterion"
            if r.n_strong_synthons >= 2 and r.heavy_atoms >= 0.5 * largest:
                r.role = "tecton"
        elif sk in skeys or pk in skeys:
            r.role = "solvent"
        elif r.n_strong_synthons >= 2 and r.heavy_atoms >= 6:
            r.role = "tecton"
        elif r.heavy_atoms == largest and largest >= 8:
            r.role = "tecton"
        elif r.heavy_atoms <= 8:
            r.role = "solvent"
        else:
            r.role = "guest"
    # Salts such as guanidinium–sulfonate: both ions build the framework; promote the largest.
    if not any(r.role == "tecton" for r in records):
        co = [r for r in records if r.role == "co_tecton"]
        if co:
            max(co, key=lambda r: r.heavy_atoms).role = "tecton"
    if any(r.role == "tecton" and r.charge != 0 for r in records):
        for r in records:
            if r.role == "counterion" and r.heavy_atoms >= 4 and r.n_strong_synthons >= 1:
                r.role = "co_tecton"


def framework_stoichiometry(records: list[MoleculeRecord]) -> list[tuple[MoleculeRecord, int]]:
    fw = [r for r in records if r.role in ("tecton", "co_tecton")]
    if not fw:
        return []
    g = reduce(math.gcd, [r.count for r in fw])
    return [(r, r.count // g) for r in fw]


def formula_counts(atoms: Atoms) -> dict[str, int]:
    return dict(Counter(atoms.get_chemical_symbols()))
