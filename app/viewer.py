"""Stage 5a: interactive viewer for the Svartsengi InSAR products.

Run:  streamlit run app/viewer.py      (in Docker: .\\dc.ps1 make app, then http://localhost:8501)

Reads the Stage 4 cubes in results/cubes/ lazily; nothing is recomputed except differences
between two epochs and window means at the selected point.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import branca.colormap as bcm  # noqa: E402
import folium  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from cmcrameri import cm as cmc  # noqa: E402
from matplotlib.colors import Normalize, to_hex  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402
from streamlit_folium import st_folium  # noqa: E402

import viz  # noqa: E402
from common import load_config, path  # noqa: E402

st.set_page_config(page_title="Svartsengi InSAR viewer", page_icon="🌋", layout="wide")


@st.cache_resource
def setup():
    cfg = load_config()
    return cfg, viz.open_cubes(cfg)


cfg, cubes = setup()
FR = viz.frames(cfg)
FIX = st.cache_data(lambda: viz.fixed_limits(cfg, cubes))()   # one colour scale per unit

# layer -> (cube, variable, filtered variable or None, unit, kind)
LAYERS = {
    "Cumulative displacement: vertical": ("dec", "up", "up_filt", "mm", "cum"),
    "Cumulative displacement: east-west": ("dec", "east", "east_filt", "mm", "cum"),
    "Cumulative displacement: LOS ascending": ("asc", "cum", "cum_filt", "mm", "cum"),
    "Cumulative displacement: LOS descending": ("desc", "cum", "cum_filt", "mm", "cum"),
    "Velocity: vertical": ("dec", "vel_up", None, "mm/yr", "vel"),
    "Velocity: east-west": ("dec", "vel_east", None, "mm/yr", "vel"),
    "Velocity: LOS ascending": ("asc", "vel", "vel_filt", "mm/yr", "vel"),
    "Velocity: LOS descending": ("desc", "vel", "vel_filt", "mm/yr", "vel"),
    "Coherence (mean): ascending": ("asc", "coh_avg", None, "", "coh"),
    "Coherence (mean): descending": ("desc", "coh_avg", None, "", "coh"),
    "Mask (LiCSBAS 15): ascending": ("asc", "mask", None, "", "mask"),
    "Mask (LiCSBAS 15): descending": ("desc", "mask", None, "", "mask"),
    "Mask: valid in both frames": ("dec", "mask", None, "", "mask"),
}
SIGN = {"dec/up": "+ up", "dec/east": "+ east", "dec/vel_up": "+ up", "dec/vel_east": "+ east"}


def dates(cube: str) -> list[pd.Timestamp]:
    return list(pd.to_datetime(cubes[cube].time.values))


@st.cache_data(show_spinner=False)
def layer_array(layer: str, filt: bool, mask: bool, a: str | None, b: str | None) -> np.ndarray:
    cube, var, fvar, _, kind = LAYERS[layer]
    ds = cubes[cube]
    v = fvar if (filt and fvar) else var
    if kind == "cum":
        t = pd.to_datetime(ds.time.values)
        i, j = int(np.argmin(abs(t - pd.Timestamp(a)))), int(np.argmin(abs(t - pd.Timestamp(b))))
        arr = ds[v].isel(time=j).values - ds[v].isel(time=i).values
    else:
        arr = ds[v].values.astype("float32")
    if kind == "mask":
        return np.where(arr > 0, 1.0, 0.0)
    if mask and "mask" in ds:
        arr = np.where(ds["mask"].values > 0, arr, np.nan)
    return arr.astype("float32")


@st.cache_data(show_spinner=False)
def point_table(lat: float, lon: float, half: int, filt: bool) -> pd.DataFrame:
    cols = {}
    for name, cube, var, fvar in (("los_asc_mm", "asc", "cum", "cum_filt"), ("los_desc_mm", "desc", "cum", "cum_filt"),
                                  ("up_mm", "dec", "up", "up_filt"), ("east_mm", "dec", "east", "east_filt")):
        cols[name] = viz.window_series(cubes[cube], fvar if filt else var, lat, lon, half)
    df = pd.concat(cols, axis=1).sort_index()
    df.index.name = "date"
    return df


@st.cache_data
def events() -> pd.DataFrame:
    return viz.load_events(cfg)


def rgba(arr: np.ndarray, cmap, vmin: float, vmax: float, alpha: float) -> np.ndarray:
    out = cmap(Normalize(vmin, vmax, clip=True)(arr))
    out[..., 3] = np.where(np.isfinite(arr), alpha, 0.0)
    return (out * 255).astype("uint8")


# ----------------------------------------------------------------------- animation
ANIM = {"Vertical": ("dec", "up", "up_filt", "+ up"), "East-west": ("dec", "east", "east_filt", "+ east"),
        "LOS ascending": ("asc", "cum", "cum_filt", "+ towards satellite"),
        "LOS descending": ("desc", "cum", "cum_filt", "+ towards satellite")}


def png_b64(img) -> str:
    import base64
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode()


@st.cache_data(show_spinner="Rendering animation frames ...", max_entries=4)
def anim_frames(comp: str, filt: bool, mask: bool, step: int, zoom: bool, lim: float) -> dict:
    """Paletted PNG per epoch of the displacement since the first epoch, all on one colour scale."""
    from PIL import Image

    cube, var, fvar, _ = ANIM[comp]
    ds = cubes[cube]
    ys, xs = viz.cropped(ds, viz.ZOOM if zoom else None)
    data = ds[fvar if filt else var].isel(lat=ys, lon=xs).values
    data = data - data[0]
    if mask:
        data = np.where(ds["mask"].isel(lat=ys, lon=xs).values > 0, data, np.nan)
    t = pd.to_datetime(ds.time.values)
    idx = list(range(0, len(t), step))
    if idx[-1] != len(t) - 1:
        idx.append(len(t) - 1)
    pal = (cmc.vik(np.linspace(0, 1, 255))[:, :3] * 255).astype("uint8")
    palette = np.vstack([pal, [[0, 0, 0]]]).ravel().tolist()
    frames = []
    for k in idx:
        a = data[k]
        q = np.clip(np.round((a + lim) / (2 * lim) * 254), 0, 254)
        q = np.where(np.isfinite(a), q, 255).astype("uint8")
        im = Image.fromarray(q, mode="P")
        im.putpalette(palette)
        im.info["transparency"] = 255
        frames.append(png_b64(im))
    hs, _ = viz.hillshade(cfg)
    hsa = xr_like(hs, cubes["asc"]).sel(lat=ds.lat[ys], lon=ds.lon[xs], method="nearest").values
    hs_png = png_b64(Image.fromarray((np.clip(hsa * 0.75 + 0.15, 0, 1) * 255).astype("uint8"), mode="L"))
    la, lo = ds.lat.values[ys], ds.lon.values[xs]
    c = cfg["sites"]["svartsengi_uplift_centre"]
    centre = viz.window_series(ds, fvar if filt else var, c["lat"], c["lon"], 1)
    centre = (centre - centre.iloc[0]).iloc[idx]
    return dict(frames=frames, dates=[f"{t[k]:%Y-%m-%d}" for k in idx], hs=hs_png,
                lat=(float(la.min()), float(la.max())), lon=(float(lo.min()), float(lo.max())),
                shape=data.shape[1:], centre=[None if not np.isfinite(v) else round(float(v), 1) for v in centre.values])


def xr_like(a: np.ndarray, ds):
    import xarray as xr
    return xr.DataArray(a, coords={"lat": ds.lat, "lon": ds.lon}, dims=("lat", "lon"))


def animation_html(F: dict, comp: str, lim: float, sign: str, ms: int) -> str:
    import json
    ny, nx = F["shape"]
    aspect = nx / (ny / np.cos(np.radians(63.9)))          # pixels are 0.001 deg; stretch latitude
    lat0, lat1 = F["lat"]
    lon0, lon1 = F["lon"]

    def pos(la, lo):
        return 100 * (lo - lon0) / (lon1 - lon0), 100 * (lat1 - la) / (lat1 - lat0)

    s, rp = cfg["sites"], cfg["licsbas"]["reference_point"]
    marks = [("+", "Uplift centre", *pos(s["svartsengi_uplift_centre"]["lat"], s["svartsengi_uplift_centre"]["lon"])),
             ("o", "Grindavík", *pos(s["grindavik"]["lat"], s["grindavik"]["lon"]))]
    if lat0 <= rp["lat"] <= lat1 and lon0 <= rp["lon"] <= lon1:
        marks.append(("□", "Reference (Straumsvík)", *pos(rp["lat"], rp["lon"])))
    mk = "".join(f'<div class="mk" style="left:{x:.2f}%;top:{y:.2f}%" title="{t}">{m}</div>'
                 for m, t, x, y in marks if 0 <= x <= 100 and 0 <= y <= 100)
    grad = ", ".join(f"{to_hex(cmc.vik(x))} {100 * x:.0f}%" for x in np.linspace(0, 1, 11))
    ev = events()
    evj = [{"d": f"{d:%Y-%m-%d}", "c": viz.EVENT_COLOURS.get(loc, viz.MUTED), "t": f"{d:%Y-%m-%d} {ty} ({loc})"}
           for d, ty, loc in zip(ev.date, ev.type, ev.location)]
    return f"""
