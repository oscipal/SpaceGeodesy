"""Stage 5b: static report figures (PDF + PNG) in figures/report/.

1 study_area          frames, AOI, reference point, sites, exclusion zones, GNSS stations
2 los_velocity        mean LOS velocity, ascending and descending
3 decomp_velocity     vertical and east-west velocity (linear fit over the common period)
4 episodes_maps       cumulative vertical displacement in selected inflation episodes
  episodes_maps_short four of them in one row (4-page report)
5 centre_timeseries   LOS, vertical and east at the uplift centre with dated events
6 gnss_comparison     InSAR vs GNSS vertical (only once Stage 6 has written results/gnss/)
7 episodes_uplift     vertical displacement and rate per episode at the uplift centre

Sized for a 2-column report (single column 3.5 in, full width 7.2 in). Everything is read from
the Stage 4 products; nothing is recomputed. Usage: python scripts/make_figures.py [names...]
"""
from __future__ import annotations

import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from cmcrameri import cm as cmc
from matplotlib_scalebar.scalebar import ScaleBar

import viz
from common import load_config, path

FULL, COL = 7.2, 3.5
plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "legend.fontsize": 7, "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "axes.edgecolor": viz.INK2, "axes.labelcolor": viz.INK, "xtick.color": viz.INK2, "ytick.color": viz.INK2,
    "savefig.dpi": 300, "figure.dpi": 100, "pdf.fonttype": 42,
})
ZOOM = dict(lon=(-22.62, -22.25), lat=(63.80, 63.95))       # Svartsengi - Sundhnukur - Grindavik


def save(fig, out, name):
    for ext in ("pdf", "png"):
        fig.savefig(out / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}.pdf/.png", flush=True)


def map_axes(ax, cfg, zoom=None, scalebar=True, sites=True):
    lat0 = 63.9
    ax.set_aspect(1 / np.cos(np.radians(lat0)))
    if zoom:
        ax.set_xlim(*zoom["lon"])
        ax.set_ylim(*zoom["lat"])
    ax.tick_params(length=2)
    from matplotlib.ticker import MultipleLocator
    ax.xaxis.set_major_locator(MultipleLocator(0.1 if zoom else 0.2))
    ax.yaxis.set_major_locator(MultipleLocator(0.05))
    ax.xaxis.set_major_formatter(lambda x, _: f"{abs(x):.1f}°W")
    ax.yaxis.set_major_formatter(lambda y, _: f"{y:.2f}°N")
    if scalebar:
        ax.add_artist(ScaleBar(111_320 * np.cos(np.radians(lat0)), units="m", location="lower right",
                               length_fraction=0.2, box_alpha=0.7, font_properties={"size": 6},
                               border_pad=0.3, pad=0.2, sep=2))
    if sites:
        s, rp = cfg["sites"], cfg["licsbas"]["reference_point"]
        c = s["svartsengi_uplift_centre"]
        ax.plot(c["lon"], c["lat"], "+", color=viz.INK, ms=7, mew=1.2, zorder=5)
        ax.plot(s["grindavik"]["lon"], s["grindavik"]["lat"], "o", ms=3.5, mfc="white", mec=viz.INK, mew=0.8, zorder=5)
        ax.plot(rp["lon"], rp["lat"], "s", ms=5, mfc="none", mec=viz.INK, mew=1.0, zorder=5)
        for st in viz.gnss_stations(cfg):
            ax.plot(st["lon"], st["lat"], "^", ms=4.5, mfc="white", mec=viz.INK, mew=0.8, zorder=5)


def background(ax, cfg, ds=None):
    hs, ext = viz.hillshade(cfg)
    ax.imshow(hs, extent=ext, cmap="gray", vmin=-0.3, vmax=1.3, interpolation="bilinear", zorder=0)


def overlay(ax, ds, data, lim, cmap=cmc.vik):
    return ax.imshow(np.asarray(data), extent=viz.extent(ds), cmap=cmap, vmin=-lim, vmax=lim,
                     interpolation="nearest", zorder=1)


# ----------------------------------------------------------------------------- figures
# Label offsets (points) for the GNSS stations in the zoomed study-area panel, chosen by eye so
# that the names of the clustered stations around the uplift centre do not overlap.
LABEL_OFFSETS = {"HS02": (-21, 3), "SKSH": (-14, -9), "GRIV": (-9, -10), "SENG": (5, 2), "ORFC": (5, 1),
                 "AUSV": (5, -5), "VMOS": (-21, -2), "GEVK": (-21, -4), "ELD1": (-8, 5), "NBIO": (5, 1),
                 "SUDV": (5, -2), "NAMC": (5, 1), "FEFC": (-8, 5)}
CLUSTER = dict(lon=(-22.57, -22.29), lat=(63.825, 63.925))   # station cluster around the uplift centre


def in_view(lon, lat, v):
    return v["lon"][0] <= lon <= v["lon"][1] and v["lat"][0] <= lat <= v["lat"][1]


