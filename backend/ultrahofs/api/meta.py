"""Health, version, platform statistics and data-source attributions."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from ..analysis.zeopp import zeopp_available
from ..db import get_db
from ..models import DataSource, GeneratedStructure, HOFEntry, Job, Molecule, Reference, User
from ..relax.engine import model_available
from .deps import current_user

router = APIRouter()

SOFTWARE = [
    {"name": "RDKit", "license": "BSD-3-Clause", "url": "https://www.rdkit.org"},
    {"name": "pymatgen", "license": "MIT", "url": "https://pymatgen.org"},
    {"name": "ASE", "license": "LGPL-2.1", "url": "https://wiki.fysik.dtu.dk/ase/"},
    {"name": "PORMAKE (RCSR topology data)", "license": "MIT; RCSR data free with citation",
     "url": "https://github.com/Sangwon91/PORMAKE", "citation": "Lee, S. et al. ACS Appl. Mater. Interfaces 2021, "
                                                              "13, 23647. RCSR: O'Keeffe, M. et al. Acc. Chem. Res. "
                                                              "2008, 41, 1782."},
    {"name": "Zeo++", "license": "modified BSD (LBNL)", "url": "http://www.zeoplusplus.org",
     "citation": "Willems, T. F. et al. Microporous Mesoporous Mater. 2012, 149, 134."},
    {"name": "MACE-OFF24", "license": "Academic Software License", "url": "https://github.com/ACEsuit/mace-off",
     "citation": "Kovács, D. P. et al. J. Am. Chem. Soc. 2025."},
    {"name": "gemmi", "license": "MPL-2.0", "url": "https://gemmi.readthedocs.io"},
    {"name": "OPSIN", "license": "MIT", "url": "https://github.com/dan2097/opsin"},
    {"name": "Ketcher", "license": "Apache-2.0", "url": "https://lifescience.opensource.epam.com/ketcher/"},
    {"name": "3Dmol.js", "license": "BSD-3-Clause", "url": "https://3dmol.csb.pitt.edu"},
    {"name": "Zhuque Fangsong (朱雀仿宋)", "license": "SIL OFL 1.1", "url": "https://github.com/TrionesType/zhuque"},
]


@router.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/meta/overview", tags=["meta"])
def overview(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    def count(model, *where):  # noqa: ANN001, ANN202
        stmt = select(func.count(model.id))
        for w in where:
            stmt = stmt.where(w)
        return db.execute(stmt).scalar_one()

    return {
        "version": __version__,
        "entries": count(HOFEntry, HOFEntry.curation_status.in_(("auto", "verified", "needs_review"))),
        "verified_or_auto": count(HOFEntry, HOFEntry.curation_status.in_(("auto", "verified"))),
        "needs_review": count(HOFEntry, HOFEntry.curation_status == "needs_review"),
        "references": count(Reference),
        "experimental_tectons": count(Molecule, Molecule.is_experimental_tecton.is_(True)),
        "molecules": count(Molecule),
        "structures": count(GeneratedStructure, GeneratedStructure.org_id == user.org_id),
        "jobs_running": count(Job, Job.status == "running"),
        "jobs_queued": count(Job, Job.status == "queued"),
        "capabilities": {"zeopp": zeopp_available(), "mace_off24": model_available()},
    }


@router.get("/meta/data-sources", tags=["meta"])
def data_sources(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    ds = [{"key": d.key, "name": d.name, "version": d.version, "url": d.url, "license": d.license,
           "attribution": d.attribution} for d in db.execute(select(DataSource)).scalars()]
    return {"datasets": ds, "software": SOFTWARE}
