# Runs inside the Docker image (see dc.ps1). On Windows:  .\dc.ps1 make <target>
SHELL := /bin/bash
PY    := python

.PHONY: help env frames download process post gnss cycles figures app all

help:
	@echo "targets: env frames download process post gnss cycles figures app all"

env:            ## Stage 0: verify toolchain
	@$(PY) -c "import osgeo, h5py, xarray, rioxarray, cmcrameri, streamlit; print('python env OK')"
	@LiCSBAS01_get_geotiff.py -h > /dev/null && echo "LiCSBAS OK ($$LICSBAS_DIR)"

frames:         ## Stage 1
	$(PY) scripts/find_frames.py

download:       ## Stage 2
	$(PY) scripts/download.py

process:        ## Stage 3
	$(PY) scripts/run_licsbas.py

post:           ## Stage 4
	$(PY) scripts/postprocess.py

gnss:           ## Stage 6
	$(PY) scripts/get_gnss.py

cycles:         ## Stage 7 (rates per cycle, pattern stability; needs gnss)
	$(PY) scripts/cycles.py

figures:        ## Stage 5b
	$(PY) scripts/make_figures.py

app:            ## Stage 5a
	streamlit run app/viewer.py --server.address 0.0.0.0 --server.port 8501

all: env frames download process post gnss cycles figures   # gnss needs the Stage 4 cubes and episodes
