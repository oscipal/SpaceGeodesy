"""Stage 7: uplift rates per cycle (GNSS and InSAR) and stability of the uplift pattern.

Answers research questions (1) and (3) of the research plan (docs/spacegeodesy_research_plan.pdf):
(1) how the uplift rate changed across the inflation cycles since October 2023 and during the
    current pause, from GNSS and InSAR;
(3) whether the spatial pattern of uplift stayed stable between cycles.
Everything is descriptive: no source model, no conversion to volume.

Rates. A period runs from 2 days after one dike or eruption to 1 day before the next (the
deflation itself takes hours to days). Its rate is the slope of a straight line fitted to all
GNSS days or InSAR epochs inside it. 1-sigma from the residuals, inflated by sqrt((1+r)/(1-r)) for
the lag-1 autocorrelation r of the residuals (uplift within a period is not exactly linear, and
daily GNSS noise is correlated). The current pause (no eruption since the end of the July 2025
eruption) is additionally split into windows of `pause_window_days`, to see whether the rate still
falls. Output: results/cycles/rates.csv, results/cycles/pause_rates.csv.

Pattern. For each inflation cycle, the vertical displacement map (first to last InSAR epoch of the
cycle, decomposition) within `fit_radius_km` of the uplift centre is fitted with an elliptical
Gaussian surface plus a constant. Its centre gives the location of the uplift, its axes the extent
(half maximum ellipse). The fit errors are inflated for spatially correlated noise: the residual
correlation length L is measured from the residual map itself, and the number of independent
pixels is taken as area / (pi L^2). The shape is compared by the correlation coefficient between
each cycle's map and the mean amplitude-normalised map of the other cycles since 2023.
Output: results/cycles/pattern.csv. Summary of both in docs/processing_notes.md.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

import viz
from common import load_config, path, update_notes

KM_LAT = 111.32


# ----------------------------------------------------------------------------- rates
def linrate(t: pd.DatetimeIndex, y: np.ndarray) -> tuple[float, float, int]:
    """Slope (mm/day), 1-sigma corrected for lag-1 autocorrelation of the residuals, n."""
    ok = np.isfinite(y)
    t, y = t[ok], np.asarray(y)[ok]
    n = len(y)
    if n < 4:
        return np.nan, np.nan, n
    d = (t - t[0]).days.values.astype(float)
    A = np.column_stack([np.ones(n), d])
    x, *_ = np.linalg.lstsq(A, y, rcond=None)
    res = y - A @ x
    s2 = res @ res / (n - 2)
    sig = float(np.sqrt(s2 * np.linalg.inv(A.T @ A)[1, 1]))
    r = float(np.corrcoef(res[:-1], res[1:])[0, 1]) if n > 4 and res.std() > 0 else 0.0
    if np.isfinite(r) and r > 0:
        sig *= np.sqrt((1 + r) / (1 - r))
    return float(x[1]), sig, n


def periods(cfg, ev: pd.DataFrame, data_end: pd.Timestamp) -> list[dict]:
    """Inflation periods since the October 2023 onset, plus the 2020 and 2022 periods (context)."""
    c = cfg["cycles"]
    start = pd.Timestamp(c["since"])
    big = ev[ev.type.isin(["dike", "eruption"]) & (ev.date >= start)].reset_index(drop=True)
    out = []
    onset = ev[(ev.type == "inflation onset") & (ev.date == start)]
    b0 = [(start, "inflation onset")] if len(onset) else []
    bounds = b0 + [(r.date, r.type) for r in big.itertuples()]
    for k, (d, typ) in enumerate(bounds):
        a = d if typ == "inflation onset" else d + pd.Timedelta(days=c["skip_days_after_event"])
        b = bounds[k + 1][0] - pd.Timedelta(days=1) if k + 1 < len(bounds) else data_end
        out.append({"period": f"{a:%Y-%m}", "start": a, "end": b, "after": f"{d:%Y-%m-%d} {typ}",
                    "open": k + 1 == len(bounds)})
    for a, b, lab in c.get("early_periods", []):
        out.insert(0, {"period": lab, "start": pd.Timestamp(a), "end": pd.Timestamp(b), "after": "", "open": False})
    return sorted(out, key=lambda p: p["start"])


def read_ts(f) -> pd.DataFrame:
    return pd.read_csv(f, parse_dates=["date"], index_col="date")


def rates(cfg, ev) -> tuple[pd.DataFrame, pd.DataFrame]:
    c = cfg["cycles"]
    res, gn = path(cfg, "results"), path(cfg, "results") / "gnss"
    centre = read_ts(res / "timeseries" / "svartsengi_uplift_centre.csv")
    st = c["rate_stations"]
    g = {s: read_ts(gn / f"{s}.csv") for s in st if (gn / f"{s}.csv").exists()}
    gi = {s: read_ts(res / "timeseries" / f"gnss_{s}.csv") for s in g if (res / "timeseries" / f"gnss_{s}.csv").exists()}
    end = max([centre.index[-1]] + [x.index[-1] for x in g.values()])
    min_days, min_cov = c["min_days"], c["min_coverage"]

    def rate(series: pd.Series, a, b, daily: bool):
        s = series[(series.index >= a) & (series.index <= b)].dropna()
        if len(s) < 4 or (s.index[-1] - s.index[0]).days < min_days:
            return np.nan, np.nan, len(s)
        if daily and len(s) < min_cov * ((b - a).days + 1):
            return np.nan, np.nan, len(s)
        return linrate(s.index, s.values)

    rows = []
    # the open period ends with the InSAR vertical data, so all columns cover the same days
    # (its continuation is in the pause windows below)
    for p in periods(cfg, ev, centre.up_mm.last_valid_index()):
        a, b = p["start"], p["end"]
        row = {"period": p["period"], "after": p["after"], "start": f"{a:%Y-%m-%d}", "end": f"{b:%Y-%m-%d}",
               "days": (b - a).days, "open": p["open"]}
        for key, s, daily in [("insar_centre_up", centre.up_mm, False), ("insar_centre_los_asc", centre.los_asc_mm, False)] \
                + [(f"gnss_{k}_up", v.up_mm, True) for k, v in g.items()] \
                + [(f"insar_{k}_up", v.up_mm, False) for k, v in gi.items()]:
            r, sg, n = rate(s, a, b, daily)
            row[f"{key}_rate"], row[f"{key}_sigma"], row[f"{key}_n"] = round(r, 3), round(sg, 3), n
        rows.append(row)
    per = pd.DataFrame(rows)

    # pause: windows from the end of the last eruption
    last = ev[ev.type == "eruption"].iloc[-1]
    p0 = (last.end_date if pd.notna(last.end_date) else last.date) + pd.Timedelta(days=1)
    w = pd.Timedelta(days=c["pause_window_days"])
    prow = []
    t = p0
    while t + w / 2 <= end:
        a, b = t, t + w - pd.Timedelta(days=1)
        row = {"window_start": f"{a:%Y-%m-%d}", "window_end": f"{min(b, end):%Y-%m-%d}"}
        for key, s, daily in [("insar_centre_up", centre.up_mm, False), ("insar_centre_los_asc", centre.los_asc_mm, False)] \
                + [(f"gnss_{k}_up", v.up_mm, True) for k, v in g.items()]:
            r, sg, n = rate(s, a, b, daily)
            row[f"{key}_rate"], row[f"{key}_sigma"], row[f"{key}_n"] = round(r, 3), round(sg, 3), n
        prow.append(row)
        t += w
    pause = pd.DataFrame(prow)
    pause.attrs["start"] = f"{p0:%Y-%m-%d}"
    return per, pause


# ----------------------------------------------------------------------------- pattern
def gauss2d(xy, A, x0, y0, sa, sb, th, c0):
    x, y = xy
    ct, st = np.cos(th), np.sin(th)
    xr = (x - x0) * ct + (y - y0) * st
    yr = -(x - x0) * st + (y - y0) * ct
    return A * np.exp(-0.5 * ((xr / sa) ** 2 + (yr / sb) ** 2)) + c0


def corr_length(res: np.ndarray, dx: float, dy: float) -> float:
    """e-folding distance (km) of the radially averaged autocorrelation of a map with NaNs."""
    m = np.isfinite(res).astype(float)
    r = np.where(m > 0, res - np.nanmean(res), 0.0)
    F = lambda a: np.fft.fft2(a, s=(2 * a.shape[0], 2 * a.shape[1]))  # noqa: E731
    num = np.real(np.fft.ifft2(F(r) * np.conj(F(r))))
    den = np.real(np.fft.ifft2(F(m) * np.conj(F(m))))
    ac = np.fft.fftshift(np.where(den > 50, num / np.maximum(den, 1), np.nan))
    ac = ac / ac[ac.shape[0] // 2, ac.shape[1] // 2]
    iy, ix = np.indices(ac.shape)
    dist = np.hypot((ix - ac.shape[1] // 2) * dx, (iy - ac.shape[0] // 2) * dy)
    edges = np.arange(0, 6, max(dx, dy))
    prof = [np.nanmean(ac[(dist >= e) & (dist < e + max(dx, dy))]) for e in edges]
    below = [e for e, p in zip(edges, prof) if p < np.exp(-1)]
    return float(below[0]) if below else float(edges[-1])


def pattern(cfg, cubes) -> pd.DataFrame:
    c = cfg["cycles"]
    d = cubes["dec"]
    t = pd.to_datetime(d.time.values)
    cen = cfg["sites"]["svartsengi_uplift_centre"]
    lat0, lon0 = cen["lat"], cen["lon"]
    kx = KM_LAT * np.cos(np.radians(lat0))
    ep = pd.read_csv(path(cfg, "results") / "episodes.csv", parse_dates=["first_epoch", "last_epoch"])
    ep = ep[(ep.component == "vertical") & (ep.days >= c["min_days"]) & (ep.displacement_mm > 0)
            & (ep.start_event.str.contains("inflation onset") | (ep.first_epoch >= pd.Timestamp(c["since"])))]
    cyc = [(r.first_epoch, r.last_epoch, f"{r.first_epoch:%b %Y}") for r in ep.itertuples()]
    ev = viz.load_events(cfg)
    last = ev[ev.type.isin(["dike", "eruption"])].date.max()
    after = t[t > last]
    if len(after) > 1:                               # the open cycle since the last eruption
        cyc.append((after[0], after[-1], f"{after[0]:%b %Y} (open)"))
    R = c["fit_radius_km"]
    sl = dict(lat=slice(lat0 + R / KM_LAT, lat0 - R / KM_LAT), lon=slice(lon0 - R / kx, lon0 + R / kx))
    sub = d.sel(**sl)
    X, Y = np.meshgrid((sub.lon.values - lon0) * kx, (sub.lat.values - lat0) * KM_LAT)
    inside = np.hypot(X, Y) <= R
    dx, dy = abs(float(sub.lon[1] - sub.lon[0])) * kx, abs(float(sub.lat[1] - sub.lat[0])) * KM_LAT
    up = sub["up"]
    mask = sub["mask"].values > 0
    maps, rows = {}, []
    for a, b, lab in cyc:
        i, j = int(np.argmin(abs(t - a))), int(np.argmin(abs(t - b)))
        m = (up.isel(time=j) - up.isel(time=i)).values
        m = np.where(mask & inside, m, np.nan)
        maps[lab] = m
        ok = np.isfinite(m)
        A0 = float(np.nanpercentile(m, 99.5))
        p0 = [A0, 0, 0, 2.0, 2.0, 0.0, 0.0]
        try:
            p, cov = curve_fit(gauss2d, (X[ok], Y[ok]), m[ok], p0=p0, maxfev=20000,
                               bounds=([0, -R, -R, 0.3, 0.3, -np.pi, -np.inf], [np.inf, R, R, 3 * R, 3 * R, np.pi, np.inf]))
        except RuntimeError:
            rows.append({"cycle": lab, "fit": "failed"})
            continue
        res = np.where(ok, m - gauss2d((X, Y), *p), np.nan)
        L = corr_length(res, dx, dy)
        n = int(ok.sum())
        n_eff = max(n * dx * dy / (np.pi * L ** 2), 7)
        cov = cov * n / n_eff
        e = np.sqrt(np.diag(cov))
        A, x0, y0, sa, sb, th, c0 = p
        if sa < sb:                                   # major axis first
            sa, sb, th = sb, sa, th + np.pi / 2
        az = (90 - np.degrees(th)) % 180              # azimuth of the major axis from north
        rows.append({
            "cycle": lab, "first_epoch": f"{t[i]:%Y-%m-%d}", "last_epoch": f"{t[j]:%Y-%m-%d}", "fit": "ok",
            "amplitude_mm": round(A, 1), "amplitude_sigma_mm": round(e[0], 1),
            "lat": round(lat0 + y0 / KM_LAT, 5), "lon": round(lon0 + x0 / kx, 5),
            "east_offset_m": round(x0 * 1000), "north_offset_m": round(y0 * 1000),
            "east_sigma_m": round(e[1] * 1000), "north_sigma_m": round(e[2] * 1000),
            "half_max_major_km": round(sa * np.sqrt(2 * np.log(2)), 2),
            "half_max_minor_km": round(sb * np.sqrt(2 * np.log(2)), 2),
            "axis_sigma_km": round(float(np.sqrt(2 * np.log(2)) * max(e[3], e[4])), 2),
            "azimuth_deg": round(az), "offset_mm": round(c0, 1),
            "residual_rms_mm": round(float(np.sqrt(np.nanmean(res ** 2))), 1),
            "corr_length_km": round(L, 2), "pixels": n,
            "resolved": bool(A > 3 * e[0]),
        })
    pat = pd.DataFrame(rows)
    # shape: correlation with the mean normalised map of the other cycles since 2023
    since = pd.Timestamp(c["since"])
    late = [r.cycle for r in pat.itertuples() if r.fit == "ok" and pd.Timestamp(r.first_epoch) >= since]
    corr = []
    for r in pat.itertuples():
        others = [maps[k] / pat.set_index("cycle").at[k, "amplitude_mm"] for k in late if k != r.cycle]
        if r.fit != "ok" or not others:
            corr.append(np.nan)
            continue
        ref = np.nanmean(np.stack(others), axis=0)
        ok = np.isfinite(ref) & np.isfinite(maps[r.cycle])
        corr.append(round(float(np.corrcoef(ref[ok], maps[r.cycle][ok])[0, 1]), 3))
    pat["corr_with_others"] = corr
    return pat


# ----------------------------------------------------------------------------- main
def main() -> int:
    cfg = load_config()
    out = path(cfg, "results") / "cycles"
    out.mkdir(parents=True, exist_ok=True)
    ev = viz.load_events(cfg)
    per, pause = rates(cfg, ev)
    per.to_csv(out / "rates.csv", index=False)
    pause.to_csv(out / "pause_rates.csv", index=False)
    pat = pattern(cfg, viz.open_cubes(cfg))
    pat.to_csv(out / "pattern.csv", index=False)

    c = cfg["cycles"]
    fmt = lambda r, s: "" if not np.isfinite(r) else f"{r:.2f} ± {s:.2f}"  # noqa: E731
    gst = [k[5:-8] for k in per.columns if k.startswith("gnss_") and k.endswith("_up_rate")]
    L = ["## Stage 7: rates per cycle and stability of the uplift pattern", "",
         "Research questions (1) and (3) of the research plan. Rates are slopes of a straight line fitted to "
         f"all GNSS days or InSAR epochs of a period (from {c['skip_days_after_event']} days after one dike or "
         "eruption to 1 day before the next), 1-sigma from the residuals, inflated for their lag-1 "
         f"autocorrelation. Periods shorter than {c['min_days']} days, or GNSS with less than "
         f"{int(c['min_coverage'] * 100)} % of the days, are left empty. Vertical (up) rates in mm/day:", "",
         "| Period | After | Days | InSAR centre | " + " | ".join(f"GNSS {s}" for s in gst) + " | "
         + " | ".join(f"InSAR at {s}" for s in gst) + " |",
         "|---|---|---|---|" + "---|" * (2 * len(gst))]
    for r in per.itertuples():
        d = r._asdict()
        L.append(f"| {r.period}{' (open)' if r.open else ''} | {r.after} | {r.days} | "
                 f"{fmt(d['insar_centre_up_rate'], d['insar_centre_up_sigma'])} | "
                 + " | ".join(fmt(d[f'gnss_{s}_up_rate'], d[f'gnss_{s}_up_sigma']) for s in gst) + " | "
                 + " | ".join(fmt(d.get(f'insar_{s}_up_rate', np.nan), d.get(f'insar_{s}_up_sigma', np.nan)) for s in gst)
                 + " |")
    L += ["", f"Current pause (since {pause.attrs['start']}, the day after the end of the last eruption), "
          f"{c['pause_window_days']} day windows, mm/day (InSAR vertical ends with the descending data; ascending "
          "LOS continues):", "",
          "| Window | InSAR centre up | InSAR centre LOS asc | " + " | ".join(f"GNSS {s} up" for s in gst) + " |",
          "|---|---|---|" + "---|" * len(gst)]
    for r in pause.to_dict("records"):
        L.append(f"| {r['window_start']} to {r['window_end']} | {fmt(r['insar_centre_up_rate'], r['insar_centre_up_sigma'])} | "
                 f"{fmt(r['insar_centre_los_asc_rate'], r['insar_centre_los_asc_sigma'])} | "
                 + " | ".join(fmt(r[f'gnss_{s}_up_rate'], r[f'gnss_{s}_up_sigma']) for s in gst) + " |")
    L += ["", f"Uplift pattern per cycle: elliptical Gaussian surface fitted to the vertical displacement within "
          f"{c['fit_radius_km']} km of the uplift centre; errors inflated for the residual correlation length "
          "(measured per map); 'corr' = correlation with the mean amplitude-normalised map of the other cycles "
          "since 2023:", "",
          "| Cycle | Epochs | Amplitude (mm) | East / north of the nominal centre (m) | Half max axes (km) | "
          "Azimuth (°) | Residual RMS (mm) | L (km) | corr |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in pat.itertuples():
        if r.fit != "ok":
            L.append(f"| {r.cycle} | fit failed | | | | | | | |")
            continue
        L.append(f"| {r.cycle}{'' if r.resolved else ' (not resolved)'} | {r.first_epoch} to {r.last_epoch} | "
                 f"{r.amplitude_mm} ± {r.amplitude_sigma_mm} | {r.east_offset_m} ± {r.east_sigma_m} / "
                 f"{r.north_offset_m} ± {r.north_sigma_m} | {r.half_max_major_km} x {r.half_max_minor_km} "
                 f"(± {r.axis_sigma_km}) | {r.azimuth_deg} | {r.residual_rms_mm} | {r.corr_length_km} | "
                 f"{r.corr_with_others} |")
    update_notes(cfg, "cycles", "\n".join(L))
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
