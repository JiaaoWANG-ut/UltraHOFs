"""Relaxation engine interface + MACE-OFF24 implementation (two-stage: atoms, then cell)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from ase import Atoms

from ..config import get_settings

MACE_OFF24_URL = "https://raw.githubusercontent.com/ACEsuit/mace-off/main/mace_off24/MACE-OFF24_medium.model"


@dataclass
class EngineInfo:
    key: str
    name: str
    version: str
    license: str
    citation: str
    elements: tuple[str, ...]


ENGINES = {
    "mace_off24": EngineInfo(
        "mace_off24", "MACE-OFF24 (medium)", "MACE-OFF24_medium",
        "Academic Software License (ASL); commercial use requires a licence from the authors",
        "Kovács, D. P. et al. MACE-OFF: Short-Range Transferable Machine Learning Force Fields for Organic "
        "Molecules. J. Am. Chem. Soc. 2025. https://doi.org/10.1021/jacs.4c07099",
        ("H", "C", "N", "O", "F", "P", "S", "Cl", "Br", "I"),
    ),
}


class RelaxError(RuntimeError):
    pass


def pick_device(pref: str | None = None) -> str:
    s = get_settings()
    pref = pref or s.relax_device
    if pref == "cpu":
        return "cpu"
    try:
        import torch

        if torch.cuda.is_available():
            free, _total = torch.cuda.mem_get_info()
            if free / 1e6 >= s.gpu_min_free_mb or pref == "cuda":
                return "cuda"
    except Exception:  # noqa: BLE001
        pass
    return "cpu"


def _candidate_model_files() -> list[Path]:
    from ..config import REPO_ROOT

    s = get_settings()
    return [s.var_dir / "models" / "MACE-OFF24_medium.model", REPO_ROOT / "var" / "models" / "MACE-OFF24_medium.model"]


def _model_path() -> str:
    s = get_settings()
    if s.mace_off_model:
        return s.mace_off_model
    for p in _candidate_model_files():
        if p.exists():
            return str(p)
    local = _candidate_model_files()[0]
    if not local.exists():
        import httpx

        local.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", MACE_OFF24_URL, follow_redirects=True, timeout=300) as r:
            r.raise_for_status()
            with open(local, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    return str(local)


def mace_off24_calculator(device: str):  # noqa: ANN201
    import warnings

    import torch

    warnings.filterwarnings("ignore")
    torch.set_num_threads(get_settings().torch_threads)
    from mace.calculators import MACECalculator

    return MACECalculator(model_paths=_model_path(), device=device, default_dtype="float64")


def check_elements(atoms: Atoms, engine: str) -> None:
    allowed = set(ENGINES[engine].elements)
    bad = sorted(set(atoms.get_chemical_symbols()) - allowed)
    if bad:
        raise RelaxError(f"{ENGINES[engine].name} does not support elements: {', '.join(bad)}")


def relax(atoms: Atoms, *, engine: str = "mace_off24", fmax_atoms: float = 0.05, fmax_cell: float = 0.02,
          steps_atoms: int = 400, steps_cell: int = 800, cell_relax: bool = True, device: str | None = None,
          progress: Callable[[float, str], None] | None = None, should_stop: Callable[[], bool] | None = None,
          traj_every: int = 10) -> dict:
    from ase.filters import FrechetCellFilter
    from ase.optimize import FIRE

    if engine not in ENGINES:
        raise RelaxError(f"unknown engine {engine}")
    s = get_settings()
    if len(atoms) > s.max_relax_atoms:
        raise RelaxError(f"structure has {len(atoms)} atoms; limit is {s.max_relax_atoms} on this server")
    check_elements(atoms, engine)
    dev = pick_device(device)
    t0 = time.time()
    calc = mace_off24_calculator(dev)
    at = atoms.copy()
    at.calc = calc
    e0 = float(at.get_potential_energy())
    v0 = float(at.cell.volume)
    frames: list[Atoms] = [at.copy()]
    total_steps = steps_atoms + (steps_cell if cell_relax else 0)
    state = {"n": 0}

    def make_cb(opt, stage: str):  # noqa: ANN001, ANN202
        def cb() -> None:
            state["n"] += 1
            if state["n"] % traj_every == 0:
                frames.append(at.copy())
            if progress and state["n"] % 5 == 0:
                try:
                    fmax = float(np.sqrt((opt.optimizable.get_forces() ** 2).sum(axis=1).max()))
                except Exception:  # noqa: BLE001
                    fmax = float("nan")
                progress(min(0.99, state["n"] / total_steps), f"{stage}: step {state['n']}, fmax {fmax:.3f} eV/Å")
            if should_stop and should_stop():
                raise RelaxError("cancelled")
        return cb

    opt1 = FIRE(at, logfile=None)
    opt1.attach(make_cb(opt1, "atoms"), interval=1)
    conv1 = opt1.run(fmax=fmax_atoms, steps=steps_atoms)
    conv2 = None
    if cell_relax:
        filt = FrechetCellFilter(at)
        opt2 = FIRE(filt, logfile=None)
        opt2.attach(make_cb(opt2, "cell"), interval=1)
        conv2 = opt2.run(fmax=fmax_cell, steps=steps_cell)
    e1 = float(at.get_potential_energy())
    v1 = float(at.cell.volume)
    frames.append(at.copy())
    out = at.copy()
    out.calc = None
    return {
        "atoms": out,
        "frames": frames,
        "engine": engine,
        "engine_name": ENGINES[engine].name,
        "license": ENGINES[engine].license,
        "citation": ENGINES[engine].citation,
        "device": dev,
        "energy_initial_eV": round(e0, 5),
        "energy_final_eV": round(e1, 5),
        "energy_change_eV": round(e1 - e0, 5),
        "volume_initial_A3": round(v0, 3),
        "volume_final_A3": round(v1, 3),
        "volume_change_pct": round(100 * (v1 - v0) / v0, 2),
        "converged_atoms": bool(conv1),
        "converged_cell": None if conv2 is None else bool(conv2),
        "steps": state["n"],
        "wall_time_s": round(time.time() - t0, 1),
    }


def frames_to_extxyz(frames: list[Atoms]) -> str:
    import io

    from ase.io import write

    buf = io.StringIO()
    write(buf, frames, format="extxyz")
    return buf.getvalue()


def model_available() -> bool:
    s = get_settings()
    return bool(s.mace_off_model) or any(p.exists() for p in _candidate_model_files())


def engines() -> list[dict]:
    return [{"key": e.key, "name": e.name, "version": e.version, "license": e.license, "citation": e.citation,
             "elements": list(e.elements), "available": model_available()} for e in ENGINES.values()]


__all__ = ["ENGINES", "RelaxError", "engines", "frames_to_extxyz", "pick_device", "relax", "Path"]
