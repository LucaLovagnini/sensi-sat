"""How much of each coarse cell is built — the grid that lets the viewer count.

**The problem this solves.** The viewer's readout should describe what is on screen.
Counting the pixels the map is drawing cannot do that: zoomed out the browser holds
`mode`-resampled overviews in which a coarse pixel is "built" if *any* of its children
is (nodata is excluded from the vote, CLAUDE.md #13), which is right for drawing — a
village must not vanish — and catastrophic for measuring. Measured on the published
`buildings-dated`: 104.3 km² at full resolution reads as 3,310.3 km² at 32x, and the
inflation runs 23.9x on dense Gran Canaria to 101.7x on scattered El Hierro, so no
single correction factor exists.

**The fix is to publish *how much* rather than *whether*.** Each cell of this grid
holds the layer's headline quantity beneath it, in square metres, summed from the real
pixels at build time. Summing cells over a window is then correct at any zoom, because
the summing happened at full resolution. Measured on `buildings-dated`: 8.54 million
cells, 207 KiB compressed, and summing every cell gives 104.33 km² — the published
figure to the decimal.

**A cell is about a hectare, and it is not square.** The grid is in degrees, so on the
shared 10 m grid a cell is 11 x 11 pixels = 110 m north-south but only ~97 m
east-west, because a degree of longitude at 28 degN is cos(28) = 0.88 of a degree of
latitude — and the east-west side shrinks further north, 97.5 m over El Hierro to
95.8 m over Lanzarote. This is why cells carry square metres computed row by row
rather than a fraction multiplied by a nominal cell size.

**Square metres, not a fraction, and that is deliberate.** It means the browser never
needs latitude correction or pixel geometry to turn cells into an answer; it adds
integers. A 10 m pixel is ~88 m² at 28 degN, not 100 (CLAUDE.md #2), and decision 7
exists to stop that arithmetic being implemented a second time.

**Overviews of this grid must be built with `average`, never `mode`, and `nodata` must
be left unset.** GDAL excludes nodata from an aggregation, so if 0 meant nodata the
empty cells would drop out of the mean and this grid would inflate exactly like the
layer it exists to fix. With nodata unset, `average` over a quantity is what averaging
a quantity means, and every overview level stays summable.
"""

from __future__ import annotations

import numpy as np
from affine import Affine

from sensisat.raster import pixel_size_deg, row_areas_m2

#: Target cell size in degrees. 0.001 deg comes to 11 pixels on the shared 10 m grid:
#: 110 m north-south, ~97 m east-west, about one hectare. The size is set by the
#: border error:
#: cells straddling the edge of a view are counted whole, and measured, the error is
#: under 1 % for views wider than about 20 cells and 31 % at ~5 cells. Finer cells
#: would push the crossover down but cost bytes; coarser would raise it.
CELL_DEG = 0.001


def cell_factor(transform: Affine, cell_deg: float = CELL_DEG) -> tuple[int, int]:
    """How many raster pixels make one coverage cell, as (rows, cols).

    At least 1: on a grid already coarser than the target cell — `density-trend` is
    ~92 m — the coverage grid is the layer itself, one cell per pixel, and that is
    correct rather than a special case.
    """
    dx, dy = pixel_size_deg(transform)
    return max(1, int(round(cell_deg / dy))), max(1, int(round(cell_deg / dx)))


def coverage_grid(values: np.ndarray, transform: Affine, *, kind: str,
                  scale: float = 1.0, cell_deg: float = CELL_DEG
                  ) -> tuple[np.ndarray, Affine]:
    """Square metres of the layer's quantity per coarse cell, and the cell transform.

    `kind` mirrors `stats.zonal`, because the same distinction applies and must not be
    made twice: extent and surface are different quantities (CLAUDE.md #3).

      "binary"   pixels > 0 count as built            -> m2 of ground they cover
      "fraction" values are a share (pass scale=0.01 for 0..100) -> m2 of cover
      "amount"   values are already m2 per pixel      -> summed as they are

    Returned as float64 m2; the caller encodes. **Rows and columns that do not fill a
    whole cell are dropped**, so the grid covers a whole number of cells — a partial
    cell at the edge would otherwise hold less ground than its neighbours while looking
    identical, which is the kind of difference nothing downstream could see.
    """
    if values.ndim != 2:
        raise ValueError(f"expected one band, got shape {values.shape}")

    fy, fx = cell_factor(transform, cell_deg)
    h, w = values.shape
    hh, ww = (h // fy) * fy, (w // fx) * fx
    if hh == 0 or ww == 0:
        raise ValueError(f"raster {values.shape} is smaller than one {fy}x{fx} cell")

    block = values[:hh, :ww]
    areas = row_areas_m2((hh, 1), transform)

    if kind == "binary":
        per_pixel = (block > 0) * areas
    elif kind == "fraction":
        per_pixel = block.astype(np.float64) * scale * areas
    elif kind == "amount":
        per_pixel = block.astype(np.float64) * scale
    else:
        raise ValueError(f"unknown kind {kind!r}")

    grid = per_pixel.reshape(hh // fy, fy, ww // fx, fx).sum(axis=(1, 3))
    coarse = Affine(transform.a * fx, transform.b, transform.c,
                    transform.d, transform.e * fy, transform.f)
    return grid, coarse
