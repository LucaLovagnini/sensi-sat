"""WSF Tracker (DLR + MindEarth, published 2026-06-10) — 10 m, twice a year.

A global GeoZarr (Zarr v3) on source.coop, readable anonymously over HTTP range
requests: no download of the 10 m global grid (1,536,433 x 4,007,502 pixels) is
needed, only the window we ask for.

Encoding, from the array's own metadata (verified 2026-09-19):
    int8, 0 = no built-up / nodata, 1..20 = the EARLIEST biannual epoch at which
    built-up was detected. 1 = 2016-07-01, 2 = 2017-01-01, 3 = 2017-07-01, ...,
    20 = 2026-01-01. Overviews (levels 1-12) aggregate by MIN over 2x2 blocks,
    "preserving the earliest detected built-up".

Two consequences worth stating plainly:

- Like WSF Evolution, this is a **growth-only** encoding. A pixel keeps the epoch
  it was first seen built, forever. It cannot express demolition, so it cannot
  show the La Palma 2021 lava burial either. No product in the WSF family can.
- Epoch 1 is a **baseline**, not a change: it carries everything already built by
  July 2016, i.e. most of the Canaries' footprint.

Produced from Sentinel-1 and Sentinel-2 inside Google Earth Engine, but
distributed openly — we consume the product, not the compute.

License: CC BY 4.0. Source: https://source.coop/mindearth/wsf
"""

from __future__ import annotations

import numpy as np
from rasterio.transform import Affine

from ..config import CANARIES_BBOX

NAME = "WSF Tracker (DLR + MindEarth)"
MEASURE = "extent"
ENCODING = "epoch first built"
RESOLUTION_M = 10
LICENSE = "CC BY 4.0"
SOURCE_URL = "https://source.coop/mindearth/wsf"

BUCKET = "us-west-2.opendata.source.coop"
PREFIX = "mindearth/wsf"
STORE = f"{BUCKET}/{PREFIX}/World_WSF_20160701-20260101.zarr"
REGION = "us-west-2"

N_EPOCHS = 20
PIXEL_DEG = 8.983152841195216e-05
ORIGIN_LON = -180.00001488697754
ORIGIN_LAT = 78.0100585990529
SHAPE = (1536433, 4007502)


def epoch_to_decimal_year(epoch: int) -> float:
    """1 -> 2016.5 (July 2016), 2 -> 2017.0, ..., 20 -> 2026.0."""
    return 2016.0 + 0.5 * epoch


def epoch_to_label(epoch: int) -> str:
    year = 2016 + (epoch - 1) // 2
    return f"{year}-07" if epoch % 2 == 1 else f"{year + 1}-01"


def epochs_up_to(decimal_year: float) -> int:
    """Highest epoch index whose date is <= the given decimal year."""
    return max(0, min(N_EPOCHS, int((decimal_year - 2016.0) / 0.5)))


# s3fs binds its filesystem to the asyncio event loop that created it, and mixing
# a hand-made filesystem with the one zarr creates leaves connections attached to a
# dead loop — which surfaces much later, and misleadingly, as an SSL error. So all
# access goes through zarr's own store, opened once per level and reused.
_ARRAYS: dict[int, object] = {}

STORAGE_OPTIONS = {"anon": True, "client_kwargs": {"region_name": REGION}}


def _open_array(level: int = 0):
    if level not in _ARRAYS:
        import zarr
        store = zarr.storage.FsspecStore.from_url(
            f"s3://{STORE}/{level}/wsf_tracker", storage_options=STORAGE_OPTIONS, read_only=True
        )
        _ARRAYS[level] = zarr.open_array(store=store, mode="r")
    return _ARRAYS[level]


def level_geometry(level: int = 0) -> tuple[float, float, float]:
    """(pixel_size_deg, origin_lon, origin_lat) for an overview level."""
    scale = 2 ** level
    return PIXEL_DEG * scale, ORIGIN_LON, ORIGIN_LAT


def window_for(bbox, level: int = 0) -> tuple[slice, slice, Affine]:
    """Row/column slices covering bbox, plus the transform of that window."""
    px, lon0, lat0 = level_geometry(level)
    lon_min, lat_min, lon_max, lat_max = bbox
    col0 = max(0, int((lon_min - lon0) / px))
    col1 = int(np.ceil((lon_max - lon0) / px))
    row0 = max(0, int((lat0 - lat_max) / px))
    row1 = int(np.ceil((lat0 - lat_min) / px))
    transform = Affine(px, 0.0, lon0 + col0 * px, 0.0, -px, lat0 - row0 * px)
    return slice(row0, row1), slice(col0, col1), transform


def load(bbox=CANARIES_BBOX, level: int = 0):
    """Return (array of epoch indices, transform, crs) for bbox.

    `level` selects an overview: 0 is native 10 m, each level halves resolution.
    Reading is lazy over the network; only the requested window is transferred.
    """
    arr = _open_array(level)
    rows, cols, transform = window_for(bbox, level)
    data = np.asarray(arr[rows, cols])
    return data, transform, "EPSG:4326"


def built_mask(bbox=CANARIES_BBOX, *, by_epoch: int | None = None, level: int = 0):
    """Boolean 'was built-up by `by_epoch`' mask (default: by the latest epoch)."""
    data, transform, crs = load(bbox, level)
    limit = N_EPOCHS if by_epoch is None else by_epoch
    return (data > 0) & (data <= limit), transform, crs


def describe() -> dict:
    """The array's own metadata, so claims about the encoding are checkable."""
    arr = _open_array(0)
    attrs = dict(arr.attrs)
    return {
        "shape": tuple(arr.shape),
        "dtype": str(arr.dtype),
        "fill_value": arr.fill_value,
        "valid_range": (attrs.get("valid_min"), attrs.get("valid_max")),
        "long_name": attrs.get("long_name"),
        "description": attrs.get("description"),
    }
