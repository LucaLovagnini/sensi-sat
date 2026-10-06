"""The shared grid: the property that lets layers be compared at all."""

from __future__ import annotations

import pytest

from sensisat import grid
from sensisat.config import ISLAND_BBOX


def test_snap_contains_the_requested_box():
    """Snapping must round outward, or a coastline is clipped by rounding."""
    for island, bbox in ISLAND_BBOX.items():
        transform, shape = grid.for_island(island)
        lon_min, lat_min, lon_max, lat_max = grid.bounds_of(transform, shape)
        assert lon_min <= bbox[0] and lat_min <= bbox[1], island
        assert lon_max >= bbox[2] and lat_max >= bbox[3], island


def test_every_island_shares_one_lattice():
    """Two islands' grids must differ by a whole number of pixels, not a fraction."""
    a, _ = grid.for_island("Gran Canaria")
    b, _ = grid.for_island("Tenerife")
    for offset in (b.c - a.c, b.f - a.f):
        pixels = offset / grid.PIXEL_DEG
        assert abs(pixels - round(pixels)) < 1e-6


def test_coarse_grid_nests_inside_the_fine_one():
    """The 20 m loss layer must land on 10 m pixel boundaries, not straddle them."""
    fine, _ = grid.for_island("La Palma")
    coarse, _ = grid.snap(ISLAND_BBOX["La Palma"], grid.PIXEL_DEG * 2)
    for offset in (coarse.c - fine.c, coarse.f - fine.f):
        pixels = offset / grid.PIXEL_DEG
        assert abs(pixels - round(pixels)) < 1e-6


def test_same_grid_detects_a_half_pixel_slip():
    from rasterio.transform import Affine

    transform, shape = grid.for_island("El Hierro")
    slipped = transform * Affine.translation(0.5, 0)
    assert grid.same_grid((transform, shape), (transform, shape))
    assert not grid.same_grid((transform, shape), (slipped, shape))
    assert not grid.same_grid((transform, shape), (transform, (shape[0] + 1, shape[1])))


def test_grid_matches_wsf_tracker_natively():
    """Era-b must need no resampling — that is why this grid was chosen."""
    from sensisat.datasets import wsf_tracker as wt

    for island, bbox in ISLAND_BBOX.items():
        ours = grid.for_island(island)
        rows, cols, transform = wt.window_for(bbox)
        theirs = (transform, (rows.stop - rows.start, cols.stop - cols.start))
        assert grid.same_grid(ours, theirs), island


def test_a_pixel_is_never_the_nominal_hundred_square_metres():
    """CLAUDE.md #2, as an assertion rather than a sentence. The grid is defined in
    degrees, so the east-west side of a pixel shrinks with cos(latitude) while the
    north-south side does not. Counting pixels and multiplying by 100 m2 is the
    arithmetic this forbids, and it is wrong by 13-15 % over the Canaries.

    The published figures in docs/concepts.md §8 are generated from these functions,
    so this test is what stands behind them."""
    import math

    from sensisat import facts as f
    from sensisat.config import (
        CANARIES_BBOX,
        EARTH_EQUATORIAL_M_PER_DEG,
        EARTH_MERIDIONAL_M_PER_DEG,
    )
    from sensisat.grid import NOMINAL_M, PIXEL_DEG

    south, north = CANARIES_BBOX[1], CANARIES_BBOX[3]
    for lat in (south, north, 28.0):
        ns, ew, area = f.pixel_metres(lat)
        # Recomputed here from the constants, not read back from the same call.
        assert ns == pytest.approx(PIXEL_DEG * EARTH_MERIDIONAL_M_PER_DEG)
        assert ew == pytest.approx(
            PIXEL_DEG * EARTH_EQUATORIAL_M_PER_DEG * math.cos(math.radians(lat)))
        assert area == pytest.approx(ns * ew)
        assert area < NOMINAL_M ** 2, "a pixel is never as big as its nominal size"

    lo, hi = f.pixel_area_range()
    assert lo < hi, "the smallest pixel is in the north, where east-west is shortest"
    assert f.pixel_metres(north)[2] == pytest.approx(lo)
    assert 86 < lo and hi < 89, (lo, hi)

    lo_pct, hi_pct = f.pixel_area_overstatement()
    # "Overstates by" is 100/a - 1. The other denominator, (100-a)/100, is what
    # CLAUDE.md #2 quotes as "~12 %" — same error, smaller-looking number.
    assert lo_pct == pytest.approx((NOMINAL_M ** 2) / hi * 100 - 100)
    assert 12 < lo_pct < hi_pct < 16, (lo_pct, hi_pct)
