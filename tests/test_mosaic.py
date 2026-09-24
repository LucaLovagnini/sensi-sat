"""The mosaic must not lose a pixel, invent one, or quietly resample.

A mosaic is exactly the kind of step whose failures are silent: an island written
in the wrong place still produces a valid COG, and an island blanked by its
neighbour's ocean still produces a map that looks plausible. So these tests assert
the two properties that cannot be eyeballed — every non-nodata pixel survives with
its value, and nothing lands off the shared grid.
"""

from __future__ import annotations

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.enums import Resampling

from sensisat.mosaic import archipelago_grid, mosaic

PX = 0.001


def _write(path, data, col_off, row_off, *, nodata=0):
    """A small island COG placed at an integer offset on a shared grid."""
    arr = data if data.ndim == 3 else data[np.newaxis, ...]
    transform = Affine(PX, 0, 10.0 + col_off * PX, 0, -PX, 50.0 - row_off * PX)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[1],
                       width=arr.shape[2], count=arr.shape[0], dtype=arr.dtype.name,
                       crs="EPSG:4326", transform=transform, nodata=nodata,
                       tiled=True, blockxsize=16, blockysize=16) as dst:
        dst.write(arr)
    return path


def test_grid_offsets_are_whole_pixels():
    t = [Affine(PX, 0, 10.0, 0, -PX, 50.0), Affine(PX, 0, 10.0 + 5 * PX, 0, -PX, 50.0 - 3 * PX)]
    transform, (h, w), offsets = archipelago_grid(t, [(4, 4), (4, 4)])
    assert offsets == [(0, 0), (5, 3)]
    assert (h, w) == (7, 9)
    assert transform.c == pytest.approx(10.0)


def test_a_half_pixel_slip_is_refused():
    """The failure that no other check can see. Resampling a categorical layer
    invents years nothing was built in, so this must fail loudly."""
    t = [Affine(PX, 0, 10.0, 0, -PX, 50.0), Affine(PX, 0, 10.0 + 2.5 * PX, 0, -PX, 50.0)]
    with pytest.raises(ValueError, match="not on the shared grid"):
        archipelago_grid(t, [(4, 4), (4, 4)])


def test_no_pixel_is_gained_or_lost(tmp_path):
    rng = np.random.default_rng(0)
    a = rng.integers(0, 5, (8, 8), dtype=np.uint8)
    b = rng.integers(0, 5, (8, 8), dtype=np.uint8)
    _write(tmp_path / "a.tif", a, 0, 0)
    _write(tmp_path / "b.tif", b, 20, 12)

    out = mosaic([tmp_path / "a.tif", tmp_path / "b.tif"], tmp_path / "all.tif",
                 blocksize=16, resampling=Resampling.mode)

    with rasterio.open(out) as src:
        got = src.read(1)
    assert int((got > 0).sum()) == int((a > 0).sum()) + int((b > 0).sum())
    assert np.array_equal(got[0:8, 0:8], a)
    assert np.array_equal(got[12:20, 20:28], b)


def test_an_island_inside_another_s_bbox_is_not_blanked(tmp_path):
    """La Graciosa sits inside Lanzarote's bounding box. If the later file's ocean
    overwrote the earlier file's land, La Graciosa would vanish and every total
    would still look reasonable."""
    big = np.zeros((10, 10), dtype=np.uint8)
    big[0, 0] = 7                      # Lanzarote's only land, far from the overlap
    small = np.zeros((2, 2), dtype=np.uint8)
    small[1, 1] = 9                    # La Graciosa, inside the big box
    _write(tmp_path / "big.tif", big, 0, 0)
    _write(tmp_path / "small.tif", small, 4, 4)

    # written small-first, so the big file's nodata passes over it afterwards
    out = mosaic([tmp_path / "small.tif", tmp_path / "big.tif"], tmp_path / "all.tif",
                 blocksize=16, resampling=Resampling.mode)
    with rasterio.open(out) as src:
        got = src.read(1)
    assert got[5, 5] == 9, "the smaller island was overwritten by its neighbour's ocean"
    assert got[0, 0] == 7


def test_multiband_islands_keep_their_bands(tmp_path):
    """buildings-dated and settlement-era-a carry a provenance band; density-trend
    carries ten epochs. Dropping one would be invisible in a single-band check."""
    a = np.stack([np.full((6, 6), 3, np.uint8), np.full((6, 6), 1, np.uint8)])
    _write(tmp_path / "a.tif", a, 0, 0)
    out = mosaic([tmp_path / "a.tif"], tmp_path / "all.tif",
                 blocksize=16, resampling=Resampling.mode)
    with rasterio.open(out) as src:
        assert src.count == 2
        assert np.array_equal(src.read(2)[0:6, 0:6], a[1])


def test_float_noise_is_tolerated_but_a_real_slip_is_not():
    """GHSL's 1/1200-degree grid is not exactly representable in binary, so a real
    1704-pixel offset measures 1704.000007. Refusing that would block a layer that
    is perfectly aligned; accepting a half-pixel slip would silently resample it."""
    base = Affine(PX, 0, 10.0, 0, -PX, 50.0)
    noise = Affine(PX, 0, 10.0 + (5 + 1e-5) * PX, 0, -PX, 50.0)
    _, _, offsets = archipelago_grid([base, noise], [(4, 4), (4, 4)])
    assert offsets[1] == (5, 0)

    slip = Affine(PX, 0, 10.0 + 5.5 * PX, 0, -PX, 50.0)
    with pytest.raises(ValueError, match="not on the shared grid"):
        archipelago_grid([base, slip], [(4, 4), (4, 4)])
