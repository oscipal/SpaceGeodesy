# Svartsengi InSAR

Ground deformation of the Svartsengi–Sundhnúkur volcanic system (Reykjanes Peninsula, Iceland) from
Sentinel-1 InSAR, 2020-01-01 to the latest acquisition. The pipeline downloads COMET LiCSAR
interferograms, builds displacement time series with LiCSBAS, and derives vertical and east–west
motion, the uplift curve at the Svartsengi inflation centre and the uplift per inflation episode.

Group project for Space Geodesy (ETH Zürich, Geomatics). The full task description is in
[docs/svartsengi_insar_plan.md](docs/svartsengi_insar_plan.md).

## Status

| Stage | Make target | Script | State |
|---|---|---|---|
| 0 Environment | `env` | Dockerfile, `environment.yml` | done |
| 1 Find frames | `frames` | `scripts/find_frames.py` | done, see [docs/frames.md](docs/frames.md) |
| 2 Download | `download` | `scripts/download.py` | done, 3747 + 1591 interferograms (3.5 GB) |
| 3 LiCSBAS time series | `process` | `scripts/run_licsbas.py` | running (step 13, ascending frame) |
| 4 Derived products | `post` | `scripts/postprocess.py` | written, not yet run |
| 5a Viewer | `app` | `app/viewer.py` | not yet written |
| 5b Report figures | `figures` | `scripts/make_figures.py` | not yet written |
| 6 GNSS | `gnss` | `scripts/get_gnss.py` | not yet written |

