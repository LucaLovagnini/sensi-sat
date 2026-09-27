"""Zonal statistics: totals per polygon.

Decision 7 of the plan says per-zone numbers are precomputed now and may be served
by an API later. So this is written as one library function with no I/O assumptions:
the batch step calls it, and a future web endpoint calls the same function on the
same rasters. There must never be a second implementation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import Affine

from .raster import row_areas_m2


def zone_masks(zones, transform: Affine, shape: tuple[int, int], crs) -> dict[str, np.ndarray]:
    """Rasterise each zone polygon onto the raster grid. Returns {name: boolean mask}."""
    if hasattr(zones, "to_crs") and zones.crs is not None and crs is not None:
        zones = zones.to_crs(crs)
    out = {}
    for name, geom in zip(zones["name"], zones.geometry, strict=False):
        if geom is None or geom.is_empty:
            continue
        out[name] = ~geometry_mask([geom], out_shape=shape, transform=transform, invert=False)
    return out


def zonal(
    raster: np.ndarray,
    transform: Affine,
    crs,
    zones,
    *,
    kind: str = "binary",
    scale: float = 1.0,
    label: str = "value",
) -> pd.DataFrame:
    """Area per zone for a raster.

    kind:
      "binary"   - raster is a boolean/0-1 mask; result is the EXTENT in km2
                   (area of pixels containing settlement).
      "fraction" - raster holds a share 0..1 (or 0..100 with scale=0.01);
                   result is the SURFACE in km2 (actual built cover).
      "amount"   - raster holds an amount per pixel already in m2 (e.g. GHSL
                   built_surface); result is that amount summed, in km2.

    The distinction matters: extent and surface are different quantities and must
    never be compared to each other (see docs/concepts.md section 3).
    """
    if kind not in {"binary", "fraction", "amount"}:
        raise ValueError(f"unknown kind {kind!r}")

    areas = row_areas_m2(raster.shape, transform)
    masks = zone_masks(zones, transform, raster.shape, crs)

    rows = []
    for name, mask in masks.items():
        if kind == "binary":
            value_km2 = float(((raster.astype(bool) & mask) * areas).sum() / 1e6)
        elif kind == "fraction":
            value_km2 = float((np.where(mask, raster * scale, 0) * areas).sum() / 1e6)
        else:  # amount, already m2 per pixel
            value_km2 = float(np.where(mask, raster * scale, 0).sum() / 1e6)
        zone_km2 = float((mask * areas).sum() / 1e6)
        rows.append({
            "zone": name,
            f"{label}_km2": round(value_km2, 3),
            "zone_km2": round(zone_km2, 1),
            "share_pct": round(100 * value_km2 / zone_km2, 2) if zone_km2 else np.nan,
            "measure": {"binary": "extent", "fraction": "surface", "amount": "surface"}[kind],
        })
    return pd.DataFrame(rows).sort_values("zone").reset_index(drop=True)


def zonal_from_file(path, zones, **kwargs) -> pd.DataFrame:
    """Same as `zonal`, reading the raster from a file."""
    with rasterio.open(path) as src:
        return zonal(src.read(1), src.transform, src.crs, zones, **kwargs)


def series_by_year(
    year_raster: np.ndarray,
    transform: Affine,
    crs,
    zones,
    years,
    *,
    label: str = "built",
) -> pd.DataFrame:
    """Cumulative extent per zone per year, from a 'year first built' raster.

    0 means never built. A pixel counts from the year it first appears onward,
    which is exactly what a growth-only encoding can express.
    """
    frames = []
    for year in years:
        mask = (year_raster > 0) & (year_raster <= year)
        df = zonal(mask, transform, crs, zones, kind="binary", label=label)
        df["year"] = year
        frames.append(df)
    return pd.concat(frames, ignore_index=True)
