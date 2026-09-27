"""World Settlement Footprint (DLR) — Evolution, 2015 and 2019.

All three are EXTENT products: a pixel is "settlement" if it contains any, so a
single house switches on the whole pixel. They are therefore comparable with each
other but never with a built-SURFACE product like GHSL.

- Evolution: one raster, value = the year a pixel was first detected as settlement
  (1985..2015), 0 = never. Growth-only by construction: the product explicitly
  excludes anything that is not settlement in 2015, so it can never show loss.
  The first year, 1985, is a BASELINE, not a growth year — it carries everything
  built before satellite record started.
- 2015 / 2019: binary snapshots at 10 m (255 = settlement).

Tiles are 2x2 degrees, named by their lower-left corner.
License: WSF Evolution and 2019 CC-BY-4.0, WSF 2015 CC0-1.0.
"""

from __future__ import annotations

from pathlib import Path

from ..config import CANARIES_BBOX, RAW
from ..download import fetch, head
from ..raster import read_window

BASE = "https://download.geoservice.dlr.de"

PRODUCTS = {
    # name: (url path, tile name template, nested in a folder?, resolution m, years)
    "wsf_evolution": ("WSF_EVO", "WSFevolution_v1_{lon}_{lat}", True, 30, "1985-2015"),
    "wsf2015": ("WSF2015", "WSF2015_v2_{lon}_{lat}", True, 10, "2015"),
    "wsf2019": ("WSF2019", "WSF2019_v1_{lon}_{lat}", False, 10, "2019"),
}

NAME = "World Settlement Footprint (DLR)"
MEASURE = "extent"
LICENSE = {"wsf_evolution": "CC-BY-4.0", "wsf2015": "CC0-1.0", "wsf2019": "CC-BY-4.0"}
SOURCE_URL = "https://geoservice.dlr.de/web/datasets/wsf_evo"

TILE_DEG = 2
EVOLUTION_FIRST_YEAR = 1985
EVOLUTION_LAST_YEAR = 2015
SETTLEMENT_VALUE = 255  # in the binary 2015/2019 products


def tiles_for_bbox(bbox=CANARIES_BBOX) -> list[tuple[int, int]]:
    """Lower-left corners of the 2x2 degree tiles intersecting bbox."""
    lon_min, lat_min, lon_max, lat_max = bbox

    def floor_to(v):
        return int(v // TILE_DEG) * TILE_DEG

    lons = range(floor_to(lon_min), floor_to(lon_max) + TILE_DEG, TILE_DEG)
    lats = range(floor_to(lat_min), floor_to(lat_max) + TILE_DEG, TILE_DEG)
    return [(lon, lat) for lon in lons for lat in lats]


def tile_url(product: str, lon: int, lat: int) -> str:
    path, template, nested, *_ = PRODUCTS[product]
    name = template.format(lon=lon, lat=lat)
    return f"{BASE}/{path}/files/{name}/{name}.tif" if nested else f"{BASE}/{path}/files/{name}.tif"


def available_tiles(product: str, bbox=CANARIES_BBOX) -> list[tuple[int, int]]:
    """Tiles that actually exist on the server. DLR omits all-ocean tiles."""
    found = []
    for lon, lat in tiles_for_bbox(bbox):
        status, _ = head(tile_url(product, lon, lat))
        if status == 200:
            found.append((lon, lat))
    return found


def fetch_tiles(product: str, bbox=CANARIES_BBOX, *, tiles=None, quiet: bool = False) -> list[Path]:
    """Download every tile covering bbox. Missing tiles are skipped, not an error."""
    if product not in PRODUCTS:
        raise ValueError(f"unknown product {product!r}; expected one of {sorted(PRODUCTS)}")
    dest_dir = RAW / product
    out: list[Path] = []
    for lon, lat in (tiles if tiles is not None else tiles_for_bbox(bbox)):
        url = tile_url(product, lon, lat)
        status, _ = head(url)
        if status != 200:
            if not quiet:
                print(f"  skip {product} tile {lon},{lat} (HTTP {status})")
            continue
        out.append(fetch(url, dest_dir / Path(url).name, quiet=quiet).path)
    return out


def load(product: str, bbox=CANARIES_BBOX, *, paths=None):
    """Return (array, transform, crs) for bbox.

    Evolution values are years (0 = never built). The binary products are
    converted from 255 to 1 so that every WSF array is directly usable as a mask.
    """
    paths = paths or fetch_tiles(product, bbox, quiet=True)
    if not paths:
        raise FileNotFoundError(f"no {product} tiles for bbox {bbox}")
    arr, transform, crs = read_window(paths, bbox, nodata=0)
    if product in {"wsf2015", "wsf2019"}:
        arr = (arr == SETTLEMENT_VALUE).astype("uint8")
    return arr, transform, crs


def built_mask(product: str, bbox=CANARIES_BBOX, year: int | None = None, *, paths=None):
    """Boolean 'is settlement' mask. For Evolution, optionally as of `year`."""
    arr, transform, crs = load(product, bbox, paths=paths)
    if product == "wsf_evolution":
        year = year or EVOLUTION_LAST_YEAR
        mask = (arr > 0) & (arr <= year)
    else:
        mask = arr > 0
    return mask, transform, crs
