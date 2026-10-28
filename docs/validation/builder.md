# Builder robustness benchmark

Experimental HOFSyn tectons with ≥3 builder-supported synthons (≤120 heavy atoms): **80**. Each is built on its top-ranked net with default options (AA stacking for layers, no interpenetration, no relaxation) through the same service the API uses. Run `python scripts/validate_builder.py` to reproduce (`--report-only` rewrites this page from `builder.json`, which holds the per-tecton results).

| ranking | ok | warning | fail |
|---|---|---|---|
| embedding-checked (default) | 56 | 17 | 6 |
| direction-only | 48 | 16 | 15 |

* built: **79 / 80** (1 without a net of matching connectivity); the embedding check changed the top net for 38 tectons
* H-bond network dimensionality ≥ net dimensionality: **73 / 79**
* medians: build time 3.67 s, max connection mismatch 0.001 Å, max synthon pairing angle 5.9°
* nets used: sql 39, hcb 13, hxl 8, cds 4, qtz 3, lon 2, dia 2, pcu 1, ths 1, fcl 1, kgm 1, acs 1

## What the checks mean

* **fail**: more intermolecular close contacts (heavy atoms < 2.6 Å, H···H < 1.6 Å, H···heavy < 1.5 Å) than max(2, number of molecules), or overlapping molecules. **warning**: fewer such contacts, an H-bond network of lower dimensionality than the net, or paired synthons more than 30° from head-on. All models are unrelaxed; MACE-OFF24 relaxation usually resolves warnings.
* **Direction-only ranking** compares connection directions with each net's ideal vertex geometry. **Embedding-checked ranking** (default in the UI and API) also embeds the top candidates and penalises nets in which paired synthons cannot meet head-on (angle > 15°), connection points do not close (> 0.3 Å) or molecules would overlap.
* An earlier assembler version scored 23 ok / 26 warning / 30 fail on this set (direction-only ranking). Its torsion search ignored hydrogen contacts, so it could leave carboxylic-acid or DAT pairs with their O–H/N–H groups facing each other (H···H ≈ 0.8 Å). Its automatic interlayer spacing also ignored the hydrogens of twisted aryl arms.
* Remaining failures are mostly irregular or flexible tectons (no net closes without strain), tectons with mixed synthons of very different reach (e.g. COOH + pyridyl), and single-component salts that need counter-ions. The benchmark tests construction robustness, not whether the experimental polymorph is reproduced (experimental HOFs are often interpenetrated or solvated).