def fig_study_area(cfg, cubes, out):
    from shapely.geometry import box
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(FULL, 2.45), gridspec_kw={"width_ratios": [1, 1.12, 1.02]})
    # (a) overview: frame footprints and AOI
    polys = {}
    cache = path(cfg, "results") / "frames"
    for g, f in viz.frames(cfg).items():
        wkt = cache / f"{f}_poly.wkt"
        if not wkt.exists():
            from common import frame_polygon
            p = frame_polygon(cfg, f)
            if p is not None:
                wkt.write_text(p.wkt)
        if wkt.exists():
            from shapely import wkt as W
            polys[g] = W.loads(wkt.read_text())
    try:
        import cartopy.io.shapereader as shp
        land = shp.natural_earth(resolution="10m", category="physical", name="land")
        view = box(-24.8, 63.2, -19.8, 64.9)
        for geom in shp.Reader(land).geometries():
            if geom.intersects(view):
                g = geom.intersection(view)
                for part in getattr(g, "geoms", [g]):
                    if part.geom_type == "Polygon":
                        x, y = part.exterior.xy
                        a.fill(x, y, color="#e4e2dc", ec=viz.INK2, lw=0.4, zorder=0)
    except Exception as e:                                   # offline: no coastline
        print(f"  (no coastline: {e})")
    for g, p in polys.items():
        x, y = p.exterior.xy
        col = viz.ASC if g == "asc" else viz.DESC
        a.plot(x, y, color=col, lw=1.2, zorder=2)
        a.fill(x, y, color=col, alpha=0.08, zorder=1)
    for g, (x, y) in (("asc", (-23.95, 63.30)), ("desc", (-21.0, 64.75))):   # inside each footprint, in view
        if g in polys:
            a.text(x, y, f"{viz.frames(cfg)[g]}\n{'ascending' if g == 'asc' else 'descending'}",
                   fontsize=6, ha="center", va="center", color=viz.ASC if g == "asc" else viz.DESC, zorder=3,
                   bbox=dict(fc="white", ec="none", alpha=0.8, pad=1))
    A = cfg["aoi"]
    a.add_patch(plt.Rectangle((A["lon_min"], A["lat_min"]), A["lon_max"] - A["lon_min"], A["lat_max"] - A["lat_min"],
                              fill=False, ec=viz.INK, lw=1.2, zorder=4))
    a.text(A["lon_max"] + 0.05, A["lat_min"] - 0.08, "AOI", fontsize=7, color=viz.INK)
    a.set_xlim(-24.8, -19.8)
    a.set_ylim(63.2, 64.9)
    map_axes(a, cfg, scalebar=True, sites=False)
    from matplotlib.ticker import MultipleLocator
    a.xaxis.set_major_locator(MultipleLocator(1))
    a.yaxis.set_major_locator(MultipleLocator(0.4))
    a.xaxis.set_major_formatter(lambda x, _: f"{abs(x):.0f}°W")
    a.yaxis.set_major_formatter(lambda y, _: f"{y:.1f}°N")
    a.set_title("(a) LiCSAR frames", loc="left")
    # (b) AOI detail
    ds = cubes["asc"]
    background(b, cfg, ds)
    for name, z in cfg["exclusion_zones"].items():
        b.add_patch(plt.Rectangle((z["lon_min"], z["lat_min"]), z["lon_max"] - z["lon_min"], z["lat_max"] - z["lat_min"],
                                  fill=False, ec=viz.INK2, lw=0.8, ls="--", zorder=2))
        # short labels (S/G, F, K), spelled out in the report caption; the full names overlap
        b.text(z["lon_max"] - 0.005, z["lat_max"] - 0.004, {"fagradalsfjall": "F", "sundhnukur_grindavik": "S/G", "krysuvik": "K"}.get(name, name), fontsize=6.5,
               ha="right", va="top", color=viz.INK, zorder=3)
    map_axes(b, cfg)
    s, rp = cfg["sites"], cfg["licsbas"]["reference_point"]
    b.text(rp["lon"] - 0.01, rp["lat"] - 0.008, "reference\n(Straumsvík)", fontsize=6, ha="right", va="top",
           color=viz.INK, zorder=6)
    aoi = dict(lon=(A["lon_min"], A["lon_max"]), lat=(A["lat_min"], A["lat_max"]))
    for st in viz.gnss_stations(cfg):          # stations outside the zoom panel are named here
        if in_view(st["lon"], st["lat"], aoi) and not in_view(st["lon"], st["lat"], CLUSTER):
            b.text(st["lon"] + 0.008, st["lat"], st["id"], fontsize=6, color=viz.INK, zorder=6)
    b.add_patch(plt.Rectangle((CLUSTER["lon"][0], CLUSTER["lat"][0]), CLUSTER["lon"][1] - CLUSTER["lon"][0],
                              CLUSTER["lat"][1] - CLUSTER["lat"][0], fill=False, ec=viz.INK, lw=1.0, zorder=4))
    b.text(CLUSTER["lon"][0], CLUSTER["lat"][0] - 0.004, "(c)", fontsize=6.5, va="top", color=viz.INK, zorder=6)
    b.set_xlim(A["lon_min"], A["lon_max"])
    b.set_ylim(A["lat_min"], A["lat_max"])
    b.set_title("(b) Study area", loc="left")
    # (c) station cluster around the uplift centre
    background(c, cfg, ds)
    map_axes(c, cfg, zoom=CLUSTER)
    c.xaxis.set_major_locator(plt.MultipleLocator(0.1))
    c.yaxis.set_major_locator(plt.MultipleLocator(0.025))
    c.yaxis.set_major_formatter(lambda y, _: f"{y:.3f}°N")
    for st in viz.gnss_stations(cfg):
        if in_view(st["lon"], st["lat"], CLUSTER):
            dx, dy = LABEL_OFFSETS.get(st["id"], (5, 1))
            c.annotate(st["id"], (st["lon"], st["lat"]), xytext=(dx, dy), textcoords="offset points",
                       fontsize=5.5, color=viz.INK, zorder=6)
    g = s["grindavik"]
    c.annotate("Grindavík", (g["lon"], g["lat"]), xytext=(-12, -9), textcoords="offset points", fontsize=5.5,
               color=viz.INK, zorder=6)
    c.set_title("(c) GNSS stations; + uplift centre", loc="left")
    fig.tight_layout(w_pad=0.6)
    save(fig, out, "fig1_study_area")


