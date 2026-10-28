# Third-party notices

UltraHOFs itself is proprietary (see [LICENSE](LICENSE)). It uses or redistributes the following
third-party data and software under their own licences.

## Data

| Data | Licence | Notes |
|---|---|---|
| [HOFSyn v2](https://doi.org/10.6084/m9.figshare.28856483.v2) (Wang, T., 2025, figshare) | CC BY 4.0 | Source of the experimental HOF database. Re-processed by UltraHOFs (structures parsed, roles and SMILES assigned, scores and pore metrics added, embedded SHELX reflection/result data removed from CIFs). The bundled database is distributed under CC BY 4.0. |
| Crystal structures cited by CCDC number | per original deposition | Please cite the original publications listed for each entry. |
| [Crossref](https://www.crossref.org) metadata | CC0 | Bibliographic metadata of the references. |
| RCSR nets via [PORMAKE](https://github.com/Sangwon91/PORMAKE) | MIT; RCSR free with citation | O'Keeffe, M. et al. *Acc. Chem. Res.* **2008**, 41, 1782. |
| [MACE-OFF24](https://github.com/ACEsuit/mace-off) model | Academic Software License | **Not redistributed.** Downloaded from the authors' repository on first use of structure relaxation; commercial use requires a licence from the authors. Kovács, D. P. et al. *J. Am. Chem. Soc.* **2025**. |

## Software (backend and container image)

| Component | Licence |
|---|---|
| Python | PSF-2.0 |
| RDKit | BSD-3-Clause |
| pymatgen | MIT |
| ASE | LGPL-2.1-or-later |
| spglib | BSD-3-Clause |
| gemmi | MPL-2.0 |
| Zeo++ (zeopp-lsmo) | BSD-3-Clause-style (Zeo++ licence) — Willems, T. F. et al. *Microporous Mesoporous Mater.* **2012**, 149, 134 |
| NumPy, SciPy, NetworkX | BSD-3-Clause |
| PyTorch | BSD-3-Clause |
| mace-torch, e3nn | MIT |
| FastAPI, Starlette, Pydantic, SQLAlchemy, Alembic, Uvicorn, HTTPX | MIT / BSD-3-Clause |
| PyJWT, argon2-cffi, python-multipart | MIT |
| py2opsin / OPSIN | MIT |

## Web interface

| Component | Licence |
|---|---|
| React, React Router, TanStack Query, i18next | MIT |
| Ant Design | MIT |
| Ketcher | Apache-2.0 |
| 3Dmol.js | BSD-3-Clause |
| Apache ECharts | Apache-2.0 |
| Fonts: 朱雀仿宋 Zhuque Fangsong, Cormorant Garamond, Inter, JetBrains Mono, Noto Sans SC | SIL Open Font License 1.1 (`frontend/public/fonts/zhuque/OFL.txt`) |

The full licence texts of the Python and JavaScript packages ship with the packages themselves
(`site-packages/*/LICENSE*`, `node_modules/*/LICENSE*`).
