"""The coverage grid: how much is built, per coarse cell.

Every test here is named for a failure that actually happened, because several of
them happened to the throwaway scripts that designed this. Expected values are
worked out from the primitives (`row_areas_m2`) rather than from the code under
test, and the rasters are small enough to reason about by hand.
"""

from __future__ import annotations

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.enums import Resampling

from sensisat.coverage import CELL_DEG, cell_factor, coverage_grid
from sensisat.raster import row_areas_m2, write_cog

PX = 8.983152841195216e-05          # the shared 10 m grid
LAT, LON = 28.10, -15.44            # over Gran Canaria, so latitudes are realistic


def grid_transform(px: float = PX) -> Affine:
    return Affine(px, 0.0, LON, 0.0, -px, LAT)


# --------------------------------------------------------------- the cell size

def test_cell_factor_follows_the_grid_it_is_given():
    """~99 m on the 10 m grid, ~six pixels on loss-events' 20 m grid, and ONE on
    density-trend's ~92 m grid — where the coverage grid is the layer itself. The
    factor must be read from the transform, never assumed."""
    assert cell_factor(grid_transform(PX)) == (11, 11)
    assert cell_factor(grid_transform(PX * 2)) == (6, 6)
    assert cell_factor(grid_transform(0.000833333)) == (1, 1)


def test_the_cell_size_is_the_one_the_measurements_assume():
    """`CELL_DEG` is not a free parameter. Cells straddling the edge of a view are
    counted whole, so the cell size sets the border error and therefore the zoom at
    which the viewer must stop summing cells and count real pixels instead —
    measured at ~99 m cells as under 1 % above roughly 20 cells wide and 31 % at
    about 5. Changing it invalidates that crossover, so this pins the value and the
    pixel count it comes to on the shared 10 m grid.
    """
    assert CELL_DEG == 0.001
    fy, fx = cell_factor(grid_transform(), CELL_DEG)
    assert (fy, fx) == (11, 11)
    # NOT square on the ground. The grid is in degrees, and a degree of longitude at
    # 28 degN is cos(28) = 0.88 of a degree of latitude, so a cell is 110 m north-south
    # and about 97 m east-west -- and the east-west side shrinks with latitude, from
    # 97.5 m over El Hierro to 95.8 m over Lanzarote. Saying "~99 m cells" is wrong;
    # the honest description is "about a hectare".
    ns = fy * PX * 111_320
    assert ns == pytest.approx(110.0, abs=0.5)
    ew_28 = fx * PX * 111_320 * np.cos(np.radians(28.1))
    assert ew_28 == pytest.approx(97.0, abs=0.5)
    assert ns * ew_28 / 1e4 == pytest.approx(1.07, abs=0.02)      # hectares


def test_a_raster_smaller_than_one_cell_is_refused():
    with pytest.raises(ValueError, match="smaller than one"):
        coverage_grid(np.ones((4, 4), np.uint8), grid_transform(), kind="binary")


# ------------------------------------------------------------- what it counts

def test_the_grid_sums_to_the_area_of_the_built_pixels():
    """The property the whole design rests on: summing every cell reproduces the
    layer's area. Measured on the real buildings-dated grid, this is 104.33 km2
    against a published 104.33."""
    t = grid_transform()
    rng = np.random.default_rng(0)
    data = (rng.random((44, 44)) < 0.2).astype(np.uint8)
    grid, _ = coverage_grid(data, t, kind="binary")
    expected = float(((data > 0) * row_areas_m2(data.shape, t)).sum())
    assert grid.sum() == pytest.approx(expected, rel=1e-12)
    assert grid.shape == (4, 4)


def test_any_non_zero_pixel_counts_once_not_as_a_whole_cell():
    """The failure this grid exists to prevent. One building in a cell must
    contribute ONE pixel of ground, not the cell's whole area — that confusion is
    what makes counting the map's own zoomed-out pixels read 3,310 km2 instead of
    104."""
    t = grid_transform()
    data = np.zeros((11, 11), np.uint8)
    data[5, 5] = 1
    grid, _ = coverage_grid(data, t, kind="binary")
    one_pixel = float(row_areas_m2((11, 1), t)[5, 0])
    whole_cell = float(row_areas_m2((11, 1), t).sum()) * 11      # 11 rows x 11 columns
    assert grid.shape == (1, 1)
    assert grid[0, 0] == pytest.approx(one_pixel, rel=1e-12)
    # and emphatically NOT the whole cell: one pixel of 121
    assert grid[0, 0] == pytest.approx(whole_cell / 121, rel=1e-3)


