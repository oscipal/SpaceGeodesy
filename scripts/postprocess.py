"""Stage 4: derived products from the LiCSBAS time series.

1. Per frame: NetCDF cube results/cubes/<frame>_los.nc (time, lat, lon) with
   cum (unfiltered) and cum_filt in mm, plus vel, vel_filt, mask, coh_avg, vstd,
   E/N/U LOS unit vectors; GeoTIFFs of velocity, mask and cumulative
   displacement per epoch in results/geotiff/<frame>/.
   Sign: LOS displacement positive = towards the satellite (LiCSBAS convention).
2. Ascending/descending decomposition into vertical and east-west on the
   ascending grid and the descending epochs inside the ascending span (ascending
   linearly interpolated in time); north neglected. -> results/cubes/decomp.nc,
   GeoTIFFs of vertical/east velocity.
3. Point time series (uplift centre, GNSS stations, extra points from config)
   averaged over a window -> results/timeseries/<name>.csv.
4. Uplift per episode between consecutive events in config/events.csv at the
   uplift centre -> results/episodes.csv.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import xarray as xr

from common import load_config, path, update_notes


# ------------------------------------------------------------------ loading
def read_bin(f: Path, shape) -> np.ndarray | None:
    return np.fromfile(f, dtype="float32").reshape(shape) if f.exists() else None


def load_frame(cfg, frame: str) -> xr.Dataset:
    d = path(cfg, "results") / "licsbas" / frame
    with h5py.File(d / "cum.h5", "r") as h:
        cum = h["cum"][()]
        dates = pd.to_datetime([str(x) for x in h["imdates"][()]], format="%Y%m%d")
        lat0, lon0 = float(h["corner_lat"][()]), float(h["corner_lon"][()])
        dlat, dlon = float(h["post_lat"][()]), float(h["post_lon"][()])
        extra = {k: h[k][()] for k in ("vel", "coh_avg", "n_unw", "hgt", "E.geo", "N.geo", "U.geo") if k in h}
        ref = h["refarea"][()]
    with h5py.File(d / "cum_filt.h5", "r") as h:
        cum_f = h["cum"][()]
        vel_f = h["vel"][()]
    n, ny, nx = cum.shape
    lat = lat0 + dlat * np.arange(ny)
    lon = lon0 + dlon * np.arange(nx)
    mask = read_bin(d / "results" / "mask", (ny, nx))
    vstd = read_bin(d / "results" / "vstd", (ny, nx))
    ds = xr.Dataset(
        {
            "cum": (("time", "lat", "lon"), cum.astype("float32"),
                    {"units": "mm", "long_name": "cumulative LOS displacement (unfiltered), + towards satellite"}),
            "cum_filt": (("time", "lat", "lon"), cum_f.astype("float32"),
                         {"units": "mm", "long_name": "cumulative LOS displacement, LiCSBAS16 filtered"}),
            "vel": (("lat", "lon"), extra["vel"].astype("float32"), {"units": "mm/yr"}),
            "vel_filt": (("lat", "lon"), vel_f.astype("float32"), {"units": "mm/yr"}),
            "coh_avg": (("lat", "lon"), extra["coh_avg"].astype("float32")),
            "los_e": (("lat", "lon"), extra["E.geo"].astype("float32")),
            "los_n": (("lat", "lon"), extra["N.geo"].astype("float32")),
            "los_u": (("lat", "lon"), extra["U.geo"].astype("float32")),
        },
        coords={"time": dates, "lat": lat, "lon": lon},
        attrs={"frame": frame, "refarea_px": ref.decode() if isinstance(ref, bytes) else str(ref),
               "reference_point": json.dumps(cfg["licsbas"]["reference_point"]),
               "source": "LiCSAR/LiCSBAS, see docs/processing_notes.md"},
    )
    if mask is not None:
        ds["mask"] = (("lat", "lon"), (np.isfinite(mask) & (mask > 0)).astype("uint8"),
                      {"long_name": "LiCSBAS15 mask, 1 = valid"})
    if vstd is not None:
        ds["vstd"] = (("lat", "lon"), vstd, {"units": "mm/yr"})
    return ds


# ---------------------------------------------------------------- geotiffs
def write_tif(f: Path, da: xr.DataArray) -> None:
    import rioxarray  # noqa: F401  (registers .rio)

    da = da.rename({"lat": "y", "lon": "x"}).rio.write_crs("EPSG:4326")
    da = da.rio.write_nodata(np.nan) if da.dtype.kind == "f" else da
    f.parent.mkdir(parents=True, exist_ok=True)
    da.rio.to_raster(f, compress="DEFLATE")


def export_geotiffs(cfg, ds: xr.Dataset, name: str) -> int:
    out = path(cfg, "results") / "geotiff" / name
    n = 0
    for v in ("vel", "vel_filt", "coh_avg", "mask", "vstd"):
        if v in ds:
            write_tif(out / f"{v}.tif", ds[v])
            n += 1
    for t in ds.time.values:
        s = pd.Timestamp(t).strftime("%Y%m%d")
        write_tif(out / "cum" / f"cum_{s}.tif", ds["cum"].sel(time=t))
        n += 1
    return n


# ------------------------------------------------------------ decomposition
def abrupt_events(cfg) -> pd.DatetimeIndex:
    """Dates of dikes and eruptions (abrupt displacement), from config/events.csv."""
    ev = pd.read_csv(path(cfg, "results").parent / cfg["postprocess"]["events_csv"], parse_dates=["date"])
    return pd.DatetimeIndex(sorted(ev.loc[ev.type.isin(["dike", "eruption"]), "date"]))


def event_aware_weights(ta: pd.DatetimeIndex, td: pd.DatetimeIndex, events: pd.DatetimeIndex, max_gap_days=24):
    """Indices and weights to bring ascending epochs ta to descending dates td without mixing
    acquisitions from before and after a dike or eruption.

    Within one interval between events: linear interpolation between the bracketing ascending
    epochs, or linear extrapolation from the two nearest ones when the descending date lies beyond
    the last (or before the first) ascending epoch of that interval; one epoch only: nearest.
    An acquisition on the day of an event counts as before it (most events started in the
    afternoon or evening; times are not used). Plain linear interpolation across events put part of
    each co-eruptive drop into the first epoch after it and biased the episode uplift low.
    Dates without an ascending epoch of the same interval within max_gap_days get w = nan.
    """
    seg = lambda t: np.searchsorted(events.values, t.normalize().values, side="left")  # noqa: E731
    sa, sd = seg(ta), seg(td)
    i0 = np.zeros(len(td), int)
    i1 = np.zeros(len(td), int)
    w = np.full(len(td), np.nan)
    for k, (t, s) in enumerate(zip(td, sd)):
        idx = np.where(sa == s)[0]
        if not len(idx) or np.min(np.abs((ta[idx] - t).days)) > max_gap_days:
            continue
        before, after = idx[ta[idx] <= t], idx[ta[idx] >= t]
        if len(before) and len(after):
            p, q = before[-1], after[0]
        elif len(idx) >= 2:
            p, q = (idx[-2], idx[-1]) if len(before) else (idx[0], idx[1])
        else:
            i0[k] = i1[k] = idx[0]
            w[k] = 0.0
            continue
        span = (ta[q] - ta[p]).days
        i0[k], i1[k] = p, q
        w[k] = 0.0 if span == 0 else (t - ta[p]).days / span
    return i0, i1, w


def decompose(cfg, asc: xr.Dataset, desc: xr.Dataset) -> xr.Dataset:
    """Solve los_a = e_a*E + u_a*U, los_d = e_d*E + u_d*U per pixel (north neglected)."""
    # common grid: ascending; descending interpolated (both are 0.001 deg LiCSAR grids)
    d = desc.interp(lat=asc.lat, lon=asc.lon, method="nearest",
                    kwargs={"fill_value": np.nan})
    off = max(float(np.abs(desc.lat.values[:, None] - asc.lat.values[None, :]).min(axis=0).max()),
              float(np.abs(desc.lon.values[:, None] - asc.lon.values[None, :]).min(axis=0).max()))
    # common dates: descending epochs within the ascending span; ascending interpolated in time
    t = d.time.where((d.time >= asc.time[0]) & (d.time <= asc.time[-1]), drop=True)
    d = d.sel(time=t)
    out = {}
    i0, i1, w = event_aware_weights(pd.to_datetime(asc.time.values), pd.to_datetime(t.values), abrupt_events(cfg))
    for var, sfx in (("cum", ""), ("cum_filt", "_filt")):
        av = asc[var].values
        a = xr.DataArray(av[i0] * (1 - w)[:, None, None] + av[i1] * w[:, None, None],
                         coords={"time": t.values, "lat": asc.lat, "lon": asc.lon}, dims=("time", "lat", "lon"))
        # re-zero both at the first common epoch
        la = (a - a.isel(time=0)).values
        ld = (d[var] - d[var].isel(time=0)).values
        ea, ua = asc.los_e.values, asc.los_u.values
        ed, ud = d.los_e.values, d.los_u.values
        det = ea * ud - ed * ua
        det = np.where(np.abs(det) > 1e-3, det, np.nan)
        east = (la * ud - ld * ua) / det
        up = (ea * ld - ed * la) / det
        note = " (from LiCSBAS16-filtered LOS)" if sfx else " (unfiltered)"
        out[f"up{sfx}"] = (("time", "lat", "lon"), up.astype("float32"),
                           {"units": "mm", "long_name": "vertical displacement" + note})
        out[f"east{sfx}"] = (("time", "lat", "lon"), east.astype("float32"),
                             {"units": "mm", "long_name": "east displacement" + note})
    ds = xr.Dataset(out, coords={"time": t.values, "lat": asc.lat, "lon": asc.lon})
    ma = np.nan_to_num(asc["mask"].values) if "mask" in asc else 1
    md = np.nan_to_num(d["mask"].values) if "mask" in d else 1
    ds["mask"] = (("lat", "lon"), ((ma > 0) & (md > 0)).astype("uint8"),
                  {"long_name": "valid in both frames' LiCSBAS15 masks"})
    # velocities over the common period by linear least squares
    yrs = (pd.to_datetime(ds.time.values) - pd.to_datetime(ds.time.values[0])).days.values / 365.25
    G = np.vstack([yrs, np.ones_like(yrs)]).T
    for v in ("up", "east"):
        y = ds[v].values.reshape(len(yrs), -1)
        ok = np.isfinite(y).all(axis=0)
        vel = np.full(y.shape[1], np.nan, "float32")
        if ok.any():
            vel[ok] = np.linalg.lstsq(G, y[:, ok], rcond=None)[0][0]
        ds[f"vel_{v}"] = (("lat", "lon"), vel.reshape(ds.lat.size, ds.lon.size), {"units": "mm/yr"})
    ds.attrs = {"method": "2-geometry LOS decomposition, north component neglected; descending grid "
                f"matched to ascending by nearest pixel (max offset {off:.6f} deg); ascending interpolated "
                "linearly in time to the descending epochs; both re-zeroed at the first common epoch",
                "period": f"{pd.Timestamp(ds.time.values[0]).date()} to {pd.Timestamp(ds.time.values[-1]).date()}"}
    return ds


# -------------------------------------------------------- point time series
def window_mean(da: xr.DataArray, lat, lon, half: int) -> xr.DataArray:
    i = int(np.abs(da.lat.values - lat).argmin())
    j = int(np.abs(da.lon.values - lon).argmin())
    w = da.isel(lat=slice(max(i - half, 0), i + half + 1), lon=slice(max(j - half, 0), j + half + 1))
    return w.mean(dim=("lat", "lon"), skipna=True)


def points(cfg) -> list[dict]:
    pts = [{"name": "svartsengi_uplift_centre", **cfg["sites"]["svartsengi_uplift_centre"], "kind": "site"}]
    for s in cfg["gnss"].get("stations") or []:
        if isinstance(s, dict) and "lat" in s:
            pts.append({"name": f"gnss_{s['id']}", "lat": s["lat"], "lon": s["lon"], "kind": "gnss"})
    for p in cfg["postprocess"].get("extra_points") or []:
        pts.append({**p, "kind": "extra"})
    return pts


def point_series(cfg, frames: dict, dec: xr.Dataset | None) -> list[Path]:
    half = cfg["postprocess"]["ts_window_px"] // 2
    out = path(cfg, "results") / "timeseries"
    out.mkdir(exist_ok=True)
    files = []
    for p in points(cfg):
        cols = []
        for geom, ds in frames.items():
            for v in ("cum", "cum_filt"):
                s = window_mean(ds[v], p["lat"], p["lon"], half).to_series()
                cols.append(s.rename(f"los_{geom}{'_filt' if v.endswith('filt') else ''}_mm"))
        if dec is not None:
            for v in ("up", "up_filt", "east", "east_filt"):
                cols.append(window_mean(dec[v], p["lat"], p["lon"], half).to_series().rename(f"{v}_mm"))
        df = pd.concat(cols, axis=1).sort_index()
        df.index.name = "date"
        f = out / f"{p['name']}.csv"
        df.to_csv(f, float_format="%.2f")
        files.append(f)
    return files


# ------------------------------------------------------------------ episodes
def episodes(cfg, centre_csv: Path) -> pd.DataFrame:
    ev = pd.read_csv(path(cfg, "results").parent / cfg["postprocess"]["events_csv"], parse_dates=["date"])
    ev = ev.sort_values("date").reset_index(drop=True)
    ts = pd.read_csv(centre_csv, parse_dates=["date"], index_col="date")
    rows = []
    for k in range(len(ev) - 1):
        t0, t1 = ev.loc[k, "date"], ev.loc[k + 1, "date"]
        for col, label in (("up_mm", "vertical"), ("los_asc_mm", "LOS asc"), ("los_desc_mm", "LOS desc")):
            if col not in ts:
                continue
            s = ts[col].dropna()
            # first acquisition after the event day, last one before the next event day
            a = s[s.index > t0]
            b = s[s.index < t1]
            if a.empty or b.empty or a.index[0] >= b.index[-1]:
                continue
            ta, tb = a.index[0], b.index[-1]
            d = float(b.iloc[-1] - a.iloc[0])
            days = (tb - ta).days
            rows.append({"episode": k + 1, "start_event": f"{t0.date()} {ev.loc[k, 'type']} ({ev.loc[k, 'location']})",
                         "end_event": f"{t1.date()} {ev.loc[k + 1, 'type']} ({ev.loc[k + 1, 'location']})",
                         "component": label, "first_epoch": ta.date(), "last_epoch": tb.date(), "days": days,
                         "displacement_mm": round(d, 1),
                         "rate_mm_per_day": round(d / days, 2) if days > 0 else np.nan})
    df = pd.DataFrame(rows)
    df.to_csv(path(cfg, "results") / "episodes.csv", index=False)
    return df


# ---------------------------------------------------------------------- main
def main() -> int:
    cfg = load_config()
    fr = cfg["licsar"]["frames"]
    frames = {"asc": load_frame(cfg, fr["ascending"]), "desc": load_frame(cfg, fr["descending"])}
    cubes = path(cfg, "results") / "cubes"
    cubes.mkdir(exist_ok=True)
    enc = lambda ds: {v: {"zlib": True, "complevel": 4} for v in ds.data_vars}  # noqa: E731
    n_tif = 0
    for geom, ds in frames.items():
        ds.to_netcdf(cubes / f"{ds.attrs['frame']}_los.nc", encoding=enc(ds))
        n_tif += export_geotiffs(cfg, ds, ds.attrs["frame"])
        print(f"{geom}: {ds.sizes['time']} epochs, cube + GeoTIFFs written", flush=True)
    dec = decompose(cfg, frames["asc"], frames["desc"])
    dec.to_netcdf(cubes / "decomp.nc", encoding=enc(dec))
    for v in ("vel_up", "vel_east", "mask"):
        write_tif(path(cfg, "results") / "geotiff" / "decomp" / f"{v}.tif", dec[v])
    print(f"decomposition: {dec.sizes['time']} common epochs, {dec.attrs['period']}", flush=True)
    files = point_series(cfg, frames, dec)
    centre = next(f for f in files if f.stem == "svartsengi_uplift_centre")
    ep = episodes(cfg, centre)
    print(f"{len(files)} point time series, {len(ep)} episode rows", flush=True)

    vert = ep[ep.component == "vertical"]
    L = ["## Stage 4: derived products", "",
         f"Generated by `scripts/postprocess.py` on {dt.date.today()}.", "",
         f"- LOS cubes: `results/cubes/<frame>_los.nc`; GeoTIFFs: `results/geotiff/<frame>/` ({n_tif} files).",
         f"- Decomposition (`results/cubes/decomp.nc`): {dec.attrs['method']}. Period {dec.attrs['period']}, "
         f"{dec.sizes['time']} epochs. Valid (both masks) fraction "
         f"{float(dec['mask'].mean()):.3f}.",
         f"- Point time series ({cfg['postprocess']['ts_window_px']}x{cfg['postprocess']['ts_window_px']} px "
         f"mean): {', '.join(f.stem for f in files)} in `results/timeseries/`.",
         f"- Episodes at the uplift centre: `results/episodes.csv` ({len(vert)} vertical, {len(ep) - len(vert)} "
         "LOS rows). Displacement between the first acquisition after an event and the last before the next "
         "event, from unfiltered cum.", ""]
    if not vert.empty:
        L += ["| Episode | from | to | days | vertical (mm) | mm/day |", "|---|---|---|---|---|---|"]
        for _, r in vert.iterrows():
            L.append(f"| {r.episode} | {r.start_event} | {r.end_event} | {r.days} | {r.displacement_mm} | "
                     f"{r.rate_mm_per_day} |")
    update_notes(cfg, "postprocess", "\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
