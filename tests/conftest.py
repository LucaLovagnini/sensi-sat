"""Fixtures: tiny rasters with known answers.

Every fixture here is small enough to reason about by hand. That is the point —
a test that needs a 42-megapixel island to fail tells you nothing about *why* it
failed, and a test over real data would also be testing whether the download
worked. The real data is exercised by the QA gates during a build; these tests
check that the machinery underneath behaves as documented.
"""

from __future__ import annotations

import numpy as np
import pytest
from rasterio.transform import from_origin

from sensisat.grid import PIXEL_DEG


@pytest.fixture
def tiny_transform():
    """A 10-pixel-per-side grid near the Canaries, on the real pixel size."""
    return from_origin(-15.5, 28.1, PIXEL_DEG, PIXEL_DEG)


@pytest.fixture
def coarse_transform():
    """The same origin at 3x the pixel size — WSF Evolution's 30 m against our 10 m."""
    return from_origin(-15.5, 28.1, PIXEL_DEG * 3, PIXEL_DEG * 3)


@pytest.fixture
def square_mask():
    """A 10x10 grid with a 4x4 block of built pixels."""
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:6, 2:6] = True
    return mask


@pytest.fixture
def zones_gdf():
    """One polygon covering the left half of the tiny grid."""
    import geopandas as gpd
    from shapely.geometry import box

    return gpd.GeoDataFrame(
        {"name": ["left half"]},
        geometry=[box(-15.5, 28.1 - 10 * PIXEL_DEG, -15.5 + 5 * PIXEL_DEG, 28.1)],
        crs="EPSG:4326",
    )