def fig_los_velocity(cfg, cubes, out):
    vs = {g: viz.masked(cubes[g], "vel") for g in ("asc", "desc")}
    lim = max(viz.sym_limit(v) for v in vs.values())
    fig, axs = plt.subplots(1, 2, figsize=(FULL, 3.4), sharey=True, layout="constrained")
    for ax, (g, v) in zip(axs, vs.items()):
        ds = cubes[g]
        background(ax, cfg, ds)
        im = overlay(ax, ds, v, lim)
        map_axes(ax, cfg)
        t = pd.to_datetime(ds.time.values)
        ax.set_title(f"({'a' if g == 'asc' else 'b'}) {'Ascending' if g == 'asc' else 'Descending'} "
                     f"{viz.frames(cfg)[g]}\n{t[0]:%Y-%m-%d} to {t[-1]:%Y-%m-%d}", loc="left")
    cb = fig.colorbar(im, ax=axs, orientation="horizontal", fraction=0.06, aspect=40)
    cb.set_label("Mean LOS velocity (mm/yr), positive towards the satellite; reference Straumsvík (square)")
    save(fig, out, "fig2_los_velocity")


def fig_decomp_velocity(cfg, cubes, out):
    d = cubes["dec"]
    vs = {"vel_up": viz.masked(d, "vel_up"), "vel_east": viz.masked(d, "vel_east")}
    lim = max(viz.sym_limit(v) for v in vs.values())
    t = pd.to_datetime(d.time.values)
    fig, axs = plt.subplots(1, 2, figsize=(FULL, 3.3), sharey=True, layout="constrained")
    for ax, (k, v), lab in zip(axs, vs.items(), ("(a) Vertical, positive up", "(b) East-west, positive east")):
        background(ax, cfg, d)
        im = overlay(ax, d, v, lim)
        map_axes(ax, cfg)
        ax.set_title(lab, loc="left")
    cb = fig.colorbar(im, ax=axs, orientation="horizontal", fraction=0.06, aspect=40)
    cb.set_label(f"Velocity (mm/yr), linear fit {t[0]:%Y-%m-%d} to {t[-1]:%Y-%m-%d}; north component neglected")
    save(fig, out, "fig3_decomp_velocity")


EPISODES = [("2020-01-21", "2020 inflation"), ("2022-05-16", "2022 inflation"),
            ("2023-11-10", "After the Grindavík dike"), ("2024-03-16", "Mar-May 2024"),
            ("2024-05-29", "May-Aug 2024"), ("2024-08-22", "Aug-Nov 2024"),
            ("2024-11-20", "Nov 2024-Apr 2025"), ("2025-04-01", "Apr-Jul 2025")]


