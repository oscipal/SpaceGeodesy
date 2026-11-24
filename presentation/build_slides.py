"""Build the final presentation from the ETH template (python-pptx).

    python presentation/build_slides.py

Reads   presentation/eth_pp_praesentation_ohne_klassifizierung.potx (ETH master and layouts)
        figures/slides/*.png (scripts/make_slide_figures.py)
Writes  presentation/svartsengi_presentation.pptx

All sample slides of the template are removed; every slide is created from a template layout,
so the ETH master (logo, footer, slide number) stays intact. Numbers are the ones in the report
(report/main.tex); speaker notes are added to each slide (full notes: speaker_notes.md).
"""
from __future__ import annotations

import copy
import io
import zipfile
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TEMPLATE = HERE / "eth_pp_praesentation_ohne_klassifizierung.potx"
FIG = ROOT / "figures" / "slides"
OUT = HERE / "svartsengi_presentation.pptx"

DATE = "15.12.2026"
FOOTER = "Space Geodesy project: Svartsengi InSAR and GNSS"

# ETH colours (template theme) and neutrals
BLUE, PETROL, RED = RGBColor(0x21, 0x5C, 0xAF), RGBColor(0x00, 0x78, 0x94), RGBColor(0xB7, 0x35, 0x2D)
INK, GREY = RGBColor(0x0B, 0x0B, 0x0B), RGBColor(0x57, 0x57, 0x57)
TINT = RGBColor(0xE9, 0xEF, 0xF7)          # light ETH blue tint for cards
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# content area of the template (EMU): left margin and width of the title and body placeholders
X0, W0 = 731837, 10728325
Y0 = 1412875                               # top of the body area
YB = 6273000                               # bottom of the body area (above the footer)


# ----------------------------------------------------------------------------- template
def open_template() -> Presentation:
    """The .potx as a presentation (only the main content type differs), without its sample slides."""
    buf = io.BytesIO()
    with zipfile.ZipFile(TEMPLATE) as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "[Content_Types].xml":
                data = data.replace(b"presentationml.template.main+xml", b"presentationml.presentation.main+xml")
            zout.writestr(item, data)
    prs = Presentation(io.BytesIO(buf.getvalue()))
    lst = prs.slides._sldIdLst
    for sid in list(lst):
        prs.part.drop_rel(sid.get(qn("r:id")))
        lst.remove(sid)
    return prs


def layout(prs, name):
    for lo in prs.slide_layouts:
        if lo.name == name:
            return lo
    raise KeyError(name)


def footer(slide):
    """Copy date, footer and slide number placeholders from the layout (python-pptx does not)."""
    tree = slide.shapes._spTree
    for ph in slide.slide_layout.placeholders:
        t = ph.placeholder_format.type
        tname = str(t).split(".")[-1].split(" ")[0]
        if tname not in ("DATE", "FOOTER", "SLIDE_NUMBER"):
            continue
        el = copy.deepcopy(ph._element)
        tree.append(el)
        if tname == "DATE":                   # fixed presentation date instead of the field
            p = el.find(".//" + qn("a:p"))
            for child in list(p):
                p.remove(child)
            r = p.makeelement(qn("a:r"), {})
            r.append(r.makeelement(qn("a:rPr"), {"lang": "en-GB"}))
            tt = r.makeelement(qn("a:t"), {})
            tt.text = DATE
            r.append(tt)
            p.append(r)
        elif tname == "FOOTER":
            el.find(".//" + qn("a:t")).text = FOOTER


def drop_empty_placeholders(slide, keep=("title",)):
    for ph in list(slide.placeholders):
        t = str(ph.placeholder_format.type).split(".")[-1].split(" ")[0].lower()
        if t in keep or ph.has_text_frame and ph.text_frame.text.strip():
            continue
        ph._element.getparent().remove(ph._element)


def new_slide(prs, layout_name, title=None, notes=None):
    s = prs.slides.add_slide(layout(prs, layout_name))
    if title is not None and s.shapes.title is not None:
        s.shapes.title.text = title
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def content_slide(prs, title, notes, layout_name="Inhalt Bild"):
    s = new_slide(prs, layout_name, title, notes)
    drop_empty_placeholders(s)
    footer(s)
    return s


