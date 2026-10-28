from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from ultrahofs.bootstrap import strip_diffraction_data
from ultrahofs.config import get_settings

CIF_WITH_DIFFRACTION = """data_x
_cell_length_a 10.0
_refine_special_details
;
 kept: an ordinary text field
;
_shelx_res_file
;
TITL x
END
;
_shelx_res_checksum 123
_shelx_hkl_file
;
   1   0   0   100.0   1.0
;
_shelx_fab_file
;
 fab data
;
loop_
_atom_site_label
_atom_site_fract_x
C1 0.1
"""


def test_strip_diffraction_data_keeps_structural_content():
    out = strip_diffraction_data(CIF_WITH_DIFFRACTION)
    assert "_shelx" not in out and "TITL" not in out and "fab data" not in out
    for kept in ("_cell_length_a 10.0", "kept: an ordinary text field", "loop_", "C1 0.1"):
        assert kept in out
    assert strip_diffraction_data(out) == out


def test_var_paths_are_portable():
    s = get_settings()
    assert s.rel_var_path(s.var_dir / "cif" / "raw" / "1.cif") == "cif/raw/1.cif"
    assert s.var_path("cif/raw/1.cif") == s.var_dir / "cif" / "raw" / "1.cif"
    assert s.var_path("/elsewhere/x.cif") == Path("/elsewhere/x.cif")
    assert s.var_path("") is None


EXPORT = """
import sys
from pathlib import Path
from fastapi.testclient import TestClient
from ultrahofs.bootstrap import bootstrap, export_seed
from ultrahofs.crystal.assemble import assemble
from ultrahofs.crystal.bb import build_bb
from ultrahofs.crystal.export import write_cif
from ultrahofs.crystal.nets import get_net

TMA = "OC(=O)c1cc(C(O)=O)cc(C(O)=O)c1"
bootstrap(log=lambda m: None)
from ultrahofs.main import app
with TestClient(app) as c:
    tok = c.post("/api/v1/auth/login", json={"username": "admin", "password": "seed-test-pw-123"}).json()
    h = {"Authorization": "Bearer " + tok["access_token"]}
    e = c.post("/api/v1/curation/entries", headers=h, json={
        "name": "TMA seed test", "components": [{"smiles": TMA, "role": "tecton"}], "topology": "hcb"}).json()
    out = assemble(get_net("hcb"), [build_bb(TMA, planar=True)] * 2)
    cif = write_cif(out.to_ase(), "tma") + "_shelx_hkl_file\\n;\\n   1   0   0   100.0   1.0\\n;\\n"
    r = c.post(f"/api/v1/curation/entries/{e['id']}/cif", headers=h, files={"file": ("tma.cif", cif.encode())},
               data={"analyze": "false"})
    assert r.status_code == 200, r.text
export_seed(Path(sys.argv[1]), log=lambda m: None)
"""

FIRST_RUN = """
import json
from fastapi.testclient import TestClient
from ultrahofs.bootstrap import bootstrap

r1 = bootstrap(log=lambda m: None)
r2 = bootstrap(log=lambda m: None)
from ultrahofs.main import app
with TestClient(app) as c:
    health = c.get("/api/v1/health").json()
    d = c.post("/api/v1/auth/demo").json()
    h = {"Authorization": "Bearer " + d["access_token"]}
    lst = c.get("/api/v1/hofs", headers=h).json()
    eid = lst["items"][0]["id"]
    raw = c.get(f"/api/v1/hofs/{eid}/cif", params={"kind": "raw"}, headers=h)
    disp = c.get(f"/api/v1/hofs/{eid}/cif", params={"kind": "display"}, headers=h)
    users = sorted(u["username"] for u in c.get("/api/v1/users", headers=h).json())
print(json.dumps({"r1": r1, "r2": r2, "health": health, "total": lst["total"], "raw_status": raw.status_code,
                  "raw_has_hkl": "_shelx_hkl" in raw.text, "raw_has_atoms": "_atom_site_fract_x" in raw.text,
                  "display_status": disp.status_code, "users": users}))
"""


def _run(code: str, env: dict, *args: str) -> str:
    r = subprocess.run([sys.executable, "-c", code, *args], env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    return r.stdout


def _env(var_dir: Path, **extra: str) -> dict:
    env = dict(os.environ, ULTRAHOFS_VAR_DIR=str(var_dir), ULTRAHOFS_DATABASE_URL=f"sqlite:///{var_dir}/ultrahofs.db")
    for k in ("ULTRAHOFS_SEED_DIR", "ULTRAHOFS_DEMO_MODE", "ULTRAHOFS_ADMIN_PASSWORD"):
        env.pop(k, None)
    env.update(extra)
    return env


def test_seed_export_then_first_run_of_a_new_installation(tmp_path):
    seed = tmp_path / "seed"
    _run(EXPORT, _env(tmp_path / "a", ULTRAHOFS_ADMIN_PASSWORD="seed-test-pw-123"), str(seed))

    manifest = json.loads((seed / "manifest.json").read_text())
    assert manifest["entries"] == 1 and manifest["cif_files"]["raw"] == 1 and manifest["cif_files"]["display"] == 1
    con = sqlite3.connect(seed / "ultrahofs.db")
    assert con.execute("select count(*) from users").fetchone()[0] == 0
    assert con.execute("select cif_raw_path from hof_entries").fetchone()[0] == "cif/raw/1.cif"
    con.close()
    assert "_shelx_hkl_file" not in (seed / "cif" / "raw" / "1.cif").read_text()
    assert (seed / "ATTRIBUTION.md").exists()

    var_b = tmp_path / "b"
    out = json.loads(_run(FIRST_RUN, _env(var_b, ULTRAHOFS_SEED_DIR=str(seed), ULTRAHOFS_DEMO_MODE="true")))
    assert out["r1"] == {"seed_loaded": True, "admin_created": True, "demo_created": True}
    assert out["r2"] == {"seed_loaded": False}  # second start: nothing reloaded, no extra accounts
    assert out["health"]["demo_mode"] is True
    assert out["total"] == 1 and out["raw_status"] == 200 and out["display_status"] == 200
    assert out["raw_has_atoms"] and not out["raw_has_hkl"]
    assert out["users"] == ["admin", "demo"]
    pw_file = var_b / "initial_admin_password.txt"
    assert pw_file.exists() and oct(pw_file.stat().st_mode & 0o777) == "0o600"