def fig_episode_maps(cfg, cubes, out):
    d = cubes["dec"]
    t = pd.to_datetime(d.time.values)
    ep = pd.read_csv(path(cfg, "results") / "episodes.csv", parse_dates=["first_epoch", "last_epoch"])
    ep = ep[ep.component == "vertical"]
    maps = []
    for start, title in EPISODES:
        r = ep[ep.start_event.str.startswith(start)]
        if r.empty:
            continue
        r = r.iloc[0]
        i, j = int(np.argmin(abs(t - r.first_epoch))), int(np.argmin(abs(t - r.last_epoch)))
        maps.append((title, t[i], t[j], viz.masked(d, "up", time=j) - viz.masked(d, "up", time=i)))
    early = [m for m in maps if m[1].year < 2023]
    late = [m for m in maps if m[1].year >= 2023]
    crop = lambda m: m.sel(lat=slice(ZOOM["lat"][1], ZOOM["lat"][0]), lon=slice(*ZOOM["lon"]))  # noqa: E731
    lims = [viz.sym_limit(np.concatenate([crop(m[3]).values.ravel() for m in grp])) if grp else 10 for grp in (early, late)]
    ncol = 3
    nrow = 1 + int(np.ceil(len(late) / ncol))
    fig, axs = plt.subplots(nrow, ncol, figsize=(FULL, 2.45 * nrow), sharex=True, sharey=True,
                            gridspec_kw={"hspace": 0.45, "wspace": 0.12})
    letters = iter("abcdefghij")
    for row, grp, lim in ((0, early, lims[0]), (1, late, lims[1])):
        for k, (title, ta, tb, m) in enumerate(grp):
            ax = axs.flat[row * ncol + k] if row == 0 else axs.flat[ncol + k]
            background(ax, cfg, d)
            im = overlay(ax, d, m, lim)
            map_axes(ax, cfg, zoom=ZOOM, scalebar=(k == 0))
            ax.set_title(f"({next(letters)}) {title}\n{ta:%Y-%m-%d} to {tb:%Y-%m-%d}", loc="left")
        if grp:
            if row == 0:
                cax = axs.flat[len(early)]
                cax.set_axis_off()
                cb = fig.colorbar(im, ax=cax, orientation="horizontal", fraction=0.5, aspect=12, location="bottom")
            else:
                for ax in axs.flat[ncol + len(late):]:
                    ax.set_axis_off()
                cb = fig.colorbar(im, ax=list(axs.flat[ncol:]), orientation="horizontal", fraction=0.04, pad=0.08, aspect=50)
            cb.set_label(f"Vertical displacement (mm), {'2020-2022' if row == 0 else 'since Nov 2023'}")
    for ax in axs.flat[len(early) + 1:ncol]:
        ax.set_axis_off()
    save(fig, out, "fig4_episodes_maps")


EPISODES_SHORT = [("2020-03-01", "Mar-Apr 2020"), ("2022-05-16", "May-Jul 2022"),
                  ("2024-05-29", "Jun-Aug 2024"), ("2024-11-20", "Nov 2024-Mar 2025")]


def fig_episode_maps_short(cfg, cubes, out):
    """Four inflation episodes in one row (for the 4-page report): two before and two after the
    onset of the Sundhnukur activity, each pair with its own colour scale."""
    d = cubes["dec"]
    t = pd.to_datetime(d.time.values)
    ep = pd.read_csv(path(cfg, "results") / "episodes.csv", parse_dates=["first_epoch", "last_epoch"])
    ep = ep[ep.component == "vertical"]
    maps = []
    for start, title in EPISODES_SHORT:
        r = ep[ep.start_event.str.startswith(start)].iloc[0]
        i, j = int(np.argmin(abs(t - r.first_epoch))), int(np.argmin(abs(t - r.last_epoch)))
        maps.append((title, t[i], t[j], viz.masked(d, "up", time=j) - viz.masked(d, "up", time=i)))
    crop = lambda m: m.sel(lat=slice(ZOOM["lat"][1], ZOOM["lat"][0]), lon=slice(*ZOOM["lon"]))  # noqa: E731
    fig, axs = plt.subplots(1, 4, figsize=(FULL, 2.35), sharey=True, layout="constrained")
    for pair in ((0, 1), (2, 3)):
        lim = viz.sym_limit(np.concatenate([crop(maps[k][3]).values.ravel() for k in pair]))
        for k in pair:
            title, ta, tb, m = maps[k]
            ax = axs[k]
            background(ax, cfg, d)
            im = overlay(ax, d, m, lim)
            map_axes(ax, cfg, zoom=ZOOM, scalebar=(k == 0))
            ax.xaxis.set_major_locator(plt.MultipleLocator(0.15))
            ax.set_title(f"({'abcd'[k]}) {title}\n{ta:%Y-%m-%d} to {tb:%Y-%m-%d}", loc="left")
        cb = fig.colorbar(im, ax=[axs[k] for k in pair], orientation="horizontal", fraction=0.06, aspect=30)
        cb.set_label("Vertical displacement (mm)")
    save(fig, out, "fig4_episodes_maps_short")


def event_lines(ax, ev, coloured=True, labels=False, min_gap_days=45):
    last = None
    for _, e in ev.iterrows():
        col = viz.EVENT_COLOURS.get(e.location, viz.MUTED) if coloured else viz.MUTED
        ax.axvline(e.date, color=col, lw=0.7, alpha=0.8 if coloured else 0.6,
                   ls=viz.EVENT_DASH.get(e.type, "solid"), zorder=0)
        # initials only where they do not collide (dense 2023-2024 sequence: one label per cluster)
        if labels and (last is None or (e.date - last).days >= min_gap_days):
            last = e.date
            ax.text(e.date, 1.01, viz.EVENT_INITIAL.get(e.location, ""), transform=ax.get_xaxis_transform(),
                    fontsize=5.5, ha="center", va="bottom", color=viz.INK2)


