"""GHSL GHS-BUILT-S R2023A (JRC) — built-up SURFACE.

Unlike WSF, this is a surface product: each cell holds the square metres of built
cover inside it, not a yes/no flag. Summing it gives "how much got built"; it is
not comparable with an extent product (see docs/concepts.md section 3).

Two properties are documented by JRC and matter for how we use it:

1. Only 1975, 1990, 2000, 2014 (Landsat) and 2018 (Sentinel-2) are OBSERVED.
   Every other 5-year epoch is spatially-temporally interpolated; 2025 and 2030
   are extrapolations. `is_observed()` reports this so the UI can flag it.
2. It is non-decreasing in time by construction: the JRC Data Package 2023 states
   the multitemporal process "can only decrease the amount of built-up surface
   going from recent to past epochs". Measured over Gran Canaria, exactly zero
   cells decrease between epochs. GHSL therefore cannot show demolition or loss.

We use the EPSG:4326 3-arcsecond variant rather than the 100 m Mollweide one so
it shares a coordinate system with WSF and needs no reprojection to compare.
Tiles are 10 x 10 degrees, zipped, named R{row}_C{col}.

License: CC BY 4.0 (European Union, JRC).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from ..config import CANARIES_BBOX, RAW
from ..download import fetch
from ..raster import read_window

BASE = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_BUILT_S_GLOBE_R2023A"

NAME = "GHS-BUILT-S R2023A (JRC)"
MEASURE = "surface"          # m2 of built cover per cell
ENCODING = "amount"          # value is already an area, in m2
LICENSE = "CC BY 4.0"
SOURCE_URL = "https://human-settlement.emergency.copernicus.eu/download.php"

EPOCHS = [1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025, 2030]
OBSERVED_EPOCHS = {1975, 1990, 2000, 2015, 2020}  # see is_observed() for the caveat
IMAGERY_YEARS = {1975: "Landsat MSS", 1990: "Landsat TM", 2000: "Landsat ETM",
                 2014: "Landsat", 2018: "Sentinel-2 composite"}
PROJECTED_EPOCHS = {2025, 2030}

TILE_DEG = 10
RESOLUTION_ARCSEC = 3

# The 4326 tile grid is NOT aligned to round degrees: it is offset by ~0.008 deg
# in longitude and ~0.9 deg in latitude. Verified by reading the transform of
# tile R7_C17, whose bounds are (-20.00792, 19.09958, -10.00792, 29.09958).
# Getting this wrong silently truncates Lanzarote and La Graciosa at 29.1 N.
GRID_LON0 = -180.00791656502537
GRID_LAT0 = 89.09958341912107


def is_observed(epoch: int) -> str:
    """How much of an epoch is measured rather than modelled.

    JRC's observed imagery years are 1975, 1990, 2000, 2014 and 2018 — which do
    not line up with the published 5-year epochs. So 2015 and 2020 are the epochs
    closest to real imagery (2014, 2018) but are still interpolated onto the
    epoch year. Nothing here is "raw" in the sense a single-date product is.
    """
    if epoch in PROJECTED_EPOCHS:
        return "projected"
    if epoch in {1975, 1990, 2000}:
        return "observed"
    if epoch in {2015, 2020}:
        return "near-observed"  # nearest imagery 2014 / 2018
    return "interpolated"


def tile_for(lon: float, lat: float) -> tuple[int, int]:
    """(row, col) of the 10x10 degree tile containing a point."""
    col = int((lon - GRID_LON0) // TILE_DEG) + 1
    row = int((GRID_LAT0 - lat) // TILE_DEG) + 1
    return row, col


def tile_bounds(row: int, col: int) -> tuple[float, float, float, float]:
    """(lon_min, lat_min, lon_max, lat_max) of a tile."""
    lon_min = GRID_LON0 + TILE_DEG * (col - 1)
    lat_max = GRID_LAT0 - TILE_DEG * (row - 1)
    return lon_min, lat_max - TILE_DEG, lon_min + TILE_DEG, lat_max


def tiles_for_bbox(bbox=CANARIES_BBOX) -> list[tuple[int, int]]:
    """Every tile intersecting bbox — the corners can fall in different tiles."""
    lon_min, lat_min, lon_max, lat_max = bbox
    rows = range(tile_for(lon_min, lat_max)[0], tile_for(lon_min, lat_min)[0] + 1)
    cols = range(tile_for(lon_min, lat_min)[1], tile_for(lon_max, lat_min)[1] + 1)
    return [(r, c) for r in rows for c in cols]


def tile_url(epoch: int, row: int, col: int) -> str:
    stem = f"GHS_BUILT_S_E{epoch}_GLOBE_R2023A_4326_{RESOLUTION_ARCSEC}ss"
    return f"{BASE}/{stem}/V1-0/tiles/{stem}_V1_0_R{row}_C{col}.zip"


def fetch_tiles(epoch: int, bbox=CANARIES_BBOX, *, quiet: bool = False) -> list[Path]:
    """Download and unzip the tiles covering bbox for one epoch. Returns .tif paths."""
    if epoch not in EPOCHS:
        raise ValueError(f"epoch {epoch} not published; choose from {EPOCHS}")
    out: list[Path] = []
    dest_dir = RAW / "ghsl"
    for row, col in tiles_for_bbox(bbox):
        url = tile_url(epoch, row, col)
        zip_path = fetch(url, dest_dir / Path(url).name, quiet=quiet).path
        tif = _unzip_tif(zip_path, dest_dir)
        if tif:
            out.append(tif)
    return out


def _unzip_tif(zip_path: Path, dest_dir: Path) -> Path | None:
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".tif")]
        if not names:
            return None
        target = dest_dir / Path(names[0]).name
        if not target.exists():
            with zf.open(names[0]) as src, target.open("wb") as dst:
                dst.write(src.read())
        return target


def load(epoch: int, bbox=CANARIES_BBOX, *, paths=None):
    """Return (array of m2 built per cell, transform, crs) for bbox."""
    paths = paths or fetch_tiles(epoch, bbox, quiet=True)
    if not paths:
        raise FileNotFoundError(f"no GHSL tiles for epoch {epoch}, bbox {bbox}")
    return read_window(paths, bbox, nodata=0)
