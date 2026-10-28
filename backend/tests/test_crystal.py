from __future__ import annotations

import dataclasses
import io
import itertools

import numpy as np
import pytest
from ase.io import read

from ultrahofs.analysis.cif_molecules import analyze_structure, assign_bond_orders, read_cif
from ultrahofs.analysis.zeopp import analyze_cif, zeopp_available
from ultrahofs.chem.conformers import best_match, kabsch_rmsd
from ultrahofs.crystal.assemble import (
    BuildOptions,
    LayerOptions,
    _rotate,
    assemble,
    recommend_for_bb,
    synthon_fit,
)
from ultrahofs.crystal.bb import BuildingBlockError, build_bb
from ultrahofs.crystal.export import FORMATS, export, write_cif
from ultrahofs.crystal.nets import bipartite_version, builtin_2d, get_net, recommend, supercell, two_coloring
from ultrahofs.crystal.qc import quality_report

from .conftest import ATC, TMA


@pytest.fixture(scope="module")
def tma_bb():
    return build_bb(TMA, planar=True)


@pytest.fixture(scope="module")
def atc_bb():
    return build_bb(ATC)


def test_builtin_2d_nets_coordination():
    cn = {name: set(n.coordination()) for name, n in builtin_2d().items()}
    assert cn == {"sql": {4}, "hcb": {3}, "kgm": {4}, "hxl": {6}}


def test_rcsr_cache_has_common_nets():
    for name in ("dia", "pcu", "srs", "ths", "nbo", "tbo"):
        net = get_net(name)
        assert net.n_nodes > 0 and len(net.edges) > 0


def test_bipartite_colouring():
    assert two_coloring(get_net("hcb")) is not None
    assert two_coloring(get_net("sql")) is None  # one node per cell → self loops
    sc, col = bipartite_version(get_net("sql"))
    assert sc.n_nodes == 2 and set(col) == {0, 1}
    assert bipartite_version(get_net("hxl")) is None


def test_supercell_preserves_coordination():
    net = get_net("dia")
    sc = supercell(net, np.diag([2, 1, 1]))
    assert sc.n_nodes == 2 * net.n_nodes
    assert set(sc.coordination()) == {4}


def test_building_block_connection_points(tma_bb, atc_bb):
    assert tma_bb.k == 3 and tma_bb.geometry == "trigonal_planar"
    assert atc_bb.k == 4 and atc_bb.geometry == "tetrahedral"
    # COOH dimer centre lies ~1.9 Å beyond the carboxyl carbon
    assert 4.0 < tma_bb.radius < 5.5


def test_unsupported_synthons_raise():
    with pytest.raises(BuildingBlockError):
        build_bb("CCCCCC")


def test_recommendation_ranks_expected_nets(tma_bb, atc_bb):
    assert recommend(tma_bb.unit, top=3)[0]["net"] == "hcb"
    names = [r["net"] for r in recommend(atc_bb.unit, top=8)]
    assert "dia" in names


def test_tma_hcb_layer_matches_known_honeycomb(tma_bb):
    out = assemble(get_net("hcb"), [tma_bb] * 2, BuildOptions(layer=LayerOptions("AA")))
    at = out.to_ase()
    a, b = at.cell.lengths()[:2]
    # experimental 2D TMA chicken-wire lattice ≈ 1.6–1.7 nm
    assert 15.5 < a < 18.0 and 15.5 < b < 18.0
    qc = quality_report(at, expected_dim=2, mol_index=out.mol_index)
    assert qc["status"] == "ok"
    assert qc["hbond_dimensionality"] == 2
    assert qc["hbonds_per_molecule"] >= 3
    assert out.info["x_mismatch_max"] < 0.05
    assert out.info["synthon_angle_max"] < 5.0


def test_torsion_alignment_fixes_flipped_carboxyls(tma_bb):
    """Whichever way the carboxyls start, alignment must give O–H···O=C pairs, never O–H facing O–H."""
    flipped = dataclasses.replace(tma_bb, coords=tma_bb.coords.copy())
    for c in flipped.connections:
        o = flipped.coords[c.axis[0]]
        flipped.coords[c.group] = _rotate(flipped.coords[c.group], o, flipped.coords[c.axis[1]] - o, np.pi)
    raw_clashes = []
    for pair in ([tma_bb, tma_bb], [tma_bb, flipped]):
        raw = assemble(get_net("hcb"), pair, BuildOptions(align_synthons=False))
        raw_clashes.append(quality_report(raw.to_ase(), mol_index=raw.mol_index)["n_close_contacts"])
        out = assemble(get_net("hcb"), pair)
        qc = quality_report(out.to_ase(), expected_dim=2, mol_index=out.mol_index)
        assert qc["n_close_contacts"] == 0 and qc["status"] == "ok"
        assert qc["hbonds_per_molecule"] >= 3
    assert max(raw_clashes) > 0  # one starting pose really is the clashing O–H/O–H arrangement