def test_the_three_kinds_are_not_interchangeable():
    """extent and surface are different quantities (CLAUDE.md #3). A half-sealed
    raster covers the same ground as a fully built one but holds half the surface."""
    t = grid_transform()
    half = np.full((11, 11), 50, np.uint8)          # 50 % sealed
    extent, _ = coverage_grid(half, t, kind="binary")
    surface, _ = coverage_grid(half, t, kind="fraction", scale=0.01)
    assert surface[0, 0] == pytest.approx(extent[0, 0] / 2, rel=1e-12)

    amount = np.full((11, 11), 7.0)                 # already m2 per pixel
    got, _ = coverage_grid(amount, t, kind="amount")
    assert got[0, 0] == pytest.approx(7.0 * 121, rel=1e-12)


def test_unknown_kind_is_refused():
    with pytest.raises(ValueError, match="unknown kind"):
        coverage_grid(np.ones((11, 11), np.uint8), grid_transform(), kind="sealed?")


def test_partial_edge_cells_are_dropped_not_half_filled():
    """A cell holding less ground than its neighbours while looking identical is a
    difference nothing downstream could see."""
    t = grid_transform()
    data = np.ones((25, 25), np.uint8)              # 2 whole cells + 3 spare pixels
    grid, coarse = coverage_grid(data, t, kind="binary")
    assert grid.shape == (2, 2)
    assert coarse.a == pytest.approx(t.a * 11)
    corner = float(((np.ones((22, 22)) > 0) * row_areas_m2((22, 1), t)).sum())
    assert grid.sum() == pytest.approx(corner, rel=1e-12)


# ------------------------------------- the harness itself, which was wrong twice

def aligned_window(row, col, size, factor):
    """A window that a cell-by-cell comparison may legitimately use.

    Exists because the script that first validated this compared 891 pixels of grid
    against 900 pixels of truth and reported errors that did not exist. Aligning the
    ORIGIN is not enough; the width must be a whole number of cells too.
    """
    if row % factor or col % factor or size % factor:
        raise ValueError(
            f"window ({row},{col}) {size}x{size} is not a whole number of "
            f"{factor}-pixel cells — comparing it would measure the test, not the grid")
    return row, col, size


def test_the_comparison_harness_refuses_a_misaligned_window():
    assert aligned_window(11, 22, 44, 11) == (11, 22, 44)
    with pytest.raises(ValueError, match="not a whole number"):
        aligned_window(11, 22, 45, 11)              # width off by one pixel
    with pytest.raises(ValueError, match="not a whole number"):
        aligned_window(5, 22, 44, 11)               # origin off by five