def fig_centre(cfg, cubes, out):
    c = cfg["sites"]["svartsengi_uplift_centre"]
    ts = pd.read_csv(path(cfg, "results") / "timeseries" / "svartsengi_uplift_centre.csv",
                     parse_dates=["date"], index_col="date")
    ev = viz.load_events(cfg)
    fig, axs = plt.subplots(3, 1, figsize=(FULL, 3.5), sharex=True, gridspec_kw={"height_ratios": [1.1, 1.1, 0.8]})
    a = axs[0]
    event_lines(a, ev, coloured=False)
    for col, g, lab in (("los_asc_mm", "asc", "ascending"), ("los_desc_mm", "desc", "descending")):
        s = ts[col].dropna()
        a.plot(s.index, s - s.iloc[0], "-", lw=0.9, color=viz.ASC if g == "asc" else viz.DESC,
               label=f"LOS {lab} ({viz.frames(cfg)[g]})")
    a.set_ylabel("LOS (mm)\n+ towards satellite")
    a.legend(loc="upper left", frameon=False)
    a.set_title(f"(a) Line of sight at the uplift centre ({c['lat']}°N, {abs(c['lon'])}°W, 3x3 pixel mean), "
                "unfiltered; event lines grey", loc="left")
    for ax, col, lab, title in ((axs[1], "up_mm", "Vertical (mm)\n+ up", "(b) Vertical"),
                                (axs[2], "east_mm", "East (mm)\n+ east", "(c) East-west")):
        event_lines(ax, ev, coloured=True, labels=(ax is axs[1]))
        s = ts[col].dropna()
        ax.plot(s.index, s - s.iloc[0], "-", lw=0.9, color=viz.INK)
        ax.set_ylabel(lab)
        ax.set_title(f"{title} from the ascending/descending decomposition (to {s.index[-1]:%Y-%m-%d})",
                     loc="left", pad=13 if ax is axs[1] else 3)
    for ax in axs:
        ax.grid(axis="y", color="#e4e2dc", lw=0.5)
        ax.spines[["top", "right"]].set_visible(False)
    hs = [plt.Line2D([], [], color=v, lw=1) for v in viz.EVENT_COLOURS.values()]
    hs += [plt.Line2D([], [], color=viz.INK2, lw=0.8, ls=v) for v in viz.EVENT_DASH.values()]
    labs = [f"{k} ({viz.EVENT_INITIAL[k]})" for k in viz.EVENT_COLOURS] + list(viz.EVENT_DASH)
    axs[2].legend(hs, labs, loc="lower left", ncol=3, frameon=False, fontsize=6.5)
    fig.align_ylabels(axs)
    fig.tight_layout(h_pad=0.6)
    save(fig, out, "fig5_centre_timeseries")


def fig_gnss(cfg, cubes, out):
    """(a) SKSH (1.1 km from the centre, 2020-2026): ascending LOS, InSAR vs GNSS projected.
    (b) Change per inflation episode, InSAR vs GNSS, all stations (results/gnss/increments.csv)."""
    g = viz.gnss_series(cfg)
    f = path(cfg, "results") / "gnss" / "increments.csv"
    if not g or not f.exists():
        print("  fig6_gnss_comparison skipped: no GNSS series yet (Stage 6)")
        return
    st = {s["id"]: s for s in viz.gnss_stations(cfg)}
    k = "SKSH" if "SKSH" in g else next(iter(g))
    fig = plt.figure(figsize=(FULL, 2.75))
    ax = fig.add_axes([0.075, 0.17, 0.53, 0.70])
    bx = fig.add_axes([0.70, 0.17, 0.28, 0.70])
    ins = viz.window_series(cubes["asc"], "cum", st[k]["lat"], st[k]["lon"], 1).dropna()
    ins = ins - ins.iloc[0]
    gn = g[k]["los_asc_mm"].dropna()
    gi = gn.reindex(ins.index.normalize())
    gi.index = ins.index
    d = (ins - gi).dropna()
    gn = gn + float(d[d.index <= d.index[0] + pd.Timedelta(days=60)].median())
    event_lines(ax, viz.load_events(cfg), coloured=False)
    ax.plot(gn.index, gn, ".", ms=1.2, color=viz.ASC, alpha=0.35, label=f"GNSS {k} (daily, projected on LOS)")
    ax.plot(ins.index, ins, "-", lw=0.9, color=viz.INK, label="InSAR ascending LOS (3x3 px)")
    ax.set_ylabel("LOS (mm), + towards satellite")
    ax.set_title(f"(a) GNSS {k} ({st[k]['dist_km']} km from the centre) relative to REYK, ascending LOS",
                 loc="left")
    ax.legend(loc="upper left", frameon=False, markerscale=6)
    ax.spines[["top", "right"]].set_visible(False)
    inc = pd.read_csv(f)
    e = inc[inc.kind == "episode"]
    style = {"los_asc": (viz.ASC, "o", "LOS asc"), "los_desc": (viz.DESC, "s", "LOS desc"),
             "up": (viz.INK, "^", "vertical")}
    lim = float(np.nanmax(np.abs(e[["insar_mm", "gnss_mm"]].values))) * 1.05
    bx.plot([-lim, lim], [-lim, lim], "-", lw=0.6, color=viz.MUTED, zorder=0)
    bad = e.reliability.fillna("") != "" if "reliability" in e else pd.Series(False, index=e.index)
    for comp, (col, mk, lab) in style.items():
        x = e[(e.component == comp) & ~bad]
        rms = float(np.sqrt((x.diff_mm ** 2).mean()))
        bx.plot(x.gnss_mm, x.insar_mm, mk, ms=3, mfc="none", mec=col, mew=0.7,
                label=f"{lab}: n={len(x)}, RMS {rms:.0f} mm")
    if bad.any():
        bx.plot(e[bad].gnss_mm, e[bad].insar_mm, "x", ms=3, color=viz.MUTED, mew=0.7,
                label=f"known unreliable (n={int(bad.sum())})")
    bx.set_xlim(-lim / 4, lim)
    bx.set_ylim(-lim / 4, lim)
    bx.set_aspect("equal")
    bx.set_xlabel("GNSS change (mm)")
    bx.set_ylabel("InSAR change (mm)")
    bx.set_title(f"(b) Per episode, {e.station.nunique()} stations", loc="left")
    bx.legend(loc="upper left", frameon=False, fontsize=6, handletextpad=0.2)
    bx.spines[["top", "right"]].set_visible(False)
    save(fig, out, "fig6_gnss_comparison")


