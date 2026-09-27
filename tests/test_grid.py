"""The shared grid: the property that lets layers be compared at all."""

from __future__ import annotations

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
