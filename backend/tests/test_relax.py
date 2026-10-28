from __future__ import annotations

import pytest

from .conftest import TMA


@pytest.mark.slow
def test_mace_off24_short_relaxation():
    from ultrahofs.crystal.assemble import assemble
    from ultrahofs.crystal.bb import build_bb
    from ultrahofs.crystal.nets import get_net
    from ultrahofs.relax.engine import model_available, relax

    if not model_available():
        pytest.skip("MACE-OFF24 model file not present")
    bb = build_bb(TMA, planar=True)
    at = assemble(get_net("hcb"), [bb] * 2).to_ase()
    res = relax(at, steps_atoms=15, steps_cell=10, device="cpu")
    assert res["energy_final_eV"] <= res["energy_initial_eV"] + 1e-6
    assert len(res["atoms"]) == len(at)