Until Stage 3 finishes, `scripts/export_quicklook.py` renders a selection of single interferograms
for a first look (see [Quick look](#quick-look)).

## Data

Two LiCSAR frames cover the study area, one per viewing geometry:

| Frame | Geometry | Coverage | Epochs | Interferograms |
|---|---|---|---|---|
| `016A_02504_162118` | ascending | 2020-01-02 – 2026-09-16 | 307 | 3747 |
| `155D_02484_191814` | descending | 2020-01-06 – 2026-02-03 | 269 | 1591 |

Products are read from the
[LiCSAR archive on JASMIN](https://gws-access.jasmin.ac.uk/public/nceo_geohazards/LiCSAR_products/)
(interferograms via CEDA). LiCSAR has not processed the descending frame beyond 2026-02-03, so the
ascending/descending decomposition ends there; later data are ascending line of sight only.

`scripts/download.py` does not fetch whole frames (about 625 GB for both since 2020). It reads only
the AOI window of each GeoTIFF through GDAL `/vsicurl/` range requests and writes the same folder
layout as `LiCSBAS01_get_geotiff.py`. It also repairs about 1070 older unwrapped-phase files whose
GeoTIFF header is off by one pixel, which LiCSBAS would otherwise skip. Details are in
[docs/processing_notes.md](docs/processing_notes.md).

## Requirements

- Docker (Docker Desktop on Windows or macOS). The image contains Python 3.11, GDAL, the packages in
  `environment.yml`, `make`, and the [COMET fork of LiCSBAS](https://github.com/comet-licsar/LiCSBAS)
  pinned to commit `a145e6c`, with a memory-layout patch for step 12 (`docker/patch_licsbas.sh`)
  and a patch making step 13 resumable and fixing its patch rows (`docker/patch_licsbas13.py`).
- About 10 GB of free disk for the image, the downloaded data and the LiCSBAS working files.
- RAM is the limiting factor for Stage 3. On a 16 GB Windows machine (Docker VM about 7.6 GB),
  `licsbas.n_para: 2` and `licsbas.mem_size_mb: 600` in `config.yaml` keep step 13 from running out
  of memory. Step 13 then takes about 22 hours for the ascending frame.

Without Docker, on Linux or macOS: create the environment with
`micromamba create -n svartsengi -f environment.yml`, clone LiCSBAS at the same commit, run
`bash docker/patch_licsbas.sh <LiCSBAS>/bin/LiCSBAS12_loop_closure.py`, then `source scripts/env.sh`
and use `make` directly. Native Windows is not supported: LiCSBAS relies on Bash scripts and on
`multiprocessing` with fork.

## Usage

All parameters live in [config.yaml](config.yaml): AOI, time window, frames, download limits, LiCSBAS
settings, reference point, sites and event table. On Windows, `dc.ps1` runs commands inside the
container:

```powershell
.\dc.ps1 build          # build the image (first time, ~25 min)
.\dc.ps1 make env       # Stage 0: check the toolchain
.\dc.ps1 make frames    # Stage 1
.\dc.ps1 make download  # Stage 2
.\dc.ps1 make process   # Stage 3
.\dc.ps1 make post      # Stage 4
.\dc.ps1 bash           # shell inside the container
```

On Linux or macOS, the equivalent is `docker run --rm -it -v "$PWD:/work" -v svartsengi-work:/vol
-e LICSBAS_WORK=/vol -w /work svartsengi-insar make <target>`.

Stage 3 runs for a day or more, so start it detached so that closing the terminal does not stop it:

```bash
docker run -d --restart on-failure:3 --name svartsengi-process \
  -v "<repo path>:/work" -v svartsengi-work:/vol -e LICSBAS_WORK=/vol -w /work \
  svartsengi-insar bash -c 'make process >> logs/make_process.out 2>&1; echo "exit: $?" >> logs/make_process.out'
```

Progress is in `logs/make_process.out` and `logs/licsbas_<frame>_<steps>.log`. Shutting down or
restarting the computer, or quitting Docker Desktop, stops the run; with the restart policy it
continues when Docker starts again. Steps that already finished are skipped, and step 13 resumes
after its last finished patch (`docker/patch_licsbas13.py`; upstream LiCSBAS cannot resume with
the small patches needed here).

### What Stage 3 does

`scripts/run_licsbas.py` runs, for each frame:

1. LiCSBAS steps 02–11: read the clipped interferograms, subtract the GACOS atmospheric model,
   reject interferograms with low coherence or poor unwrapping coverage.
2. Choose one reference window valid for both frames: at least 24 km from the uplift centre, outside
   the active areas, unwrapped in at least 95 % of interferograms, with the highest coherence. The
   current choice is Straumsvík (64.0458 N, 22.0243 W, 27 km away), stored in `config.yaml`.
3. LiCSBAS steps 12–16: loop-closure check, small-baseline inversion, velocity uncertainty, masking
   and spatio-temporal filter.
4. Export: copy `cum.h5`, `cum_filt.h5` and the result rasters to `results/licsbas/<frame>/`,
   re-referenced to the common window (LiCSBAS 13 and 16 would otherwise pick their own reference
   pixel), and the QC figures to `figures/qc/<frame>/`.

Each phase is skipped when its outputs exist and the parameters affecting results are unchanged;
`python scripts/run_licsbas.py --force` redoes everything, `--frame <id>` processes one frame.
For quick checks of a finished time series, LiCSBAS ships its own interactive viewer,
`LiCSBAS_plot_ts.py`.

### Quick look

```powershell
.\dc.ps1 python scripts/export_quicklook.py
```

writes PNGs of 19 single interferograms around the main events (2020 inflation, Fagradalsfjall dikes,
the Grindavík dike of 10 Nov 2023, the Sundhnúkur eruptions 2023–2025 and the latest pairs) to
`results/quicklook/`, as line-of-sight displacement, re-wrapped fringes and coherence, referenced to
the Straumsvík window. These are single LiCSAR interferograms without weather correction or
time-series inversion. `results/quicklook/viewer.html` is a browser viewer for them (it loads its
files over HTTP, so serve the folder, e.g. `python -m http.server`, rather than opening the file).

## Outputs

| Path | Content |
|---|---|
| `data/<frame>/` | clipped interferograms, coherence, GACOS, download manifest |
| `results/frames/summary.json` | frame search results |
| `results/licsbas/<frame>/` | LiCSBAS `cum.h5`, `cum_filt.h5`, result rasters (re-referenced) |
| `results/cubes/`, `results/geotiff/` | NetCDF cubes and GeoTIFFs (Stage 4) |
| `results/timeseries/`, `results/episodes.csv` | point time series and uplift per episode (Stage 4) |
| `figures/qc/<frame>/` | LiCSBAS quality-control figures |
| `docs/frames.md`, `docs/processing_notes.md` | per-stage summaries, written by the scripts |
| `logs/` | download and LiCSBAS logs |

`data/`, `results/`, `logs/` and `figures/qc/` are not tracked by git. Line-of-sight displacement is
positive towards the satellite (LiCSBAS convention). Eruption and intrusion dates used for the
episodes are in [config/events.csv](config/events.csv), each with its source.

## Repository layout

```
config.yaml            all parameters
config/events.csv      dated events (inflation onsets, dikes, eruptions) with sources
scripts/               one script per stage, plus common.py (config, server access)
docker/                LiCSBAS patch applied in the image
Dockerfile, environment.yml, dc.ps1, Makefile
docs/                  task plan, frame summary, processing notes
```

## Acknowledgement

LiCSAR contains modified Copernicus Sentinel data 2020–2026 analysed by the Centre for the
Observation and Modelling of Earthquakes, Volcanoes and Tectonics (COMET).

## References

- Lazecký, M., et al. (2020). LiCSAR: An automatic InSAR tool for measuring and monitoring tectonic
  and volcanic activity. *Remote Sensing*, 12(15), 2430.
  [doi:10.3390/rs12152430](https://doi.org/10.3390/rs12152430)
- Morishita, Y., et al. (2020). LiCSBAS: An open-source InSAR time series analysis package
  integrated with the LiCSAR automated Sentinel-1 InSAR processor. *Remote Sensing*, 12(3), 424.
  [doi:10.3390/rs12030424](https://doi.org/10.3390/rs12030424)
- Yu, C., Li, Z., Penna, N. T., & Crippa, P. (2018). Generic atmospheric correction model for
  Interferometric Synthetic Aperture Radar observations. *Journal of Geophysical Research: Solid
  Earth*, 123, 9202–9222. [doi:10.1029/2017JB015305](https://doi.org/10.1029/2017JB015305)
- Parks, M., et al. (2025). *Earth and Planetary Science Letters*, 658, 119324 (reference results
  for the uplift per episode). [doi:10.1016/j.epsl.2025.119324](https://doi.org/10.1016/j.epsl.2025.119324)
