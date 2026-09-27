"""The one grid every published 10 m layer lands on.

Why a *shared* grid matters. Seven layers come from five producers in three
coordinate systems: WSF is EPSG:4326, Copernicus is EPSG:3035 (a metre-based
projection for Europe), the cadastre is EPSG:32628 (UTM zone 28N). If each were
published on its own grid, the viewer could not stack them and the QA gates could
not compare them without resampling on every comparison — and every resampling of
categorical data is a chance to invent a value that was never measured.

So everything is put on ONE grid, once, at build time. Two layers of the same
island then have byte-identical transforms and shapes, and `a & b` is a valid
question about the same piece of ground.

**Which grid.** WSF Tracker's native grid, unchanged:

- It is EPSG:4326, which WSF Evolution, WSF 2015/2019 and GHSL already use, so
  four of our seven layers need no reprojection at all.
- It is the native grid of era-b, the source carrying 2016 to today — the layer
  we least want to disturb.
- Web maps expect geographic or Web Mercator coordinates; EPSG:3035 would have to
  be converted for display anyway.

The cost is that Copernicus (3035) is reprojected once here rather than never.
That is the right trade: it is reprojected with nearest-neighbour for classes and
bilinear for the percentage layer, exactly once, and recorded in the STAC item.

**Pixels are degrees, not metres.** A "10 m" pixel here is 8.983e-05 degrees on
both axes. At 28 N that is 9.98 m north-south but only 8.81 m east-west — about
88 m2, not 100 m2. Never count pixels and multiply; `raster.row_areas_m2` and
`raster.area_km2` integrate the true area row by row.
"""

from __future__ import annotations

import numpy as np
from rasterio.transform import Affine

from .config import CANARIES_BBOX, ISLAND_BBOX

BBox = tuple[float, float, float, float]

# WSF Tracker's global grid, read from the array's own metadata (see
# datasets/wsf_tracker.py). Reused verbatim so era-b never needs resampling.
PIXEL_DEG = 8.983152841195216e-05
ORIGIN_LON = -180.00001488697754
ORIGIN_LAT = 78.0100585990529

CRS = "EPSG:4326"
NOMINAL_M = 10

# The coarse grid for surface/density comparison: ~100 m cells, the resolution at
# which extent products and surface products can be compared fairly.
COARSE_DEG = 0.001


def snap(bbox: BBox = CANARIES_BBOX, pixel_deg: float = PIXEL_DEG) -> tuple[Affine, tuple[int, int]]:
    """Align a bounding box outward onto the global grid.

    Returns (transform, (height, width)). Outward means the returned window always
    contains the requested box, so a coastline is never clipped by rounding.

    Snapping to a *global* origin rather than to the box itself is what makes two
    islands' grids sub-pixel compatible: any two windows share the same lattice, so
    a pixel boundary in one is a pixel boundary in the other.
    """
    lon_min, lat_min, lon_max, lat_max = bbox
    col0 = int(np.floor((lon_min - ORIGIN_LON) / pixel_deg))
    col1 = int(np.ceil((lon_max - ORIGIN_LON) / pixel_deg))
    row0 = int(np.floor((ORIGIN_LAT - lat_max) / pixel_deg))
    row1 = int(np.ceil((ORIGIN_LAT - lat_min) / pixel_deg))
    transform = Affine(pixel_deg, 0.0, ORIGIN_LON + col0 * pixel_deg,
                       0.0, -pixel_deg, ORIGIN_LAT - row0 * pixel_deg)
    return transform, (row1 - row0, col1 - col0)


def for_island(island: str, pixel_deg: float = PIXEL_DEG) -> tuple[Affine, tuple[int, int]]:
    """The published grid for one island."""
    if island not in ISLAND_BBOX:
        raise KeyError(f"unknown island {island!r}; expected one of {sorted(ISLAND_BBOX)}")
    return snap(ISLAND_BBOX[island], pixel_deg)


def bounds_of(transform: Affine, shape: tuple[int, int]) -> BBox:
    """(lon_min, lat_min, lon_max, lat_max) actually covered by a grid."""
    height, width = shape
    lon_min = transform.c
    lat_max = transform.f
    return (lon_min, lat_max + transform.e * height, lon_min + transform.a * width, lat_max)


def same_grid(a: tuple[Affine, tuple[int, int]], b: tuple[Affine, tuple[int, int]],
              tol: float = 1e-9) -> bool:
    """Do two (transform, shape) pairs describe exactly the same pixels?

    The QA gates use this before any pixel-by-pixel comparison, so that a silent
    half-pixel offset can never be mistaken for disagreement between datasets.
    """
    (ta, sa), (tb, sb) = a, b
    if sa != sb:
        return False
    return all(abs(x - y) < tol for x, y in zip(ta[:6], tb[:6], strict=True))


def describe(island: str | None = None) -> dict:
    """The grid's parameters, for the STAC item and for printing."""
    transform, shape = for_island(island) if island else snap()
    return {
        "crs": CRS,
        "pixel_deg": PIXEL_DEG,
        "nominal_m": NOMINAL_M,
        "shape": shape,
        "megapixels": round(shape[0] * shape[1] / 1e6, 1),
        "bounds": tuple(round(v, 6) for v in bounds_of(transform, shape)),
        "origin": (ORIGIN_LON, ORIGIN_LAT),
    }
