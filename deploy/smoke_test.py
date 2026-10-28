"""End-to-end smoke test of a running UltraHOFs server in demo mode (standard library only).

    python3 deploy/smoke_test.py http://127.0.0.1:8000 [--no-relax]

Exercises what a trial user does: demo login, database statistics and an entry's 3D structure,
molecule evaluation, topology suggestion, structure building/export and a MACE-OFF24 relaxation job.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TMA = "OC(=O)c1cc(C(O)=O)cc(C(O)=O)c1"


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/") + "/api/v1"
        self.token = ""

    def call(self, method: str, path: str, body: dict | None = None, raw: bool = False, timeout: float = 300):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = r.read().decode()
        except urllib.error.HTTPError as e:
            raise AssertionError(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}") from e
        return payload if raw else json.loads(payload)


def step(name: str) -> None:
    print(f"[smoke] {name}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="http://127.0.0.1:8000")
    ap.add_argument("--no-relax", action="store_true")
    ap.add_argument("--min-entries", type=int, default=600)
    args = ap.parse_args()
    c = Client(args.base)

    step("health")
    h = c.call("GET", "/health")
    assert h["status"] == "ok" and h["demo_mode"] is True, h

    step("demo login")
    c.token = c.call("POST", "/auth/demo")["access_token"]

    step("database statistics")
    ov = c.call("GET", "/meta/overview")
    assert ov["entries"] >= args.min_entries and ov["references"] >= 200, ov
    assert ov["capabilities"]["zeopp"], "Zeo++ missing"

    step("entry list, citation and 3D structure")
    items = c.call("GET", "/hofs?size=20")["items"]
    shown = 0
    for e in items:
        d = c.call("GET", f"/hofs/{e['id']}")
        if d.get("has_raw_cif") or d.get("has_framework_cif"):
            cif = c.call("GET", f"/hofs/{e['id']}/cif?kind=display", raw=True)
            assert "_cell_length_a" in cif
            shown += 1
    assert shown >= 5, f"only {shown} entries had a displayable structure"

    step("evaluate a molecule (trimesic acid)")
    ev = c.call("POST", "/molecules/evaluate", {"input": TMA, "n_confs": 3})
    assert ev["score"]["score"] > 0 and ev["precedent"]["status"] != "none", ev.get("precedent")

    step("topology suggestion")
    sug = c.call("POST", "/topologies/suggest", {"smiles": TMA})
    assert sug["nets"][0]["net"] == "hcb", [n["net"] for n in sug["nets"][:5]]

    step("build hcb layer + export CIF")
    st = c.call("POST", "/structures/build", {"net": "hcb", "node": TMA, "name": "smoke TMA hcb"})
    assert st["qc"]["status"] == "ok", st["qc"]
    cif = c.call("GET", f"/structures/{st['id']}/export?format=cif", raw=True)
    assert "_cell_length_a" in cif

    if not args.no_relax:
        step("MACE-OFF24 relaxation job (downloads the model on first use)")
        job = c.call("POST", f"/structures/{st['id']}/relax",
                     {"engine": "mace_off24", "steps_atoms": 60, "steps_cell": 40})
        t0 = time.time()
        while True:
            j = c.call("GET", f"/jobs/{job['id']}")
            if j["status"] not in ("queued", "running"):
                break
            if time.time() - t0 > 900:
                raise AssertionError(f"relaxation job still {j['status']} after 900 s")
            time.sleep(5)
        assert j["status"] == "succeeded", j.get("error") or j
        relaxed = c.call("GET", f"/structures/{j['result']['structure_id']}")
        assert relaxed["status"] == "relaxed", relaxed["status"]
        print(f"[smoke] relaxation finished in {time.time() - t0:.0f} s", flush=True)

    print("[smoke] all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