def fig_episode_uplift(cfg, cubes, out):
    ep = pd.read_csv(path(cfg, "results") / "episodes.csv", parse_dates=["first_epoch", "last_epoch"])
    ep = ep[(ep.component == "vertical") & (ep.days >= 20)].reset_index(drop=True)
    lab = [f"{a:%b}–{b:%b}\n{a:%Y}" if a.year == b.year else f"{a:%b %y}–\n{b:%b %y}"
           for a, b in zip(ep.first_epoch, ep.last_epoch)]
    x = np.arange(len(ep))
    fig, axs = plt.subplots(2, 1, figsize=(FULL, 3.6), sharex=True)
    for ax, col, ylab in ((axs[0], "displacement_mm", "Vertical (mm)"), (axs[1], "rate_mm_per_day", "Rate (mm/day)")):
        ax.bar(x, ep[col], width=0.7, color=viz.INK2, edgecolor="white", linewidth=1)
        ax.axhline(0, color=viz.INK, lw=0.6)
        ax.set_ylabel(ylab)
        ax.grid(axis="y", color="#e4e2dc", lw=0.5)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axs[0].set_title("(a) Vertical displacement at the uplift centre between consecutive events "
                     "(first acquisition after to last before)", loc="left")
    axs[1].set_title("(b) Mean rate", loc="left")
    axs[1].set_xticks(x, lab, fontsize=6)
    fig.tight_layout()
    save(fig, out, "fig7_episodes_uplift")


RATE_STYLE = {"insar_centre_up": ("InSAR, uplift centre", viz.INK, "-"),
              "gnss_HS02_up": ("GNSS HS02 (0.8 km)", viz.ASC, "-"),
              "gnss_SKSH_up": ("GNSS SKSH (1.1 km)", viz.ASC, "--"),
              "gnss_SENG_up": ("GNSS SENG (2.2 km)", viz.ASC, ":")}


def draw_rates(ax, cfg, lw=1.2, band=True):
    """Vertical uplift rate per inflation period (horizontal segments, +-1 sigma band) and in the
    windows of the current pause, from results/cycles/ (scripts/cycles.py)."""
    d = path(cfg, "results") / "cycles"
    per = pd.read_csv(d / "rates.csv", parse_dates=["start", "end"])
    per = per[per.start >= pd.Timestamp(cfg["cycles"]["since"])]
    pause = pd.read_csv(d / "pause_rates.csv", parse_dates=["window_start", "window_end"])
    p0 = pause.window_start.min()
    per = per[~per.open.astype(bool)]                          # the open period is shown as pause windows
    for key, (lab, col, ls) in RATE_STYLE.items():
        if f"{key}_rate" not in per:
            continue
        first = True
        for a, b, r, s in list(zip(per.start, per.end, per[f"{key}_rate"], per[f"{key}_sigma"])) + \
                list(zip(pause.window_start, pause.window_end, pause[f"{key}_rate"], pause[f"{key}_sigma"])):
            if not np.isfinite(r):
                continue
            ax.plot([a, b], [r, r], ls, color=col, lw=lw, label=lab if first else None, zorder=3)
            if band:
                ax.fill_between([a, b], r - s, r + s, color=col, alpha=0.15, lw=0, zorder=2)
            first = False
    key = "insar_centre_los_asc"
    first = True
    for a, b, r, s in zip(pause.window_start, pause.window_end, pause[f"{key}_rate"], pause[f"{key}_sigma"]):
        if np.isfinite(r) and a > pd.Timestamp("2026-01-01"):
            ax.plot([a, b], [r, r], "-", color=viz.MUTED, lw=lw, label="InSAR, centre, ascending LOS" if first else None,
                    zorder=3)
            first = False
    ev = viz.load_events(cfg)
    for e in ev[(ev.date >= pd.Timestamp(cfg["cycles"]["since"])) & ev.type.isin(["dike", "eruption"])].date:
        ax.axvline(e, color=viz.EVENT_COLOURS["Sundhnukur"], lw=0.6, alpha=0.5, zorder=0)
    ax.axvline(p0, color=viz.INK2, lw=0.8, ls="--", zorder=1)
    ax.axhline(0, color=viz.INK2, lw=0.5)
    return p0