def test_best_match_equals_brute_force():
    rng = np.random.default_rng(3)
    for n in (2, 3, 4, 5):
        v = rng.normal(size=(n, 3))
        v /= np.linalg.norm(v, axis=1)[:, None]
        rot = np.linalg.qr(rng.normal(size=(3, 3)))[0]
        rot *= np.sign(np.linalg.det(rot))
        tg = (v @ rot)[rng.permutation(n)]
        brute = min(kabsch_rmsd(v, tg[list(p)])[0] for p in itertools.permutations(range(n)))
        rmsd, r, perm = best_match(v, tg)
        assert abs(rmsd - brute) < 1e-9 and rmsd < 1e-6
        assert abs(np.linalg.det(r) - 1.0) < 1e-9
        assert np.allclose(v @ r, tg[list(perm)], atol=1e-6)


def test_recommendation_demotes_nets_with_angled_synthon_pairs():
    """Isophthalate arms pair head-on in sql but at ~50° in kgm (clashing dimers)."""
    bb = build_bb("O=C(O)c1cc(C(=O)O)cc(-c2ccc(-c3cc(C(=O)O)cc(C(=O)O)c3)cc2)c1")
    static = [r["net"] for r in recommend(bb.unit, top=3)]
    assert static[0] == "kgm"  # direction matching alone prefers kgm
    recs = recommend_for_bb(bb, top=6)
    assert recs[0]["net"] == "sql" and recs[0]["fit_ok"] and recs[0]["synthon_angle"] < 15
    kgm = [r for r in recs if r["net"] == "kgm"]
    assert not kgm or (kgm[0]["synthon_angle"] > 30 and not kgm[0]["fit_ok"])
    fit = synthon_fit(get_net("kgm"), [bb] * 3)
    assert fit["synthon_angle_max"] > 30


def test_atc_dia_and_interpenetration(atc_bb):
    net = get_net("dia")
    one = assemble(net, [atc_bb] * net.n_nodes)
    two = assemble(net, [atc_bb] * net.n_nodes, BuildOptions(interpenetration=2))
    q1 = quality_report(one.to_ase(), expected_dim=3, mol_index=one.mol_index)
    assert q1["hbond_dimensionality"] == 3 and q1["status"] == "ok"
    assert len(two.symbols) == 2 * len(one.symbols)
    assert two.info["interpenetration_min_distance"] > 2.5


def test_exports_round_trip(tma_bb):
    out = assemble(get_net("hcb"), [tma_bb] * 2)
    at = out.to_ase()
    for fmt in FORMATS:
        text = export(at, fmt, "test")
        assert len(text) > 100
    back = read(io.StringIO(export(at, "cif", "t")), format="cif")
    assert len(back) == len(at)
    assert np.allclose(back.cell.cellpar(), at.cell.cellpar(), atol=1e-3)


def test_cif_molecule_extraction_round_trip(tma_bb):
    out = assemble(get_net("hcb"), [tma_bb] * 2)
    atoms = read_cif(write_cif(out.to_ase(), "tma"))
    res = analyze_structure(atoms)
    tect = [m for m in res.molecules if m.role == "tecton"]
    assert len(tect) == 1 and tect[0].count == 2
    assert tect[0].keys["inchikey"] == "QMKYBPDZANOJGF-UHFFFAOYSA-N"  # trimesic acid
    assert res.confidence == 1.0


def test_assign_bond_orders_handles_salts():
    from rdkit import Chem
    from rdkit.Chem import AllChem, rdDetermineBonds

    for smi in ("NC(=[NH2+])c1ccccc1", "[O-]C(=O)c1ccccc1", "O=[N+]([O-])c1ccccc1", "N#Cc1ccccc1"):
        m = Chem.AddHs(Chem.MolFromSmiles(smi))
        AllChem.EmbedMolecule(m, randomSeed=1)
        xyz = Chem.MolToXYZBlock(m)
        base = Chem.MolFromXYZBlock(xyz)
        rdDetermineBonds.DetermineConnectivity(base)
        out = assign_bond_orders(base)
        assert out is not None
        assert Chem.MolToInchiKey(out) == Chem.MolToInchiKey(Chem.MolFromSmiles(smi))


@pytest.mark.skipif(not zeopp_available(), reason="Zeo++ not installed")
def test_zeopp_on_porous_layer(tma_bb):
    out = assemble(get_net("hcb"), [tma_bb] * 2)
    pm = analyze_cif(write_cif(out.to_ase(), "tma"))
    assert pm["lcd_A"] > pm["pld_A"] > 0
    assert 0 < pm["void_fraction_geometric"] < 1


def test_dedupe_collapses_stacked_symmetry_copies():
    """CIFs that list a whole cell *and* symmetry operators expand into dozens of coincident copies."""
    import time

    from ase import Atoms

    from ultrahofs.analysis.cif_molecules import dedupe_overlaps

    rng = np.random.default_rng(0)
    base = dedupe_overlaps(Atoms("C" * 400, scaled_positions=rng.random((400, 3)), cell=[30, 30, 30], pbc=True))
    copies = 24
    stacked = Atoms(base.get_chemical_symbols() * copies, cell=base.cell, pbc=True,
                    positions=np.tile(base.positions, (copies, 1)) + rng.normal(0, 1e-3, (copies * len(base), 3)))
    t0 = time.time()
    out = dedupe_overlaps(stacked)
    assert len(out) == len(base)
    assert time.time() - t0 < 10
