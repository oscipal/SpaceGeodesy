# Processing notes

<!-- auto:download -->
## Stage 2: download

AOI-clipped download with `scripts/download.py` (GDAL /vsicurl/ windowed reads) instead of `LiCSBAS01_get_geotiff.py`, which would fetch whole frames (~450 GB asc + ~175 GB desc since 2020). Output layout is identical to LiCSBAS01.

Time window: 2020-01-01 to 2026-11-02.

| Frame | ifgs listed | ifgs downloaded | ifgs unavailable | epochs | GACOS ok | size (GB) |
|---|---|---|---|---|---|---|
| `016A_02504_162118` | 3747 | 3747 | 0 | 307 | 307 | 2.45 |
| `155D_02484_191814` | 1591 | 1591 | 0 | 269 | 269 | 1.09 |

`016A_02504_162118`: 515 ifgs (20200102 to 20230913) have unw files with the frame's dimensions but a faulty GeoTIFF header: pixel scale 0.001*N/(N-1) deg instead of 0.001 (N = frame width/height) and a half-pixel origin shift, an off-by-one in the header rather than a different grid. Evidence: the cc file of the same pair has the correct frame georeferencing, and LiCSAR geocodes to fixed 0.001 deg frame grids. On 016A_02504_162118, 2020 and 2024 coherence patterns align to (-0.04, 0.01) px; a test aligning unw valid-data masks with cc was too noisy (0.2 to 1.3 px) to decide on its own. These files were cut by pixel window and given the reference georeferencing (no resampling), which is also how stock LiCSBAS reads them.
Full lists in `data/<frame>/download_manifest.json`.

`155D_02484_191814`: 555 ifgs (20200106 to 20230911) have unw files with the frame's dimensions but a faulty GeoTIFF header: pixel scale 0.001*N/(N-1) deg instead of 0.001 (N = frame width/height) and a half-pixel origin shift, an off-by-one in the header rather than a different grid. Evidence: the cc file of the same pair has the correct frame georeferencing, and LiCSAR geocodes to fixed 0.001 deg frame grids. On 016A_02504_162118, 2020 and 2024 coherence patterns align to (-0.04, 0.01) px; a test aligning unw valid-data masks with cc was too noisy (0.2 to 1.3 px) to decide on its own. These files were cut by pixel window and given the reference georeferencing (no resampling), which is also how stock LiCSBAS reads them.
Full lists in `data/<frame>/download_manifest.json`.
<!-- /auto:download -->

## Known limitations

- Descending frame `155D_02484_191814` has no LiCSAR products after 2026-02-03 (checked 2026-11-02;
  ascending `016A_02504_162118` runs to 2026-09-16). Vertical/east-west decomposition is therefore
  limited to the period up to 2026-02-03; after that only ascending LOS is available. Accepted by the
  group on 2026-11-02 rather than switching tracks.