def fig_rates(cfg, cubes, out):
    fig, ax = plt.subplots(figsize=(FULL, 2.4))
    p0 = draw_rates(ax, cfg)
    ax.text(p0 + pd.Timedelta(days=8), 7.5, "pause: no eruption since\nthe end of the July 2025 eruption,\n60 day windows",
            fontsize=6.5, va="top", color=viz.INK2)
    ax.set_ylabel("Uplift rate (mm/day)")
    ax.set_ylim(-0.5, 12.5)
    ax.grid(axis="y", color="#e4e2dc", lw=0.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(0.2, 1.02), frameon=False, ncol=2, fontsize=6.5)
    save(fig, out, "fig_rates")


def draw_pattern(ax, cfg, ms=4, lw=1.0):
    """Half maximum ellipses and centres (+-1 sigma) of the fitted uplift per cycle since the
    October 2023 onset (results/cycles/pattern.csv), coloured by time; dashed = cycles whose fit
    is affected by other deformation (cycles.pattern_outliers in config.yaml)."""
    pat = pd.read_csv(path(cfg, "results") / "cycles" / "pattern.csv")
    pat = pat[(pat.fit == "ok") & pat.resolved.astype(bool)].copy()
    pat["t"] = pd.to_datetime(pat.first_epoch)
    kx = 111.32 * np.cos(np.radians(63.87))
    cmap = cmc.batlow
    t0, t1 = pat.t.min(), pat.t.max()
    odd = {str(k) for k in cfg["cycles"].get("pattern_outliers", {})}
    ph = np.linspace(0, 2 * np.pi, 100)
    for r in pat.itertuples():
        col = cmap(0.9 * (r.t - t0) / (t1 - t0))
        dashed = r.first_epoch in odd
        az = np.radians(r.azimuth_deg)                   # major axis, clockwise from north
        u, v = r.half_max_major_km * np.cos(ph), r.half_max_minor_km * np.sin(ph)
        e, n = u * np.sin(az) + v * np.cos(az), u * np.cos(az) - v * np.sin(az)
        ax.plot(r.lon + e / kx, r.lat + n / 111.32, "--" if dashed else "-", color=col, lw=lw, zorder=3)
        ax.errorbar(r.lon, r.lat, xerr=r.east_sigma_m / 1000 / kx, yerr=r.north_sigma_m / 1000 / 111.32,
                    fmt="o", ms=ms, mfc="white" if dashed else col, color=col, mec=col, mew=1.0,
                    elinewidth=0.8, zorder=5)
    return pat, cmap, t0, t1


def fig_pattern(cfg, cubes, out):
    """(a) Map of the fitted uplift centres and half maximum ellipses per cycle; (b) offset of the
    centre from the nominal centre, half maximum axes and shape correlation per cycle."""
    fig = plt.figure(figsize=(FULL, 2.6))
    ax = fig.add_axes([0.0, 0.1, 0.46, 0.82])
    background(ax, cfg)
    pat, cmap, t0, t1 = draw_pattern(ax, cfg)
    map_axes(ax, cfg, zoom={"lon": (-22.585, -22.32), "lat": (63.828, 63.912)})
    ax.set_title("(a) Uplift centre and half maximum ellipse per cycle", loc="left")
    odd = {str(k) for k in cfg["cycles"].get("pattern_outliers", {})}
    lab = lambda r: r.cycle.replace(" (open)", "*")  # noqa: E731
    gs = fig.add_gridspec(3, 1, left=0.57, right=0.99, bottom=0.12, top=0.92, hspace=0.15)
    b = [fig.add_subplot(gs[k]) for k in range(3)]
    x = np.arange(len(pat))
    cols = [cmap(0.9 * (t - t0) / (t1 - t0)) for t in pat.t]
    for k, r in enumerate(pat.itertuples()):
        m = dict(mfc="white" if r.first_epoch in odd else cols[k], mec=cols[k], color=cols[k], ms=4, elinewidth=0.8)
        b[0].errorbar(k - 0.12, r.east_offset_m, r.east_sigma_m, fmt="s", **m)
        b[0].errorbar(k + 0.12, r.north_offset_m, r.north_sigma_m, fmt="o", **m)
        b[1].errorbar(k, r.half_max_major_km, r.axis_sigma_km, fmt="o", **m)
        b[1].errorbar(k, r.half_max_minor_km, r.axis_sigma_km, fmt="v", **m)
        b[2].plot(k, r.corr_with_others, "o", **{q: m[q] for q in ("mfc", "mec", "ms")})
    b[0].set_ylabel("Offset (m)")
    b[0].legend([plt.Line2D([], [], marker=s, ls="", color=viz.INK2, ms=4) for s in "so"], ["east", "north"],
                loc="upper center", bbox_to_anchor=(0.5, 1.08), frameon=False, ncol=2, fontsize=6.5, handletextpad=0.1)
    b[1].set_ylabel("Axes (km)")
    b[1].set_ylim(1.8, 5.6)
    b[0].set_ylim(-1000, 2400)
    b[1].legend([plt.Line2D([], [], marker=s, ls="", color=viz.INK2, ms=4) for s in "ov"], ["major", "minor"],
                loc="upper center", bbox_to_anchor=(0.5, 1.08), frameon=False, ncol=2, fontsize=6.5, handletextpad=0.1)
    b[2].set_ylabel("Shape corr.")
    b[2].set_ylim(0.5, 1.02)
    b[0].set_title("(b) Centre, extent and shape per cycle", loc="left")
    for a in b:
        a.set_xticks(x)
        a.set_xticklabels([lab(r) if a is b[2] else "" for r in pat.itertuples()], rotation=40, ha="right",
                          fontsize=6.5)
        a.grid(axis="y", color="#e4e2dc", lw=0.5)
        a.spines[["top", "right"]].set_visible(False)
        a.set_xlim(-0.5, len(pat) - 0.5)
    b[0].axhline(0, color=viz.INK2, lw=0.5)
    save(fig, out, "fig_pattern")


