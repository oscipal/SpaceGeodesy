"""Stage 5b: static report figures (PDF + PNG) in figures/report/.

1 study_area          frames, AOI, reference point, sites, exclusion zones, GNSS stations
2 los_velocity        mean LOS velocity, ascending and descending
3 decomp_velocity     vertical and east-west velocity (linear fit over the common period)
4 episodes_maps       cumulative vertical displacement in selected inflation episodes
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
def fig_study_area(cfg, cubes, out):
    from shapely.geometry import box
    fig, (a, b) = plt.subplots(1, 2, figsize=(FULL, 3.1), gridspec_kw={"width_ratios": [1, 1.25]})
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
    a.set_title("(a) LiCSAR frames and area of interest", loc="left")
    # (b) AOI detail
    ds = cubes["asc"]
    background(b, cfg, ds)
    for name, z in cfg["exclusion_zones"].items():
        b.add_patch(plt.Rectangle((z["lon_min"], z["lat_min"]), z["lon_max"] - z["lon_min"], z["lat_max"] - z["lat_min"],
                                  fill=False, ec=viz.INK2, lw=0.8, ls="--", zorder=2))
        b.text(z["lon_min"] + 0.005, z["lat_max"] - 0.004, {"fagradalsfjall": "Fagradalsfjall", "sundhnukur_grindavik": "Sundhnúkur/Grindavík", "krysuvik": "Krýsuvík"}.get(name, name), fontsize=6,
               va="top", color=viz.INK, zorder=3)
    map_axes(b, cfg)
    s, rp = cfg["sites"], cfg["licsbas"]["reference_point"]
    for lab, (lo, la), dx in (("uplift centre", (s["svartsengi_uplift_centre"]["lon"], s["svartsengi_uplift_centre"]["lat"]), 0.01),
                             ("Grindavík", (s["grindavik"]["lon"], s["grindavik"]["lat"]), 0.01),
                             ("reference (Straumsvík)", (rp["lon"], rp["lat"] - 0.012), -0.01)):
        b.text(lo + dx, la + 0.004, lab, fontsize=6.5, ha="left" if dx > 0 else "right", color=viz.INK, zorder=6)
    for st in viz.gnss_stations(cfg):
        b.text(st["lon"] + 0.008, st["lat"], st["id"], fontsize=6, color=viz.INK, zorder=6)
    b.set_xlim(A["lon_min"], A["lon_max"])
    b.set_ylim(A["lat_min"], A["lat_max"])
    b.set_title("(b) Study area (hillshade of the LiCSAR DEM)", loc="left")
    fig.tight_layout()
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
    fig, axs = plt.subplots(3, 1, figsize=(FULL, 5.4), sharex=True, gridspec_kw={"height_ratios": [1.1, 1.1, 0.8]})
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
    fig = plt.figure(figsize=(FULL, 3.3))
    ax = fig.add_axes([0.075, 0.15, 0.53, 0.72])
    bx = fig.add_axes([0.70, 0.15, 0.28, 0.72])
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
    for comp, (col, mk, lab) in style.items():
        x = e[e.component == comp]
        rms = float(np.sqrt((x.diff_mm ** 2).mean()))
        bx.plot(x.gnss_mm, x.insar_mm, mk, ms=3, mfc="none", mec=col, mew=0.7,
                label=f"{lab}: n={len(x)}, RMS {rms:.0f} mm")
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
        "episodes_maps": fig_episode_maps, "centre_timeseries": fig_centre, "gnss_comparison": fig_gnss,
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
