#!/usr/bin/env bash
# Put LiCSBAS on PATH/PYTHONPATH. Already done in the Docker image;
# source this when running natively on Linux:  source scripts/env.sh
# Override the install location with LICSBAS_DIR=/path/to/LiCSBAS.
export LICSBAS_DIR="${LICSBAS_DIR:-$HOME/LiCSBAS}"
if [ ! -d "$LICSBAS_DIR/bin" ]; then
  echo "LiCSBAS not found at $LICSBAS_DIR (git clone https://github.com/comet-licsar/LiCSBAS)" >&2
  return 1 2>/dev/null || exit 1
fi
case ":$PATH:" in *":$LICSBAS_DIR/bin:"*) ;; *) export PATH="$LICSBAS_DIR/bin:$PATH" ;; esac
case ":${PYTHONPATH:-}:" in *":$LICSBAS_DIR/LiCSBAS_lib:"*) ;; *) export PYTHONPATH="$LICSBAS_DIR/LiCSBAS_lib${PYTHONPATH:+:$PYTHONPATH}" ;; esac
