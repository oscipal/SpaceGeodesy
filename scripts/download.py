"""Stage 2: AOI-clipped download of LiCSAR products in LiCSBAS01 layout.

Replaces LiCSBAS01_get_geotiff.py, which downloads whole frames (~110 MB per
unw.tif; ~625 GB for both frames since 2020). LiCSAR GeoTIFFs are stored with
one row per strip, so GDAL /vsicurl/ reads only the AOI rows (~15 MB transferred,
~1 MB written per interferogram).

Output (identical to LiCSBAS01, so LiCSBAS02+ run unchanged):
  data/<frame>/GEOC/<frame>.geo.{E,N,U,hgt}.tif, baselines, metadata.txt, network.png
  data/<frame>/GEOC/<d1>_<d2>/<d1>_<d2>.geo.{unw,cc}.tif
  data/<frame>/GACOS/<date>.sltd.geo.tif            (clipped with a margin)

Resumable and idempotent: finished files are skipped, partial files are written
to *.part and renamed only when complete, unavailable products are recorded in
data/<frame>/download_manifest.json. Work proceeds in yearly chunks.

Usage: python scripts/download.py [--frame FRAME] [--yes]
  --yes  continue even if the on-disk estimate exceeds download.max_gb_per_frame
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from osgeo import gdal

from common import (ROOT, frame_url, http_get, list_ifgs, load_config, path,
                    update_notes)

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_HTTP_TIMEOUT", "90")

TRANSFER_MB_PER_IFG = 15.5     # measured 2026-11-02 on 016A_02504_162118 (unw 14.7 + cc 0.8)
HREF_RE = re.compile(r"href=['\"]([^'\"]+)['\"]")
_lock = threading.Lock()


# --------------------------------------------------------------------------- utils
def setup_log(cfg: dict, frame: str) -> logging.Logger:
    log = logging.getLogger(frame)
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fh = logging.FileHandler(path(cfg, "logs") / f"download_{frame}.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(fh)
    log.addHandler(sh)
    return log


def resolve(entry_url: str, fname: str) -> str | None:
    """LiCSAR entries are HTML indexes since the 2025 storage migration; find the file link."""
    r = http_get(entry_url)
    if r.status_code != 200:
        return None
    for href in HREF_RE.findall(r.text):
        if href.endswith("/" + fname):
            return href
    return None


def valid_tif(p: Path, shape: tuple[int, int] | None = None) -> bool:
    if not p.exists():
        return False
    try:
        ds = gdal.Open(str(p))
        ok = ds is not None and (shape is None or (ds.RasterYSize, ds.RasterXSize) == shape)
        ds = None
        return ok
    except RuntimeError:
        return False


CREATE_OPTS = ["COMPRESS=DEFLATE", "TILED=NO"]


def clip(src_url: str, dst: Path, *, srcwin=None, projwin=None, grid=None,
         resample: str = "bilinear") -> str | None:
    """Clip a remote GeoTIFF onto the AOI grid.

    grid = (full-frame geotransform, full-frame (width, height), AOI geotransform,
    AOI width, AOI height). Returns None (on the reference grid), "header" (pixel
    window cut, reference georeferencing assigned) or "warped" (resampled).

    Older LiCSAR unw files (e.g. 2020 pairs on 016A_02504_162118) have the frame's
    dimensions but a header pixel scale of 0.001*N/(N-1) deg (0.00100014 / 0.00100025)
    and a half-pixel origin shift: an off-by-one in writing the header, not a
    different grid. The cc file of the same pair carries the correct frame
    georeferencing, and stock LiCSBAS reads these files as plain pixel arrays too.
    Such files are cut by pixel window and given the reference georeferencing.
    Only files whose dimensions differ from the frame are warped (LiCSBAS02 would
    otherwise skip them for differing dimensions).
    """
    src = f"/vsicurl/{src_url}"
    part = dst.with_name(dst.name + ".part")
    status = None
    ullr = None
    if grid is not None:
        frame_gt, frame_size, aoi_gt, w, h = grid
        ds = gdal.Open(src)
        gt, size = ds.GetGeoTransform(), (ds.RasterXSize, ds.RasterYSize)
        ds = None
        if any(abs(a - b) > 1e-9 for a, b in zip(gt, frame_gt)):
            if size == tuple(frame_size):
                status = "header"
                ullr = [aoi_gt[0], aoi_gt[3], aoi_gt[0] + w * aoi_gt[1], aoi_gt[3] + h * aoi_gt[5]]
            else:
                bounds = (aoi_gt[0], aoi_gt[3] + h * aoi_gt[5], aoi_gt[0] + w * aoi_gt[1], aoi_gt[3])
                gdal.Warp(str(part), src, outputBounds=bounds, width=w, height=h,
                          resampleAlg=resample, srcNodata=0, dstNodata=0, format="GTiff",
                          creationOptions=CREATE_OPTS)
                part.replace(dst)
                return "warped"
    gdal.Translate(str(part), src, srcWin=srcwin, projWin=projwin, outputBounds=ullr,
                   format="GTiff", creationOptions=CREATE_OPTS)
    part.replace(dst)
    return status


# ----------------------------------------------------------------------- manifest
def load_manifest(wd: Path) -> dict:
    f = wd / "download_manifest.json"
    if f.exists():
        return json.loads(f.read_text())
    return {"missing_ifg": {}, "missing_gacos": {}, "window": None}


def save_manifest(wd: Path, m: dict) -> None:
    with _lock:
        tmp = wd / "download_manifest.json.part"
        tmp.write_text(json.dumps(m, indent=1, sort_keys=True))
        tmp.replace(wd / "download_manifest.json")


# ----------------------------------------------------------------------- steps
def get_metadata(cfg, frame, geoc: Path, man: dict, log) -> tuple[list[int], tuple]:
    a = cfg["aoi"]
    meta = f"{frame_url(cfg, frame)}/metadata"
    hgt = geoc / f"{frame}.geo.hgt.tif"
    if not valid_tif(hgt):
        log.info("clipping hgt to AOI (defines the reference grid)")
        clip(f"{meta}/{frame}.geo.hgt.tif", hgt,
             projwin=[a["lon_min"], a["lat_max"], a["lon_max"], a["lat_min"]])
    # pixel window of the AOI in the full frame grid, derived from the clipped hgt
    src = gdal.Open(f"/vsicurl/{meta}/{frame}.geo.hgt.tif")
    src_gt, src_size = src.GetGeoTransform(), (src.RasterXSize, src.RasterYSize)
    src = None
    ds = gdal.Open(str(hgt))
    gt = ds.GetGeoTransform()
    xoff = round((gt[0] - src_gt[0]) / src_gt[1])
    yoff = round((gt[3] - src_gt[3]) / src_gt[5])
    window = [xoff, yoff, ds.RasterXSize, ds.RasterYSize]
    if man.get("window") not in (None, window):
        raise RuntimeError(f"AOI window changed {man['window']} -> {window}; delete {geoc.parent} "
                           "and re-download (AOI in config.yaml was modified)")
    man["window"] = window
    log.info(f"AOI window (xoff, yoff, w, h) = {window}, pixel {gt[1]:.6f} deg")
    grid = (src_gt, src_size, gt, window[2], window[3])

    for comp in ("E", "N", "U"):
        dst = geoc / f"{frame}.geo.{comp}.tif"
        if not valid_tif(dst, (window[3], window[2])):
            clip(f"{meta}/{frame}.geo.{comp}.tif", dst, srcwin=window, grid=grid)
    for name in ("baselines", "metadata.txt", "network.png"):
        dst = geoc / name
        if not dst.exists():
            r = http_get(f"{meta}/{name}")
            if r.status_code == 200:
                dst.write_bytes(r.content)
            else:
                log.warning(f"{name} not available ({r.status_code})")
    return window, grid


def get_ifg(cfg, frame, geoc, pair, window, grid):
    """Returns (pair, error or None, grid status: None | "header" | "warped")."""
    d = geoc / pair
    d.mkdir(exist_ok=True)
    shape = (window[3], window[2])
    status = None
    for ext, alg in (("unw", "bilinear"), ("cc", "near")):
        dst = d / f"{pair}.geo.{ext}.tif"
        if valid_tif(dst, shape):
            continue
        url = resolve(f"{frame_url(cfg, frame)}/interferograms/{pair}", f"{pair}.geo.{ext}.tif")
        if url is None:
            return pair, f"{ext} unavailable", status
        s = clip(url, dst, srcwin=window, grid=grid, resample=alg)
        status = "warped" if "warped" in (s, status) else (s or status)
    return pair, None, status


def get_gacos(cfg, frame, gdir, date):
    dst = gdir / f"{date}.sltd.geo.tif"
    if valid_tif(dst):
        return date, None, False
    url = resolve(f"{frame_url(cfg, frame)}/epochs/{date}", f"{date}.sltd.geo.tif")
    if url is None:
        return date, "unavailable", False
    a, m = cfg["aoi"], cfg["download"]["gacos_margin_deg"]
    clip(url, dst, projwin=[a["lon_min"] - m, a["lat_max"] + m, a["lon_max"] + m, a["lat_min"] - m])
    return date, None, False


def run_parallel(fn, items, n, log, label):
    """Returns ({item: error}, {item: grid status} for items not on the reference grid)."""
    errors, regridded = {}, {}
    done = 0
    with ThreadPoolExecutor(max_workers=n) as ex:
        futs = {ex.submit(fn, it): it for it in items}
        for fut in as_completed(futs):
            it = futs[fut]
            try:
                _, err, rs = fut.result()
            except Exception as e:      # network/GDAL failure: leave for next run
                err, rs = f"error: {e}", None
            if err:
                errors[it] = err
                log.warning(f"  {label} {it}: {err}")
            if rs:
                regridded[it] = rs
            done += 1
            if done % 100 == 0 or done == len(items):
                log.info(f"  {label}: {done}/{len(items)}")
    return errors, regridded


# ----------------------------------------------------------------------- main
def download_frame(cfg: dict, frame: str, assume_yes: bool) -> dict:
    log = setup_log(cfg, frame)
    dl = cfg["download"]
    wd = path(cfg, "data") / frame
    geoc, gdir = wd / "GEOC", wd / "GACOS"
    geoc.mkdir(parents=True, exist_ok=True)
    man = load_manifest(wd)
    start, end = cfg["time"]["start"], cfg["time"]["end"]
    log.info(f"=== {frame}: {start} to {end}")

    window, grid = get_metadata(cfg, frame, geoc, man, log)
    man.setdefault("regridded_ifg", {})
    save_manifest(wd, man)

    pairs = [f"{a:%Y%m%d}_{b:%Y%m%d}" for a, b in list_ifgs(cfg, frame) if a >= start and b <= end]
    epochs = sorted({d for p in pairs for d in p.split("_")})
    skip = set() if dl.get("retry_missing") else {p for p, e in man["missing_ifg"].items()
                                                  if "unavailable" in e}
    todo = [p for p in pairs if p not in skip
            and not all(valid_tif(geoc / p / f"{p}.geo.{x}.tif") for x in ("unw", "cc"))]

    # volume estimate: measure one clipped pair if none exist yet
    sample = next((geoc / p for p in pairs if (geoc / p / f"{p}.geo.unw.tif").exists()), None)
    if sample is None and todo:
        get_ifg(cfg, frame, geoc, todo[0], window, grid)
        sample = geoc / todo[0]
    per_ifg_mb = sum(f.stat().st_size for f in sample.glob("*.tif")) / 1e6 if sample else 1.0
    est_gb = len(pairs) * per_ifg_mb / 1e3 * 1.15          # +15 % for GACOS and metadata
    xfer_gb = len(todo) * TRANSFER_MB_PER_IFG / 1e3
    free_gb = shutil.disk_usage(wd).free / 1e9
    log.info(f"{len(pairs)} ifgs, {len(epochs)} epochs; {len(todo)} ifgs to fetch, "
             f"{len(skip)} known unavailable")
    log.info(f"expected on disk: {est_gb:.1f} GB ({per_ifg_mb:.2f} MB/ifg); "
             f"to transfer: ~{xfer_gb:.0f} GB; free disk: {free_gb:.0f} GB")
    if est_gb > dl["max_gb_per_frame"] and not assume_yes:
        log.error(f"estimate exceeds cap of {dl['max_gb_per_frame']} GB; re-run with --yes to continue")
        sys.exit(2)
    if est_gb > free_gb * 0.9:
        log.error("not enough free disk space")
        sys.exit(2)

    by_year = defaultdict(list)
    for p in todo:
        by_year[p[9:13]].append(p)
    for year in sorted(by_year):
        log.info(f"-- ifgs ending in {year}: {len(by_year[year])}")
        errs, rs = run_parallel(lambda p: get_ifg(cfg, frame, geoc, p, window, grid),
                                by_year[year], dl["n_parallel"], log, "ifg")
        man["regridded_ifg"].update(rs)
        if rs:
            n_h = sum(v == "header" for v in rs.values())
            log.info(f"  {n_h} ifgs with faulty header georeferencing (cut by pixel window), "
                     f"{len(rs) - n_h} warped onto the reference grid")
        for p, e in errs.items():
            man["missing_ifg"][p] = e
        for p in by_year[year]:
            if p not in errs:
                man["missing_ifg"].pop(p, None)
        save_manifest(wd, man)

    if dl.get("get_gacos"):
        gdir.mkdir(exist_ok=True)
        gskip = set() if dl.get("retry_missing") else set(man["missing_gacos"])
        gtodo = [e for e in epochs if e not in gskip and not valid_tif(gdir / f"{e}.sltd.geo.tif")]
        log.info(f"-- GACOS: {len(gtodo)} epochs to fetch")
        errs, _ = run_parallel(lambda e: get_gacos(cfg, frame, gdir, e), gtodo,
                               dl["n_parallel"], log, "gacos")
        man["missing_gacos"].update(errs)
        for e in gtodo:
            if e not in errs:
                man["missing_gacos"].pop(e, None)
        save_manifest(wd, man)

    n_ok = sum(all(valid_tif(geoc / p / f"{p}.geo.{x}.tif") for x in ("unw", "cc")) for p in pairs)
    n_gacos = len(list(gdir.glob("*.sltd.geo.tif"))) if gdir.exists() else 0
    size_gb = sum(f.stat().st_size for f in wd.rglob("*") if f.is_file()) / 1e9
    summary = {"frame": frame, "ifgs_listed": len(pairs), "ifgs_ok": n_ok,
               "ifgs_missing": len(man["missing_ifg"]), "epochs": len(epochs),
               "ifgs_regridded": man["regridded_ifg"],
               "gacos_ok": n_gacos, "gacos_missing": sorted(man["missing_gacos"]),
               "size_gb": round(size_gb, 2), "window": window}
    log.info(f"done: {summary['ifgs_ok']}/{len(pairs)} ifgs, {n_gacos}/{len(epochs)} GACOS, "
             f"{size_gb:.2f} GB")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frame")
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    cfg = load_config()
    frames = [args.frame] if args.frame else [f for f in cfg["licsar"]["frames"].values() if f]
    summaries = [download_frame(cfg, f, args.yes) for f in frames]

    L = ["## Stage 2: download", "",
         "AOI-clipped download with `scripts/download.py` (GDAL /vsicurl/ windowed reads) "
         "instead of `LiCSBAS01_get_geotiff.py`, which would fetch whole frames "
         "(~450 GB asc + ~175 GB desc since 2020). Output layout is identical to LiCSBAS01.", "",
         f"Time window: {cfg['time']['start']} to {cfg['time']['end']}.", "",
         "| Frame | ifgs listed | ifgs downloaded | ifgs unavailable | epochs | GACOS ok | size (GB) |",
         "|---|---|---|---|---|---|---|"]
    for s in summaries:
        L.append(f"| `{s['frame']}` | {s['ifgs_listed']} | {s['ifgs_ok']} | {s['ifgs_missing']} | "
                 f"{s['epochs']} | {s['gacos_ok']} | {s['size_gb']} |")
    for s in summaries:
        r = s["ifgs_regridded"]
        hdr = sorted(p for p, v in r.items() if v == "header")
        warped = sorted(p for p, v in r.items() if v == "warped")
        if hdr:
            L.append(f"\n`{s['frame']}`: {len(hdr)} ifgs ({hdr[0][:8]} to {hdr[-1][9:]}) have unw "
                     "files with the frame's dimensions but a faulty GeoTIFF header: pixel scale "
                     "0.001*N/(N-1) deg instead of 0.001 (N = frame width/height) and a half-pixel "
                     "origin shift, an off-by-one in the header rather than a different grid. "
                     "Evidence: the cc file of the same pair has the correct frame georeferencing, "
                     "and LiCSAR geocodes to fixed 0.001 deg frame grids. On 016A_02504_162118, 2020 "
                     "and 2024 coherence patterns align to (-0.04, 0.01) px; a test aligning unw "
                     "valid-data masks with cc was too noisy (0.2 to 1.3 px) to decide on its own. "
                     "These files were cut by pixel window and given the reference georeferencing "
                     "(no resampling), which is also how stock LiCSBAS reads them.")
        if warped:
            L.append(f"\n`{s['frame']}`: {len(warped)} ifgs had dimensions different from the frame "
                     "and were warped onto the reference grid (unw bilinear, cc nearest).")
        if r:
            L.append("Full lists in `data/<frame>/download_manifest.json`.")
    for s in summaries:
        if s["gacos_missing"]:
            g = s["gacos_missing"]
            L.append(f"\nGACOS missing for `{s['frame']}` ({len(g)} epochs): "
                     + ", ".join(g[:40]) + (" ..." if len(g) > 40 else ""))
    update_notes(cfg, "download", "\n".join(L))
    return 0 if all(s["ifgs_ok"] + s["ifgs_missing"] == s["ifgs_listed"] for s in summaries) else 1


if __name__ == "__main__":
    sys.exit(main())
