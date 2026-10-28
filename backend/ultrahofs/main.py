"""FastAPI application: REST API under /api/v1 and (optionally) the built web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import auth, build, design, hofs, meta
from .chem.standardize import MoleculeInputError
from .config import REPO_ROOT, get_settings
from .crystal.assemble import AssemblyError
from .crystal.bb import BuildingBlockError
from .db import init_db


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="UltraHOFs API", version=__version__,
                  description="Ultra-X (知声无界) hydrogen-bonded organic framework design platform",
                  docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.exception_handler(MoleculeInputError)
    async def _mol_err(_req: Request, exc: MoleculeInputError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(BuildingBlockError)
    async def _bb_err(_req: Request, exc: BuildingBlockError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(AssemblyError)
    async def _asm_err(_req: Request, exc: AssemblyError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    for r in (meta.router, auth.router, hofs.router, design.router, build.router):
        app.include_router(r, prefix="/api/v1")

    dist = s.web_dir or (REPO_ROOT / "frontend" / "dist")
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        for sub in ("fonts", "brand"):
            if (dist / sub).exists():
                app.mount(f"/{sub}", StaticFiles(directory=dist / sub), name=sub)

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404, "Not Found")
            f = dist / path
            if path and f.is_file() and dist in f.resolve().parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    @app.on_event("startup")
    def _startup() -> None:
        init_db()

    return app


app = create_app()

__all__ = ["app", "Path"]