def test_exact_on_every_cell_aligned_window():
    """Aligned, the grid is not an approximation of the answer — it is the answer."""
    t = grid_transform()
    rng = np.random.default_rng(3)
    data = (rng.random((110, 110)) < 0.1).astype(np.uint8)
    grid, _ = coverage_grid(data, t, kind="binary")
    areas = row_areas_m2(data.shape, t)
    for size in (11, 22, 55, 110):
        r, c, s = aligned_window(0, 0, size, 11)
        exact = float(((data[r:r + s, c:c + s] > 0) * areas[r:r + s]).sum())
        assert grid[: s // 11, : s // 11].sum() == pytest.approx(exact, rel=1e-12)


# --------------------------------------- why we do not count what the map draws

def _sparse_island(size=1024, share=0.005, seed=1):
    rng = np.random.default_rng(seed)
    a = np.zeros((size, size), np.uint8)
    idx = rng.choice(size * size, int(size * size * share), replace=False)
    a.flat[idx] = 120
    return a


def test_counting_mode_overviews_would_inflate_the_answer(tmp_path):
    """Documents WHY the panel does not count the pixels the map is drawing.

    Overviews use `mode` with 0 as nodata, so a coarse pixel is "built" if ANY child
    is — deliberately, or villages vanish when you zoom out (CLAUDE.md #13). That
    makes them unusable for measuring. If this test ever fails because the inflation
    has gone away, the overview resampling has changed and the map has a new problem.
    """
    t = grid_transform()
    data = _sparse_island()
    path = write_cog(tmp_path / "m.tif", data, t, "EPSG:4326", resampling=Resampling.mode)
    with rasterio.open(path) as src:
        full = float(((src.read(1) > 0) * row_areas_m2(data.shape, t)).sum())
        levels = src.overviews(1)
    assert levels, "fixture needs overviews to make the point"
    with rasterio.open(path, OVERVIEW_LEVEL=len(levels) - 1) as src:
        coarse = src.read(1)
        counted = float(((coarse > 0) * row_areas_m2(coarse.shape, src.transform)).sum())
    # The factor compounds with depth: at ONE level a coarse pixel has four children
    # and "built if any" can at most quadruple it, which is why the fixture is large
    # enough to carry two. Measured on the real archipelago layer, 32x zoom-out turns
    # 104.3 km2 into 3,310.3.
    assert counted > full * 5, (
        f"mode overviews no longer inflate ({counted / full:.1f}x over {len(levels)} "
        "levels) — if that is intentional, the map's zoom-out behaviour changed too")


def test_the_coverage_grid_does_not_inflate_where_overviews_do(tmp_path):
    """The same sparse island, measured both ways. This is the whole argument."""
    t = grid_transform()
    data = _sparse_island()
    grid, _ = coverage_grid(data, t, kind="binary")
    # against the ground the grid actually covers: 1024 px is 93 whole cells of 11
    # plus a one-pixel strip, dropped by design. Comparing against the full raster
    # instead measures the drop, not the grid — which is the mistake this file exists
    # to stop being made twice.
    kept = (data.shape[0] // 11) * 11
    retained = float(((data[:kept, :kept] > 0) * row_areas_m2((kept, 1), t)).sum())
    assert grid.sum() == pytest.approx(retained, rel=1e-12)
    assert retained < float(((data > 0) * row_areas_m2(data.shape, t)).sum())


# ------------------------------- the companion must survive being read zoomed out

def _coverage_like(size=512, seed=5):
    """A grid shaped like a real coverage companion: mostly empty, a scatter of cells
    holding square metres. Values fit uint16 because a cell of ~1 ha holds at most
    about 10,000 m2."""
    rng = np.random.default_rng(seed)
    a = np.zeros((size, size), np.uint16)
    idx = rng.choice(size * size, int(size * size * 0.2), replace=False)
    a.flat[idx] = rng.integers(1, 10_000, idx.size, dtype=np.uint16)
    return a


def _total_at_each_level(path):
    """Total implied by each stored overview: the mean of a level times how many
    full-resolution pixels each of its pixels stands for."""
    with rasterio.open(path) as src:
        full = float(src.read(1).astype(np.float64).sum())
        levels = src.overviews(1)
    out = []
    for i, factor in enumerate(levels):
        with rasterio.open(path, OVERVIEW_LEVEL=i) as src:
            out.append((factor, float(src.read(1).astype(np.float64).sum()) * factor * factor))
    return full, out


def test_nodata_must_be_unset_or_the_companion_inflates_like_the_layer_it_fixes(tmp_path):
    """The single most important detail in the whole design.

    GDAL excludes nodata from an aggregation. If 0 meant nodata on a grid whose zeros
    are *real measurements* — ground with nothing built on it — the empty cells would
    drop out of the average, every overview would read as the mean of only the
    non-empty cells, and this grid would overstate exactly like the `mode` overviews
    it exists to replace.
    """
    t = grid_transform()
    data = _coverage_like()

    good = write_cog(tmp_path / "unset.tif", data, t, "EPSG:4326",
                     nodata=None, resampling=Resampling.average)
    full, levels = _total_at_each_level(good)
    assert levels, "fixture needs overviews to make the point"
    for factor, implied in levels:
        assert implied == pytest.approx(full, rel=0.01), (
            f"level {factor}x implies {implied:,.0f} against {full:,.0f} at full "
            "resolution — averaging is no longer summable")

    bad = write_cog(tmp_path / "zero.tif", data, t, "EPSG:4326",
                    nodata=0, resampling=Resampling.average)
    _, bad_levels = _total_at_each_level(bad)
    worst = max(implied / full for _, implied in bad_levels)
    assert worst > 1.5, (
        f"with nodata=0 the empty cells are no longer excluded from the average "
        f"({worst:.2f}x) — if GDAL changed this, the reason for nodata=None has gone")


def test_average_overview_rounding_does_not_run_away_with_depth(tmp_path):
    """Each level rounds to uint16, and rounding at one level feeds the next. The
    question is whether that drifts or stays put. Pinned so a dtype change is noticed.
    """
    t = grid_transform()
    path = write_cog(tmp_path / "c.tif", _coverage_like(size=1024), t, "EPSG:4326",
                     nodata=None, resampling=Resampling.average)
    full, levels = _total_at_each_level(path)
    assert len(levels) >= 2, "need depth for the question to mean anything"
    drifts = [abs(implied - full) / full for _, implied in levels]
    assert max(drifts) < 0.005, f"drift by level: {[round(d, 5) for d in drifts]}"
    assert drifts[-1] < drifts[0] * 20, "error compounds sharply with depth"
