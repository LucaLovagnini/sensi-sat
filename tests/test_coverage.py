"""Why the readout cannot count the pixels the map is drawing — pinned as tests.

This file used to test `sensisat/coverage.py`, a grid of how much is built per
coarse cell, designed to let the viewer count at any zoom. It was retired on
2026-09-25 when the per-year bands it needed came to 3,631 KiB per layer, and the
module itself was deleted on 2026-10-08. What survives is the EVIDENCE that
decided the design, because it holds whatever ships: COG overviews are built for
drawing, and drawing and measuring want opposite things from them.

  * `mode` overviews inflate a count — a coarse pixel is "built" if any child is;
  * the inflation depends on clustering, so no single correction factor undoes it;
  * declaring 0 as nodata makes `average` overviews overstate in the same way;
  * `average` rounding to an integer type does not drift with depth.

Expected values come from the primitives (`row_areas_m2`), never from the code
under test, and the rasters are small enough to reason about by hand.
"""

from __future__ import annotations

import numpy as np
import pytest
import rasterio
from affine import Affine
from rasterio.enums import Resampling

from sensisat.raster import row_areas_m2, write_cog

PX = 8.983152841195216e-05          # the shared 10 m grid
LAT, LON = 28.10, -15.44            # over Gran Canaria, so latitudes are realistic


def grid_transform(px: float = PX) -> Affine:
    return Affine(px, 0.0, LON, 0.0, -px, LAT)


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


def _clustered_island(size=1024, share=0.005):
    """The same number of built pixels as `_sparse_island`, packed into one block."""
    a = np.zeros((size, size), np.uint8)
    n = int(size * size * share)                    # exactly as many as _sparse_island
    side = int(np.ceil(n ** 0.5))
    rows, rest = divmod(n, side)
    a[:rows, :side] = 120
    a[rows, :rest] = 120
    return a


def _inflation_at_coarsest(tmp_path, name, data):
    t = grid_transform()
    path = write_cog(tmp_path / f"{name}.tif", data, t, "EPSG:4326", resampling=Resampling.mode)
    with rasterio.open(path) as src:
        full = float(((src.read(1) > 0) * row_areas_m2(data.shape, t)).sum())
        levels = src.overviews(1)
    with rasterio.open(path, OVERVIEW_LEVEL=len(levels) - 1) as src:
        coarse = src.read(1)
        counted = float(((coarse > 0) * row_areas_m2(coarse.shape, src.transform)).sum())
    return counted / full


def test_overview_inflation_depends_on_clustering_so_no_correction_factor_exists(tmp_path):
    """Why the readout cannot count the map's pixels and divide by a constant.

    viewer.md and count.js both cite this file for two claims: that `mode` overviews
    inflate a count (the test above), and that the inflation depends on how clustered
    the buildings are — 23.9x on dense Gran Canaria against 101.7x on scattered El
    Hierro at 32x — so no single correction factor can undo it. Until 2026-10-08 no
    test asserted the second claim; the documents said this file "pins both" and it
    pinned one. Found while retiring sensisat/coverage.py, by checking which test
    carried each claim before deleting any.

    Same built area, two arrangements. If a correction factor existed, the two
    inflations would match.
    """
    sparse, dense = _sparse_island(), _clustered_island()
    assert (sparse > 0).sum() == (dense > 0).sum(), (
        "the fixtures must hold the same built area or the comparison means nothing")
    scattered = _inflation_at_coarsest(tmp_path, "scattered", sparse)
    clustered = _inflation_at_coarsest(tmp_path, "clustered", dense)
    assert clustered < 2, f"a compact block barely inflates; got {clustered:.1f}x"
    assert scattered > clustered * 5, (
        f"scattered {scattered:.1f}x vs clustered {clustered:.1f}x — if these converge,"
        " a single correction factor would work and the far regime could be revisited")


# ------------------------- average overviews: what 0 means, and what rounding does

def _coverage_like(size=512, seed=5):
    """A continuous grid shaped like the density layers: mostly empty ground, with a
    scatter of cells holding square metres of built surface. Values fit uint16
    because a cell of ~1 ha holds at most about 10,000 m2."""
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


def test_nodata_must_be_unset_or_average_overviews_overstate(tmp_path):
    """For any layer whose overviews use `average` and whose 0 is a real value.

    GDAL excludes nodata from an aggregation. If 0 means nodata on a grid whose zeros
    are *real measurements* — ground with nothing built or sealed on it — the empty
    cells drop out of the average, every overview reads as the mean of only the
    non-empty cells, and the zoomed-out picture overstates.

    Written for the retired coverage grid; it governs `density-current` (% sealed)
    and `density-trend` (m2 built), the two layers built with `average` overviews.
    Both are published with nodata=0 as of 2026-10-08, and measured over Gran Canaria
    they overstate when zoomed out — 4.46 % sealed drawn as 9.60 % at 32x, 65.96 m2
    drawn as 85.57 at 16x. Display only: no published figure counts overview pixels.
    Recorded in the project plan; the fix changes how empty ground is drawn.
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
