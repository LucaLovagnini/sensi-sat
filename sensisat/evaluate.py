"""One test harness for every candidate 'year first built' product.

Every dataset gets the SAME two tests so the comparison is fair:
  1. Extent by year for an island (km2, latitude-corrected), for plausibility and
     growth rate.
  2. The cadastre cell test (HISDAC-ES, 100 m): of cells with a building dated <= Y,
     how many does the product flag by Y (recall); of cells the product flags by Y,
     how many contain any building (precision).
Inputs are a 'year first built' array (0 = never) with its transform and CRS.
"""
from __future__ import annotations

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

from . import zones
from .config import RAW
from .raster import area_km2
from .stats import zone_masks

MINCOY = RAW / "hisdac_es" / "canary" / "can_regcan_age" / "hisdac_es_age_mincoy_v1_100.tif"


def extent_by_year(year_arr, transform, crs, island: str, years) -> dict[int, float]:
    isl = zones.islands()
    z = isl[isl["name"] == island]
    m = zone_masks(z, transform, year_arr.shape, crs)[island]
    return {y: round(area_km2((year_arr > 0) & (year_arr <= y) & m, transform), 2) for y in years}


def cadastre_cell_test(year_arr, transform, crs, island: str, year: int = 1990) -> dict:
    with rasterio.open(MINCOY) as s:
        coy, ct, cc = s.read(1), s.transform, s.crs
    isl = zones.islands()
    mc = zone_masks(isl, ct, coy.shape, cc)[island]
    y = np.where(year_arr > 0, year_arr, 9999).astype("int32")
    d = np.full(coy.shape, 9999, "int32")
    reproject(y, d, src_transform=transform, src_crs=crs, dst_transform=ct, dst_crs=cc,
              resampling=Resampling.min, src_nodata=9999, dst_nodata=9999)
    cells = mc & (coy > 0) & (coy <= year)
    n = int(cells.sum())
    flagged = mc & (d <= year)
    return {
        "island": island, "year": year, "cells_with_building": n,
        "recall_pct": round(100 * (cells & (d <= year)).sum() / n, 1) if n else np.nan,
        "never_flagged_pct": round(100 * (cells & (d == 9999)).sum() / n, 1) if n else np.nan,
        "precision_any_building_pct": round(100 * (flagged & (coy > 0)).sum() / max(int(flagged.sum()), 1), 1),
        "flagged_cells": int(flagged.sum()),
    }


def report(label: str, year_arr, transform, crs, island: str = "Gran Canaria",
           years=(1985, 1990, 1995, 2000, 2005, 2010, 2015), test_year: int = 1990) -> dict:
    ext = extent_by_year(year_arr, transform, crs, island, years)
    ct = cadastre_cell_test(year_arr, transform, crs, island, test_year)
    g = ext[years[-1]] / ext[years[0]] - 1 if ext[years[0]] else np.nan
    print(f"{label:22s} {island}: extent " + " ".join(f"{y}:{v:6.1f}" for y, v in ext.items())
          + f" km2 | growth {years[0]}->{years[-1]} {100*g:+.0f} %")
    print(f"{'':22s} cadastre {test_year}: recall {ct['recall_pct']} %  never-flagged {ct['never_flagged_pct']} %  "
          f"precision {ct['precision_any_building_pct']} %")
    return {"product": label, **{f"km2_{y}": v for y, v in ext.items()}, "growth_pct": round(100 * g, 1), **ct}
