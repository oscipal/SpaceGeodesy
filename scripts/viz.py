"""Shared pieces for the viewer (app/viewer.py) and the report figures (scripts/make_figures.py).

Colours (validated with the dataviz palette checker, light surface):
- LOS ascending / descending: blue / orange (pass all checks).
- Event locations: Svartsengi green, Fagradalsfjall violet, Sundhnukur red (pass; colour-blind
  separation 7.2, so event lines also carry the location initial as a second cue).
- Orange and red are too close to share a plot: panels with coloured LOS series draw event
  lines in grey; vertical / east series are drawn in neutral ink on their own panels.
Maps: cmcrameri vik (diverging, displacement and velocity), oslo (coherence).
"""
from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd
import xarray as xr

from common import ROOT, path

ASC, DESC = "#2a78d6", "#eb6834"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#9a9893"
EVENT_COLOURS = {"Svartsengi": "#008300", "Fagradalsfjall": "#6250d6", "Sundhnukur": "#e34948"}
EVENT_INITIAL = {"Svartsengi": "S", "Fagradalsfjall": "F", "Sundhnukur": "Su"}
EVENT_DASH = {"eruption": "solid", "dike": "dashed", "inflation onset": "dotted"}


def plain(s: str) -> str:
    """'Sundhnúkur' -> 'Sundhnukur' (events.csv and config use both spellings)."""
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()


def load_events(cfg) -> pd.DataFrame:
    ev = pd.read_csv(ROOT / cfg["postprocess"]["events_csv"], parse_dates=["date", "end_date"])
    ev["location"] = ev["location"].map(plain)
    return ev.sort_values("date").reset_index(drop=True)


def frames(cfg) -> dict[str, str]:
    fr = cfg["licsar"]["frames"]
    return {"asc": fr["ascending"], "desc": fr["descending"]}


def open_cubes(cfg) -> dict[str, xr.Dataset]:
    """Lazily opened Stage 4 cubes: 'asc', 'desc' (LOS) and 'dec' (vertical/east)."""
    cubes = path(cfg, "results") / "cubes"
    out = {k: xr.open_dataset(cubes / f"{f}_los.nc") for k, f in frames(cfg).items()}
    out["dec"] = xr.open_dataset(cubes / "decomp.nc")
    return out


def hgt(cfg) -> np.ndarray:
    """LiCSAR DEM heights (m) on the ascending grid (same grid as the decomposition)."""
    f = path(cfg, "results") / "licsbas" / frames(cfg)["asc"] / "results" / "hgt"
    ds = open_cubes(cfg)["asc"]
    z = np.fromfile(f, dtype=np.float32).reshape(ds.sizes["lat"], ds.sizes["lon"])
    return np.where(np.isfinite(z), z, 0)


_HS = {}


def hillshade(cfg) -> tuple[np.ndarray, list[float]]:
    """(hillshade 0..1, imshow extent) of the LiCSAR DEM on the ascending grid; cached."""
    if "hs" not in _HS:
        from matplotlib.colors import LightSource

        ds = open_cubes(cfg)["asc"]
        dy = abs(float(ds.lat[1] - ds.lat[0])) * 111_320
        dx = abs(float(ds.lon[1] - ds.lon[0])) * 111_320 * np.cos(np.radians(float(ds.lat.mean())))
        hs = LightSource(azdeg=315, altdeg=45).hillshade(hgt(cfg), vert_exag=3, dx=dx, dy=dy)
        # the DEM over the sea is ~100 m of noise (ellipsoidal heights): flat there (mean coherence < 0.12)
        coh = ds["coh_avg"].values
        hs = np.where(np.isfinite(coh) & (coh >= 0.12), hs, 0.3)   # sea: mid grey, distinct from 0 (white)
        _HS["hs"] = (hs, extent(ds))
    return _HS["hs"]


def extent(ds: xr.Dataset) -> list[float]:
    """imshow extent [left, right, bottom, top] for a (lat descending, lon ascending) grid."""
    dlat, dlon = float(ds.lat[1] - ds.lat[0]), float(ds.lon[1] - ds.lon[0])
    return [float(ds.lon[0]) - dlon / 2, float(ds.lon[-1]) + dlon / 2,
            float(ds.lat[-1]) + dlat / 2, float(ds.lat[0]) - dlat / 2]


