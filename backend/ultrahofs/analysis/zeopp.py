"""Zeo++ wrapper: pore diameters, accessible surface area/volume, channel dimensionality."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ..config import get_settings

N2_PROBE = 1.86


def zeopp_available() -> bool:
    return shutil.which(get_settings().zeopp_binary) is not None


def _run(args: list[str], cwd: Path, timeout: int) -> None:
    proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"zeo++ failed: {proc.stderr[-500:] or proc.stdout[-500:]}")


def _kv(text: str) -> dict[str, float]:
    out = {}
    for key, val in re.findall(r"([A-Za-z_^0-9/]+):\s+([-0-9.eE+]+)", text):
        try:
            out[key] = float(val)
        except ValueError:
            pass
    return out


def analyze_cif(cif_text: str, probe: float = 1.2, sa_probe: float = N2_PROBE, samples_sa: int = 2000,
                samples_vol: int = 20000, timeout: int = 300) -> dict:
    """Run Zeo++ on a (P1) CIF string.

    Channels / accessible volume use ``probe`` (default 1.2 Å, small gases); the surface area uses
    ``sa_probe`` (default N2, 1.86 Å) to resemble BET-type comparisons.
    """
    exe = shutil.which(get_settings().zeopp_binary)
    if exe is None:
        raise RuntimeError("Zeo++ 'network' binary not found")
    with tempfile.TemporaryDirectory(prefix="zeopp_") as tmp:
        d = Path(tmp)
        (d / "s.cif").write_text(cif_text)
        _run([exe, "-ha", "-res", "s.res", "s.cif"], d, timeout)
        _run([exe, "-ha", "-chan", str(probe), "s.chan", "s.cif"], d, timeout)
        _run([exe, "-ha", "-sa", str(sa_probe), str(sa_probe), str(samples_sa), "s.sa", "s.cif"], d, timeout)
        _run([exe, "-ha", "-vol", str(probe), str(probe), str(samples_vol), "s.vol", "s.cif"], d, timeout)
        _run([exe, "-ha", "-vol", "0", "0", str(samples_vol), "s0.vol", "s.cif"], d, timeout)
        res = (d / "s.res").read_text().split()
        chan = (d / "s.chan").read_text()
        sa = _kv((d / "s.sa").read_text().splitlines()[0])
        vol = _kv((d / "s.vol").read_text().splitlines()[0])
        vol0 = _kv((d / "s0.vol").read_text().splitlines()[0])
    m = re.search(r"(\d+)\s+channels identified of dimensionality\s*([\d\s]*)", chan)
    n_chan = int(m.group(1)) if m else 0
    chan_dims = [int(x) for x in m.group(2).split()] if m and m.group(2).strip() else []
    return {
        "probe_radius_A": probe,
        "sa_probe_radius_A": sa_probe,
        "lcd_A": float(res[1]),
        "pld_A": float(res[2]),
        "lcd_free_path_A": float(res[3]),
        "n_channels": n_chan,
        "channel_dimensionality": max(chan_dims) if chan_dims else 0,
        "density_g_cm3": sa.get("Density"),
        "asa_m2_g": sa.get("ASA_m^2/g"),
        "asa_m2_cm3": sa.get("ASA_m^2/cm^3"),
        "accessible_volume_fraction": vol.get("AV_Volume_fraction"),
        "accessible_volume_cm3_g": vol.get("AV_cm^3/g"),
        "void_fraction_geometric": vol0.get("AV_Volume_fraction"),
        "cell_volume_A3": sa.get("Unitcell_volume"),
    }


def porous_verdict(metrics: dict, probe: float = 1.2) -> str:
    """'yes' if a probe of the given radius percolates through a channel (PLD >= 2*probe)."""
    pld = metrics.get("pld_A") or 0.0
    return "yes" if pld >= 2 * probe and metrics.get("channel_dimensionality", 0) >= 1 else "no"
