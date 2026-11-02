# Svartsengi InSAR Pipeline: Plan for Claude Code

## Context

This is an ETH Space Geodesy course project (group work). Topic: magma inflow and inflation/deflation cycles at the Svartsengi volcanic system and the Sundhnúkur crater row (Reykjanes Peninsula, SW Iceland), from late 2023 to the present. The focus is geodetic processing (InSAR and GNSS), not geological or magma flow modelling.

InSAR source: COMET LiCSAR Sentinel-1 products, processed into time series with LiCSBAS.

Your job: build a reproducible pipeline that downloads the required data, runs the processing automatically, and produces easy-to-use visualisations (interactive for exploration, static for the report).

Work in stages. After each stage, run it, check the outputs, and report what you found before moving on. Do not guess frame IDs, station names, or event dates: verify them from the data server or official sources and record the source.

## Area and time of interest

- Svartsengi uplift centre: approx. 63.88 N, 22.43 W
- Sundhnúkur crater row: approx. 63.87 to 63.90 N, 22.35 to 22.40 W
- Grindavík: approx. 63.84 N, 22.43 W
- Processing AOI (clip box): lon -22.70 to -22.15, lat 63.75 to 64.00 (adjust if needed so a stable reference area is included)
- Time window: 2020-01-01 to the latest available acquisition. This covers the 2020 to 2022 inflation/deflation cycles at Svartsengi and the activity since October 2023.
- Note: the Fagradalsfjall eruptions (2021, 2022, 2023) lie inside the AOI, east of Svartsengi, with their own diking and deformation. Keep them in the data, but exclude that area when choosing the reference point and mark it in the figures.

All of these values go into a single `config.yaml`, not hard-coded in scripts.

## Stage 0: Environment

1. Create a conda environment (`environment.yml`) with Python 3.11, gdal, numpy, scipy, h5py, xarray, rioxarray, matplotlib, pandas, pyyaml, requests, tqdm, plus the visualisation stack (see Stage 5).
2. Install LiCSBAS from the maintained fork: `git clone https://github.com/comet-licsar/LiCSBAS`. Do NOT use `yumorishita/LiCSBAS`; its download URLs broke after COMET's storage migration in October 2025.
3. Follow the LiCSBAS install instructions (add `bin` to PATH, `LiCSBAS_lib` to PYTHONPATH) and wrap this in `scripts/env.sh`.
4. Verify with `LiCSBAS01_get_geotiff.py -h`.

## Stage 1: Find the LiCSAR frames

