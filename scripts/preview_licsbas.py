"""Low-resolution dry run of Stage 3 to check the processing before the full run finishes.

Runs the same LiCSBAS chain as scripts/run_licsbas.py (same thresholds, GACOS, network and
reference point) but multilooked 5x5 (~250 m x 550 m pixels instead of ~50 m x 110 m), so it
takes hours instead of days. Work dir: $LICSBAS_WORK/preview/<frame>, with GEOC/GACOS linked to
the main work dirs (no copy). Nothing in results/licsbas is touched.

Figures (figures/preview/):
  vel_<frame>.png        LOS velocity map
  cum_<frame>.png        cumulative LOS displacement over selected intervals
  ts_uplift_centre.png   LOS time series at the uplift centre, asc + desc, with events

Usage: LICSBAS_WORK=/vol python scripts/preview_licsbas.py [--plots-only]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import xarray as xr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from cmcrameri import cm as cmc

import run_licsbas as R
from common import load_config, path

NLOOK = 5
EVENT_COLOURS = {"Svartsengi": "#2a7f62", "Fagradalsfjall": "#7a5195", "Sundhnukur": "#c0392b", "Sundhnúkur": "#c0392b"}


def preview_cfg():
    cfg = load_config()
    lb = cfg["licsbas"]
    lb["n_look"] = NLOOK
    lb["n_para"] = 1
    lb["mem_size_mb"] = 40           # small patches: keeps step 13 well under 1 GB
    return cfg


def run_frame(cfg, frame: str, base: Path) -> Path:
    prev = base / "preview"
    wd = prev / frame
    wd.mkdir(parents=True, exist_ok=True)
    for sub in ("GEOC", "GACOS"):
        if not (wd / sub).exists():
            (wd / sub).symlink_to(base / frame / sub)
    os.environ["LICSBAS_WORK"] = str(prev)       # R.workdir() -> prev/<frame>
    ts = wd / f"TS_{R.geocml(cfg)}"
    log = path(cfg, "logs") / f"preview_{frame}.log"
    if not (ts / "info" / "11bad_ifg.txt").exists():
        R.run(["bash", R.write_batch(cfg, wd, "02", "11").name], wd, log)
        (wd / ".phaseA").write_text("preview")
    rp = dict(cfg["licsbas"]["reference_point"], window_px=1)   # one 5x5-multilooked pixel
    if not (ts / "cum_filt.h5").exists():
        R.phase_b(cfg, frame, rp)
    os.environ["LICSBAS_WORK"] = str(base)
    return ts


# ------------------------------------------------------------------ plotting
def load_ts(ts: Path, rp: dict):
    with h5py.File(ts / "cum.h5", "r") as h:
        cum = h["cum"][()]
        dates = pd.to_datetime([str(x) for x in h["imdates"][()]], format="%Y%m%d")
        lat0, lon0 = float(h["corner_lat"][()]), float(h["corner_lon"][()])
        dlat, dlon = float(h["post_lat"][()]), float(h["post_lon"][()])
        vel = h["vel"][()]
        los = {k: h[f"{k.upper()}.geo"][()] for k in ("e", "n", "u")}
    mask_f = ts / "results" / "mask"
    mask = np.fromfile(mask_f, dtype="float32").reshape(vel.shape) if mask_f.exists() else np.ones_like(vel)
    mask = np.where(mask == 0, np.nan, 1.0)
    r = int(round((rp["lat"] - lat0) / dlat))
    c = int(round((rp["lon"] - lon0) / dlon))
    cum = cum - np.nanmean(cum[:, r - 1:r + 2, c - 1:c + 2], axis=(1, 2))[:, None, None]  # Straumsvik, as the full run
    vel = vel - np.nanmean(vel[r - 1:r + 2, c - 1:c + 2])
    ny, nx = vel.shape
    extent = [lon0 - dlon / 2, lon0 + dlon * (nx - 0.5), lat0 + dlat * (ny - 0.5), lat0 - dlat / 2]
    return dict(cum=cum, dates=dates, vel=vel, mask=mask, los=los, lat0=lat0, lon0=lon0, dlat=dlat, dlon=dlon,
                extent=extent)


def rc(d, lat, lon):
    return int(round((lat - d["lat0"]) / d["dlat"])), int(round((lon - d["lon0"]) / d["dlon"]))


def mark_sites(ax, cfg):
    s, rp = cfg["sites"], cfg["licsbas"]["reference_point"]
    ax.plot(s["svartsengi_uplift_centre"]["lon"], s["svartsengi_uplift_centre"]["lat"], "k+", ms=9, mew=1.5)
    ax.plot(s["grindavik"]["lon"], s["grindavik"]["lat"], "ko", ms=4, mfc="w")
    ax.plot(rp["lon"], rp["lat"], "ks", ms=6, mfc="none", mew=1.5)
    ax.set_aspect(1 / np.cos(np.radians(63.9)))
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")


def nearest(dates, day):
    return int(np.argmin(np.abs(dates - pd.Timestamp(day))))


def plot_frame(cfg, frame, d, out):
    geom = "ascending" if "A_" in frame else "descending"
    v = d["vel"] * d["mask"]
    lim = np.nanpercentile(np.abs(v), 99)
    fig, ax = plt.subplots(figsize=(7, 5.5))
    im = ax.imshow(v, extent=d["extent"], cmap=cmc.vik, vmin=-lim, vmax=lim, interpolation="nearest")
    mark_sites(ax, cfg)
    fig.colorbar(im, ax=ax, shrink=0.8, label="LOS velocity (mm/yr), + towards satellite")
    ax.set_title(f"Preview ({NLOOK}x{NLOOK} looks): mean LOS velocity, {geom} {frame}\n"
                 f"{d['dates'][0].date()} to {d['dates'][-1].date()}, ref. Straumsvik (square)", fontsize=10)
    fig.tight_layout()
    fig.savefig(out / f"vel_{frame}.png", dpi=130)
    plt.close(fig)

    intervals = [("2020-01-01", "2021-02-20", "2020 inflation"),
                 ("2023-10-20", "2023-11-15", "Oct-Nov 2023 incl. dike"),
                 ("2024-04-05", "2024-05-27", "inflation Apr-May 2024"),
                 ("2023-10-01", "2026-12-31", "Oct 2023 to latest")]
    fig, axs = plt.subplots(2, 2, figsize=(11, 8.5))
    for ax, (a, b, title) in zip(axs.flat, intervals):
        i, j = nearest(d["dates"], a), nearest(d["dates"], b)
        if j <= i:
            ax.set_axis_off()
            continue
        dd = (d["cum"][j] - d["cum"][i]) * d["mask"]
        lim = max(10, np.nanpercentile(np.abs(dd), 99))
        im = ax.imshow(dd, extent=d["extent"], cmap=cmc.vik, vmin=-lim, vmax=lim, interpolation="nearest")
        mark_sites(ax, cfg)
        fig.colorbar(im, ax=ax, shrink=0.8, label="LOS (mm)")
        ax.set_title(f"{title}\n{d['dates'][i].date()} to {d['dates'][j].date()}", fontsize=10)
    fig.suptitle(f"Preview: cumulative LOS displacement, {geom} {frame}", fontsize=11)
    fig.tight_layout()
    fig.savefig(out / f"cum_{frame}.png", dpi=120)
    plt.close(fig)


def plot_centre(cfg, data, out):
    c = cfg["sites"]["svartsengi_uplift_centre"]
    ev = pd.read_csv(Path(__file__).resolve().parents[1] / cfg["postprocess"]["events_csv"], parse_dates=["date"])
    fig, ax = plt.subplots(figsize=(11, 4.8))
    for _, e in ev.iterrows():
        ax.axvline(e["date"], color=EVENT_COLOURS.get(e["location"], "grey"),
                   lw=0.8, alpha=0.6, ls="-" if e["type"] == "eruption" else "--")
    for frame, d in data.items():
        r, k = rc(d, c["lat"], c["lon"])
        s = d["cum"][:, r - 1:r + 2, k - 1:k + 2].reshape(len(d["dates"]), -1)
        s = np.nanmean(s, axis=1)
        s = s - s[0]
        lab = "ascending LOS" if "A_" in frame else "descending LOS"
        ax.plot(d["dates"], s, ".-", ms=3, lw=0.8, label=f"{lab} ({frame})")
    for loc, col in (("Svartsengi", "#2a7f62"), ("Fagradalsfjall", "#7a5195"), ("Sundhnúkur", "#c0392b")):
        ax.plot([], [], color=col, lw=1, label=f"events: {loc} (solid = eruption, dashed = dike/onset)")
    ax.set_ylabel("Cumulative LOS displacement (mm), + towards satellite")
    ax.set_title(f"Preview: uplift centre {c['lat']} N, {abs(c['lon'])} W (3x3 multilooked pixels), "
                 "unfiltered, ref. Straumsvik", fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(out / "ts_uplift_centre.png", dpi=130)
    plt.close(fig)


# ------------------------------------------------------------ decomposition
def to_ds(d) -> xr.Dataset:
    """Preview frame as the Dataset layout postprocess.decompose expects (cum_filt = cum here)."""
    ny, nx = d["vel"].shape
    v2 = ("lat", "lon")
    return xr.Dataset(
        {"cum": (("time", "lat", "lon"), d["cum"]), "cum_filt": (("time", "lat", "lon"), d["cum"]),
         "los_e": (v2, d["los"]["e"]), "los_n": (v2, d["los"]["n"]), "los_u": (v2, d["los"]["u"]),
         "mask": (v2, np.nan_to_num(d["mask"]))},
        coords={"time": d["dates"], "lat": d["lat0"] + d["dlat"] * np.arange(ny),
                "lon": d["lon0"] + d["dlon"] * np.arange(nx)})


def smooth3(a):
    p = np.pad(a, 1, constant_values=np.nan)
    st = np.stack([p[i:i + a.shape[0], j:j + a.shape[1]] for i in range(3) for j in range(3)])
    with np.errstate(all="ignore"):
        return np.nanmean(st, axis=0)


def peak(dec, a, b, box):
    """Location of the largest 3x3-smoothed uplift between the dates a and b inside box."""
    t = pd.to_datetime(dec.time.values)
    i, j = nearest(t, a), nearest(t, b)
    du = smooth3(((dec.up[j] - dec.up[i]) * dec["mask"].where(dec["mask"] > 0)).values)
    lat, lon = dec.lat.values[:, None], dec.lon.values[None, :]
    inside = (lat >= box[0]) & (lat <= box[1]) & (lon >= box[2]) & (lon <= box[3])
    k = np.unravel_index(np.nanargmax(np.where(inside, du, np.nan)), du.shape)
    return float(dec.lat[k[0]]), float(dec.lon[k[1]]), float(du[k]), t[i], t[j]


def plot_decomp(cfg, data, out):
    import postprocess as P
    fa, fd = (next(f for f in data if s in f) for s in ("A_", "D_"))
    dec = P.decompose(cfg, to_ds(data[fa]), to_ds(data[fd]))
    t = pd.to_datetime(dec.time.values)
    box = (63.84, 63.92, -22.58, -22.40)       # Svartsengi, west of the Sundhnukur dike line
    peaks = {name: peak(dec, a, b, box) for name, a, b in
             (("2020", "2020-01-01", "2021-02-20"), ("Jun-Aug 2024", "2024-06-01", "2024-08-15"),
              ("Dec 2024-Mar 2025", "2024-12-10", "2025-03-30"))}
    for name, (la, lo, du, ta, tb) in peaks.items():
        print(f"uplift peak {name} ({ta.date()} to {tb.date()}): {la:.4f} N {lo:.4f} E, {du:.0f} mm", flush=True)
    old = cfg["sites"]["svartsengi_uplift_centre"]
    new = {"lat": round(np.mean([p[0] for p in peaks.values()]), 3),
           "lon": round(np.mean([p[1] for p in peaks.values()]), 3)}
    print(f"mean peak: {new}  (config: {old})", flush=True)

    m = dec["mask"].where(dec["mask"] > 0)
    i0, i1 = nearest(t, "2024-06-01"), nearest(t, "2024-08-15")
    j0, j1 = nearest(t, "2023-10-01"), len(t) - 1
    fig, axs = plt.subplots(2, 2, figsize=(11, 8.5))
    for ax, (var, a, b) in zip(axs.flat, (("up", i0, i1), ("east", i0, i1), ("up", j0, j1), ("east", j0, j1))):
        dd = ((dec[var][b] - dec[var][a]) * m).values
        lim = max(10, np.nanpercentile(np.abs(dd), 99))
        im = ax.imshow(dd, extent=data[fa]["extent"], cmap=cmc.vik, vmin=-lim, vmax=lim, interpolation="nearest")
        mark_sites(ax, cfg)
        ax.plot(new["lon"], new["lat"], "x", color="m", ms=9, mew=2)
        fig.colorbar(im, ax=ax, shrink=0.8, label=f"{'vertical (+ up)' if var == 'up' else 'east (+ east)'} (mm)")
        ax.set_title(f"{var}: {t[a].date()} to {t[b].date()}", fontsize=10)
    fig.suptitle("Preview: asc/desc decomposition (north neglected); + = config centre, x = uplift peak", fontsize=11)
    fig.tight_layout()
    fig.savefig(out / "decomp_maps.png", dpi=120)
    plt.close(fig)

    ev = pd.read_csv(Path(__file__).resolve().parents[1] / cfg["postprocess"]["events_csv"], parse_dates=["date"])
    fig, axs = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True)
    for ax, var in zip(axs, ("up", "east")):
        for _, e in ev.iterrows():
            ax.axvline(e["date"], color=EVENT_COLOURS.get(e["location"], "grey"), lw=0.8, alpha=0.5,
                       ls="-" if e["type"] == "eruption" else "--")
        for lab, p in ((f"config centre {old['lat']}, {old['lon']}", old), (f"uplift peak {new['lat']}, {new['lon']}", new)):
            s = P.window_mean(dec[var].where(m > 0), p["lat"], p["lon"], 1).values
            ax.plot(t, s - s[0], ".-", ms=3, lw=0.8, label=lab)
        ax.set_ylabel(f"{'vertical, + up' if var == 'up' else 'east, + east'} (mm)")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="upper left")
    axs[0].set_title(f"Preview: decomposed displacement, 3x3 multilooked pixels, {t[0].date()} to {t[-1].date()}",
                     fontsize=10)
    fig.tight_layout()
    fig.savefig(out / "decomp_ts.png", dpi=130)
    plt.close(fig)

    # uplift and drop per Sundhnukur cycle at the peak
    s = P.window_mean(dec.up.where(m > 0), new["lat"], new["lon"], 1).to_series()
    er = ev[(ev["type"] == "eruption") & ev["location"].str.startswith("Sundhn")]["date"].sort_values().tolist()
    print("eruption     uplift since previous eruption  drop at eruption (mm)", flush=True)
    for prev, cur in zip(er[:-1], er[1:]):
        after_prev, before = s[s.index > prev], s[s.index < cur]
        after = s[s.index > cur]
        if len(after_prev) and len(before) and len(after):
            print(f"{cur.date()}   {before.iloc[-1] - after_prev.iloc[0]:8.0f}   {after.iloc[0] - before.iloc[-1]:8.0f}"
                  f"   (epochs {before.index[-1].date()} / {after.index[0].date()})", flush=True)


def main() -> int:
    cfg = preview_cfg()
    base = Path(os.environ.get("LICSBAS_WORK", ""))
    if not base.name:
        sys.exit("set LICSBAS_WORK (the main LiCSBAS work dir)")
    frames = [f for f in cfg["licsar"]["frames"].values() if f]
    out = Path(__file__).resolve().parents[1] / "figures" / "preview"
    out.mkdir(parents=True, exist_ok=True)
    data = {}
    for frame in frames:
        ts = base / "preview" / frame / f"TS_{R.geocml(cfg)}"
        if "--plots-only" not in sys.argv:
            ts = run_frame(cfg, frame, base)
        if (ts / "cum.h5").exists():
            data[frame] = load_ts(ts, cfg["licsbas"]["reference_point"])
            plot_frame(cfg, frame, data[frame], out)
            print(f"[{frame}] preview figures written", flush=True)
    if data:
        plot_centre(cfg, data, out)
    if len(data) == 2:
        plot_decomp(cfg, data, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
