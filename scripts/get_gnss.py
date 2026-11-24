"""Stage 6: GNSS time series from the Nevada Geodetic Laboratory (NGL) and comparison with InSAR.

1. Station search: NGL DataHoldings.txt, stations within gnss.search_radius_km of the uplift
   centre -> results/gnss/stations.csv and a table in docs/processing_notes.md. The station IDs
   to process are listed in config.yaml (gnss.stations), taken from that search, not guessed.
2. Download the daily IGS20 tenv3 series of those stations and of the reference station
   (gnss.reference_station, REYK).
3. Antenna changes (NGL steps.txt, code 1) inside the analysis window are removed by fitting a
   line plus a step to +-step_window_days around the change. Receiver-only changes and earthquake
   steps (code 2) are kept: the latter are real displacement.
4. Reference: every station minus REYK on common days. This removes plate motion and common-mode
   errors; InSAR is relative to Straumsvik, ~11 km from REYK (the two are assumed to move alike).
5. Output per station results/gnss/<ID>.csv: date, east_mm, north_mm, up_mm (zero at the first
   day on or after the analysis start), 1-sigma, and the projection on the ascending and
   descending line of sight (LiCSBAS unit vectors at the station, + towards the satellite).
   InSAR at each station (Stage 4 format) -> results/timeseries/gnss_<ID>.csv.
6. Comparison at the InSAR epochs (3x3 pixel mean, same day GNSS): offset removed, RMS,
   correlation and trend of the difference -> results/gnss/comparison.csv.
7. REYK check: linear velocity and residual transients in IGS20 over the analysis window.
"""
from __future__ import annotations

import io
import json
import sys

import numpy as np
import pandas as pd
import requests

from common import load_config, path, update_notes

NGL = "https://geodesy.unr.edu"
HOLDINGS = f"{NGL}/NGLStationPages/DataHoldings.txt"
STEPS = f"{NGL}/NGLStationPages/steps.txt"
TENV3 = NGL + "/gps_timeseries/IGS20/tenv3/IGS20/{sta}.tenv3"
UA = {"User-Agent": "svartsengi-insar-course-project"}


def fetch(url: str, dest, max_age_days: float = 7) -> str:
    """Download url to dest unless a copy younger than max_age_days exists; return the text."""
    if dest.exists() and (pd.Timestamp.now() - pd.Timestamp(dest.stat().st_mtime, unit="s")).days < max_age_days:
        return dest.read_text()
    r = requests.get(url, headers=UA, timeout=120)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(r.text)
    return r.text


def dist_km(lat, lon, lat0, lon0):
    dy = (np.asarray(lat) - lat0) * 111.32
    dx = (np.asarray(lon) - lon0) * 111.32 * np.cos(np.radians(lat0))
    return np.hypot(dx, dy)


def holdings(cfg) -> pd.DataFrame:
    txt = fetch(HOLDINGS, path(cfg, "data") / "gnss" / "DataHoldings.txt")
    rows = []
    for line in txt.splitlines()[1:]:
        p = line.split()
        if len(p) < 11:
            continue
        lon = float(p[2])
        rows.append(dict(id=p[0], lat=float(p[1]), lon=lon - 360 if lon > 180 else lon, height_m=float(p[3]),
                         first=pd.Timestamp(p[7]), last=pd.Timestamp(p[8]), n_days=int(p[10])))
    return pd.DataFrame(rows).drop_duplicates("id").set_index("id")


def antenna_steps(cfg, ids) -> dict[str, list[pd.Timestamp]]:
    txt = fetch(STEPS, path(cfg, "data") / "gnss" / "steps.txt")
    out: dict[str, list] = {}
    for line in txt.splitlines():
        p = line.split()
        if len(p) >= 4 and p[0] in ids and p[2] == "1" and "Antenna" in p[3]:
            out.setdefault(p[0], []).append(pd.to_datetime(p[1], format="%y%b%d"))
    return out


def read_tenv3(cfg, sta: str) -> pd.DataFrame:
    txt = fetch(TENV3.format(sta=sta), path(cfg, "data") / "gnss" / f"{sta}.tenv3", max_age_days=3)
    df = pd.read_csv(io.StringIO(txt), sep=r"\s+")
    df.columns = [c.strip("_") for c in df.columns]
    out = pd.DataFrame({
        "east_mm": (df["e0(m)"] + df["east(m)"]) * 1000,
        "north_mm": (df["n0(m)"] + df["north(m)"]) * 1000,
        # NGL up jumps when the logged antenna height changes (e.g. VMOS, NBIO in 2024): add it back
        "up_mm": (df["u0(m)"] + df["up(m)"] + df["ant(m)"]) * 1000,
        "sig_e_mm": df["sig_e(m)"] * 1000, "sig_n_mm": df["sig_n(m)"] * 1000, "sig_u_mm": df["sig_u(m)"] * 1000,
    })
    out.index = pd.to_datetime(df["YYMMMDD"], format="%y%b%d")
    out.index.name = "date"
    return out[~out.index.duplicated()].sort_index()