1. The products live under `https://gws-access.jasmin.ac.uk/public/nceo_geohazards/LiCSAR_products/<track>/<frame_id>/`. If that host fails, check the COMET-LiCS portal (https://comet.nerc.ac.uk/comet-lics-portal) for the current URL.
2. Earlier studies of this area used ascending track 16 and descending track 155. List the frame directories under tracks 16 and 155.
3. For each candidate frame, download only the small metadata files (e.g. `metadata/<frame>.geo.hgt.tif` or `.geo.E.tif`) and check whether the AOI is fully covered.
4. Also check neighbouring tracks if one geometry has poor coverage, but prefer one ascending and one descending frame.
5. For each chosen frame, count the available interferograms in the time window and report the number of epochs, the first and last dates, and any large gaps.
6. Write the selected frame IDs into `config.yaml` and a short `docs/frames.md` with the evidence.

Implement this as `scripts/find_frames.py`.

## Stage 2: Download

1. `scripts/download.py` (or a shell wrapper) runs `LiCSBAS01_get_geotiff.py -f <frame> -s <start> -e <end> --get_gacos` for each frame in its own working directory: `data/<frame_id>/`.
2. Downloads must be resumable and idempotent (re-running skips existing files).
3. Print expected data volume before downloading. If a frame exceeds roughly 20 GB, stop and ask first. With a 2020 start the volume will be noticeably larger; consider downloading in yearly chunks so a failure does not restart everything.
4. Log to `logs/download_<frame>.log`.

## Stage 3: LiCSBAS time series per frame

Use LiCSBAS's `batch_LiCSBAS.sh` (copy it into each frame directory and set the parameters from `config.yaml` via a small generator script) rather than reimplementing the steps.

Steps to run:
- 02 `ml_prep`: multilooking. Start with `n=1` (about 100 m pixels); the AOI is small.
- 03op GACOS correction: on, if GACOS coverage is complete for the epochs; otherwise report which epochs are missing and decide (drop them or skip GACOS).
- 04op mask: optional.
- 05op clip to the AOI from `config.yaml`.
- 11 unwrapping check, 12 loop closure, 13 small baseline inversion, 14 velocity std, 15 mask, 16 spatiotemporal filter.

Reference point: choose a stable, coherent area well outside the deformation zone (at least about 15 km from the uplift centre, not on the young lava fields). Put it in `config.yaml` and justify it in `docs/processing_notes.md`.

Known difficulties, handle and document them:
- Dike intrusions (especially 10 November 2023) caused metre-scale displacement and surface fracturing. Expect unwrapping errors and decorrelation around Grindavík and the Sundhnúkur dikes. Do not try to "fix" this; mask it via the coherence and loop closure thresholds and report what was masked.
- New lava flows decorrelate completely. These areas will be masked; that is expected.
- LiCSBAS's temporal filter (step 16) smooths sharp deflation steps. Keep both `cum.h5` (unfiltered) and `cum_filt.h5`, and use the unfiltered one for event-related displacement.
- Sentinel-1 revisit was 6 days (S1A and S1B) until S1B failed in December 2021, then 12 days until Sentinel-1C became operational in 2025. Report the effective sampling per frame and period, and check the interferogram network for gaps or disconnections around these transitions.
- Over almost six years, the network is long. If loop closure or the inversion shows problems in specific periods (eruptions, snow cover in winter, the S1B gap), report them per period instead of tuning thresholds globally until everything passes.
- Fagradalsfjall dikes and lava fields (2021 to 2023) will also decorrelate; handle them the same way as Sundhnúkur.

Output per frame: `cum.h5`, `cum_filt.h5`, velocity, coherence and mask rasters, plus the LiCSBAS QC figures. Save the QC figures to `figures/qc/<frame>/` and summarise problems in `docs/processing_notes.md`.

## Stage 4: Derived products

`scripts/postprocess.py`:

1. Export cumulative displacement per epoch and mean velocity to GeoTIFF (LOS, mm), and a NetCDF/xarray cube per frame (`time, lat, lon`) for easy loading in notebooks.
2. Ascending/descending decomposition: resample both frames to a common grid, interpolate both time series to common dates (or use overlapping intervals only), and solve per pixel for vertical and east-west displacement using the LiCSAR E/N/U LOS unit vectors (neglect north, state this assumption). Output vertical and east-west cubes and velocity maps.
3. Point time series extraction at:
   - the uplift centre (pixel or small averaged window, e.g. 3x3),
   - a list of GNSS station locations from `config.yaml`,
   - any additional user-defined points.
   Save as CSV in `results/timeseries/`.
4. Event table: compile `config/events.csv` with dates from 2020 onward: Svartsengi inflation episodes in 2020 to 2022, Fagradalsfjall dike intrusions and eruptions (2021, 2022, 2023), and the Sundhnúkur dike intrusions and eruptions from November 2023 onward (sources: Icelandic Meteorological Office, vedur.is, and Parks et al. 2025, EPSL 658, 119324). Each row needs a type column (inflation onset, dike, eruption), a location column (Svartsengi, Fagradalsfjall, Sundhnúkur), and a source column. Use it to:
   - mark events in all time series plots,
   - compute uplift per inflation episode (between consecutive events) and the corresponding mean uplift rate at the uplift centre.

## Stage 5: Visualisation (priority: easy to use)

### 5a Interactive viewer
Build one local app, Streamlit preferred (`app/viewer.py`, run with `streamlit run app/viewer.py`):
- map view (basemap with hillshade or OSM) with a layer selector: LOS velocity (asc/desc), vertical velocity, east-west velocity, coherence, mask
- date slider showing cumulative displacement at that date
- click on a pixel (or enter lat/lon) to plot its time series below the map, with event dates as vertical lines
- toggle filtered/unfiltered time series
- overlay of GNSS station locations and, if available, GNSS time series in the same plot (vertical component vs InSAR vertical)
- download button for the displayed time series as CSV

Keep the app fast: load the precomputed NetCDF cubes, do not recompute anything in the app.

Also mention in the README that LiCSBAS ships its own interactive viewer (`LiCSBAS_plot_ts.py`) for quick checks.

### 5b Report figures (`scripts/make_figures.py`)
Static, publication-ready figures (PDF and PNG, consistent colour scales, scientific colour maps such as `vik`/`roma` from cmcrameri, scale bar, lat/lon axes, units in mm or mm/yr):
1. Study area map with frames, AOI, reference point, GNSS stations
2. LOS velocity maps, ascending and descending
3. Vertical and east-west velocity maps
4. Cumulative vertical displacement for selected inflation episodes, both 2020 to 2022 and since 2023 (small multiples)
5. Time series at the uplift centre from 2020 to present with event markers, coloured by location (Svartsengi, Fagradalsfjall, Sundhnúkur)
6. InSAR vs GNSS comparison at one or two stations (plus RMS difference)
7. Uplift per inflation episode (bar or scatter plot)

Figure size should suit a 2-column, 4-page report. Save to `figures/report/`.

## Stage 6: GNSS (prepared hook, source not final)

The GNSS data source is not decided yet; a likely option is the Nevada Geodetic Laboratory (geodesy.unr.edu, `tenv3` daily time series in IGS14/IGS20).
- Write `scripts/get_gnss.py` that, given station IDs in `config.yaml`, downloads NGL time series and converts them to a common CSV format (date, east, north, up in mm, relative to the first epoch).
- Find stations within about 15 km of the uplift centre in the NGL station list and report them with distance; do not guess station codes.
- For comparison with InSAR, reference both to the same stable point or compare relative displacement over the same intervals, and project GNSS ENU into the LOS of each frame.

## Orchestration and repository layout

```
config.yaml
config/events.csv
environment.yml
Makefile            # targets: env, frames, download, process, post, figures, app, all
scripts/            # find_frames.py, download.py, run_licsbas.py, postprocess.py, get_gnss.py, make_figures.py
app/viewer.py
data/<frame_id>/    # raw LiCSAR + LiCSBAS working dirs (git-ignored)
results/            # cubes, GeoTIFFs, CSV time series
figures/qc/, figures/report/
docs/frames.md, docs/processing_notes.md
logs/
README.md
```

`make all` must run the whole chain from an empty `data/` folder. Every step reads parameters only from `config.yaml`.

## Acceptance criteria

- `make all` runs end to end without manual steps (except the 20 GB confirmation).
- Each processing stage writes a short summary (frame IDs, number of epochs and interferograms used, masked fraction, reference point) to `docs/processing_notes.md`.
- Uplift at the centre per inflation episode is plausible in order of magnitude relative to published values (Parks et al. 2025); large discrepancies are flagged, not hidden.
- Viewer starts with one command and shows maps plus clickable time series.
- README explains setup, running, outputs, and the required data acknowledgement and citations.

## Required acknowledgement and citations (put in README)

- Acknowledgement: "LiCSAR contains modified Copernicus Sentinel data [years used] analysed by the Centre for the Observation and Modelling of Earthquakes, Volcanoes and Tectonics (COMET)."
- Lazecký et al. (2020), LiCSAR, Remote Sensing 12, 2430, doi:10.3390/rs12152430
- Morishita et al. (2020), LiCSBAS, Remote Sensing 12, 424, doi:10.3390/rs12030424
- Yu et al. (2018) for GACOS, if used
- Parks et al. (2025), EPSL 658, 119324, doi:10.1016/j.epsl.2025.119324 (reference results)
