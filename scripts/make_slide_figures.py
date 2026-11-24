"""Figures for the presentation (PNG) in figures/slides/.

Drawn at the size they take on a 16:9 slide (13.33 x 7.5 in), so the font sizes below are the
sizes seen on the slide (labels at least 16 pt, as the presentation guidelines ask). Same data,
colours and colour maps as the report figures (scripts/make_figures.py); nothing is recomputed.

  timeline      dated events since 2020 (motivation slide)
  study_area    frames overview and station map
  maps          vertical displacement, 2020 vs 2024 inflation episode
  centre        vertical displacement at the uplift centre with events
  episodes      uplift and rate per inflation episode with uncertainties
  gnss          InSAR vs GNSS change per episode (scatter)
  sksh          ascending LOS at SKSH, InSAR vs GNSS (backup)
  rates         uplift rate per inflation period and in the pause (question 1)
  pattern       uplift centre and extent per cycle (question 3)

Usage: python scripts/make_slide_figures.py [names...]
Arial is used when its font file is found in $SLIDE_FONT_DIR (e.g. C:/Windows/Fonts mounted at
/fonts); otherwise matplotlib's default sans serif.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cmcrameri import cm as cmc
from matplotlib import font_manager

import make_figures as mf
import viz
from common import load_config, path

_fd = Path(os.environ.get("SLIDE_FONT_DIR", "/fonts"))
for name in ("arial.ttf", "arialbd.ttf"):
    if (_fd / name).exists():
        font_manager.fontManager.addfont(str(_fd / name))
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"],
    "font.size": 16, "axes.titlesize": 17, "axes.labelsize": 17, "xtick.labelsize": 16, "ytick.labelsize": 16,
    "legend.fontsize": 15, "axes.linewidth": 1.0, "xtick.major.width": 1.0, "ytick.major.width": 1.0,
    "xtick.major.size": 5, "ytick.major.size": 5, "lines.linewidth": 2.0,
    "axes.edgecolor": viz.INK2, "axes.labelcolor": viz.INK, "xtick.color": viz.INK2, "ytick.color": viz.INK2,
    "axes.spines.top": False, "axes.spines.right": False,
    "savefig.dpi": 200, "figure.dpi": 100,
})
GRID = dict(axis="y", color="#e4e2dc", lw=0.8)


def save(fig, out, name):
    fig.savefig(out / f"{name}.png", bbox_inches="tight", pad_inches=0.05, facecolor="white")
    plt.close(fig)
    print(f"  {name}.png", flush=True)


def deg_axes(ax, dx=0.1, dy=0.05, fx="{:.1f}", fy="{:.2f}"):
    ax.set_aspect(1 / np.cos(np.radians(63.9)))
    ax.xaxis.set_major_locator(plt.MultipleLocator(dx))
    ax.yaxis.set_major_locator(plt.MultipleLocator(dy))
    ax.xaxis.set_major_formatter(lambda x, _: fx.format(abs(x)) + "°W")
    ax.yaxis.set_major_formatter(lambda y, _: fy.format(y) + "°N")
    for s in ("top", "right"):
        ax.spines[s].set_visible(True)


def scalebar(ax, km, size=14):
    from matplotlib_scalebar.scalebar import ScaleBar
    ax.add_artist(ScaleBar(111_320 * np.cos(np.radians(63.9)), units="m", location="lower right",
                           fixed_value=km * 1000, length_fraction=None, box_alpha=0.8,
                           font_properties={"size": size}, border_pad=0.4, pad=0.3, sep=3))


def sites(ax, cfg, labels=False, ms=11):
    s = cfg["sites"]
    c = s["svartsengi_uplift_centre"]
    ax.plot(c["lon"], c["lat"], "+", color=viz.INK, ms=ms + 6, mew=3, zorder=6)
    g = s["grindavik"]
    ax.plot(g["lon"], g["lat"], "o", ms=ms * 0.7, mfc="white", mec=viz.INK, mew=1.5, zorder=6)
    for st in viz.gnss_stations(cfg):
        if st.get("role") != "reference":
            ax.plot(st["lon"], st["lat"], "^", ms=ms, mfc="white", mec=viz.INK, mew=1.5, zorder=6)


# ----------------------------------------------------------------------------- figures
def fig_timeline(cfg, cubes, out):
    """Dated events since 2020: inflation onsets, dike intrusions and eruptions, one row per site."""
    ev = viz.load_events(cfg)
    rows = {"Svartsengi": 2, "Fagradalsfjall": 1, "Sundhnukur": 0}
    names = {"Svartsengi": "Svartsengi", "Fagradalsfjall": "Fagradalsfjall", "Sundhnukur": "Sundhnúkur"}
    mk = {"inflation onset": ("^", "inflation onset"), "dike": ("|", "dike intrusion"), "eruption": ("o", "eruption")}
    fig, ax = plt.subplots(figsize=(11.6, 2.9))
    for loc, y in rows.items():
        ax.axhline(y, color="#e4e2dc", lw=1.0, zorder=0)
    for _, e in ev.iterrows():
        if e.location not in rows:
            continue
        m, _ = mk.get(e.type, ("o", ""))
        col = viz.EVENT_COLOURS[e.location]
        kw = dict(ms=26, mew=3.5) if m == "|" else dict(ms=12, mew=1.5, mfc=col if m == "o" else "white")
        ax.plot(e.date, rows[e.location], m, color=col, mec=col, zorder=3, **kw)
    ax.set_yticks(list(rows.values()), [names[k] for k in rows])
    ax.set_ylim(-0.6, 2.6)
    ax.set_xlim(pd.Timestamp("2019-12-01"), pd.Timestamp("2026-10-01"))
    ax.spines[["left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    hs = [plt.Line2D([], [], ls="none", marker=m, color=viz.INK2, mfc="white" if m == "^" else viz.INK2,
                     ms=26 if m == "|" else 11, mew=3.5 if m == "|" else 1.5) for m, _ in mk.values()]
    ax.legend(hs, [lab for _, lab in mk.values()], loc="upper left", bbox_to_anchor=(0.0, 1.32), ncol=3,
              frameon=False, handletextpad=0.3, columnspacing=1.5)
    save(fig, out, "timeline")


def fig_study_area(cfg, cubes, out):
    from shapely import wkt as W
    from shapely.geometry import box
    fig = plt.figure(figsize=(11.6, 5.0))
    a = fig.add_axes([0.0, 0.08, 0.36, 0.84])
    b = fig.add_axes([0.45, 0.08, 0.55, 0.84])
    # (a) frames, processed area, reference and REYK
    view = dict(lon=(-24.8, -19.8), lat=(63.2, 64.9))
    try:
        import cartopy.io.shapereader as shp
        land = shp.natural_earth(resolution="10m", category="physical", name="land")
        vb = box(view["lon"][0], view["lat"][0], view["lon"][1], view["lat"][1])
        for geom in shp.Reader(land).geometries():
            if geom.intersects(vb):
                g = geom.intersection(vb)
                for part in getattr(g, "geoms", [g]):
                    if part.geom_type == "Polygon":
                        x, y = part.exterior.xy
                        a.fill(x, y, color="#e4e2dc", ec=viz.INK2, lw=0.6, zorder=0)
    except Exception as e:                                   # offline: no coastline
        print(f"  (no coastline: {e})")
    a.set_facecolor("#f4f7fa")
    for g, f in viz.frames(cfg).items():
        wf = path(cfg, "results") / "frames" / f"{f}_poly.wkt"
        if wf.exists():
            x, y = W.loads(wf.read_text()).exterior.xy
            a.plot(x, y, color=viz.ASC if g == "asc" else viz.DESC, lw=3, zorder=2)
    A = cfg["aoi"]
    a.add_patch(plt.Rectangle((A["lon_min"], A["lat_min"]), A["lon_max"] - A["lon_min"], A["lat_max"] - A["lat_min"],
                              fill=False, ec=viz.INK, lw=2.2, zorder=4))
    rp = cfg["licsbas"]["reference_point"]
    a.plot(rp["lon"], rp["lat"], "s", ms=10, mfc="white", mec=viz.INK, mew=2, zorder=5)
    a.text(rp["lon"] + 0.15, rp["lat"] - 0.05, "InSAR\nreference", ha="left", va="top", fontsize=15, zorder=6,
           bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
    reyk = [s for s in viz.gnss_stations(cfg) if s["id"] == "REYK"][0]
    a.plot(reyk["lon"], reyk["lat"], "^", ms=12, mfc=viz.INK, mec=viz.INK, zorder=5)
    a.text(reyk["lon"] + 0.15, reyk["lat"] + 0.03, "REYK", fontsize=15, va="bottom", zorder=6, bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
    a.text(A["lon_min"] - 0.1, A["lat_min"] - 0.05, "processed\narea", fontsize=15, va="top", ha="right", zorder=6,
           bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
    a.set_xlim(*view["lon"])
    a.set_ylim(*view["lat"])
    deg_axes(a, dx=2.0, dy=0.4, fx="{:.0f}", fy="{:.1f}")
    hs = [plt.Line2D([], [], color=viz.ASC, lw=3), plt.Line2D([], [], color=viz.DESC, lw=3)]
    a.legend(hs, ["ascending frame", "descending frame"], loc="lower left", bbox_to_anchor=(0, 1.0),
             frameon=False, ncol=1, handlelength=1.4, borderaxespad=0.2)
    # (b) station cluster
    v = dict(lon=(-22.58, -22.28), lat=(63.825, 63.93))
    hs_, ext = viz.hillshade(cfg)
    b.imshow(hs_, extent=ext, cmap="gray", vmin=-0.3, vmax=1.3, interpolation="bilinear", zorder=0)
    sites(b, cfg)
    off = {"HS02": (-14, 14), "SKSH": (-28, 14), "GRIV": (-18, -28), "SENG": (12, 2), "ORFC": (12, -2),
           "AUSV": (12, -8), "VMOS": (-66, -4), "GEVK": (-64, -8), "ELD1": (-40, -30), "NBIO": (12, -2),
           "SUDV": (12, -6), "NAMC": (12, -4), "FEFC": (-30, 14)}
    for st in viz.gnss_stations(cfg):
        if v["lon"][0] <= st["lon"] <= v["lon"][1] and v["lat"][0] <= st["lat"] <= v["lat"][1]:
            b.annotate(st["id"], (st["lon"], st["lat"]), xytext=off.get(st["id"], (12, 0)),
                       textcoords="offset points", fontsize=14, color=viz.INK, zorder=7,
                       bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.5))
    g = cfg["sites"]["grindavik"]
    b.annotate("Grindavík", (g["lon"], g["lat"]), xytext=(10, -22), textcoords="offset points", fontsize=14,
               zorder=7, bbox=dict(fc="white", ec="none", alpha=0.6, pad=0.5))
    b.set_xlim(*v["lon"])
    b.set_ylim(*v["lat"])
    deg_axes(b, dx=0.1, dy=0.025, fy="{:.3f}")
    scalebar(b, 2)
    hs = [plt.Line2D([], [], ls="none", marker="^", ms=12, mfc="white", mec=viz.INK, mew=1.5),
          plt.Line2D([], [], ls="none", marker="+", ms=17, color=viz.INK, mew=3)]
    b.legend(hs, ["GNSS station (NGL)", "uplift centre"], loc="lower left", bbox_to_anchor=(0, 1.0),
             frameon=False, ncol=2, borderaxespad=0.2)
    save(fig, out, "study_area")


def fig_maps(cfg, cubes, out):
    """Same uplift pattern in 2020 and 2024, ten times larger: two maps with their own scales."""
    d = cubes["dec"]
    t = pd.to_datetime(d.time.values)
    ep = pd.read_csv(path(cfg, "results") / "episodes.csv", parse_dates=["first_epoch", "last_epoch"])
    ep = ep[ep.component == "vertical"]
    fig, axs = plt.subplots(1, 2, figsize=(11.6, 5.0), layout="constrained")
    for ax, start, title in zip(axs, ("2020-03-01", "2024-05-29"), ("March to April 2020", "June to August 2024")):
        r = ep[ep.start_event.str.startswith(start)].iloc[0]
        i, j = int(np.argmin(abs(t - r.first_epoch))), int(np.argmin(abs(t - r.last_epoch)))
        m = viz.masked(d, "up", time=j) - viz.masked(d, "up", time=i)
        crop = m.sel(lat=slice(mf.ZOOM["lat"][1], mf.ZOOM["lat"][0]), lon=slice(*mf.ZOOM["lon"]))
        lim = float(np.ceil(viz.sym_limit(crop.values) / 10) * 10)
        mf.background(ax, cfg, d)
        im = ax.imshow(np.asarray(m), extent=viz.extent(d), cmap=cmc.vik, vmin=-lim, vmax=lim,
                       interpolation="nearest", zorder=1)
        sites(ax, cfg, ms=9)
        ax.set_xlim(*mf.ZOOM["lon"])
        ax.set_ylim(*mf.ZOOM["lat"])
        deg_axes(ax, dx=0.15, dy=0.05)
        ax.set_title(f"{t[i]:%d.%m.%Y} to {t[j]:%d.%m.%Y}", loc="left")
        cb = fig.colorbar(im, ax=ax, orientation="horizontal", fraction=0.07, aspect=25, pad=0.02)
        cb.set_label("Vertical displacement (mm)")
    scalebar(axs[0], 5)
    save(fig, out, "maps")


def fig_centre(cfg, cubes, out):
    ts = pd.read_csv(path(cfg, "results") / "timeseries" / "svartsengi_uplift_centre.csv",
                     parse_dates=["date"], index_col="date")
    ev = viz.load_events(cfg)
    fig, ax = plt.subplots(figsize=(11.6, 4.7))
    for _, e in ev.iterrows():
        ax.axvline(e.date, color=viz.EVENT_COLOURS.get(e.location, viz.MUTED), lw=1.2, alpha=0.7,
                   ls=viz.EVENT_DASH.get(e.type, "solid"), zorder=0)
    s = ts["up_mm"].dropna()
    ax.plot(s.index, s - s.iloc[0], "-", lw=2.2, color=viz.INK)
    ax.set_ylabel("Vertical (mm), + up")
    ax.grid(**GRID)
    hs = [plt.Line2D([], [], color=c, lw=2) for c in viz.EVENT_COLOURS.values()]
    hs += [plt.Line2D([], [], color=viz.INK2, lw=1.5, ls=v) for v in ("dotted", "dashed", "solid")]
    labs = ["Svartsengi", "Fagradalsfjall", "Sundhnúkur", "inflation onset", "dike intrusion", "eruption"]
    ax.legend(hs, labs, loc="lower left", ncol=3, frameon=False, bbox_to_anchor=(0, 1.0),
              handlelength=1.6, columnspacing=1.2)
    ax.set_xlim(pd.Timestamp("2020-01-01"), s.index[-1] + pd.Timedelta(days=40))
    save(fig, out, "centre")


def fig_episodes(cfg, cubes, out):
    ep = pd.read_csv(path(cfg, "results") / "episodes.csv", parse_dates=["first_epoch", "last_epoch"])
    ep = ep[(ep.component == "vertical") & (ep.days >= 20) & (ep.displacement_mm > 0)].reset_index(drop=True)
    ep = ep[ep.first_epoch >= pd.Timestamp("2023-11-01")].reset_index(drop=True)
    # the episode still open after the last event (not in episodes.csv): as in the report, Table 1
    ts = pd.read_csv(path(cfg, "results") / "timeseries" / "svartsengi_uplift_centre.csv",
                     parse_dates=["date"], index_col="date")["up_mm"].dropna()
    last_ev = viz.load_events(cfg).date.max()
    s = ts[ts.index > last_ev]
    if len(s) > 1:
        days = (s.index[-1] - s.index[0]).days
        sig = cfg["postprocess"]["episode_sigma_mm"]["up"]
        ep = pd.concat([ep, pd.DataFrame([{"first_epoch": s.index[0], "displacement_mm": s.iloc[-1] - s.iloc[0],
                                           "rate_mm_per_day": (s.iloc[-1] - s.iloc[0]) / days,
                                           "displacement_sigma_mm": sig, "rate_sigma_mm_per_day": sig / days}])],
                       ignore_index=True)
    lab = [f"{a:%b %y}" for a in ep.first_epoch]
    x = np.arange(len(ep))
    colours = ["#8fb6e8"] * (len(ep) - 1) + ["#d3e3f6"]
    fig, axs = plt.subplots(1, 2, figsize=(8.6, 5.2), layout="constrained")
    for ax, col, sig, ylab, title in ((axs[0], "displacement_mm", "displacement_sigma_mm", "Uplift (mm)", "Uplift per episode"),
                                      (axs[1], "rate_mm_per_day", "rate_sigma_mm_per_day", "Rate (mm/day)", "Mean uplift rate")):
        ax.bar(x, ep[col], width=0.65, color=colours, edgecolor=["none"] * (len(ep) - 1) + [viz.ASC],
               linestyle="--", linewidth=1.5)
        ax.errorbar(x, ep[col], yerr=ep[sig], fmt="none", ecolor=viz.INK, elinewidth=1.8, capsize=5)
        ax.set_xticks(x, lab, rotation=45, ha="right", rotation_mode="anchor")
        ax.set_ylabel(ylab)
        ax.set_title(title, loc="left")
        ax.grid(**GRID)
        ax.set_axisbelow(True)
    axs[1].text(x[0], ep[col].iloc[0] + ep[sig].iloc[0] + 0.3, f"{ep[col].iloc[0]:.1f}", ha="center", fontsize=15)
    axs[1].text(x[-1], ep[col].iloc[-1] + ep[sig].iloc[-1] + 0.3, f"{ep[col].iloc[-1]:.2f}", ha="center", fontsize=15)
    axs[1].set_ylim(0, 14.5)
    axs[0].set_xlabel("Episode start")
    axs[1].set_xlabel("Episode start")
    save(fig, out, "episodes")


def fig_gnss(cfg, cubes, out):
    inc = pd.read_csv(path(cfg, "results") / "gnss" / "increments.csv")
    e = inc[inc.kind == "episode"]
    bad = e.reliability.fillna("") != ""
    style = {"los_asc": (viz.ASC, "o", "ascending LOS"), "los_desc": (viz.DESC, "s", "descending LOS"),
             "up": (viz.INK, "^", "vertical")}
    lim = float(np.nanmax(np.abs(e[["insar_mm", "gnss_mm"]].values))) * 1.05
    fig, ax = plt.subplots(figsize=(6.0, 5.2))
    ax.plot([-lim, lim], [-lim, lim], "-", lw=1.2, color=viz.MUTED, zorder=0)
    for comp, (col, mk, lab) in style.items():
        x = e[(e.component == comp) & ~bad]
        rms = float(np.sqrt((x.diff_mm ** 2).mean()))
        ax.plot(x.gnss_mm, x.insar_mm, mk, ms=8, mfc="none", mec=col, mew=1.6, label=f"{lab}: {rms:.0f} mm")
    ax.set_xlim(-lim / 4, lim)
    ax.set_ylim(-lim / 4, lim)
    ax.set_aspect("equal")
    ax.set_xlabel("GNSS change (mm)")
    ax.set_ylabel("InSAR change (mm)")
    ax.legend(loc="upper left", frameon=False, title="RMS difference", title_fontsize=15, alignment="left",
              handletextpad=0.2)
    save(fig, out, "gnss")


def fig_sksh(cfg, cubes, out):
    g = viz.gnss_series(cfg)
    st = {s["id"]: s for s in viz.gnss_stations(cfg)}
    k = "SKSH"
    ins = viz.window_series(cubes["asc"], "cum", st[k]["lat"], st[k]["lon"], 1).dropna()
    ins = ins - ins.iloc[0]
    gn = g[k]["los_asc_mm"].dropna()
    gi = gn.reindex(ins.index.normalize())
    gi.index = ins.index
    d = (ins - gi).dropna()
    gn = gn + float(d[d.index <= d.index[0] + pd.Timedelta(days=60)].median())
    fig, ax = plt.subplots(figsize=(11.6, 4.6))
    ax.plot(gn.index, gn, ".", ms=3, color=viz.ASC, alpha=0.5, label="GNSS SKSH, daily, projected on LOS")
    ax.plot(ins.index, ins, "-", lw=2, color=viz.INK, label="InSAR ascending LOS, 3 x 3 pixels")
    ax.set_ylabel("LOS (mm), + towards satellite")
    ax.grid(**GRID)
    ax.legend(loc="upper left", frameon=False, markerscale=4)
    save(fig, out, "sksh")


def fig_rates(cfg, cubes, out):
    """Uplift rate per inflation period and in the windows of the pause (question 1)."""
    fig, ax = plt.subplots(figsize=(8.4, 5.2))
    p0 = mf.draw_rates(ax, cfg, lw=2.6)
    ax.text(p0 + pd.Timedelta(days=12), 6.2, "pause:\n60 day\nwindows", fontsize=15, va="top", color=viz.INK2)
    ax.set_ylabel("Uplift rate (mm/day)")
    ax.set_ylim(-0.5, 12.5)
    ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(bymonth=[1, 7]))
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b\n%Y"))
    ax.grid(**GRID)
    ax.legend(loc="upper right", frameon=False, fontsize=14, handlelength=2.2)
    save(fig, out, "rates")


def fig_pattern(cfg, cubes, out):
    """Fitted centre and half maximum ellipse per cycle, and distance to the 2024 to 2026 centre (question 3)."""
    fig = plt.figure(figsize=(11.6, 5.0))
    ax = fig.add_axes([0.0, 0.08, 0.5, 0.86])
    mf.background(ax, cfg)
    pat, cmap, t0, t1 = mf.draw_pattern(ax, cfg, ms=9, lw=2.0)
    c = cfg["sites"]["svartsengi_uplift_centre"]
    ax.plot(c["lon"], c["lat"], "+", color=viz.INK, ms=14, mew=2, zorder=6)
    ax.set_xlim(-22.585, -22.32)
    ax.set_ylim(63.828, 63.912)
    deg_axes(ax, dx=0.1, dy=0.04)
    scalebar(ax, 2)
    odd = {str(k) for k in cfg["cycles"].get("pattern_outliers", {})}
    stable = pat[(pat.t >= pd.Timestamp("2024-03-01")) & ~pat.first_epoch.isin(odd)]
    e0, n0 = stable.east_offset_m.mean(), stable.north_offset_m.mean()
    b = fig.add_axes([0.645, 0.30, 0.35, 0.62])
    for k, r in enumerate(pat.itertuples()):
        col = cmap(0.9 * (r.t - t0) / (t1 - t0))
        d = np.hypot(r.east_offset_m - e0, r.north_offset_m - n0)
        s = np.hypot(r.east_sigma_m, r.north_sigma_m)
        hollow = r.first_epoch in odd
        b.errorbar(k, d, s, fmt="o", ms=10, mfc="white" if hollow else col, mec=col, color=col, elinewidth=1.6)
    b.set_xticks(range(len(pat)))
    b.set_xticklabels([r.cycle.replace(" (open)", "*") for r in pat.itertuples()], rotation=50, ha="right",
                      fontsize=15)
    b.set_ylabel("Distance to the\n2024 to 2026 centre (m)")
    b.set_ylim(0, 2000)
    b.grid(**GRID)
    save(fig, out, "pattern")


FIGS = {"timeline": fig_timeline, "study_area": fig_study_area, "maps": fig_maps, "centre": fig_centre,
        "episodes": fig_episodes, "gnss": fig_gnss, "sksh": fig_sksh, "rates": fig_rates, "pattern": fig_pattern}


def main() -> int:
    cfg = load_config()
    out = path(cfg, "figures") / "slides"
    out.mkdir(parents=True, exist_ok=True)
    cubes = viz.open_cubes(cfg)
    for n in sys.argv[1:] or list(FIGS):
        FIGS[n](cfg, cubes, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
