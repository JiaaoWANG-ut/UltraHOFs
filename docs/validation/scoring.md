# HOF-likeness score validation

Positive–unlabeled check: experimental HOF tectons (HOFSyn-derived, this database) vs. a background set of 78 generic organic molecules (acids, amides, drugs, sugars, solvents). Background molecules are *not* proven non-HOFs, so AUC measures enrichment, not classification accuracy.

| set | n | median | p10 | p90 |
|---|---|---|---|---|
| experimental_all | 296 | 48.8 | 20.2 | 86.1 |
| experimental_with_classical_synthon | 213 | 60.6 | 34.8 | 87.5 |
| experimental_with_>=3_synthons | 118 | 82.9 | 46.0 | 89.9 |
| background_all | 78 | 27.9 | 17.2 | 48.8 |
| background_with_classical_synthon | 52 | 33.4 | 20.6 | 53.8 |

* ROC-AUC (all): **0.725**
* ROC-AUC (molecules with ≥1 classical H-bond synthon — the score's design domain): **0.869**
* 28% of experimental entries' tectons have no classical N–H/O–H synthon (porous molecular crystals held by weaker C–H···X contacts are included in HOFSyn); the score is designed for synthon-driven HOFs and ranks those low by construction.

Highest-scoring background molecules (expected false positives):

* `OC(=O)c1ccc(cc1)C(O)=O` — 58.5
* `OC(=O)c1ccccc1C(O)=O` — 55.8
* `OC(=O)C1CCC(CC1)C(O)=O` — 55.1
* `OC(=O)CC(O)=O` — 55.0
* `OC(=O)c1cccc(C(O)=O)c1` — 54.1
* `OC(=O)CC(O)(CC(O)=O)C(O)=O` — 53.8
* `OC(=O)C=CC(O)=O` — 51.9
* `O=C(O)CNC(=O)c1ccccc1` — 48.8

The score remains a ranking heuristic and is never presented as a formation probability.