def remove_steps(df: pd.DataFrame, steps: list, win: int, events: pd.Series) -> tuple[pd.DataFrame, list[str]]:
    """Line + step fit over +-win days around each antenna change; skipped if an event is inside."""
    notes = []
    for s in steps:
        if not (df.index[0] < s <= df.index[-1]):
            continue
        near = events[(events > s - pd.Timedelta(days=win)) & (events < s + pd.Timedelta(days=win))]
        if len(near):
            notes.append(f"{s:%Y-%m-%d} antenna change not corrected (event {near.iloc[0]:%Y-%m-%d} in the window)")
            continue
        w = df[(df.index > s - pd.Timedelta(days=win)) & (df.index < s + pd.Timedelta(days=win))]
        t = (w.index - s).days.values.astype(float)
        if (t < 0).sum() < 5 or (t >= 0).sum() < 5:
            notes.append(f"{s:%Y-%m-%d} antenna change not corrected (too few days around it)")
            continue
        A = np.column_stack([np.ones_like(t), t, (t >= 0).astype(float)])
        txt = []
        for c in ("east_mm", "north_mm", "up_mm"):
            ok = w[c].notna().values
            step = np.linalg.lstsq(A[ok], w[c].values[ok], rcond=None)[0][2]
            df.loc[df.index >= s, c] -= step
            txt.append(f"{c[0].upper()} {step:+.1f}")
        notes.append(f"{s:%Y-%m-%d} antenna change removed ({', '.join(txt)} mm)")
    return df, notes


def los_vectors(cubes, lat, lon) -> dict[str, tuple[float, float, float]]:
    out = {}
    for g in ("asc", "desc"):
        ds = cubes[g]
        p = ds.sel(lat=lat, lon=lon, method="nearest")
        out[g] = tuple(float(p[v]) for v in ("los_e", "los_n", "los_u"))
    return out


def at(gn: pd.Series, t: pd.Timestamp, tol_days: int = 1) -> float:
    """GNSS daily value on the day of t (or the mean of the days within +-tol_days)."""
    w = gn[(gn.index >= t.normalize() - pd.Timedelta(days=tol_days)) & (gn.index <= t.normalize() + pd.Timedelta(days=tol_days))]
    v = gn.get(t.normalize(), np.nan)
    return float(v) if np.isfinite(v) else (float(w.mean()) if len(w) else np.nan)


def increments(ins: pd.Series, gn: pd.Series, windows) -> list[dict]:
    """InSAR vs GNSS change between the same two InSAR epochs, for each (kind, label, t0, t1).
    Gaps in GNSS do not matter as long as GNSS exists on both dates (it is an absolute position)."""
    ins = ins.dropna()
    out = []
    for kind, label, a, b in windows:
        ia = ins.index[ins.index <= a]
        ib = ins.index[ins.index >= b]
        if not len(ia) or not len(ib):
            continue
        ta, tb = ia[-1], ib[0]
        if (a - ta).days > 15 or (tb - b).days > 15:
            continue
        ga, gb = at(gn, ta), at(gn, tb)
        if not (np.isfinite(ga) and np.isfinite(gb)):
            continue
        di, dg = float(ins[tb] - ins[ta]), gb - ga
        out.append({"kind": kind, "label": label, "t0": f"{ta:%Y-%m-%d}", "t1": f"{tb:%Y-%m-%d}",
                    "insar_mm": round(di, 1), "gnss_mm": round(dg, 1), "diff_mm": round(di - dg, 1)})
    return out


def compare(ins: pd.Series, gn: pd.Series) -> dict:
    ins = ins.dropna()
    g = gn.reindex(ins.index.normalize())
    g.index = ins.index
    ok = g.notna()
    n = int(ok.sum())
    if n < 5:
        return {"n": n}
    a, b = ins[ok], g[ok]
    d = a - b - (a - b).median()
    yrs = (a.index - a.index[0]).days.values / 365.25
    trend = float(np.polyfit(yrs, d.values, 1)[0]) if yrs[-1] > 0.5 else np.nan
    return {"n": n, "first": f"{a.index[0]:%Y-%m-%d}", "last": f"{a.index[-1]:%Y-%m-%d}",
            "offset_mm": round(float((a - b).mean()), 1), "rms_mm": round(float(np.sqrt((d ** 2).mean())), 1),
            "r": round(float(np.corrcoef(a, b)[0, 1]), 3), "trend_mm_yr": round(trend, 1),
            "gnss_range_mm": round(float(b.max() - b.min()), 1)}


