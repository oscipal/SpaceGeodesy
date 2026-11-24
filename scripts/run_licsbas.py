"""Stage 3: LiCSBAS time series per frame, driven by config.yaml.

Phases (each frame):
  A  copy data/<frame>/{GEOC,GACOS} into the work dir, generate batch_LiCSBAS.sh
     from the LiCSBAS template, run steps 02-11 (multilook, GACOS, unw check)
  R  choose ONE reference window common to both frames (or use the one in
     config.yaml) and write it as TS_*/info/120ref.txt, which steps 12 and 13
     read instead of auto-selecting a reference
  B  run steps 12-16 (loop closure, SB inversion, vel std, mask, filter)
  E  export cum.h5, cum_filt.h5, result rasters and info to results/licsbas/<frame>/,
     QC figures to figures/qc/<frame>/, summary to docs/processing_notes.md

Work dir: $LICSBAS_WORK/<frame> (a Docker volume, see dc.ps1), else data/<frame>.
Phases are skipped when their outputs exist and the parameters are unchanged;
use --force to redo everything.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from common import CONFIG_PATH, ROOT, load_config, path, update_notes

TEMPLATE = Path(os.environ.get("LICSBAS_DIR", "/opt/LiCSBAS")) / "batch_LiCSBAS.sh"


# ------------------------------------------------------------------ helpers
def workdir(cfg, frame) -> Path:
    base = os.environ.get("LICSBAS_WORK")
    d = Path(base) / frame if base else path(cfg, "data") / frame
    d.mkdir(parents=True, exist_ok=True)
    return d


def geocml(cfg) -> str:
    lb = cfg["licsbas"]
    d = f"GEOCml{lb['n_look']}"
    if lb.get("gacos"):
        d += "GACOS"
    if lb.get("mask"):
        d += "mask"
    return d


def sync_tree(src: Path, dst: Path) -> int:
    """Copy files missing or different in size; returns number copied."""
    n = 0
    for root, _, files in os.walk(src):
        r = Path(root)
        out = dst / r.relative_to(src)
        out.mkdir(parents=True, exist_ok=True)
        for f in files:
            if f.endswith(".part"):
                continue
            s, t = r / f, out / f
            if not t.exists() or t.stat().st_size != s.stat().st_size:
                # buffered copy: os.sendfile (used by shutil.copy2) fails with ENOMEM
                # on Docker Desktop bind mounts under page-cache pressure
                with open(s, "rb") as fi, open(t, "wb") as fo:
                    shutil.copyfileobj(fi, fo, 1 << 20)
                shutil.copystat(s, t)
                n += 1
    return n


def params_hash(d: dict) -> str:
    return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:12]


def read_par(p: Path) -> dict:
    out = {}
    for line in p.read_text().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.split()[0] if v.split() else ""
    return out


class Grid:
    """Geographic grid of a GEOCml/TS dir from EQA.dem_par (pixel centres)."""

    def __init__(self, dem_par: Path):
        p = read_par(dem_par)
        self.width, self.length = int(p["width"]), int(p["nlines"])
        self.lat0, self.lon0 = float(p["corner_lat"]), float(p["corner_lon"])
        self.dlat, self.dlon = float(p["post_lat"]), float(p["post_lon"])

    def latlon(self):
        lats = self.lat0 + self.dlat * np.arange(self.length)
        lons = self.lon0 + self.dlon * np.arange(self.width)
        return lats, lons

    def rc(self, lat, lon):
        return int(round((lat - self.lat0) / self.dlat)), int(round((lon - self.lon0) / self.dlon))

    def read(self, f: Path, dtype="float32"):
        return np.fromfile(f, dtype=dtype).reshape(self.length, self.width)


def run(cmd: list[str], cwd: Path, log: Path) -> None:
    print(f"$ {' '.join(cmd)}  (cwd {cwd}, log {log})", flush=True)
    with open(log, "a", encoding="utf-8") as lf:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            lf.write(line)
            lf.flush()      # keep the log current for monitoring
            if re.search(r"Successfully finished|Error|error|Traceback|Start step|LiCSBAS\d+", line):
                print("   " + line.rstrip(), flush=True)
        if p.wait() != 0:
            raise SystemExit(f"command failed ({p.returncode}): {' '.join(cmd)}; see {log}")


# ------------------------------------------------------------ batch script
STEP12_OVERRIDES = {"loop_thre", "nullify"}


def batch_vars(cfg, start: str, end: str, frame: str | None = None) -> dict:
    """Batch-script variables; `frame` applies licsbas.frame_overrides (step 12 only)."""
    lb, fl = cfg["licsbas"], cfg["licsbas"]["filter"]
    ov = (lb.get("frame_overrides") or {}).get(frame) or {} if frame else {}
    if set(ov) - STEP12_OVERRIDES:
        raise SystemExit(f"frame_overrides.{frame}: only {sorted(STEP12_OVERRIDES)} allowed, got {sorted(ov)}")
    th = {**lb["thresholds"], **{k: ov[k] for k in ("loop_thre",) if k in ov}}
    v = {
        "start_step": start, "end_step": end,
        "nlook": str(lb["n_look"]),
        "n_para": str(lb.get("n_para") or ""),
        "do03op_GACOS": "y" if lb.get("gacos") else "n",
        "do04op_mask": "y" if lb.get("mask") else "n",
        # AOI clipping already happens in scripts/download.py
        "do05op_clip": "n",
        "p11_unw_thre": th.get("unw_thre"), "p11_coh_thre": th.get("coh_thre"),
        "p12_loop_thre": th.get("loop_thre"),
        "p15_n_ifg_noloop_thre": th.get("n_ifg_noloop_thre"),
        "p16_filtwidth_km": fl.get("filtwidth_km"), "p16_filtwidth_yr": fl.get("filtwidth_yr"),
        "p13_mem_size": lb.get("mem_size_mb"),
    }
    if ov.get("nullify"):
        # only set when used, so the parameter hash of frames without it stays unchanged
        v["p12_nullify"] = "y"
    if int(start) > 10:
        # the template only derives the GACOS/mask dir name while running steps 03-05
        v["GEOCmldir"] = geocml(cfg)
    if lb.get("skip_pngs"):
        # per-loop / per-ifg PNGs (tens of thousands); summary QC figures are still made
        v.update(p12_skippngs="y", p13_skippngs="y", p16_skippngs="y")
    return {k: ("" if x is None else str(x)) for k, x in v.items()}


def result_vars(cfg, start, end, frame=None) -> dict:
    """batch_vars without options that do not change the numerical results."""
    return {k: v for k, v in batch_vars(cfg, start, end, frame).items()
            if not k.endswith("skippngs") and k not in ("n_para", "p13_mem_size")}


def write_batch(cfg, wd: Path, start: str, end: str, frame=None) -> Path:
    text = TEMPLATE.read_text()
    for k, val in batch_vars(cfg, start, end, frame).items():
        text, n = re.subn(rf'^{k}=("[^"]*"|\'[^\']*\'|\S*)', f'{k}="{val}"', text, count=1, flags=re.M)
        if n != 1:
            raise SystemExit(f"variable {k} not found in {TEMPLATE}")
    f = wd / f"batch_LiCSBAS_{start}_{end}.sh"
    f.write_text(text)
    f.chmod(0o755)
    return f


# ----------------------------------------------------------------- phases
def phase_a(cfg, frame, force=False) -> Path:
    wd = workdir(cfg, frame)
    src = path(cfg, "data") / frame
    if wd.resolve() != src.resolve():
        for sub in ("GEOC", "GACOS"):
            if (src / sub).exists():
                n = sync_tree(src / sub, wd / sub)
                print(f"[{frame}] synced {sub}: {n} files copied to {wd}", flush=True)
    man = json.loads((src / "download_manifest.json").read_text())
    if cfg["licsbas"].get("gacos") and man.get("missing_gacos"):
        print(f"[{frame}] WARNING GACOS missing for {len(man['missing_gacos'])} epochs: "
              f"{sorted(man['missing_gacos'])[:20]} ...", flush=True)
    # p15_* (masking) cannot affect steps 02-11; left out so changing it keeps phase A (and steps 12-13)
    rv = {k: v for k, v in result_vars(cfg, "02", "11").items() if not k.startswith("p15_")}
    key = params_hash({"v": rv, "n_ifg": len(list((wd / "GEOC").glob("2*_2*")))})
    marker = wd / ".phaseA"
    ts = wd / f"TS_{geocml(cfg)}"
    if not force and marker.exists() and marker.read_text() == key and (ts / "info/11bad_ifg.txt").exists():
        print(f"[{frame}] phase A up to date", flush=True)
        return ts
    # step 12 --nullify keeps the original as *.unw.ori and reads that on later runs; after
    # steps 02-11 rewrite the .unw files those backups are stale
    for f in (wd / geocml(cfg)).glob("*/*.unw.ori"):
        f.unlink()
    run(["bash", write_batch(cfg, wd, "02", "11").name], wd, path(cfg, "logs") / f"licsbas_{frame}_02_11.log")
    (ts / "refstats.npz").unlink(missing_ok=True)
    marker.write_text(key)
    return ts


def ref_stats(cfg, frame) -> tuple[Grid, np.ndarray, np.ndarray, int]:
    """Mean coherence and unwrapped fraction over ifgs that passed step 11."""
    wd = workdir(cfg, frame)
    gdir, ts = wd / geocml(cfg), wd / f"TS_{geocml(cfg)}"
    cache = ts / "refstats.npz"
    g = Grid(gdir / "EQA.dem_par")
    if cache.exists():
        z = np.load(cache)
        return g, z["coh"], z["unw"], int(z["n"])
    bad = set((ts / "info/11bad_ifg.txt").read_text().split())
    ifgs = sorted(p.name for p in gdir.glob("2*_2*") if p.is_dir() and p.name not in bad)
    coh = np.zeros((g.length, g.width))
    unw = np.zeros((g.length, g.width))
    for p in ifgs:
        c = g.read(gdir / p / f"{p}.cc", "uint8").astype(float) / 255.0
        u = g.read(gdir / p / f"{p}.unw")
        coh += c
        unw += np.isfinite(u) & (u != 0)
    coh /= len(ifgs)
    unw /= len(ifgs)
    np.savez(cache, coh=coh, unw=unw, n=len(ifgs))
    return g, coh, unw, len(ifgs)


def in_box(lat, lon, b, buf=0.0):
    return (b["lat_min"] - buf <= lat <= b["lat_max"] + buf) and (b["lon_min"] - buf <= lon <= b["lon_max"] + buf)


def km(lat1, lon1, lat2, lon2):
    dy = (lat2 - lat1) * 111.2
    dx = (lon2 - lon1) * 111.2 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot(dx, dy)


def choose_reference(cfg, frames) -> dict:
    lb = cfg["licsbas"]
    rp = lb.get("reference_point")
    if rp and rp.get("source") == "manual":
        print(f"using manual reference point {rp}", flush=True)
        return rp
    rs = lb.get("reference_selection", {})
    half = rs.get("window_px", 5) // 2
    min_km = rs.get("min_distance_km", 15)
    min_unw = rs.get("min_unw_fraction", 0.95)
    buf = rs.get("exclusion_buffer_deg", 0.01)
    centre = cfg["sites"]["svartsengi_uplift_centre"]
    stats = {f: ref_stats(cfg, f) for f in frames}
    g0 = stats[frames[0]][0]
    lats, lons = g0.latlon()
    best = None
    for i in range(half, g0.length - half, 2):
        for j in range(half, g0.width - half, 2):
            lat, lon = lats[i], lons[j]
            if km(lat, lon, centre["lat"], centre["lon"]) < min_km:
                continue
            if any(in_box(lat, lon, z, buf) for z in cfg["exclusion_zones"].values()):
                continue
            score, ok = [], True
            for f in frames:
                g, coh, unw, _ = stats[f]
                r, c = g.rc(lat, lon)
                if not (half <= r < g.length - half and half <= c < g.width - half):
                    ok = False
                    break
                win_u = unw[r - half:r + half + 1, c - half:c + half + 1]
                if win_u.min() < min_unw:
                    ok = False
                    break
                score.append(coh[r - half:r + half + 1, c - half:c + half + 1].mean())
            if ok and (best is None or min(score) > best[0]):
                best = (min(score), lat, lon, score)
    if best is None:
        raise SystemExit("no reference window satisfies the constraints; set licsbas.reference_point manually")
    s, lat, lon, per = best
    out = {"lat": round(float(lat), 4), "lon": round(float(lon), 4), "window_px": 2 * half + 1,
           "source": "auto",
           "mean_coh": {f: round(float(x), 3) for f, x in zip(frames, per)},
           "distance_km": round(km(lat, lon, centre["lat"], centre["lon"]), 1)}
    write_reference_to_config(out)
    return out


def write_reference_to_config(rp: dict) -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    val = json.dumps(rp, separators=(", ", ": ")).replace('"', "")
    text, n = re.subn(r"^(\s+reference_point:)[^\n#]*(#[^\n]*)?",
                      lambda m: f"{m.group(1)} {val}  # auto-selected by run_licsbas.py; set source: manual to override",
                      text, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("reference_point not found in config.yaml")
    CONFIG_PATH.write_text(text, encoding="utf-8")


def write_120ref(cfg, frame, rp) -> str:
    wd = workdir(cfg, frame)
    g = Grid(wd / geocml(cfg) / "EQA.dem_par")
    r, c = g.rc(rp["lat"], rp["lon"])
    h = rp["window_px"] // 2
    area = f"{c - h}:{c + h + 1}/{r - h}:{r + h + 1}"
    (wd / f"TS_{geocml(cfg)}" / "info" / "120ref.txt").write_text(area + "\n")
    return area


def phase_b(cfg, frame, rp, force=False) -> Path:
    wd = workdir(cfg, frame)
    ts = wd / f"TS_{geocml(cfg)}"
    area = write_120ref(cfg, frame, rp)
    rv, a = result_vars(cfg, "12", "16", frame), (wd / ".phaseA").read_text()
    key = params_hash({"v": rv, "ref": area, "a": a})
    # steps 12-13 (a day of computing) depend only on these; step 14-16 options may change on their own
    key13 = params_hash({"v": {k: v for k, v in rv.items() if not k.startswith(("p14_", "p15_", "p16_"))},
                         "ref": area, "a": a})
    marker, marker13 = wd / ".phaseB", wd / ".phaseB13"
    if not force and marker.exists() and marker.read_text() == key and (ts / "cum_filt.h5").exists():
        print(f"[{frame}] phase B up to date", flush=True)
        return ts, area
    if marker.exists() and not marker13.exists():
        # runs finished before .phaseB13 existed: their marker hashed all variables without the p15 ones
        legacy = params_hash({"v": {k: v for k, v in rv.items() if not k.startswith("p15_")}, "ref": area, "a": a})
        if marker.read_text() == legacy:
            marker13.write_text(key13)
    print(f"[{frame}] reference area (x1:x2/y1:y2) {area}", flush=True)
    # Resumable in three parts; .phaseB_progress holds "<key> <last finished part>".
    # Step 13 takes ~1 day on this machine and stores each finished patch, so after an
    # interruption (sleep, Docker restart) it continues with --load_patches. This needs the
    # image's docker/patch_licsbas13.py and LICSBAS13_CUM_IN_MEMORY=1: upstream LiCSBAS
    # cannot resume when --mem_size is small enough to avoid running out of memory.
    log = path(cfg, "logs") / f"licsbas_{frame}_12_16.log"
    prog = wd / ".phaseB_progress"
    done = prog.read_text().split() if prog.exists() else []
    done = done[1] if len(done) == 2 and done[0] == key13 and not force else ""
    if not force and marker13.exists() and marker13.read_text() == key13 and (ts / "cum.h5").exists():
        done = "13"
        print(f"[{frame}] steps 12-13 up to date, redoing 14-16", flush=True)
    if done not in ("12", "13"):
        run(["bash", write_batch(cfg, wd, "12", "12", frame).name], wd, log)
        for f in ("cum", "vel", "vintercept", "resid_rms", "n_gap", "n_ifg_noloop", "maxTlen",
                  "gap_patches"):                   # stale patches from an older step 13
            (ts / "results" / f).unlink(missing_ok=True)
        marker13.unlink(missing_ok=True)
        prog.write_text(f"{key13} 12")
        done = "12"
    if done == "12":
        bv = batch_vars(cfg, "13", "13")
        cmd = ["LiCSBAS13_sb_inv.py", "-d", geocml(cfg), "--load_patches"]
        if bv["p13_mem_size"]:
            cmd += ["--mem_size", bv["p13_mem_size"]]
        if bv["n_para"]:
            cmd += ["--n_para", bv["n_para"]]
        if cfg["licsbas"].get("skip_pngs"):
            cmd.append("--nopngs")
        os.environ["LICSBAS13_CUM_IN_MEMORY"] = "1"   # resumable with small patches
        run(cmd, wd, log)
        prog.write_text(f"{key13} 13")
        marker13.write_text(key13)
    run(["bash", write_batch(cfg, wd, "14", "16", frame).name], wd, log)
    marker.write_text(key)
    prog.unlink(missing_ok=True)
    return ts, area


# ------------------------------------------------------------------ export
def rereference(h5file: Path, area: str) -> dict:
    """Re-reference cum and vel in an exported cum*.h5 to our reference window.

    LiCSBAS13 and 16 always re-reference cum/vel to an automatically chosen
    single pixel (lowest RMS w.r.t. the median; info/13ref.txt), which may lie
    anywhere in the scene. The 120ref.txt window only sets the reference used
    during the inversion. Subtracting the window mean per epoch is exact.
    """
    import h5py

    x1, x2, y1, y2 = [int(s) for s in re.split("[:/]", area)]
    with h5py.File(h5file, "r+") as h:
        old = h["refarea"][()]
        old = old.decode() if isinstance(old, bytes) else str(old)
        cum = h["cum"][()]
        ref_ts = np.nanmean(cum[:, y1:y2, x1:x2], axis=(1, 2))
        n_valid = int(np.isfinite(cum[:, y1:y2, x1:x2]).all(axis=0).sum())
        if not np.isfinite(ref_ts).all():
            raise SystemExit(f"{h5file}: reference window {area} has epochs without data")
        h["cum"][...] = cum - ref_ts[:, None, None]
        vel = h["vel"][()]
        vref = float(np.nanmean(vel[y1:y2, x1:x2]))
        h["vel"][...] = vel - vref
        for k, v in (("refarea", area), ("refarea_licsbas", old)):
            if k in h:
                del h[k]
            h.create_dataset(k, data=v)
    return {"licsbas_ref": old, "window_px_valid_all_epochs": n_valid,
            "vel_offset_mm_yr": round(vref, 2)}


def export(cfg, frame, ts: Path, area: str) -> dict:
    res = path(cfg, "results") / "licsbas" / frame
    qc = path(cfg, "figures") / "qc" / frame
    for d in (res, qc):
        d.mkdir(parents=True, exist_ok=True)
    reref = {}
    for f in ("cum.h5", "cum_filt.h5"):
        shutil.copy2(ts / f, res / f)
        reref[f] = rereference(res / f, area)
    for sub in ("results", "info"):
        if (ts / sub).exists():
            shutil.copytree(ts / sub, res / sub, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("*.png", "*.kml"))
    shutil.copy2(workdir(cfg, frame) / geocml(cfg) / "EQA.dem_par", res / "EQA.dem_par")
    # velocity rasters (vel, vel.mskd, vel.filt, ...) carry the LiCSBAS auto reference too
    g = Grid(res / "EQA.dem_par")
    x1, x2, y1, y2 = [int(s) for s in re.split("[:/]", area)]
    for f in sorted((res / "results").glob("vel*")):
        if f.suffix:            # skip e.g. .png/.kml (binaries have no extension)
            continue
        v = g.read(f)
        off = np.nanmean(v[y1:y2, x1:x2])
        if np.isfinite(off):
            (v - off).astype("float32").tofile(f)
    n_png = 0
    for sub in ("", "results", "info", "network", "12loop"):
        src = ts / sub
        if not src.exists():
            continue
        for p in src.glob("*.png"):
            dst = qc / (f"{sub}_{p.name}" if sub else p.name)
            shutil.copy2(p, dst)
            n_png += 1
    s = summarise(cfg, frame, ts, res, n_png)
    s["refarea"] = area
    s["rereference"] = reref
    return s


def bad_list(f: Path) -> list[str]:
    return f.read_text().split() if f.exists() else []


def summarise(cfg, frame, ts: Path, res: Path, n_png: int) -> dict:
    import h5py

    g = Grid(res / "EQA.dem_par")
    wd = workdir(cfg, frame)
    all_ifgs = sorted(p.name for p in (wd / geocml(cfg)).glob("2*_2*") if p.is_dir())
    bad11 = bad_list(ts / "info/11bad_ifg.txt")
    bad12 = bad_list(ts / "info/12bad_ifg.txt")
    bad = set(bad11) | set(bad12)
    with h5py.File(ts / "cum.h5", "r") as h:
        imdates = [str(d) for d in h["imdates"][()]]
        refarea = h["refarea"][()] if "refarea" in h else None
    mask = g.read(ts / "results/mask")
    hgt = g.read(ts / "results/hgt") if (ts / "results/hgt").exists() else None
    land = np.isfinite(hgt) & (hgt != 0) if hgt is not None else np.ones_like(mask, bool)
    valid = np.isfinite(mask) & (mask > 0)
    per_year = {}
    for y in sorted({p[9:13] for p in all_ifgs}):
        ys = [p for p in all_ifgs if p[9:13] == y]
        per_year[y] = {"ifgs": len(ys), "bad11": sum(p in set(bad11) for p in ys),
                       "bad12": sum(p in set(bad12) for p in ys)}
    by_month = Counter(p[9:15] for p in bad)
    nullify = None
    if (ts / "results/n_nullify_rat").exists() and (lb_ov := (cfg["licsbas"].get("frame_overrides") or {})
                                                    .get(frame, {})).get("nullify"):
        rat = g.read(ts / "results/n_nullify_rat")[land]
        nullify = {"median": round(float(np.nanmedian(rat)), 3), "p95": round(float(np.nanpercentile(rat, 95)), 3),
                   "over_half": round(float(np.nanmean(rat > 0.5)), 3), "loop_thre": lb_ov.get("loop_thre")}
    return {
        "nullify": nullify,
        "frame": frame, "epochs": len(imdates), "first": imdates[0], "last": imdates[-1],
        "ifgs_total": len(all_ifgs), "ifgs_used": len(all_ifgs) - len(bad),
        "bad11": len(bad11), "bad12": len(bad12),
        "masked_fraction_land": round(float(1 - valid[land].mean()), 3),
        "refarea": refarea.decode() if isinstance(refarea, bytes) else str(refarea),
        "per_year": per_year, "worst_months": by_month.most_common(6), "qc_pngs": n_png,
    }


def write_notes(cfg, summaries, rp) -> None:
    lb = cfg["licsbas"]
    L = ["## Stage 3: LiCSBAS time series", "",
         f"Generated by `scripts/run_licsbas.py` on {dt.date.today()}. LiCSBAS {geocml(cfg)} "
         f"(n_look={lb['n_look']}, GACOS {'on' if lb.get('gacos') else 'off'}, mask "
         f"{'on' if lb.get('mask') else 'off'}; AOI clip done at download). Thresholds: LiCSBAS defaults "
         "unless set in config.yaml.", "",
         "### Reference point", "",
         f"- lat {rp['lat']}, lon {rp['lon']}, {rp['window_px']}x{rp['window_px']} px window "
         f"({rp['window_px'] * 100} m), {rp.get('distance_km', '?')} km from the Svartsengi uplift centre "
         f"(source: {rp.get('source')}).",
         "- Selection: the window with the highest mean coherence (minimum over both frames) among windows "
         "at least "
         f"{lb.get('reference_selection', {}).get('min_distance_km', 15)} km from the uplift centre, outside "
         "all exclusion zones (Fagradalsfjall, Sundhnukur/Grindavik, Krysuvik), with every pixel unwrapped "
         f"in at least {lb.get('reference_selection', {}).get('min_unw_fraction', 0.95):.0%} of the "
         "interferograms that passed step 11. The same location is used for both frames.",
         f"- Mean coherence in the window: {rp.get('mean_coh')}.", "",
         "### Per frame", "",
         "| Frame | epochs | first | last | ifgs | used | bad (11) | bad (12) | masked land fraction | ref area (px) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for s in summaries:
        L.append(f"| `{s['frame']}` | {s['epochs']} | {s['first']} | {s['last']} | {s['ifgs_total']} | "
                 f"{s['ifgs_used']} | {s['bad11']} | {s['bad12']} | {s['masked_fraction_land']} | "
                 f"{s['refarea']} |")
    for s in summaries:
        L += ["", f"Rejected interferograms by year (`{s['frame']}`, by second date):", "",
              "| Year | ifgs | bad step 11 | bad step 12 |", "|---|---|---|---|"]
        for y, v in s["per_year"].items():
            L.append(f"| {y} | {v['ifgs']} | {v['bad11']} | {v['bad12']} |")
        L.append(f"\nMonths with most rejections: {s['worst_months']}")
    for s in summaries:
        nf = s.get("nullify")
        if not nf:
            continue
        L += ["", f"### Deviation from the plan: step 12 for `{s['frame']}`", "",
              "The plan says to mask the dike-related unwrapping errors through the coherence and loop-closure "
              "thresholds, not to fix them, and not to tune thresholds globally. With the default loop threshold "
              "(1.5 rad), step 12 rejected all 10 descending interferograms across the 10 Nov 2023 dike (scene "
              "loop RMS 2-28 rad) and split the network into three pieces (20231110-20231122, 20231216-20240109), "
              "so step 13 bridged the dike step with its smoothness constraint and lost it in every later "
              "descending epoch. The loop errors sit at the dike: 54-59 % of the pixels near it fail to close, "
              "3-4 % elsewhere. For this frame only (`licsbas.frame_overrides` in config.yaml), step 12 runs with "
              f"loop threshold {nf['loop_thre']} rad and `--nullify`: pixels whose loops all exceed pi are set to "
              "NaN in each interferogram instead of dropping the whole interferogram, so the dike zone is still "
              "masked, but per pixel. The ascending frame keeps the defaults.", "",
              f"Masked by nullify (land pixels, share of each pixel's interferograms in loops): median "
              f"{nf['median']:.1%}, 95th percentile {nf['p95']:.1%}; {nf['over_half']:.1%} of pixels lost more "
              "than half. Effect against GNSS (Stage 6, 14 stations, median whole-series RMS, 1.5 rad run vs this "
              "setting, compared on 2026-11-24): descending LOS "
              "87 -> 20 mm, east-west 49 -> 28 mm, vertical 39 -> 31 mm. Near the dike the step is still not "
              "recovered (see the known-unreliable values in Stage 4 and 6)."]
    L += ["", "### Re-referencing", "",
          "LiCSBAS steps 13 and 16 always re-reference `cum`/`vel` to an automatically chosen single "
          "pixel (lowest RMS of cum w.r.t. the median, `info/13ref.txt`), wherever it lies; the "
          "`120ref.txt` window only sets the reference during the inversion. The exported "
          "`cum.h5`/`cum_filt.h5` and `results/vel*` rasters are therefore re-referenced to the mean of "
          "the reference window above (exact: one constant per epoch). LiCSBAS's own choice is kept "
          "as `refarea_licsbas` in the h5 files.", ""]
    for s in summaries:
        for f, r in s.get("rereference", {}).items():
            L.append(f"- `{s['frame']}/{f}`: LiCSBAS ref {r['licsbas_ref']}, window pixels valid in all "
                     f"epochs {r['window_px_valid_all_epochs']}/{rp['window_px'] ** 2}, velocity offset "
                     f"removed {r['vel_offset_mm_yr']} mm/yr")
    L += ["", "Outputs: `results/licsbas/<frame>/` (cum.h5 unfiltered, cum_filt.h5 filtered, results/ "
          "rasters as float32 binaries on the grid in EQA.dem_par, info/), QC figures in `figures/qc/<frame>/`. "
          "Use cum.h5 (unfiltered) for event-related displacement; step 16 smooths sharp steps."]
    update_notes(cfg, "licsbas", "\n".join(L))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="redo all phases")
    ap.add_argument("--frame", help="process one frame only (reference still uses both)")
    args = ap.parse_args()
    cfg = load_config()
    frames = [f for f in cfg["licsar"]["frames"].values() if f]
    todo = [args.frame] if args.frame else frames
    for f in frames:
        phase_a(cfg, f, args.force)
    rp = choose_reference(cfg, frames)
    print(f"reference point: {rp}", flush=True)
    summaries = []
    for f in todo:
        ts, area = phase_b(cfg, f, rp, args.force)
        s = export(cfg, f, ts, area)
        print(f"[{f}] {json.dumps({k: v for k, v in s.items() if k != 'per_year'})}", flush=True)
        summaries.append(s)
    write_notes(cfg, summaries, rp)
    (path(cfg, "results") / "licsbas" / "summary.json").write_text(
        json.dumps({"reference_point": rp, "frames": summaries}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
