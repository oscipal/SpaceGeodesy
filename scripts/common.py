"""Shared helpers: config loading and LiCSAR server access."""
from __future__ import annotations

import datetime as dt
import os
import re
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"

FRAME_RE = re.compile(r"\b(\d{3}[AD]_\d{5}_\d{6})\b")
IFG_RE = re.compile(r">(\d{8})_(\d{8})<")

# GDAL network reads: never list remote directories, only touch .tif files.
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "2")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    t = cfg["time"]
    t["start"] = _to_date(t["start"])
    t["end"] = _to_date(t["end"]) if t.get("end") else dt.date.today()
    return cfg


def _to_date(v) -> dt.date:
    if isinstance(v, dt.date):
        return v
    return dt.datetime.strptime(str(v).replace("-", ""), "%Y%m%d").date()


def path(cfg: dict, key: str) -> Path:
    p = ROOT / cfg["paths"][key]
    p.mkdir(parents=True, exist_ok=True)
    return p


def track_of(frame: str) -> int:
    return int(frame[:3])


def frame_url(cfg: dict, frame: str) -> str:
    return f"{cfg['licsar']['base_url']}/{track_of(frame)}/{frame}"


_session = requests.Session()


def http_get(url: str, retries: int = 4, timeout: int = 120) -> requests.Response:
    for i in range(retries):
        try:
            r = _session.get(url, timeout=timeout)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == retries - 1:
                raise
            time.sleep(2 ** i)
    raise RuntimeError("unreachable")


def list_frames(cfg: dict, track: int) -> list[str]:
    r = http_get(f"{cfg['licsar']['base_url']}/{track}/")
    return sorted(set(FRAME_RE.findall(r.text)))


def list_ifgs(cfg: dict, frame: str) -> list[tuple[dt.date, dt.date]]:
    r = http_get(f"{frame_url(cfg, frame)}/interferograms/")
    pairs = {(_to_date(a), _to_date(b)) for a, b in IFG_RE.findall(r.text)}
    return sorted(pairs)


def frame_polygon(cfg: dict, frame: str):
    from shapely.geometry import Polygon

    r = http_get(f"{frame_url(cfg, frame)}/metadata/{frame}-poly.txt")
    if r.status_code != 200:
        return None
    v = [float(x) for x in r.text.split()]
    return Polygon(list(zip(v[0::2], v[1::2])))


def update_notes(cfg: dict, section: str, body: str) -> None:
    """Replace (or append) an auto-generated section in docs/processing_notes.md."""
    f = path(cfg, "docs") / "processing_notes.md"
    text = f.read_text(encoding="utf-8") if f.exists() else "# Processing notes\n"
    start, end = f"<!-- auto:{section} -->", f"<!-- /auto:{section} -->"
    block = f"{start}\n{body.rstrip()}\n{end}"
    if start in text and end in text:
        pre, rest = text.split(start, 1)
        text = pre + block + rest.split(end, 1)[1]
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    f.write_text(text, encoding="utf-8")


COMPONENT_ALIASES = {"vertical": "up", "LOS asc": "los_asc", "LOS desc": "los_desc"}


def reliability(cfg: dict, t0, t1, component: str, station: str | None = None) -> str:
    """Reasons from postprocess.unreliable that apply to the interval t0-t1 of a component
    (at a GNSS station, if given); "" when none applies."""
    comp = COMPONENT_ALIASES.get(component, component)
    day = lambda x: x.date() if isinstance(x, dt.datetime) else _to_date(x)  # noqa: E731 (also pd.Timestamp)
    t0, t1 = day(t0), day(t1)
    out = []
    for r in cfg["postprocess"].get("unreliable") or []:
        if "epochs_between" in r:
            a, b = (day(x) for x in r["epochs_between"])
            hit = comp in r["components"] and any(a < t < b for t in (t0, t1))
        else:
            e = day(r["spans_event"])
            hit = station is not None and comp in (r["stations"].get(station) or []) and t0 <= e < t1
        if hit:
            out.append(" ".join(r["reason"].split()))
    return " | ".join(out)


def aoi_box(cfg: dict):
    from shapely.geometry import box

    a = cfg["aoi"]
    return box(a["lon_min"], a["lat_min"], a["lon_max"], a["lat_max"])
