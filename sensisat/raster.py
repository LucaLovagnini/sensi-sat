"""Reading, windowing and measuring rasters.

Two things here are easy to get wrong and are therefore done explicitly:

1. **Area on a geographic grid.** WSF and most of our sources are in EPSG:4326,
   where a pixel is a fixed number of degrees, so its ground area shrinks as
   latitude increases. `area_km2` integrates the true area row by row instead of
   multiplying a pixel count by a nominal 30x30 m.
2. **Resampling of categorical data.** "Year first built" and class labels must
   never be averaged. Every reprojection here uses nearest-neighbour.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.transform import Affine, from_bounds
from rasterio.warp import Resampling, reproject

from .config import EARTH_EQUATORIAL_M_PER_DEG, EARTH_MERIDIONAL_M_PER_DEG

BBox = tuple[float, float, float, float]  # lon_min, lat_min, lon_max, lat_max


def read_window(paths: list[Path] | list[str], bbox: BBox, nodata=0):
    """Merge the given tiles and return only `bbox`. Returns (array, transform, crs).

    rasterio's merge reads just the requested window from each file, so passing a
    whole archipelago's worth of tiles and asking for one island is cheap.
    """
    srcs = [rasterio.open(p) for p in paths]
    try:
        arr, transform = merge(srcs, bounds=bbox, nodata=nodata)
        return arr[0], transform, srcs[0].crs
    finally:
        for s in srcs:
            s.close()


def pixel_size_deg(transform: Affine) -> tuple[float, float]:
    return abs(transform.a), abs(transform.e)


def row_areas_m2(shape: tuple[int, int], transform: Affine) -> np.ndarray:
    """Ground area of one pixel in each raster row, for a geographic (degree) grid.

    Returned shape is (height, 1) so it broadcasts against the raster.
    """
    height, _ = shape
    dx_deg, dy_deg = pixel_size_deg(transform)
    # Latitude at the centre of each row.
    rows = np.arange(height) + 0.5
    lats = transform.f + transform.e * rows
    ns = dy_deg * EARTH_MERIDIONAL_M_PER_DEG
    ew = dx_deg * EARTH_EQUATORIAL_M_PER_DEG * np.cos(np.radians(lats))
    return (ns * ew).reshape(height, 1)


def area_km2(mask: np.ndarray, transform: Affine) -> float:
    """Area of the True pixels of a boolean mask, in km2, latitude-corrected."""
    if mask.dtype != bool:
        mask = mask.astype(bool)
    return float((mask * row_areas_m2(mask.shape, transform)).sum() / 1e6)


def weighted_km2(values: np.ndarray, transform: Affine) -> float:
    """Area-weighted sum for fractional rasters (e.g. 0-100 % sealed) -> km2."""
    return float((values * row_areas_m2(values.shape, transform)).sum() / 1e6)


def is_geographic(crs) -> bool:
    try:
        return bool(crs and crs.is_geographic)
    except AttributeError:
        return False


def to_web_mercator(arr: np.ndarray, transform: Affine, crs, bounds_3857, width: int, height: int,
                    nodata=0, resampling: Resampling = Resampling.nearest) -> np.ndarray:
    """Reproject onto an explicit EPSG:3857 grid (used to overlay on basemap tiles)."""
    dst = np.zeros((height, width), dtype=arr.dtype)
    reproject(
        arr, dst,
        src_transform=transform, src_crs=crs,
        dst_transform=from_bounds(*bounds_3857, width, height), dst_crs="EPSG:3857",
        resampling=resampling, src_nodata=nodata, dst_nodata=nodata,
    )
    return dst


def resample_to(arr: np.ndarray, transform: Affine, crs,
                ref_transform: Affine, ref_shape: tuple[int, int], ref_crs,
                nodata=0, resampling: Resampling = Resampling.nearest) -> np.ndarray:
    """Put `arr` onto the grid of another raster, so the two can be compared pixel by pixel."""
    dst = np.zeros(ref_shape, dtype=arr.dtype)
    reproject(
        arr, dst,
        src_transform=transform, src_crs=crs,
        dst_transform=ref_transform, dst_crs=ref_crs,
        resampling=resampling, src_nodata=nodata, dst_nodata=nodata,
    )
    return dst


def fraction_grid(mask: np.ndarray, transform: Affine, crs, cell_deg: float = 0.001):
    """Share of each coarse cell that is built (0..1), plus its transform.

    This is the bridge between EXTENT products (10/30 m pixels containing
    settlement) and SURFACE products (m2 built per 100 m cell): summing the
    fractions gives surface, counting cells above a threshold gives extent.
    `cell_deg` of 0.001 deg is roughly 100 m.
    """
    dx, dy = pixel_size_deg(transform)
    fy = max(1, int(round(cell_deg / dy)))
    fx = max(1, int(round(cell_deg / dx)))
    h, w = mask.shape
    hh, ww = (h // fy) * fy, (w // fx) * fx
    block = mask[:hh, :ww].astype(np.float32).reshape(hh // fy, fy, ww // fx, fx)
    frac = block.mean(axis=(1, 3))
    coarse_transform = Affine(transform.a * fx, transform.b, transform.c,
                              transform.d, transform.e * fy, transform.f)
    return frac, coarse_transform


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection over union of two boolean masks: both-built / either-built.

    Plain agreement is useless here because ~95 % of pixels are 'neither built',
    which would score any two maps above 0.9. IoU only looks at the union of what
    the two maps call built.
    """
    a, b = a.astype(bool), b.astype(bool)
    union = np.logical_or(a, b).sum()
    if union == 0:
        return float("nan")
    return float(np.logical_and(a, b).sum() / union)


def write_cog(path: Path, arr: np.ndarray, transform: Affine, crs, *,
              nodata=0, compress: str = "deflate", predictor: int = 2) -> Path:
    """Write a sparse, tiled, overview-bearing GeoTIFF the way we would publish it.

    SPARSE_OK means all-nodata blocks (i.e. ocean) cost no bytes; without it the
    ocean around an island dominates the file. Overviews are built with nearest
    resampling because the values are categorical.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff", "height": arr.shape[0], "width": arr.shape[1], "count": 1,
        "dtype": arr.dtype.name, "crs": crs, "transform": transform, "nodata": nodata,
        "tiled": True, "blockxsize": 256, "blockysize": 256,
        "compress": compress, "predictor": predictor, "SPARSE_OK": True,
    }
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(arr, 1)
        dst.build_overviews([2, 4, 8, 16, 32], Resampling.nearest)
        dst.update_tags(ns="rio_overview", resampling="nearest")
    return path


def describe(path: Path) -> dict:
    """Small summary of a raster file, for the evaluation tables."""
    with rasterio.open(path) as src:
        dx, dy = abs(src.transform.a), abs(src.transform.e)
        lat_mid = src.bounds.bottom + (src.bounds.top - src.bounds.bottom) / 2
        approx_m = math.sqrt(dx * EARTH_MERIDIONAL_M_PER_DEG * dy * EARTH_EQUATORIAL_M_PER_DEG
                             * math.cos(math.radians(lat_mid))) if src.crs and src.crs.is_geographic else dx
        return {
            "path": str(path),
            "MiB": round(Path(path).stat().st_size / 1048576, 3),
            "width": src.width, "height": src.height,
            "dtype": src.dtypes[0], "nodata": src.nodata,
            "crs": str(src.crs),
            "pixel_deg": round(dx, 8) if src.crs and src.crs.is_geographic else None,
            "pixel_m_approx": round(approx_m, 1),
            "overviews": src.overviews(1),
            "bounds": tuple(round(v, 4) for v in src.bounds),
        }