def reference_check(ref: pd.DataFrame, t0, t1, events: pd.Series) -> dict:
    """Linear + annual fit of the reference station; residual scatter and steps at the big events."""
    r = ref[(ref.index >= t0) & (ref.index <= t1)]
    yrs = (r.index - r.index[0]).days.values / 365.25
    A = np.column_stack([np.ones_like(yrs), yrs, np.sin(2 * np.pi * yrs), np.cos(2 * np.pi * yrs)])
    out = {"span": f"{r.index[0]:%Y-%m-%d} to {r.index[-1]:%Y-%m-%d}", "days": len(r)}
    for c in ("east_mm", "north_mm", "up_mm"):
        ok = r[c].notna().values
        x, *_ = np.linalg.lstsq(A[ok], r[c].values[ok], rcond=None)
        res = r[c] - A @ x
        steps = []
        for e in events:
            b = res[(res.index >= e - pd.Timedelta(days=10)) & (res.index < e)]
            a = res[(res.index > e) & (res.index <= e + pd.Timedelta(days=10))]
            if len(a) > 3 and len(b) > 3:
                steps.append(float(a.median() - b.median()))
        out[c] = {"velocity_mm_yr": round(float(x[1]), 1), "annual_amp_mm": round(float(np.hypot(x[2], x[3])), 1),
                  "residual_std_mm": round(float(res.std()), 1),
                  "max_abs_step_at_events_mm": round(float(np.max(np.abs(steps))), 1) if steps else None,
                  "median_abs_step_at_events_mm": round(float(np.median(np.abs(steps))), 1) if steps else None}
    return out


