"""Runtime configuration (environment variables prefixed with ULTRAHOFS_)."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ULTRAHOFS_", env_file=str(REPO_ROOT / ".env"), extra="ignore"
    )

    app_name: str = "UltraHOFs"
    environment: str = "dev"
    var_dir: Path = REPO_ROOT / "var"
    data_dir: Path = REPO_ROOT / "data"
    database_url: str = ""
    secret_key: str = ""
    access_token_minutes: int = 120
    refresh_token_days: int = 14
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    crossref_mailto: str = ""
    http_timeout_s: float = 30.0

    zeopp_binary: str = "network"
    max_build_atoms: int = 8000
    max_relax_atoms: int = 1500
    max_generate_sync: int = 400

    worker_poll_s: float = 2.0
    worker_concurrency: int = 1
    torch_threads: int = 8
    relax_device: str = "auto"  # auto | cpu | cuda
    gpu_min_free_mb: int = 8000
    relax_timeout_s: int = 3600
    mace_off_model: str = ""  # path or URL of the MACE-OFF24 model file

    executor: str = "local"  # local | slurm
    slurm_account: str = "m4517"
    slurm_qos: str = "regular"
    slurm_constraint: str = "gpu"

    enable_csd: bool = True

    web_dir: Path | None = None  # built web UI; default <repo>/frontend/dist
    seed_dir: Path | None = None  # data bundle copied into an empty installation (see `ultrahofs export-seed`)
    demo_mode: bool = False  # password-less "demo" login for private trial environments (e.g. Codespaces)
    admin_password: str = ""  # initial admin password; random (printed + saved under var/) when empty

    @property
    def artifacts_dir(self) -> Path:
        return self.var_dir / "artifacts"

    @property
    def cache_dir(self) -> Path:
        return self.var_dir / "cache"

    def var_path(self, p: str | Path | None) -> Path | None:
        """Resolve a file path stored in the database; relative paths are relative to ``var_dir``."""
        if not p:
            return None
        p = Path(p)
        return p if p.is_absolute() else self.var_dir / p

    def rel_var_path(self, p: str | Path) -> str:
        """Path to store in the database: relative to ``var_dir`` when inside it, so data stay portable."""
        p = Path(p)
        try:
            return p.resolve().relative_to(self.var_dir.resolve()).as_posix()
        except ValueError:
            return str(p)

    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.var_dir / 'ultrahofs.db'}"

    def resolved_secret_key(self) -> str:
        if self.secret_key:
            return self.secret_key
        key_file = self.var_dir / "secret.key"
        if key_file.exists():
            return key_file.read_text().strip()
        self.var_dir.mkdir(parents=True, exist_ok=True)
        key = secrets.token_urlsafe(48)
        key_file.write_text(key)
        key_file.chmod(0o600)
        return key


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.var_dir, s.artifacts_dir, s.cache_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s