# ----------------------------------------------------------------------------- drawing helpers
def text(slide, x, y, w, h, paras, size=18, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, bullets=False, space=6, name=None):
    """paras: list of str or (str, dict(size, bold, color)) or list of runs [(str, dict), ...]."""
    tb = slide.shapes.add_textbox(Emu(x), Emu(y), Emu(w), Emu(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Emu(0)
    tf.margin_top = tf.margin_bottom = Emu(0)
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        runs = para if isinstance(para, list) else [para]
        for run in runs:
            s, o = (run, {}) if isinstance(run, str) else run
            r = p.add_run()
            r.text = s
            f = r.font
            f.name = "Arial"
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.color.rgb = o.get("color", color)
        if bullets:
            pPr = p._p.get_or_add_pPr()
            pPr.set("marL", str(Emu(Pt(18))))
            pPr.set("indent", str(-Emu(Pt(18))))
            bu = pPr.makeelement(qn("a:buChar"), {"char": "•"})
            pPr.append(bu)
    return tb


def box(slide, x, y, w, h, fill=TINT, line=None, shape=MSO_SHAPE.RECTANGLE, name=None):
    sh = slide.shapes.add_shape(shape, Emu(x), Emu(y), Emu(w), Emu(h))
    if name:
        sh.name = name
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(1.5)
    sh.shadow.inherit = False
    return sh


def box_text(sh, paras, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.MIDDLE, margin=Pt(10)):
    tf = sh.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = Emu(margin)
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        runs = para if isinstance(para, list) else [para]
        for run in runs:
            s, o = (run, {}) if isinstance(run, str) else run
            r = p.add_run()
            r.text = s
            r.font.name = "Arial"
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", bold)
            r.font.color.rgb = o.get("color", color)


def arrow(slide, x1, y1, x2, y2, color=GREY):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Emu(x1), Emu(y1), Emu(x2), Emu(y2))
    c.line.color.rgb = color
    c.line.width = Pt(2.25)
    ln = c.line._get_or_add_ln()
    ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return c


def picture(slide, name, x, y, w, h, align="center"):
    """Fit figures/slides/<name>.png into the box, keeping its aspect ratio."""
    f = FIG / f"{name}.png"
    iw, ih = Image.open(f).size
    s = min(w / iw, h / ih)
    pw, ph = int(iw * s), int(ih * s)
    px = x + (w - pw) // 2 if align == "center" else x
    py = y + (h - ph) // 2
    pic = slide.shapes.add_picture(str(f), Emu(px), Emu(py), Emu(pw), Emu(ph))
    pic.name = name
    return pic


def source(slide, s):
    text(slide, X0, YB + 40000, W0, 200000, [s], size=10, color=GREY, name="Source")


def stat(slide, x, y, w, value, label, color=BLUE, vsize=40):
    text(slide, x, y, w, Pt(vsize * 1.25), [value], size=vsize, bold=True, color=color)
    text(slide, x, y + Emu(Pt(vsize * 1.3)), w, 700000, [label], size=16, color=GREY)


def table(slide, x, y, w, rows, col_w, size=16, header_fill=BLUE, row_h=Pt(30)):
    t = slide.shapes.add_table(len(rows), len(rows[0]), Emu(x), Emu(y), Emu(w), Emu(row_h * len(rows))).table
    tot = sum(col_w)
    for j, cw in enumerate(col_w):
        t.columns[j].width = Emu(int(w * cw / tot))
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = header_fill if i == 0 else (TINT if i % 2 == 0 else WHITE)
            c.margin_left = c.margin_right = Pt(8)
            c.margin_top = c.margin_bottom = Pt(4)
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            r = p.add_run()
            r.text = val
            r.font.name = "Arial"
            r.font.size = Pt(size)
            r.font.bold = i == 0
            r.font.color.rgb = WHITE if i == 0 else INK
    return t


# ----------------------------------------------------------------------------- slides
def divider(prs, n, question, notes):
    s = new_slide(prs, "Zwischenslide", f"Question {n}: {question}", notes)
    footer(s)
    return s


def build():
    prs = open_template()
    names = "Cai Zhihao, Raúl Lara, Génio Lay da Silva, Diogo Correia, Otto Scipal"

    # 1 title -----------------------------------------------------------------
    s = new_slide(prs, "Titelfolie 04", "Inflation Cycles at Svartsengi, Iceland: GNSS and InSAR Comparison and "
                  "Source Stability",
                  notes="[Speaker 1] 0.5 min. Introduce the team and the topic: the inflation cycles at Svartsengi "
                        "since 2023 and the current pause, measured with Sentinel-1 InSAR and GNSS.")
    for ph in s.placeholders:
        i = ph.placeholder_format.idx
        if i == 13:
            tf = ph.text_frame
            tf.text = names
            for line in ("Space Geodesy, final project presentation", "15 December 2026, Zurich"):
                tf.add_paragraph().text = line
            tf.paragraphs[0].runs[0].font.bold = True
        elif i == 16:
            ph.text_frame.text = "Institute of Geodesy and Photogrammetry"
    drop_empty_placeholders(s, keep=("title", "center_title"))

    # 2 motivation --------------------------------------------------------------
    s = content_slide(prs, "Eleven dike intrusions since November 2023, but no eruption since August 2025",
                      "[Speaker 1] 1 min. Svartsengi already inflated in 2020 and 2022 without eruptions. Since "
                      "November 2023 the pattern repeats: magma collects beneath Svartsengi, the ground rises, then "
                      "a dike breaks out towards Sundhnúkur and the ground drops within hours. 11 intrusions and 9 "
                      "eruptions until July 2025. Since August 2025 nothing happened, although the ground keeps "
                      "rising. Why? Supply declining, or the crust stronger? Both would show in rate and pattern.")
    picture(s, "timeline", X0, Y0, W0, 3000000)
    text(s, X0, Y0 + 3250000, W0, 1500000, [
        "Magma accumulates at 4 to 5 km depth beneath Svartsengi, the ground rises",
        "A dike propagates towards Sundhnúkur, the ground subsides within hours",
        "Since August 2025: uplift continues, but no new intrusion (the current pause)",
    ], size=18, bullets=True)
    source(s, "Event dates: Parks et al. (2025), EPSL 658, 119324; Parks et al. (2026), EGU26-6017; "
              "Icelandic Meteorological Office")

    # 3 background ---------------------------------------------------------------
    s = content_slide(prs, "GNSS and InSAR complement each other",
                      "[Speaker 1] 1 min. GNSS gives precise daily 3D positions, but only at a few points. InSAR maps "
                      "the whole area, but only in the line of sight of the satellite and every 6 or 12 days. "
                      "Two viewing geometries allow a split into vertical and east motion.")
    cw = (W0 - 400000) // 2
    for k, (head, lines) in enumerate((
            ("GNSS", ["Daily positions in 3D", "Millimetre precision", "Only at single stations"]),
            ("InSAR (Sentinel-1)", ["Maps the whole area, about 100 m pixels", "Line of sight only",
                                    "Every 6 or 12 days"]))):
        x = X0 + k * (cw + 400000)
        b = box(s, x, Y0, cw, 2500000, name=f"Card {head}")
        box_text(b,
                 [[(head, {"size": 24, "bold": True, "color": BLUE})]] + [[("•  " + l, {"size": 20})] for l in lines],
                 anchor=MSO_ANCHOR.TOP, margin=Pt(20))
    b = box(s, X0, Y0 + 2900000, W0, 1100000, fill=BLUE, name="Combined")
    box_text(b, [[("Combined: ascending + descending InSAR give vertical and east motion; GNSS checks them",
                   {"size": 20, "bold": True, "color": WHITE})]], margin=Pt(20))

    # 4 research questions ---------------------------------------------------------
    s = content_slide(prs, "Three questions from the research plan",
                      "[Speaker 1] 0.5 min. Read the three questions; the results follow in this order. We describe "
                      "rates and the geometry of the uplift; no source model and no volumes.")
    qs = [("1", "Uplift rate", "How did the uplift rate change across the cycles since October 2023 and during "
                               "the current pause?"),
          ("2", "InSAR and GNSS", "How well do InSAR time series agree with GNSS during rapid volcanic "
                                  "deformation?"),
          ("3", "Uplift pattern", "Did the spatial pattern of uplift (centre, extent) stay stable between cycles?")]
    for k, (n, head, q) in enumerate(qs):
        y = Y0 + k * 1350000
        c = box(s, X0, y + 150000, 800000, 800000, fill=BLUE, shape=MSO_SHAPE.OVAL, name=f"Q{n}")
        box_text(c, [[(n, {"size": 28, "bold": True, "color": WHITE})]], align=PP_ALIGN.CENTER, margin=Pt(0))
        b = box(s, X0 + 1050000, y, W0 - 1050000, 1100000, name=f"Question {n}")
        box_text(b, [[(head, {"size": 20, "bold": True, "color": BLUE})], [(q, {"size": 20})]], margin=Pt(14))
    source(s, "No source modelling and no conversion to volumes (assumptions not available)")

    # 5 study area -----------------------------------------------------------------
    s = content_slide(prs, "Two Sentinel-1 frames and 14 GNSS stations cover the uplift area",
                      "[Speaker 2] 1 min. Left: the two LiCSAR frames, the processed area and the InSAR reference "
                      "at Straumsvík, 11 km from the GNSS reference REYK. Right: the GNSS stations around the uplift "
                      "centre; most were installed after November 2023, only SKSH and SENG cover the whole period.")
    picture(s, "study_area", X0, Y0, W0, YB - Y0)
    source(s, "Coastline: Natural Earth; elevation model: LiCSAR; station positions: Nevada Geodetic Laboratory")

    # 6 data ------------------------------------------------------------------------
    s = content_slide(prs, "Six years of Sentinel-1 and GNSS data",
                      "[Speaker 2] 1 min. All LiCSAR interferograms since January 2020. The descending frame ends "
                      "on 3 February 2026 because LiCSAR has not processed later scenes, so vertical and east end "
                      "there; ascending continues to September 2026. GNSS: daily NGL solutions for 14 stations, most "
                      "until May 2026, SENG until October 2026.")
    table(s, X0, Y0, W0, [
        ["Dataset", "Content", "Period"],
        ["InSAR ascending 016A_02504_162118", "3747 interferograms, 307 epochs", "01.2020 to 16.09.2026"],
        ["InSAR descending 155D_02484_191814", "1591 interferograms, 269 epochs", "01.2020 to 03.02.2026"],
        ["GNSS", "14 stations within 15 km, daily IGS20, reference REYK", "2020 to 05.2026 (SENG 10.2026)"],
        ["Weather model", "GACOS tropospheric delay for every epoch", "2020 to 2026"],
    ], col_w=[3.2, 4.4, 2.5], size=16, row_h=Pt(44))
    stat(s, X0, Y0 + 3100000, 3400000, "6 or 12 days", "Sentinel-1 revisit (12 days in 2022 to 2024)")
    stat(s, X0 + 3700000, Y0 + 3100000, 3400000, "≈ 100 m", "pixel size of the LiCSAR products")
    stat(s, X0 + 7400000, Y0 + 3100000, 3300000, "39 km", "uplift centre to GNSS reference REYK")
    source(s, "LiCSAR contains modified Copernicus Sentinel data 2020 to 2026 analysed by COMET; "
              "GACOS: Yu et al. (2018); GNSS: NGL, Blewitt et al. (2018)")

    # 7 processing chain --------------------------------------------------------------
    s = content_slide(prs, "From interferograms to rates and uplift maps per cycle",
                      "[Speaker 2] 1.5 min. Top: InSAR. LiCSBAS removes the weather delay, rejects bad interferograms, "
                      "checks loop closure, inverts the network and masks unreliable pixels; ascending and "
                      "descending are combined into vertical and east. Bottom: GNSS relative to REYK, antenna offsets "
                      "and outliers removed. Rates: a line fitted per inflation period, uncertainty corrected for "
                      "correlated noise. Pattern: an elliptical Gaussian fitted to each cycle's uplift map.")
    bw, bh, gap = 2300000, 1250000, 510000
    ys = (Y0 + 250000, Y0 + 2650000)
    rows = (
        [("LiCSAR", "interferograms, 2 frames"), ("LiCSBAS", "GACOS, quality and loop checks, inversion, mask"),
         ("Decomposition", "LOS asc + desc to vertical and east"), ("Cycle maps", "Gaussian fit: centre, extent, shape")],
        [("NGL GNSS", "daily positions, 14 stations"), ("Cleaning", "relative to REYK, offsets and outliers removed"),
         ("Rates per period", "line fit, σ for correlated noise"), ("Comparison", "LOS and rates at the stations")],
    )
    for r, (y, row) in enumerate(zip(ys, rows)):
        for k, (head, sub) in enumerate(row):
            x = X0 + k * (bw + gap)
            last = (r == 1 and k == 3)
            b = box(s, x, y, bw, bh, fill=BLUE if last else TINT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=f"Step {r}{k}")
            b.adjustments[0] = 0.08
            col = WHITE if last else INK
            box_text(b, [[(head, {"size": 18, "bold": True, "color": WHITE if last else BLUE})],
                         [(sub, {"size": 14, "color": col})]], align=PP_ALIGN.CENTER, margin=Pt(6))
            if k < 3:
                arrow(s, x + bw + 40000, y + bh // 2, x + bw + gap - 40000, y + bh // 2)
    x_mid = X0 + 2 * (bw + gap) + bw // 2
    arrow(s, x_mid, ys[0] + bh + 40000, x_mid, ys[1] - 40000)
    text(s, X0, ys[1] + bh + 350000, W0, 500000,
         ["Software: LiCSBAS (COMET version) and Python scripts in Docker; all settings in one configuration file"],
         size=16, color=GREY)
    source(s, "LiCSBAS: Morishita et al. (2020); decomposition: Wright et al. (2004)")

    # ===== question 1 ==================================================================
    divider(prs, 1, "How did the uplift rate change across the cycles and during the pause?",
            "[Speaker 3] Transition to the first question.")

    s = content_slide(prs, "Since November 2023: steady uplift, then sudden subsidence at every event",
                      "[Speaker 3] 1 min. Vertical displacement at the uplift centre. Small uplift periods in 2020 "
                      "and 2022. From November 2023 a saw tooth: weeks of steady uplift, then a drop at each dike "
                      "intrusion or eruption. Each cycle from March 2024 added 235 to 325 mm. After July 2025 no "
                      "drop any more: the centre rose by 325 ± 20 mm until February 2026.")
    picture(s, "centre", X0, Y0, W0, YB - Y0)
    source(s, "Mean over 3 x 3 pixels at the uplift centre (63.866°N, 22.458°W), unfiltered LiCSBAS time series")

    s = content_slide(prs, "The uplift rate fell in steps, and keeps falling during the pause",
                      "[Speaker 3] 1.5 min. Each segment is the rate of one inflation period, black InSAR, blue GNSS. "
                      "About 11 mm/day after the first intrusion, about 6 in early 2024, then constant at about 4 "
                      "through 2024, 2.6 in 2025. In the pause the rate no longer stays constant: from 2.5 mm/day in "
                      "August 2025 it falls window by window to 0.39 ± 0.05 mm/day at SENG in autumn 2026. "
                      "InSAR and GNSS show the same decline. HS02 is closest to the centre and fastest, so compare "
                      "rates only at the same point.")
    picture(s, "rates", X0, Y0, 7700000, YB - Y0, align="left")
    x2 = X0 + 7950000
    stat(s, x2, Y0 + 300000, 2780000, "0.39 ± 0.05", "mm/day at SENG, Aug to Oct 2026 (2.25 in Aug 2025)",
         color=PETROL, vsize=30)
    text(s, x2, Y0 + 2200000, 2780000, 2400000, [
        "Nov 2023: 11.4 ± 1.2 mm/day (HS02)",
        "2024: about 4 mm/day",
        "2025: about 2.6 mm/day",
    ], size=16, bullets=True, space=8)
    source(s, "Line fit per period; 1σ corrected for autocorrelated residuals; pause from 6 Aug 2025 in 60 day windows")

    # ===== question 2 ==================================================================
    divider(prs, 2, "How well does InSAR agree with GNSS during rapid deformation?",
            "[Speaker 4] Transition to the second question.")

    s = content_slide(prs, "During inflation InSAR agrees with GNSS within 15 to 20 mm",
                      "[Speaker 4] 1 min. Each point is the change over one inflation period at one station, InSAR "
                      "against GNSS. They lie on the 1:1 line: RMS 16 mm ascending, 15 mm descending, 20 mm vertical, "
                      "11 stations. The rates per period agree too: InSAR is on average 0.18 mm/day, or 5 to 7 %, "
                      "lower than GNSS at HS02 and SENG.")
    picture(s, "gnss", X0, Y0, 5600000, YB - Y0, align="left")
    x2 = X0 + 6200000
    stat(s, x2, Y0 + 200000, 4400000, "15 to 20 mm", "RMS difference per inflation period, 11 stations")
    text(s, x2, Y0 + 2000000, 4400000, 2600000, [
        "80 to 86 pairs per component",
        "Rates: InSAR 0.18 mm/day (5 to 7 %) below GNSS",
        "SKSH, 2020 to 2026: 23 mm RMS over the whole series",
    ], size=18, bullets=True, space=10)
    source(s, "Pairs affected by known problems (descending gap Dec 2023 to Jan 2024, steps at the dikes) excluded")

    s = content_slide(prs, "Across the dike intrusions InSAR fails near the dikes",
                      "[Speaker 4] 1.5 min. Metre scale motion at the dikes cannot be unwrapped over 100 m pixels, "
                      "and new lava destroys coherence. With default settings all ten descending interferograms "
                      "across 10 November 2023 were rejected; after the fix the misfit to GNSS dropped from 87 to "
                      "20 mm. Still, next to the dikes the step is wrong by 350 to 760 mm. Also the fast cycles of "
                      "late 2023 had too few 12 day epochs for an InSAR rate: there GNSS is needed.")
    cw = (W0 - 2 * 350000) // 3
    for k, (val, lab, col) in enumerate((
            ("350 to 760 mm", "misfit of the 10 Nov 2023 step at the 5 stations next to the dikes", RED),
            ("57 to 93 mm", "RMS over all intrusions and eruptions (vertical, east, ascending)", RED),
            ("87 → 20 mm", "median RMS to GNSS, descending LOS, before and after the loop closure fix", BLUE))):
        x = X0 + k * (cw + 350000)
        b = box(s, x, Y0, cw, 1900000, name=f"Stat {k}")
        box_text(b, [[(val, {"size": 32 if k == 0 else 28, "bold": k == 0, "color": col})],
                     [(lab, {"size": 16, "color": INK})]], anchor=MSO_ANCHOR.TOP, margin=Pt(16))
    text(s, X0, Y0 + 2300000, W0, 2200000, [
        "Unwrapping: metre scale gradients over 50 to 110 m pixels; new lava removes coherence",
        "12 day revisit in 2023 and 2024: too few epochs for the short cycles, GNSS needed",
        "Away from the dikes: troposphere and the two references (11 km apart) remain",
    ], size=18, bullets=True, space=10)

    # ===== question 3 ==================================================================
    divider(prs, 3, "Did the spatial pattern of uplift stay stable between cycles?",
            "[Speaker 5] Transition to the third question.")

    s = content_slide(prs, "Same uplift pattern in 2020 and 2024, but about ten times larger",
                      "[Speaker 5] 1 min. Vertical displacement over two inflation periods. The pattern is elliptical "
                      "and centred west of the Sundhnúkur crater row, at about the same place. Note the colour "
                      "scales: 50 mm in 2020, more than 250 mm in 2024. Grey pixels are masked, mostly new lava.")
    picture(s, "maps", X0, Y0, W0, YB - Y0)
    source(s, "Triangles: GNSS stations; +: uplift centre; circle: Grindavík. Decomposition of both frames")

    s = content_slide(prs, "Since March 2024 the uplift centre has not moved by more than 90 m",
                      "[Speaker 5] 1.5 min. For each cycle an elliptical Gaussian was fitted to the uplift map. Left: "
                      "fitted centres and half maximum ellipses, coloured by time. Right: distance to the mean centre "
                      "since 2024. The cycles since March 2024, including the pause, lie within 90 m, with 50 to 90 m "
                      "uncertainty; extent 3.5 by 2.6 km, shape correlation 0.97 to 0.98. 2020 and 2022 lie 0.3 to "
                      "0.9 km away, but are ten times smaller. The two open symbols are affected by dikes. A stable "
                      "surface pattern does not prove a stable source; that needs modelling.")
    picture(s, "pattern", X0, Y0, W0, 4300000)
    text(s, X0, Y0 + 4350000, W0, 500000, [[
        ("< 90 m ", {"bold": True, "color": BLUE, "size": 24}),
        ("centre shift since Mar 2024; extent 3.5 × 2.6 km and shape (r = 0.97 to 0.98) unchanged", {"size": 18})]],
        size=18)
    source(s, "Open symbols, dashed: Nov 2023 (24 days after the first dike) and Apr 2025 (dike to the north east). "
              "Jul 2025*: pause, to 3 Feb 2026")

    # plan vs reality --------------------------------------------------------------------
    s = content_slide(prs, "The research plan was kept, with five adjustments",
                      "[Speaker 5] 1 min. Same data, same questions, GNSS validation. Five changes, each for a "
                      "concrete reason. Biggest one: no dedicated Sentinel-1 processing, LiCSAR was enough during "
                      "inflation but not at the dikes. Practical challenges: no local Python or LaTeX, so everything "
                      "ran in Docker; LiCSBAS ran out of memory with many workers.")
    table(s, X0, Y0, W0, [
        ["Plan", "Done", "Reason"],
        ["Dedicated Sentinel-1 processing where needed", "LiCSAR products only", "Enough during inflation; not at dikes"],
        ["Default loop closure threshold", "Descending: 3 rad, pixel wise removal", "Nov 2023 step rejected otherwise"],
        ["Reference at least 15 km away", "At least 24 km, area extended", "Less uplift signal at the reference"],
        ["Both frames to the latest date", "Descending ends 03.02.2026", "Not yet processed by LiCSAR"],
        ["Uplift centre 63.88°N, 22.43°W", "Measured peak, 63.866°N, 22.458°W", "Same peak in several periods"],
    ], col_w=[3.4, 3.4, 3.4], size=16, row_h=Pt(40))
    text(s, X0, Y0 + 3500000, W0, 1100000, [
        [("Challenges: ", {"bold": True}), "unwrapping at the dikes, 12 day revisit in 2022 to 2024, "
                                          "LiCSBAS memory limits, no local tools (all processing in Docker)"],
    ], size=18)

    # summary -----------------------------------------------------------------------------
    s = content_slide(prs, "Summary: the rate keeps falling, the pattern stays",
                      "[Speaker 5] 1 min. One answer per question. Outlook: descending data after February 2026 and "
                      "offset tracking near the dikes would close the main gaps.")
    pts = [("1", "Uplift rate fell in steps (11.4 → 4 → 2.6 mm/day) and keeps falling in the pause, "
                 "to 0.39 ± 0.05 mm/day"),
           ("2", "InSAR agrees with GNSS within 15 to 20 mm and 0.2 mm/day during inflation, "
                 "but fails next to the dikes"),
           ("3", "Since March 2024 centre, extent and shape of the uplift are stable (< 90 m)")]
    for k, (n, t) in enumerate(pts):
        y = Y0 + k * 1000000
        c = box(s, X0, y, 650000, 650000, fill=BLUE, shape=MSO_SHAPE.OVAL, name=f"Point {n}")
        box_text(c, [[(n, {"size": 22, "bold": True, "color": WHITE})]], align=PP_ALIGN.CENTER, margin=Pt(0))
        text(s, X0 + 900000, y - 100000, W0 - 900000, 850000, [t], size=20, anchor=MSO_ANCHOR.MIDDLE)
    b = box(s, X0, Y0 + 3400000, W0, 1000000, name="Outlook")
    box_text(b, [[("Outlook: ", {"size": 18, "bold": True, "color": BLUE}),
                  ("descending data after February 2026, offset tracking at the dikes, "
                   "source modelling to test the stability of the source", {"size": 18})]], margin=Pt(16))

    # thank you ---------------------------------------------------------------------------
    s = new_slide(prs, "Schlussfolie", notes="[Speaker 5] Thank the audience and open the discussion.")
    for ph in s.placeholders:
        if ph.placeholder_format.idx == 1:
            tf = ph.text_frame
            tf.text = "Thank you. Questions?"
            r = tf.paragraphs[0].runs[0]
            r.font.size = Pt(36)
            r.font.bold = True
            for line in ("", names, "Space Geodesy, Institute of Geodesy and Photogrammetry, ETH Zurich"):
                tf.add_paragraph().text = line
    drop_empty_placeholders(s, keep=())

    # backup ----------------------------------------------------------------------------------
    s = content_slide(prs, "Backup: uplift rate per period, InSAR and GNSS (mm/day)",
                      "Backup for questions on the rates. Same values as Table 1 of the report.")
    table(s, X0, Y0, W0, [
        ["Period from", "InSAR centre", "GNSS HS02", "GNSS SENG", "Period from", "InSAR centre", "GNSS HS02", "GNSS SENG"],
        ["2023-11-12", "–", "11.39 ± 1.17", "9.54 ± 1.81", "Pause:", "", "", ""],
        ["2023-12-20", "–", "6.00 ± 0.98", "5.38 ± 0.91", "2025-08-06", "2.58 ± 0.18", "2.51 ± 0.06", "2.25 ± 0.06"],
        ["2024-01-16", "–", "6.08 ± 0.31", "5.45 ± 0.27", "2025-10-05", "1.51 ± 0.14", "1.62 ± 0.04", "1.39 ± 0.06"],
        ["2024-03-18", "4.05 ± 0.20", "3.72 ± 0.13", "3.60 ± 0.11", "2025-12-04", "0.96 ± 0.10", "1.03 ± 0.07", "0.92 ± 0.05"],
        ["2024-05-31", "4.16 ± 0.22", "4.79 ± 0.30", "3.78 ± 0.13", "2026-02-02", "–", "0.76 ± 0.07", "0.68 ± 0.05"],
        ["2024-08-24", "4.01 ± 0.24", "4.08 ± 0.12", "3.45 ± 0.10", "2026-04-03", "–", "–", "0.62 ± 0.05"],
        ["2024-11-22", "2.74 ± 0.24", "2.73 ± 0.17", "2.38 ± 0.12", "2026-06-02", "–", "–", "0.36 ± 0.05"],
        ["2025-04-03", "2.56 ± 0.35", "2.84 ± 0.15", "2.53 ± 0.11", "2026-08-01", "–", "–", "0.39 ± 0.05"],
    ], col_w=[1.3, 1.4, 1.4, 1.4, 1.3, 1.4, 1.4, 1.4], size=13, row_h=Pt(32))
    source(s, "Line fit per period (2 days after an event to 1 day before the next); 60 day windows in the pause")

    s = content_slide(prs, "Backup: SKSH, 1.1 km from the centre, InSAR follows GNSS from 2020 to 2026",
                      "Backup for questions on the GNSS comparison and the LOS projection.")
    picture(s, "sksh", X0, Y0, W0, YB - Y0)
    source(s, "GNSS: NGL daily positions relative to REYK, projected onto the ascending LOS; RMS difference 23 mm")

    s = content_slide(prs, "Backup: LiCSBAS settings",
                      "Backup for questions on the processing. Only the descending frame uses the changed step 12 "
                      "settings.")
    table(s, X0, Y0, W0, [
        ["Setting", "Value", "Note"],
        ["Multilooking", "none (LiCSAR 0.001°)", "about 111 x 49 m"],
        ["Weather correction", "GACOS (step 03)", "all epochs available"],
        ["Step 11 thresholds", "default", "coherence, unwrapped fraction"],
        ["Step 12 loop threshold", "1.5 rad asc, 3 rad desc", "desc: nullify failing pixels"],
        ["Step 15 mask", "n_ifg_noloop > 50", "pixels outside closed loops"],
        ["Reference", "5 x 5 px at Straumsvík", "coherence 0.62 and 0.64, 27 km from centre"],
        ["Networks used", "3247 asc, 1513 desc", "303 and 267 epochs, connected"],
    ], col_w=[2.8, 3.4, 4.0], size=16, row_h=Pt(36))

    prs.save(OUT)
    print(f"wrote {OUT} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    build()