def main() -> int:
    cfg = load_config()
    sys.path.insert(0, str(path(cfg, "results").parent / "scripts"))
    import viz

    g = cfg["gnss"]
    c = cfg["sites"]["svartsengi_uplift_centre"]
    t0 = pd.Timestamp(cfg["time"]["start"]) if "time" in cfg and "start" in cfg["time"] else pd.Timestamp("2020-01-01")
    out = path(cfg, "results") / "gnss"
    out.mkdir(parents=True, exist_ok=True)

    # 1. station search
    h = holdings(cfg)
    h["dist_km"] = dist_km(h.lat, h.lon, c["lat"], c["lon"]).round(1)
    near = h[(h.dist_km <= g["search_radius_km"]) & (h["last"] >= t0)].sort_values("dist_km")
    ids = list(g["stations"])
    ref_id = g["reference_station"]
    missing = [s for s in ids + [ref_id] if s not in h.index]
    if missing:
        raise SystemExit(f"Station IDs not in the NGL holdings: {missing}")
    not_listed = sorted(set(near.index) - set(ids))
    sel = h.loc[ids + [ref_id]].copy()
    cubes = viz.open_cubes(cfg)
    lat_ok = (sel.lat.between(float(cubes["asc"].lat.min()), float(cubes["asc"].lat.max())) &
              sel.lon.between(float(cubes["asc"].lon.min()), float(cubes["asc"].lon.max())))
    sel["in_insar_area"] = lat_ok
    sel["role"] = ["station"] * len(ids) + ["reference"]
    sel[["lat", "lon", "height_m", "dist_km", "first", "last", "n_days", "in_insar_area", "role"]].to_csv(
        out / "stations.csv", date_format="%Y-%m-%d")
    print(f"{len(near)} NGL stations within {g['search_radius_km']} km with data since {t0:%Y-%m-%d}; "
          f"processing {len(ids)} + reference {ref_id}", flush=True)

    # 2.-4. download, antenna steps, reference
    ev = viz.load_events(cfg)
    events = ev["date"]
    steps = antenna_steps(cfg, set(ids + [ref_id]))
    win = int(g.get("step_window_days", 15))
    ref = read_tenv3(cfg, ref_id)
    ref, ref_notes = remove_steps(ref, steps.get(ref_id, []), win, events)
    step_notes = {ref_id: ref_notes}
    series = {}
    for s in ids:
        df = read_tenv3(cfg, s)
        df, step_notes[s] = remove_steps(df, steps.get(s, []), win, events)
        rel = df[["east_mm", "north_mm", "up_mm"]].sub(ref[["east_mm", "north_mm", "up_mm"]]).dropna()
        rel = rel[rel.index >= t0]
        if rel.empty:
            print(f"  {s}: no days in common with {ref_id} after {t0:%Y-%m-%d}", flush=True)
            continue
        rel = rel - rel.iloc[0]
        for c_ in ("e", "n", "u"):
            rel[f"sig_{c_}_mm"] = np.hypot(df[f"sig_{c_}_mm"], ref[f"sig_{c_}_mm"]).reindex(rel.index)
        if sel.at[s, "in_insar_area"]:
            for gname, (le, ln, lu) in los_vectors(cubes, sel.at[s, "lat"], sel.at[s, "lon"]).items():
                rel[f"los_{gname}_mm"] = rel.east_mm * le + rel.north_mm * ln + rel.up_mm * lu
        rel.round(2).to_csv(out / f"{s}.csv", date_format="%Y-%m-%d")
        series[s] = rel
        print(f"  {s}: {len(rel)} days {rel.index[0]:%Y-%m-%d} to {rel.index[-1]:%Y-%m-%d}", flush=True)

    # 5. InSAR point time series at the stations (same format as Stage 4's results/timeseries/)
    import postprocess
    pts = [{"name": f"gnss_{s}", "lat": sel.at[s, "lat"], "lon": sel.at[s, "lon"], "kind": "gnss"}
           for s in ids if sel.at[s, "in_insar_area"]]
    ts_files = postprocess.point_series(cfg, {"asc": cubes["asc"], "desc": cubes["desc"]}, cubes["dec"], pts)

    # 6. comparison with InSAR
    rows, inc_rows = [], []
    big_ev = ev[ev.type.isin(["dike", "eruption"]) & (ev.date >= t0)]
    episodes = pd.read_csv(path(cfg, "results") / "episodes.csv", parse_dates=["first_epoch", "last_epoch"])
    EP_COMP = {"up": "vertical", "los_asc": "LOS asc", "los_desc": "LOS desc"}
    comp = (("up", "dec", "up", "up_mm"), ("east", "dec", "east", "east_mm"),
            ("los_asc", "asc", "cum", "los_asc_mm"), ("los_desc", "desc", "cum", "los_desc_mm"))
    for s, df in series.items():
        if not sel.at[s, "in_insar_area"]:
            continue
        la, lo = sel.at[s, "lat"], sel.at[s, "lon"]
        i = int(np.abs(cubes["dec"].lat.values - la).argmin())
        j = int(np.abs(cubes["dec"].lon.values - lo).argmin())
        masked = bool(cubes["dec"]["mask"].values[i, j] == 0)
        coh = float(cubes["asc"]["coh_avg"].values[i, j])
        for name, cube, var, col in comp:
            ins = viz.window_series(cubes[cube], var, la, lo, 1)
            r = compare(ins, df[col])
            rows.append({"station": s, "component": name, "dist_km": sel.at[s, "dist_km"],
                         "insar_masked": masked, "coh_avg_asc": round(coh, 2), **r})
            win = [("event", f"{e.date:%Y-%m-%d} {e.type} ({e.location})", e.date - pd.Timedelta(days=1),
                    e.date + pd.Timedelta(days=1)) for e in big_ev.itertuples()]
            epc = EP_COMP.get(name)
            if epc:
                win += [("episode", f"{r_.start_event} to {r_.end_event}", r_.first_epoch, r_.last_epoch)
                        for r_ in episodes[episodes.component == epc].itertuples()]
            for x in increments(ins, df[col], win):
                inc_rows.append({"station": s, "dist_km": sel.at[s, "dist_km"], "component": name, **x})
    cmp_df = pd.DataFrame(rows)
    cmp_df.to_csv(out / "comparison.csv", index=False)
    inc = pd.DataFrame(inc_rows)
    inc.to_csv(out / "increments.csv", index=False)

    # 7. reference station check
    big = ev[ev.type.isin(["dike", "eruption"]) & (ev.date >= t0)]["date"]
    rc = reference_check(ref, t0, ref.index[-1], big)
    (out / "reference_check.json").write_text(json.dumps(rc, indent=2))

    # notes
    L = ["## Stage 6: GNSS", "",
         f"Source: Nevada Geodetic Laboratory, daily IGS20 `tenv3` series ({NGL}). "
         f"Stations within {g['search_radius_km']} km of the uplift centre ({c['lat']} N, {abs(c['lon'])} W) "
         f"with data since {t0:%Y-%m-%d}, from the NGL station list (not guessed):", "",
         "| Station | Lat | Lon | Distance (km) | Data | Days |", "|---|---|---|---|---|---|"]
    for s, r in sel.iterrows():
        tag = " (reference)" if r.role == "reference" else ""
        L.append(f"| {s}{tag} | {r.lat:.4f} | {r.lon:.4f} | {r.dist_km} | {r['first']:%Y-%m-%d} – {r['last']:%Y-%m-%d} "
                 f"| {r.n_days} |")
    if not_listed:
        L += ["", f"Also within the radius but not processed: {', '.join(not_listed)}."]
    L += ["", f"All series are relative to {ref_id} (Reykjavik, {sel.at[ref_id, 'dist_km']} km from the centre, "
          "outside the InSAR area), which removes plate motion and common-mode errors; InSAR is relative to "
          "Straumsvik, 11 km from REYK. GNSS is projected on each line of sight with the LiCSBAS unit vectors.", "",
          "Antenna changes (NGL steps.txt):", ""]
    for s, n in step_notes.items():
        for x in n:
            L.append(f"- {s}: {x}")
    L += ["", f"Reference station {ref_id} in IGS20, {rc['span']} (linear + annual fit; 'step' = median "
          "residual 10 days after minus 10 days before each dike or eruption):", "",
          "| Component | Velocity (mm/yr) | Annual amplitude (mm) | Residual std (mm) | Median / max step at events (mm) |",
          "|---|---|---|---|---|"]
    for k in ("east_mm", "north_mm", "up_mm"):
        x = rc[k]
        L.append(f"| {k[:-3]} | {x['velocity_mm_yr']} | {x['annual_amp_mm']} | {x['residual_std_mm']} | "
                 f"{x['median_abs_step_at_events_mm']} / {x['max_abs_step_at_events_mm']} |")
    L += ["", "Change between the same two InSAR epochs, InSAR minus GNSS (3x3 pixel mean; GNSS on the same "
          "days). 'episode' = the inflation episodes of results/episodes.csv, 'event' = last epoch before to first "
          "epoch after a dike or eruption:", "",
          "| Component | Kind | Pairs | Median GNSS change (mm) | Median abs. difference (mm) | RMS difference (mm) |",
          "|---|---|---|---|---|---|"]
    for (comp_, kind), x in inc.groupby(["component", "kind"]):
        L.append(f"| {comp_} | {kind} | {len(x)} | {x.gnss_mm.abs().median():.0f} | {x.diff_mm.abs().median():.0f} | "
                 f"{np.sqrt((x.diff_mm ** 2).mean()):.0f} |")
    worst = inc[inc.kind == "event"].reindex(inc[inc.kind == "event"].diff_mm.abs().sort_values(ascending=False).index).head(8)
    L += ["", "Largest event differences:", "", "| Station | Component | Event | InSAR (mm) | GNSS (mm) | Difference (mm) |",
          "|---|---|---|---|---|---|"]
    for _, r in worst.iterrows():
        L.append(f"| {r.station} | {r.component} | {r.label} | {r.insar_mm} | {r.gnss_mm} | {r.diff_mm} |")
    L += ["", "Whole series, InSAR minus GNSS at the InSAR epochs, median offset removed (affected by GNSS gaps "
          "spanning large events, e.g. SKSH Sep 2023 - 2025); trend = linear trend of the difference:", "",
          "| Station | km | Component | Epochs | Period | GNSS range (mm) | RMS (mm) | r | Trend (mm/yr) | Masked |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in cmp_df.iterrows():
        if r.get("n", 0) < 5 or pd.isna(r.get("rms_mm")):
            continue
        L.append(f"| {r.station} | {r.dist_km} | {r.component} | {r.n} | {r['first']} – {r['last']} | "
                 f"{r.gnss_range_mm} | {r.rms_mm} | {r.r} | {r.trend_mm_yr} | {'yes' if r.insar_masked else ''} |")
    L += ["", f"InSAR point time series at the {len(ts_files)} stations inside the InSAR area "
          f"({cfg['postprocess']['ts_window_px']}x{cfg['postprocess']['ts_window_px']} px mean, same columns as "
          "Stage 4): `results/timeseries/gnss_<ID>.csv`."]
    update_notes(cfg, "gnss", "\n".join(L))
    print(f"comparison: {len(cmp_df)} rows; reference {ref_id}: "
          + ", ".join(f"{k[:-3]} {rc[k]['velocity_mm_yr']} mm/yr" for k in ("east_mm", "north_mm", "up_mm")), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