<style>
 body {{ margin:0; font-family: system-ui, sans-serif; color:#0b0b0b; background:#fff; }}
 #wrap {{ position:relative; width:100%; aspect-ratio:{aspect:.4f}; background:#ddd; overflow:hidden; border-radius:4px; }}
 #wrap img {{ position:absolute; inset:0; width:100%; height:100%; image-rendering:auto; }}
 .mk {{ position:absolute; transform:translate(-50%,-50%); font:700 18px system-ui; color:#0b0b0b;
        text-shadow:0 0 3px #fff,0 0 3px #fff; pointer-events:auto; }}
 #date {{ position:absolute; left:10px; top:8px; background:rgba(255,255,255,.85); padding:3px 8px;
          border-radius:4px; font:600 16px system-ui; }}
 #ctl {{ display:flex; gap:10px; align-items:center; margin:10px 0 4px; flex-wrap:wrap; }}
 #ctl button {{ font-size:15px; padding:4px 14px; border:1px solid #c3c2b7; border-radius:4px; background:#fff; cursor:pointer; }}
 #sl {{ flex:1; min-width:200px; }}
 #cb {{ height:12px; border-radius:2px; background:linear-gradient(to right, {grad}); }}
 #cbl {{ display:flex; justify-content:space-between; font-size:12px; color:#52514e; }}
 #ts {{ width:100%; height:140px; margin-top:8px; }}
</style>
<div id="wrap"><img src="data:image/png;base64,{F['hs']}"><img id="fr" style="opacity:.85">{mk}<div id="date"></div></div>
<div id="ctl"><button id="pl">▶ Play</button><input id="sl" type="range" min="0" max="{len(F['frames']) - 1}" value="0">
<label>Speed <select id="sp"><option value="2">0.5x</option><option value="1" selected>1x</option>
<option value="0.5">2x</option><option value="0.25">4x</option></select></label>
<label><input id="lp" type="checkbox" checked> loop</label></div>
<div id="cb"></div><div id="cbl"><span>◀ −{lim:.0f}</span><span>0</span><span>+{lim:.0f} ▶ mm</span></div>
<div style="font-size:12px;color:#52514e;margin-top:2px">{comp} displacement since {F['dates'][0]} ({sign}); same colour
scale in every frame; arrows: values beyond the scale are shown in the end colour.</div>
<svg id="ts" viewBox="0 0 1000 140" preserveAspectRatio="none"></svg>
<script>
const F = {json.dumps(F['frames'])}, D = {json.dumps(F['dates'])}, C = {json.dumps(F['centre'])}, E = {json.dumps(evj)};
const fr = document.getElementById('fr'), sl = document.getElementById('sl'), dt = document.getElementById('date'),
      pl = document.getElementById('pl'), sp = document.getElementById('sp'), lp = document.getElementById('lp'),
      ts = document.getElementById('ts');
const t0 = Date.parse(D[0]), t1 = Date.parse(D[D.length-1]);
const xs = d => 40 + 950 * (Date.parse(d) - t0) / (t1 - t0);
const v = C.filter(x => x !== null), lo = Math.min(0, ...v), hi = Math.max(...v);
const ys = y => 125 - 110 * (y - lo) / ((hi - lo) || 1);
let svg = '';
for (const e of E) {{ const x = xs(e.d); if (x >= 40 && x <= 990) svg += `<line x1="${{x}}" x2="${{x}}" y1="10" y2="128" stroke="${{e.c}}" stroke-width="1.5" opacity=".7"><title>${{e.t}}</title></line>`; }}
let p = ''; C.forEach((y, i) => {{ if (y !== null) p += (p ? 'L' : 'M') + xs(D[i]).toFixed(1) + ',' + ys(y).toFixed(1); }});
svg += `<path d="${{p}}" fill="none" stroke="#0b0b0b" stroke-width="2"/>`;
svg += `<text x="4" y="14" font-size="12" fill="#52514e">${{hi.toFixed(0)}} mm</text><text x="4" y="128" font-size="12" fill="#52514e">${{lo.toFixed(0)}}</text>`;
svg += `<text x="40" y="139" font-size="11" fill="#52514e">uplift centre (3x3 px), {comp.lower()}</text>`;
svg += `<line id="cur" y1="8" y2="130" stroke="#e34948" stroke-width="2"/><circle id="dot" r="5" fill="#e34948"/>`;
ts.innerHTML = svg;
const cur = document.getElementById('cur'), dot = document.getElementById('dot');
let i = 0, timer = null;
function show(k) {{ i = k; fr.src = 'data:image/png;base64,' + F[k]; sl.value = k; dt.textContent = D[k];
  const x = xs(D[k]); cur.setAttribute('x1', x); cur.setAttribute('x2', x);
  if (C[k] !== null) {{ dot.setAttribute('cx', x); dot.setAttribute('cy', ys(C[k])); dot.style.display=''; }} else dot.style.display='none'; }}
function stop() {{ clearInterval(timer); timer = null; pl.textContent = '▶ Play'; }}
function play() {{ if (timer) return stop(); pl.textContent = '❚❚ Pause';
  timer = setInterval(() => {{ if (i + 1 >= F.length) {{ if (lp.checked) show(0); else stop(); }} else show(i + 1); }},
                      {ms} * parseFloat(sp.value)); }}
pl.onclick = play; sl.oninput = () => {{ stop(); show(+sl.value); }};
sp.onchange = () => {{ if (timer) {{ stop(); play(); }} }};
show(0);
</script>"""


def animation_page(filt: bool, mask: bool):
    st.subheader("Animation: cumulative displacement since the first acquisition")
    c1, c2, c3, c4 = st.columns([1.2, 1.2, 1, 1])
    comp = c1.selectbox("Component", list(ANIM))
    zoom = c2.radio("Area", ["Svartsengi–Sundhnúkur", "Whole area"], horizontal=True) != "Whole area"
    step = {"every acquisition": 1, "every 2nd": 2, "every 4th": 4}[c3.selectbox("Frames", ["every acquisition", "every 2nd", "every 4th"])]
    ms = c4.select_slider("Frame time (ms)", [60, 100, 150, 250, 400], value=150)
    lim = st.session_state.get("lim_mm", FIX["mm"])
    F = anim_frames(comp, filt, mask, step, zoom, lim)
    st.caption(f"{len(F['frames'])} frames, {F['dates'][0]} to {F['dates'][-1]}, colour scale ±{lim:.0f} mm "
               f"(the map's displacement scale), {'filtered' if filt else 'unfiltered'}, "
               f"{'masked' if mask else 'unmasked'}. Each frame is one Sentinel-1 acquisition of the inverted time "
               "series (not a single interferogram). Vertical and east-west end 2026-02-03 with the descending data.")
    ny, nx = F["shape"]
    h = int(900 * ny / np.cos(np.radians(63.9)) / nx) + 260
    st.iframe(animation_html(F, comp, lim, ANIM[comp][3], ms), height=min(h, 1100))


# ------------------------------------------------------------------------- sidebar
c0 = cfg["sites"]["svartsengi_uplift_centre"]
if "lat_in" not in st.session_state:
    st.session_state.lat_in, st.session_state.lon_in = float(c0["lat"]), float(c0["lon"])
if "pending" in st.session_state:                       # map click from the previous run
    st.session_state.lat_in, st.session_state.lon_in = st.session_state.pop("pending")

with st.sidebar:
    view = st.radio("View", ["Map and time series", "Animation"], horizontal=True)
    st.header("Map layer" if view == "Map and time series" else "Data")
    layer = st.selectbox("Layer", list(LAYERS), label_visibility="collapsed")
    cube, var, fvar, unit, kind = LAYERS[layer]
    filt = st.toggle("Filtered (LiCSBAS 16)", value=False,
                     help="Spatio-temporal filter of step 16. It smooths sharp steps at dikes and eruptions; "
                          "use the unfiltered data for event-related displacement.")
    use_mask = st.toggle("Apply LiCSBAS mask", value=True, disabled=kind == "mask")
    a = b = None
    if kind == "cum":
        dl = dates(cube)
        fmt = lambda d: d.strftime("%Y-%m-%d")  # noqa: E731
        since_first = st.radio("Displacement", [f"Since the first acquisition ({fmt(dl[0])})", "Between two dates"],
                               index=0) != "Between two dates"
        if since_first:
            b = st.select_slider("Up to", options=dl, value=dl[-1], format_func=fmt)
            a = dl[0]
        else:
            a, b = st.select_slider("Between", options=dl, value=(dl[0], dl[-1]), format_func=fmt)
        a, b = str(a.date()), str(b.date())
    arr = layer_array(layer, filt, use_mask, a, b)
    if kind in ("cum", "vel"):
        fixed = FIX[unit]
        if st.toggle("Fixed colour scale", value=True,
                     help=f"Same scale for every date, layer and animation frame: ±{fixed:.0f} mm for displacement "
                          f"(vertical, east-west and LOS alike), ±{FIX['mm/yr']:.0f} mm/yr for velocity."):
            lim = fixed
        else:
            lim = st.slider(f"Colour limit (± {unit})", 10.0, 2.0 * fixed, fixed, step=10.0,
                            help="Applies to all dates and layers of this unit, and to the animation.")
        st.session_state[f"lim_{unit}"] = lim
        cmap, vmin, vmax = cmc.vik, -lim, lim
    elif kind == "coh":
        cmap, vmin, vmax = cmc.oslo, 0.0, 1.0
    else:
        cmap, vmin, vmax = cmc.grayC_r, 0.0, 1.0
    opacity = st.slider("Opacity", 0.1, 1.0, 0.8, 0.05)

    st.header("Point")
    st.number_input("Latitude", key="lat_in", format="%.4f", step=0.001)
    st.number_input("Longitude", key="lon_in", format="%.4f", step=0.001)
    if st.button("Back to the uplift centre"):
        st.session_state.pending = (float(c0["lat"]), float(c0["lon"]))
        st.rerun()
    half = {"1 x 1": 0, "3 x 3 (as Stage 4)": 1, "5 x 5": 2}[
        st.radio("Averaging window (pixels, ~100 m)", ["1 x 1", "3 x 3 (as Stage 4)", "5 x 5"], index=1)]
    gn = viz.gnss_series(cfg)
    gst = {s["id"]: s for s in viz.gnss_stations(cfg)}
    dkm = {k: float(np.hypot((gst[k]["lat"] - st.session_state.lat_in) * 111.32,
                             (gst[k]["lon"] - st.session_state.lon_in) * 111.32 * np.cos(np.radians(63.9))))
           for k in gn}
    order = sorted(gn, key=dkm.get)
    show_gnss = st.multiselect("GNSS stations (Stage 6)", order, default=order[:1] if order and dkm[order[0]] < 1.5 else [],
                               format_func=lambda k: f"{k} ({dkm[k]:.1f} km)",
                               help="NGL daily positions relative to REYK, projected on each line of sight, "
                                    "shifted to the InSAR series over their first 60 common days. The "
                                    "list is sorted by distance from the selected point." if gn
                                    else "No GNSS series yet (Stage 6).", disabled=not gn)

lat, lon = float(st.session_state.lat_in), float(st.session_state.lon_in)

# ----------------------------------------------------------------------------- map
st.title("Svartsengi–Sundhnúkur ground deformation, Sentinel-1 InSAR 2020–2026")
if view == "Animation":
    animation_page(filt, use_mask)
    st.stop()
ds = cubes[cube]
la, lo = ds.lat.values, ds.lon.values
dlat, dlon = abs(float(la[1] - la[0])), float(lo[1] - lo[0])
bounds = [[float(la.min()) - dlat / 2, float(lo.min()) - dlon / 2], [float(la.max()) + dlat / 2, float(lo.max()) + dlon / 2]]

m = folium.Map(location=[63.89, -22.36], zoom_start=11, tiles=None, control_scale=True)
folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}",
                 attr="Esri, World Hillshade", name="Hillshade (Esri)").add_to(m)
folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                 attr="Esri, World Imagery", name="Satellite (Esri)").add_to(m)
folium.raster_layers.ImageOverlay(rgba(arr, cmap, vmin, vmax, opacity), bounds=bounds, mercator_project=True,
                                  name=layer, interactive=False).add_to(m)
if kind != "mask":
    sign = SIGN.get(f"{cube}/{var}", "+ towards satellite") if kind in ("cum", "vel") else ""
    cap = f"{layer} ({unit}{', ' + sign if sign else ''})" + (f", {a} to {b}" if kind == "cum" else "")
    bcm.LinearColormap([to_hex(cmap(x)) for x in np.linspace(0, 1, 11)], vmin=vmin, vmax=vmax, caption=cap).add_to(m)

s, rp = cfg["sites"], cfg["licsbas"]["reference_point"]
folium.Marker([s["svartsengi_uplift_centre"]["lat"], s["svartsengi_uplift_centre"]["lon"]], tooltip="Uplift centre",
              icon=folium.Icon(color="black", icon="plus")).add_to(m)
folium.CircleMarker([s["grindavik"]["lat"], s["grindavik"]["lon"]], radius=5, color="#0b0b0b", fill=True,
                    fill_color="white", fill_opacity=1, tooltip="Grindavík").add_to(m)
folium.RegularPolygonMarker([rp["lat"], rp["lon"]], number_of_sides=4, radius=7, color="#0b0b0b", fill=False,
                            tooltip=f"Reference window, Straumsvík ({rp['window_px']}x{rp['window_px']} px)").add_to(m)
for g in viz.gnss_stations(cfg):
    if g.get("role") == "reference":
        continue
    folium.RegularPolygonMarker([g["lat"], g["lon"]], number_of_sides=3, radius=7, color="#0b0b0b",
                                fill=True, fill_color="white", fill_opacity=1, tooltip=f"GNSS {g['id']} (NGL, {g['first']:%Y-%m} to {g['last']:%Y-%m})").add_to(m)
folium.CircleMarker([lat, lon], radius=7, color="#e34948", weight=3, fill=False,
                    tooltip=f"Selected point {lat:.4f}, {lon:.4f}").add_to(m)
folium.LayerControl(collapsed=True).add_to(m)

st.caption("Click the map to plot the time series of a pixel. Displacement is relative to the Straumsvík reference "
           "window (square), line of sight (LOS) positive towards the satellite.")
out = st_folium(m, height=520, use_container_width=True, returned_objects=["last_clicked"], key="map")
click = (out or {}).get("last_clicked")
if click:
    new = (round(float(click["lat"]), 5), round(float(click["lng"]), 5))
    if st.session_state.get("last_click") != new:
        st.session_state.last_click = new
        st.session_state.pending = new
        st.rerun()

# ---------------------------------------------------------------------- time series
inside = bounds[0][0] <= lat <= bounds[1][0] and bounds[0][1] <= lon <= bounds[1][1]
if not inside:
    st.warning("The selected point is outside the processed area.")
    st.stop()
df = point_table(lat, lon, half, filt)
ev = events()
fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.06, row_heights=[0.38, 0.38, 0.24],
                    subplot_titles=("Line of sight (mm, + towards satellite); event lines grey",
                                    "Vertical (mm, + up), from the asc/desc decomposition",
                                    "East-west (mm, + east)"))
for col, name, colour in (("los_asc_mm", f"LOS ascending {FR['asc']}", viz.ASC),
                          ("los_desc_mm", f"LOS descending {FR['desc']}", viz.DESC)):
    sr = df[col].dropna()
    if not sr.empty:
        fig.add_trace(go.Scatter(x=sr.index, y=sr - sr.iloc[0], name=name, mode="lines+markers",
                                 line=dict(color=colour, width=2), marker=dict(size=4),
                                 hovertemplate="%{x|%Y-%m-%d}: %{y:.1f} mm"), row=1, col=1)
for row, col, name in ((2, "up_mm", "Vertical InSAR"), (3, "east_mm", "East-west InSAR")):
    sr = df[col].dropna()
    if not sr.empty:
        fig.add_trace(go.Scatter(x=sr.index, y=sr - sr.iloc[0], name=name, mode="lines+markers",
                                 line=dict(color=viz.INK, width=2), marker=dict(size=4), showlegend=False,
                                 hovertemplate="%{x|%Y-%m-%d}: %{y:.1f} mm"), row=row, col=1)
for n, k in enumerate(show_gnss):
    # GNSS relative to REYK, projected on each LOS; shifted by the median difference to the InSAR
    # series of the selected point over the first 60 common days (so later drift stays visible)
    for row, col, colour, lab in ((1, "los_asc_mm", viz.ASC, "LOS asc"), (1, "los_desc_mm", viz.DESC, "LOS desc"),
                                  (2, "up_mm", viz.INK2, "vertical"), (3, "east_mm", viz.INK2, "east")):
        if col not in gn[k] or df[col].dropna().empty:
            continue
        g = gn[k][col].dropna()
        ins = (df[col] - df[col].dropna().iloc[0]).dropna()
        gi = g.reindex(ins.index.normalize())
        gi.index = ins.index
        d = (ins - gi).dropna()
        off = float(d[d.index <= d.index[0] + pd.Timedelta(days=60)].median()) if len(d) else 0.0
        fig.add_trace(go.Scatter(x=g.index, y=g + off, name=f"GNSS {k}", legendgroup=k, showlegend=row == 2,
                                 mode="markers", marker=dict(color=colour, size=3, opacity=0.45,
                                                             symbol=["circle", "diamond", "square"][n % 3]),
                                 hovertemplate=f"GNSS {k} {lab} " + "%{x|%Y-%m-%d}: %{y:.1f} mm"), row=row, col=1)
for _, e in ev.iterrows():
    for row in (1, 2, 3):
        fig.add_vline(x=e.date, line_width=1, row=row, col=1,
                      line_dash={"solid": "solid", "dashed": "dash", "dotted": "dot"}[viz.EVENT_DASH.get(e.type, "solid")],
                      line_color=viz.MUTED if row == 1 else viz.EVENT_COLOURS.get(e.location, viz.MUTED),
                      opacity=0.6 if row == 1 else 0.8)
top = df["up_mm"].dropna()
ytop = float((top - top.iloc[0]).max()) if not top.empty else 0.0
fig.add_trace(go.Scatter(x=ev.date, y=[ytop] * len(ev), mode="markers", name="Events",
                         marker=dict(symbol="triangle-down", size=9,
                                     color=[viz.EVENT_COLOURS.get(x, viz.MUTED) for x in ev.location]),
                         text=[f"{d:%Y-%m-%d} {t} ({loc}): {desc}" for d, t, loc, desc in
                               zip(ev.date, ev.type, ev.location, ev.description)],
                         hovertemplate="%{text}<extra></extra>", showlegend=False), row=2, col=1)
fig.update_layout(height=760, margin=dict(l=10, r=10, t=40, b=10), hovermode="x unified",
                  legend=dict(orientation="h", yanchor="bottom", y=1.04, x=0),
                  plot_bgcolor="white", font=dict(size=12))
fig.update_yaxes(gridcolor="#e4e2dc", zeroline=True, zerolinecolor="#c3c2b7")
fig.update_xaxes(gridcolor="#f0efec")

st.subheader(f"Time series at {lat:.4f} N, {abs(lon):.4f} W "
             f"({2 * half + 1}x{2 * half + 1} pixels, {'filtered' if filt else 'unfiltered'})")
st.caption("Events: green Svartsengi, violet Fagradalsfjall, red Sundhnúkur; solid eruption, dashed dike, dotted "
           "inflation onset (hover the triangles). The decomposition ends 2026-02-03 with the descending data; "
           "it neglects the north component.")
st.plotly_chart(fig, width="stretch")

c1, c2 = st.columns([1, 3])
c1.download_button("Download time series (CSV)", df.to_csv(float_format="%.2f").encode(),
                   file_name=f"insar_{lat:.4f}_{lon:.4f}_{2 * half + 1}px{'_filt' if filt else ''}.csv",
                   mime="text/csv")
c2.caption("Columns: cumulative displacement in mm relative to the first epoch of each series and to the "
           "reference window; empty cells are epochs not observed by that geometry.")

with st.expander("Uplift per episode at the uplift centre (Stage 4)"):
    epf = path(cfg, "results") / "episodes.csv"
    if epf.exists():
        ep = pd.read_csv(epf)
        st.dataframe(ep[ep.component == "vertical"].drop(columns="component"), hide_index=True, width="stretch")
with st.expander("About the data"):
    st.markdown(
        f"- LiCSAR interferograms (COMET), frames `{FR['asc']}` (ascending) and `{FR['desc']}` (descending), "
        "time series with LiCSBAS (GACOS weather correction, loop-closure check, small-baseline inversion).\n"
        "- Reference: 5x5 pixel window at Straumsvík, 27 km from the uplift centre.\n"
        "- Mask: LiCSBAS step 15 (coherence, unwrapping, loop closure, residuals).\n"
        "- Static report figures: `scripts/make_figures.py`; LiCSBAS also ships `LiCSBAS_plot_ts.py` for quick checks.\n"
        "- Contains modified Copernicus Sentinel data 2020–2026 analysed by COMET.")