def masked(ds: xr.Dataset, var: str, **sel) -> xr.DataArray:
    da = ds[var].isel(**sel) if sel else ds[var]
    return da.where(ds["mask"] > 0) if "mask" in ds else da


def window_series(ds: xr.Dataset, var: str, lat: float, lon: float, half: int = 1) -> pd.Series:
    """Mean over a (2 half + 1)^2 pixel window, as in Stage 4 (postprocess.window_mean)."""
    i = int(np.abs(ds.lat.values - lat).argmin())
    j = int(np.abs(ds.lon.values - lon).argmin())
    w = ds[var].isel(lat=slice(max(i - half, 0), i + half + 1), lon=slice(max(j - half, 0), j + half + 1))
    return w.mean(dim=("lat", "lon"), skipna=True).to_series()


def gnss_stations(cfg) -> list[dict]:
    """Stations written by Stage 6 (results/gnss/stations.csv): id, lat, lon, dist_km, first, last, role."""
    f = path(cfg, "results") / "gnss" / "stations.csv"
    if not f.exists():
        return []
    df = pd.read_csv(f, parse_dates=["first", "last"])
    return df.rename(columns={df.columns[0]: "id"}).to_dict("records")


def gnss_series(cfg) -> dict[str, pd.DataFrame]:
    """Stage 6 series results/gnss/<ID>.csv (relative to the reference station): date, east_mm,
    north_mm, up_mm, sig_*_mm, los_asc_mm, los_desc_mm. Nearest station first."""
    d = path(cfg, "results") / "gnss"
    st = sorted((s for s in gnss_stations(cfg) if s.get("role") != "reference"), key=lambda s: s["dist_km"])
    return {s["id"]: pd.read_csv(d / f"{s['id']}.csv", parse_dates=["date"], index_col="date")
            for s in st if (d / f"{s['id']}.csv").exists()}


CUM_VARS = (("asc", "cum"), ("desc", "cum"), ("dec", "up"), ("dec", "east"))
VEL_VARS = (("asc", "vel"), ("desc", "vel"), ("dec", "vel_up"), ("dec", "vel_east"))


def fixed_limits(cfg, cubes: dict, pct: float = 99.5) -> dict[str, float]:
    """One symmetric colour limit per unit, shared by every layer, date and animation frame.

    'mm': pct-th percentile of |vertical displacement since the first epoch| over all epochs
    (masked), rounded up to 100 mm (618 -> 700 mm). East-west and LOS reach > 1 m right at the
    dikes and saturate there on this scale; the uplift signal uses the full range.
    'mm/yr': pct-th percentile of |velocity| over the four velocity maps, rounded up to 10.
    Cached in results/cubes/colour_limits.json (recomputed when a cube is newer).
    """
    import json

    cache = path(cfg, "results") / "cubes" / "colour_limits.json"
    newest = max((path(cfg, "results") / "cubes").glob("*.nc"), key=lambda p: p.stat().st_mtime).stat().st_mtime
    if cache.exists() and cache.stat().st_mtime > newest:
        return json.loads(cache.read_text())
    d = cubes["dec"]
    up = d["up"].values
    up = np.abs(up - up[0])[:, d["mask"].values > 0]
    vel = np.concatenate([np.abs(cubes[c][v].values[cubes[c]["mask"].values > 0]) for c, v in VEL_VARS])
    out = {"mm": float(np.ceil(np.nanpercentile(up, pct) / 100) * 100),
           "mm/yr": float(np.ceil(np.nanpercentile(vel, pct) / 10) * 10)}
    cache.write_text(json.dumps(out))
    return out


def cropped(ds, region: dict | None):
    """isel slices of a (lat descending, lon ascending) grid for region {lat: (lo, hi), lon: (lo, hi)}."""
    if not region:
        return slice(None), slice(None)
    la, lo = ds.lat.values, ds.lon.values
    ys = np.where((la >= region["lat"][0]) & (la <= region["lat"][1]))[0]
    xs = np.where((lo >= region["lon"][0]) & (lo <= region["lon"][1]))[0]
    return slice(ys[0], ys[-1] + 1), slice(xs[0], xs[-1] + 1)


ZOOM = {"lon": (-22.62, -22.25), "lat": (63.80, 63.95)}   # Svartsengi - Sundhnukur - Grindavik


def sym_limit(a, pct=99, floor=10.0) -> float:
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    return float(max(floor, np.percentile(np.abs(a), pct))) if a.size else floor
