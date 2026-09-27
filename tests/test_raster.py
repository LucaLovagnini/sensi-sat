"""Area maths and file writing — the two places a silent error would be invisible."""

from __future__ import annotations

import math
import subprocess

import numpy as np
import rasterio

from sensisat.config import EARTH_EQUATORIAL_M_PER_DEG, EARTH_MERIDIONAL_M_PER_DEG, pixel_area_m2
from sensisat.grid import PIXEL_DEG
from sensisat.raster import area_km2, fraction_grid, iou, row_areas_m2, write_cog


def test_pixel_area_shrinks_with_latitude():
    """A '10 m' pixel is 10 m north-south everywhere but narrower as you go north.

    This is the error that would inflate every area by ~12 % at Canary latitudes if
    pixels were counted and multiplied by a nominal 100 m2.
    """
    equator = pixel_area_m2(PIXEL_DEG, 0.0)
    canaries = pixel_area_m2(PIXEL_DEG, 28.0)
    assert canaries < equator
    assert math.isclose(canaries / equator, math.cos(math.radians(28.0)), rel_tol=1e-9)

    expected = (PIXEL_DEG * EARTH_MERIDIONAL_M_PER_DEG) * \
               (PIXEL_DEG * EARTH_EQUATORIAL_M_PER_DEG * math.cos(math.radians(28.0)))
    assert math.isclose(canaries, expected, rel_tol=1e-12)
    assert canaries < 100.0          # ~88 m2, not the nominal 100


def test_nominal_pixel_count_would_overstate_area(tiny_transform, square_mask):
    nominal_km2 = square_mask.sum() * 100 / 1e6
    assert area_km2(square_mask, tiny_transform) < nominal_km2


def test_row_areas_decrease_going_north(tiny_transform):
    areas = row_areas_m2((10, 10), tiny_transform)
    assert areas.shape == (10, 1)
    assert (np.diff(areas.ravel()) > 0).all()   # rows run north to south, so area grows


def test_fraction_grid_preserves_total_area(tiny_transform, square_mask):
    """Averaging a mask to coarser cells does NOT remove resolution inflation.

    The plan once claimed it did; it does not, and this test pins the real property
    so the claim cannot quietly come back.
    """
    frac, coarse = fraction_grid(square_mask, tiny_transform, None, cell_deg=PIXEL_DEG * 2)
    fine = (square_mask * row_areas_m2(square_mask.shape, tiny_transform)).sum()
    # row_areas_m2 already reflects the coarse cell size, so no extra factor here.
    coarse_total = (frac * row_areas_m2(frac.shape, coarse)).sum()
    assert math.isclose(fine, coarse_total, rel_tol=1e-3)


def test_iou_ignores_the_empty_background():
    a = np.zeros((10, 10), bool)
    a[0:4, 0:4] = True
    b = np.zeros((10, 10), bool)
    b[2:6, 2:6] = True
    assert math.isclose(iou(a, a), 1.0)
    assert math.isclose(iou(a, b), 4 / 28)          # 2x2 overlap, 28 in the union
    assert np.isnan(iou(np.zeros((4, 4), bool), np.zeros((4, 4), bool)))


def test_written_file_is_a_valid_cog(tmp_path, tiny_transform):
    arr = np.zeros((2, 512, 512), "uint8")
    arr[0, 100:300, 100:300] = 116
    arr[1, 100:300, 100:300] = 1
    path = write_cog(tmp_path / "x.tif", arr, tiny_transform, "EPSG:4326",
                     band_descriptions=["year", "provenance"], tags={"layer": "test"})
    with rasterio.open(path) as src:
        assert src.count == 2
        assert src.descriptions == ("year", "provenance")
        assert src.tags()["layer"] == "test"
        assert src.overviews(1)
    proc = subprocess.run(["rio", "cogeo", "validate", "--strict", str(path)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_two_dimensional_input_writes_one_band(tmp_path, tiny_transform):
    path = write_cog(tmp_path / "one.tif", np.zeros((256, 256), "uint8"),
                     tiny_transform, "EPSG:4326")
    with rasterio.open(path) as src:
        assert src.count == 1