def anim_vertical(cfg, cubes, out, fps=8):
    """Animated GIF: vertical displacement since the first epoch, one frame per acquisition,
    fixed colour scale (viz.fixed_limits, same as the viewer), with the uplift-centre series."""
    d = cubes["dec"]
    lim = viz.fixed_limits(cfg, cubes)["mm"]
    ys, xs = viz.cropped(d, viz.ZOOM)
    sub = d.isel(lat=ys, lon=xs)
    up = sub["up"].values
    up = np.where(sub["mask"].values > 0, up - up[0], np.nan)
    t = pd.to_datetime(d.time.values)
    c = cfg["sites"]["svartsengi_uplift_centre"]
    cs = viz.window_series(d, "up", c["lat"], c["lon"], 1)
    cs = cs - cs.iloc[0]
    ev = viz.load_events(cfg)
    fig = plt.figure(figsize=(FULL * 0.75, 5.0), dpi=90)
    ax = fig.add_axes([0.08, 0.36, 0.74, 0.58])
    cax = fig.add_axes([0.83, 0.40, 0.022, 0.50])
    tax = fig.add_axes([0.09, 0.07, 0.86, 0.2])
    background(ax, cfg)
    im = ax.imshow(up[0], extent=viz.extent(sub), cmap=cmc.vik, vmin=-lim, vmax=lim, interpolation="nearest", zorder=1)
    map_axes(ax, cfg, zoom=ZOOM)
    cb = fig.colorbar(im, cax=cax, extend="both")
    cb.set_label("Vertical (mm), + up")
    title = ax.set_title("", loc="left", fontsize=9)
    event_lines(tax, ev, coloured=True)
    tax.plot(cs.index, cs.values, "-", lw=0.9, color=viz.INK)
    cur = tax.axvline(t[0], color=viz.INK, lw=1.2)
    dot, = tax.plot([t[0]], [0], "o", ms=4, color=viz.INK)
    tax.set_ylabel("Centre (mm)")
    tax.set_xlim(t[0], t[-1])
    tax.spines[["top", "right"]].set_visible(False)

    def frame(k):
        im.set_data(up[k])
        title.set_text(f"Vertical displacement since {t[0]:%d %b %Y}:  {t[k]:%d %b %Y}")
        cur.set_xdata([t[k], t[k]])
        dot.set_data([t[k]], [cs.iloc[k]])
        return im, title, cur, dot

    # Render frames ourselves and quantise them all to one shared palette without dithering, so
    # unchanged pixels stay identical between frames and GIF delta compression works (~10x smaller).
    from PIL import Image

    def grab(k):
        frame(k)
        fig.canvas.draw()
        return Image.fromarray(np.asarray(fig.canvas.buffer_rgba())[..., :3].copy())

    probe = [grab(k) for k in (0, len(t) // 3, 2 * len(t) // 3, len(t) - 1)]
    mosaic = Image.new("RGB", (probe[0].width, probe[0].height * len(probe)))
    for n, p in enumerate(probe):
        mosaic.paste(p, (0, n * p.height))
    pal = mosaic.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    imgs = [grab(k).quantize(palette=pal, dither=Image.Dither.NONE) for k in range(len(t))]
    f = out / "anim_vertical.gif"
    imgs[0].save(f, save_all=True, append_images=imgs[1:], duration=int(1000 / fps), loop=0, optimize=False,
                 disposal=1)
    plt.close(fig)
    print(f"  {f.name} ({len(t)} frames, ±{lim:.0f} mm)", flush=True)


FIGS = {"study_area": fig_study_area, "los_velocity": fig_los_velocity, "decomp_velocity": fig_decomp_velocity,
        "episodes_maps": fig_episode_maps, "episodes_maps_short": fig_episode_maps_short, "centre_timeseries": fig_centre,
        "gnss_comparison": fig_gnss, "rates": fig_rates, "pattern": fig_pattern,
        "episodes_uplift": fig_episode_uplift, "anim_vertical": anim_vertical}


def main() -> int:
    cfg = load_config()
    out = path(cfg, "figures") / "report"
    out.mkdir(exist_ok=True)
    cubes = viz.open_cubes(cfg)
    names = sys.argv[1:] or list(FIGS)
    for n in names:
        FIGS[n](cfg, cubes, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
