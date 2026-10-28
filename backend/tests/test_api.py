from __future__ import annotations

from .conftest import ATC, TMA


def test_health(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_unknown_api_path_is_json_404_not_the_web_ui(client):
    r = client.get("/api/v1/no-such-endpoint")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


def test_auth_required(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401


def test_me(client, admin_headers):
    r = client.get("/api/v1/auth/me", headers=admin_headers)
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_member_cannot_curate(client, member_headers):
    assert client.get("/api/v1/curation/queue", headers=member_headers).status_code == 403
    assert client.get("/api/v1/users", headers=member_headers).status_code == 403


def test_curated_entry_and_precedent_lookup(client, admin_headers):
    body = {"name": "TMA test framework", "components": [{"smiles": TMA, "role": "tecton", "name": "trimesic acid"}],
            "topology": "hcb", "hbond_class": "carboxy", "solvents": ["water"], "temperature": "rt",
            "evidence": {"geometric_porosity": {"value": "yes", "note": "test"}}}
    r = client.post("/api/v1/curation/entries", json=body, headers=admin_headers)
    assert r.status_code == 200, r.text
    entry = r.json()
    assert entry["evidence"]["crystal_structure_reported"]["value"] == "yes"
    assert entry["evidence"]["geometric_porosity"]["source"] == "curated"
    lst = client.get("/api/v1/hofs", params={"q": "TMA"}, headers=admin_headers).json()
    assert lst["total"] >= 1
    detail = client.get(f"/api/v1/hofs/{entry['id']}", headers=admin_headers).json()
    assert detail["all_components"][0]["svg"].startswith("<svg") or "<svg" in detail["all_components"][0]["svg"]
    # exact precedent for the same molecule given as its anion
    ev = client.post("/api/v1/molecules/evaluate", json={"input": TMA, "n_confs": 3}, headers=admin_headers).json()
    assert ev["precedent"]["status"] == "exact"
    assert ev["score"]["score"] > 75
    assert ev["nets"]["nets"][0]["net"] == "hcb"
    anion = "[O-]C(=O)c1cc(C([O-])=O)cc(C([O-])=O)c1"
    ev2 = client.post("/api/v1/molecules/evaluate", json={"input": anion, "n_confs": 2, "suggest_nets": False},
                      headers=admin_headers).json()
    assert ev2["precedent"]["status"] == "same_parent"
    s = client.post("/api/v1/hofs/search/structure", json={"query": "c1ccccc1C(=O)O", "mode": "substructure"},
                    headers=admin_headers).json()
    assert s["total"] >= 1
    patch = client.patch(f"/api/v1/hofs/{entry['id']}", json={"curation_status": "verified", "topology": "hcb"},
                         headers=admin_headers)
    assert patch.status_code == 200 and patch.json()["curation_status"] == "verified"
    stats = client.get("/api/v1/hofs/stats", headers=admin_headers).json()
    assert stats["n_entries"] >= 1


def test_generate_sync(client, member_headers):
    r = client.post("/api/v1/molecules/generate", json={"cores": ["benzene_135"], "arms": ["none", "phenylene"],
                                                        "synthons": ["carboxylic_acid"], "with_3d": True},
                    headers=member_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "sync" and data["n"] == 2
    assert all(c["route"]["en"] for c in data["candidates"])


def test_libraries_and_topologies(client, member_headers):
    lib = client.get("/api/v1/libraries", headers=member_headers).json()
    assert len(lib["cores"]) > 15 and len(lib["synthons"]) > 10
    tops = client.get("/api/v1/topologies", params={"precedent": True}, headers=member_headers).json()
    assert any(t["name"] == "dia" for t in tops["items"])
    d = client.get("/api/v1/topologies/hcb", headers=member_headers).json()
    assert d["dim"] == 2 and d["bipartite"]
    sug = client.post("/api/v1/topologies/suggest", json={"smiles": ATC}, headers=member_headers).json()
    assert "dia" in [n["net"] for n in sug["nets"]]
    dia = next(n for n in sug["nets"] if n["net"] == "dia")
    assert dia["fit_ok"] and dia["synthon_angle"] < 15 and dia["x_mismatch"] < 0.3


def test_build_export_and_relax_job(client, member_headers):
    r = client.post("/api/v1/structures/build", json={"net": "hcb", "node": TMA, "name": "TMA-hcb"},
                    headers=member_headers)
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["qc"]["status"] == "ok" and st["cif"].startswith("#")
    for fmt in ("cif", "cif_sym", "poscar", "xyz", "lammps", "pdb"):
        e = client.get(f"/api/v1/structures/{st['id']}/export", params={"format": fmt}, headers=member_headers)
        assert e.status_code == 200 and len(e.text) > 100
    job = client.post(f"/api/v1/structures/{st['id']}/relax", json={"steps_atoms": 20, "steps_cell": 0},
                      headers=member_headers)
    assert job.status_code == 200 and job.json()["status"] == "queued"
    jobs = client.get("/api/v1/jobs", headers=member_headers).json()
    assert jobs["total"] >= 1
    cancel = client.post(f"/api/v1/jobs/{job.json()['id']}/cancel", headers=member_headers).json()
    assert cancel["status"] == "cancelled"


def test_build_bipartite_salt(client, member_headers):
    body = {"net": "hcb", "mode": "bipartite", "node_a": "NC(=[NH2+])c1cc(C(N)=[NH2+])cc(C(N)=[NH2+])c1",
            "node_b": "[O-]C(=O)c1cc(C([O-])=O)cc(C([O-])=O)c1", "analyze": False}
    r = client.post("/api/v1/structures/build", json=body, headers=member_headers)
    assert r.status_code == 200, r.text
    assert r.json()["qc"]["hbond_dimensionality"] == 2


def test_build_errors_are_422(client, member_headers):
    r = client.post("/api/v1/structures/build", json={"net": "dia", "node": TMA}, headers=member_headers)
    assert r.status_code == 422
    r = client.post("/api/v1/structures/build", json={"net": "nonexistent-net", "node": TMA}, headers=member_headers)
    assert r.status_code == 404


def test_projects(client, member_headers):
    p = client.post("/api/v1/projects", json={"name": "Demo"}, headers=member_headers).json()
    ev = client.post("/api/v1/molecules/evaluate", json={"input": ATC, "n_confs": 2, "suggest_nets": False},
                     headers=member_headers).json()
    p2 = client.post(f"/api/v1/projects/{p['id']}/items", json={"item_type": "molecule",
                                                                 "item_id": ev["molecule_id"]},
                     headers=member_headers).json()
    assert p2["n_items"] == 1 and p2["items"][0]["smiles"]
    assert client.delete(f"/api/v1/projects/{p['id']}", headers=member_headers).json()["ok"]
