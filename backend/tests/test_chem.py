from __future__ import annotations

import pytest
from rdkit import Chem

from ultrahofs.chem.enumerate import enumerate_tectons, route_hint
from ultrahofs.chem.pairs import evaluate_pair, stoichiometry
from ultrahofs.chem.scoring import score_molecule
from ultrahofs.chem.standardize import MoleculeInputError, mol_keys, parse_molecule
from ultrahofs.chem.synthons import SYNTHON_TYPES, _compiled, connection_count, find_synthons

from .conftest import ATC, MTB, TMA, TTBI


def test_all_synthon_smarts_compile():
    for st in SYNTHON_TYPES:
        for s in st.smarts:
            _compiled(s)


@pytest.mark.parametrize("smiles,expected", [
    (TMA, {"carboxylic_acid": 3}),
    (TTBI, {"benzimidazolone": 3}),
    ("Nc1nc(N)nc(-c2ccccc2)n1", {"dat": 1}),
    ("NC(=[NH2+])c1ccccc1", {"amidinium": 1}),
    ("[O-]S(=O)(=O)c1ccc(-c2ccc(S([O-])(=O)=O)cc2)cc1", {"sulfonate": 2}),
    ("O=C1NC(=O)c2ccc3C(=O)NC(=O)c4ccc1c2c34", {"imide": 2}),
    ("O=c1ccc(-c2ccccc2)c[nH]1", {"pyridone": 1}),
])
def test_synthon_detection(smiles, expected):
    found = {}
    for m in find_synthons(Chem.MolFromSmiles(smiles)):
        found[m.key] = found.get(m.key, 0) + 1
    assert found == expected


def test_keys_match_across_protonation():
    acid = mol_keys(parse_molecule(TMA))
    anion = mol_keys(parse_molecule("[O-]C(=O)c1cc(C([O-])=O)cc(C([O-])=O)c1"))
    assert acid.inchikey != anion.inchikey
    assert acid.parent_key == anion.parent_key


def test_bad_input_rejected():
    with pytest.raises(MoleculeInputError):
        parse_molecule("not a molecule ((")


def test_scores_rank_known_tectons_above_decoys():
    known = [TMA, ATC, TTBI, MTB]
    decoys = ["OC(=O)CCCCC(O)=O", "OC(=O)c1ccccc1C(O)=O", "OC(=O)CCCN(CCCC(O)=O)CCCC(O)=O",
              "CC(C)Cc1ccc(C(C)C(O)=O)cc1"]
    ks = [score_molecule(Chem.MolFromSmiles(s), n_confs=3)["score"] for s in known]
    ds = [score_molecule(Chem.MolFromSmiles(s), n_confs=3)["score"] for s in decoys]
    assert min(ks) > max(ds)
    assert all(k >= 75 for k in ks)


def test_enumeration_reproduces_landmark_tectons():
    keys = {c.keys["inchikey"] for c in enumerate_tectons(min_sites=3)}
    for s in (TMA, ATC, TTBI, MTB):
        assert Chem.MolToInchiKey(Chem.MolFromSmiles(s)) in keys


def test_enumeration_is_symmetric_and_unique():
    cands = list(enumerate_tectons(["benzene_135"], ["none", "phenylene"], ["carboxylic_acid", "dat"]))
    assert len(cands) == 4
    assert len({c.keys["inchikey"] for c in cands}) == 4
    for c in cands:
        assert connection_count(find_synthons(Chem.MolFromSmiles(c.smiles))) == 3


def test_route_hint_bilingual():
    r = route_hint("pyrene", "phenylene", "carboxylic_acid")
    assert r["en"] and r["zh"] and "Suzuki" in " ".join(r["en"])


def test_pair_stoichiometry_and_motif():
    assert stoichiometry(4, -2) == (1, 2)
    assert stoichiometry(3, -3) == (1, 1)
    res = evaluate_pair("NC(=[NH2+])c1ccc(C(c2ccc(C(N)=[NH2+])cc2)(c2ccc(C(N)=[NH2+])cc2)c2ccc(C(N)=[NH2+])cc2)cc1",
                        "[O-]C(=O)c1ccc(C([O-])=O)cc1", with_3d=False)
    assert res["stoichiometry"] == {"cation": 1, "anion": 2}
    assert res["complementarity"]["score"] == 1.0
