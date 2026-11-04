#!/usr/bin/env bash
# Performance patch for LiCSBAS12_loop_closure.py (comet-licsar/LiCSBAS @ a145e6c).
#
# The 4th loop keeps three cubes (y, x, ifg) of ~0.8 GB each for 3747 ifgs and
# writes them one ifg at a time along the LAST axis, so every write touches every
# memory page of the cube. As soon as part of a cube is swapped out (Docker VM with
# 8 GB), each loop faults the whole cube back in and step 12 effectively stalls
# (observed: stuck >20 min at loop 17800/26964, 680 MB swapped).
#
# Fix: store the cubes as (ifg, y, x) so each per-ifg slice is contiguous.
# Pure memory-layout change: same values, same results.
set -euo pipefail
f="${1:-/opt/LiCSBAS/bin/LiCSBAS12_loop_closure.py}"

n_loc=$(grep -c '\.loc\[:, :, ' "$f")
n_dims=$(grep -c 'dims=\["y", "x", "ifgd"\]' "$f")
n_full=$(grep -c 'np.full((length, width, len(ifgdates)), nullify_aggressive)' "$f")
n_zero=$(grep -c 'np.zeros((length, width, len(ifgdates)), dtype=np.int8)' "$f")
if [ "$n_dims" -ne 3 ] || [ "$n_full" -ne 1 ] || [ "$n_zero" -ne 2 ] || [ "$n_loc" -lt 20 ]; then
  echo "patch_licsbas.sh: unexpected source (dims=$n_dims full=$n_full zeros=$n_zero loc=$n_loc); update the patch" >&2
  exit 1
fi

sed -i \
  -e 's/dims=\["y", "x", "ifgd"\]/dims=["ifgd", "y", "x"]/' \
  -e 's/np.full((length, width, len(ifgdates)), nullify_aggressive)/np.full((len(ifgdates), length, width), nullify_aggressive)/' \
  -e 's/np.zeros((length, width, len(ifgdates)), dtype=np.int8)/np.zeros((len(ifgdates), length, width), dtype=np.int8)/' \
  -e 's/\.loc\[:, :, \([a-z0-9_]*\)\]/.loc[\1]/g' \
  "$f"

if grep -v '^\s*#' "$f" | grep -q '\.loc\[:, :, '; then
  echo "patch_licsbas.sh: leftover (y, x, ifg) indexing" >&2
  exit 1
fi
echo "patched $f: loop-closure cubes stored as (ifg, y, x)"
