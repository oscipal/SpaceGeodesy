"""Quick-look PNGs of selected single interferograms (before the time-series inversion).

For each pair: LOS displacement (unwrapped phase converted to mm and referenced to the
Straumsvik window), re-wrapped fringes (one colour cycle = lambda/2 = 27.7 mm LOS) and coherence,
plus a hillshade per frame. Writes results/quicklook/*.png and quicklook.json for the viewer.

Usage: python scripts/export_quicklook.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from osgeo import gdal

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from cmcrameri import cm as cmc

from common import load_config, path

ASC, DESC = "016A_02504_162118", "155D_02484_191814"
WAVELENGTH = 0.055465764662349676          # m, Sentinel-1 C-band (from LiCSBAS slc.mli.par)
R2MM = -WAVELENGTH / (4 * np.pi) * 1000    # rad -> mm, positive = towards the satellite (LiCSBAS convention)

# (frame, pair, label, what the pair spans); dates from config/events.csv
PAIRS = [
    (ASC, "20200126_20200225", "Svartsengi inflation 2020", "First of the 2020 Svartsengi inflation episodes (onset 21 Jan 2020)."),
    (ASC, "20210219_20210225", "Fagradalsfjall dike, Feb 2021", "Dike intrusion that began on 24 Feb 2021 and led to the March 2021 eruption."),
    (ASC, "20220720_20220801", "Fagradalsfjall dike, Jul 2022", "Dike intrusion on 30 Jul 2022 ahead of the August 2022 eruption."),
    (ASC, "20231019_20231031", "Svartsengi inflation, Oct 2023", "Renewed uplift at Svartsengi, onset about 28 Oct 2023."),
    (ASC, "20231031_20231112", "Grindavik dike, 10 Nov 2023", "The 15 km dike under Sundhnukur and Grindavik on 10 Nov 2023; graben subsidence and opening."),
    (DESC, "20231110_20231122", "Grindavik dike (descending)", "Same intrusion seen from the descending track, plus the first rebound of Svartsengi."),
    (DESC, "20231216_20231228", "Eruption 18 Dec 2023", "First Sundhnukur eruption (18-21 Dec 2023)."),
    (ASC, "20240111_20240123", "Eruption 14 Jan 2024", "Eruption next to Grindavik (14-16 Jan 2024)."),
    (ASC, "20240204_20240216", "Eruption 8 Feb 2024", "Short eruption on 8-9 Feb 2024."),
    (ASC, "20240311_20240323", "Eruption 16 Mar 2024", "Start of the longest eruption (16 Mar - 9 May 2024)."),
    (ASC, "20240428_20240522", "Inflation before May 2024", "Uplift at Svartsengi between eruptions, recharge of the reservoir."),
    (ASC, "20240522_20240603", "Eruption 29 May 2024", "Eruption of 29 May - 22 Jun 2024."),
    (DESC, "20240520_20240601", "Eruption 29 May 2024 (descending)", "Same event from the descending track."),
    (ASC, "20240814_20240826", "Eruption 22 Aug 2024", "Eruption of 22 Aug - 6 Sep 2024."),
    (ASC, "20241118_20241212", "Eruption 20 Nov 2024", "Eruption of 20 Nov - 8 Dec 2024 (24-day pair, 12-day sampling gap)."),
    (ASC, "20250330_20250405", "Eruption 1 Apr 2025", "Short eruption and dike on 1 Apr 2025."),
    (ASC, "20250710_20250716", "Eruption 16 Jul 2025", "Eruption of 16 Jul - 5 Aug 2025."),
    (DESC, "20260122_20260203", "Latest descending pair", "Most recent descending pair processed by LiCSAR (track ends 3 Feb 2026)."),
    (ASC, "20260904_20260916", "Latest ascending pair", "Most recent ascending pair in our download."),
]


def read(p: Path):
    ds = gdal.Open(str(p))
    a = ds.GetRasterBand(1).ReadAsArray().astype("float32")
    return a, ds.GetGeoTransform()


def extent(gt, shape):
    h, w = shape
    return [gt[0], gt[0] + gt[1] * w, gt[3] + gt[5] * h, gt[3]]  # W, E, S, N


def ref_value(d, gt, lat, lon, win):
    r, c = int(round((lat - gt[3]) / gt[5])), int(round((lon - gt[0]) / gt[1]))
    h = win // 2
    v = d[max(r - h, 0):r + h + 1, max(c - h, 0):c + h + 1]
    return float(np.nanmedian(v)) if np.isfinite(v).any() else None


def rgba(arr, cmap, vmin, vmax):
    out = cmap(np.clip((arr - vmin) / (vmax - vmin), 0, 1))
    out[~np.isfinite(arr), 3] = 0
    return out


def hillshade(hgt, gt):
    dy = abs(gt[5]) * 111320.0
    dx = gt[1] * 111320.0 * np.cos(np.radians(gt[3] + gt[5] * hgt.shape[0] / 2))
    gy, gx = np.gradient(np.nan_to_num(hgt), dy, dx)
    slope, aspect = np.arctan(np.hypot(gx, gy) * 2), np.arctan2(-gx, gy)
    az, alt = np.radians(315), np.radians(45)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    out = np.dstack([np.clip(hs, 0, 1)] * 3 + [np.ones_like(hs)])
    out[(hgt <= 0.5) | ~np.isfinite(hgt), 3] = 0  # sea
    return out


def main():
    cfg = load_config()
    ref = cfg["licsbas"]["reference_point"]
    out = path(cfg, "results") / "quicklook"
    out.mkdir(parents=True, exist_ok=True)
    meta = {"reference": {"lat": ref["lat"], "lon": ref["lon"], "window_px": ref["window_px"]},
            "sites": cfg.get("sites", {}), "frames": {}, "pairs": []}
    for name, cmap in (("vik", cmc.vik), ("romaO", cmc.romaO), ("grayC_r", cmc.grayC_r)):
        plt.imsave(out / f"cbar_{name}.png", np.repeat(cmap(np.linspace(0, 1, 256))[None], 8, axis=0))
    for fr in (ASC, DESC):
        hgt, gt = read(path(cfg, "data") / fr / "GEOC" / f"{fr}.geo.hgt.tif")
        plt.imsave(out / f"hillshade_{fr}.png", hillshade(hgt, gt))
        meta["frames"][fr] = {"extent": extent(gt, hgt.shape), "shape": list(hgt.shape),
                              "orbit": "ascending" if "A_" in fr else "descending"}
    for fr, pair, label, note in PAIRS:
        g = path(cfg, "data") / fr / "GEOC" / pair
        unw, gt = read(g / f"{pair}.geo.unw.tif")
        cc, _ = read(g / f"{pair}.geo.cc.tif")
        bad = ~np.isfinite(unw) | (unw == 0)
        d = np.where(bad, np.nan, unw * R2MM)
        r = ref_value(d, gt, ref["lat"], ref["lon"], ref["window_px"])
        d = d - (r if r is not None else np.nanmedian(d))
        lim = float(max(10.0, np.ceil(np.nanpercentile(np.abs(d), 99) / 10) * 10))
        plt.imsave(out / f"{fr}_{pair}_disp.png", rgba(d, cmc.vik, -lim, lim))
        plt.imsave(out / f"{fr}_{pair}_fringe.png", rgba(np.mod(d, WAVELENGTH / 2 * 1000), cmc.romaO, 0, WAVELENGTH / 2 * 1000))
        ccn = cc / 255.0 if np.nanmax(cc) > 1.5 else cc
        plt.imsave(out / f"{fr}_{pair}_coh.png", rgba(np.where(ccn > 0, ccn, np.nan), cmc.grayC_r, 0, 1))
        d1, d2 = pair.split("_")
        days = int((np.datetime64(f"{d2[:4]}-{d2[4:6]}-{d2[6:]}") - np.datetime64(f"{d1[:4]}-{d1[4:6]}-{d1[6:]}")).astype(int))
        meta["pairs"].append({
            "frame": fr, "pair": pair, "label": label, "note": note, "days": days,
            "orbit": meta["frames"][fr]["orbit"], "extent": extent(gt, unw.shape), "lim_mm": lim,
            "max_toward_mm": round(float(np.nanpercentile(d, 99.9)), 1),
            "max_away_mm": round(float(np.nanpercentile(d, 0.1)), 1),
            "valid_frac": round(float(np.mean(~bad)), 3),
            "mean_coh": round(float(np.nanmean(np.where(ccn > 0, ccn, np.nan))), 2),
            "ref_ok": r is not None,
        })
        print(pair, fr[:4], f"lim {lim:.0f} mm, valid {np.mean(~bad):.2f}", flush=True)
    (out / "quicklook.json").write_text(json.dumps(meta, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
