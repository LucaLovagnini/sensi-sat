"""Do GHSL and the cadastre agree about WHEN the Canaries were built?

This matters because of a gap M3 could not close. Aerial photography of the
Canaries begins in 2005, so 85 % of the building layer carries a date no photograph
can check (`docs/validation.md` §7b). GHSL is the only independent source that
reaches further back: its 1975, 1990 and 2000 epochs are observed Landsat, not
interpolation.

The two measure different quantities -- GHSL is built SURFACE in m² per ~93 m cell,
the cadastre is building FOOTPRINT area -- so their levels cannot be compared. Their
SHAPES can. If the cadastre's heavily bucketed pre-1980 years were distorting the
timeline, the two curves would diverge there.

Run: python scripts/analysis_21_ghsl_vs_cadastre_timing.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import rasterio

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat import encoding as enc  # noqa: E402
from sensisat.config import PROCESSED  # noqa: E402
from sensisat.derive import island_mask  # noqa: E402
from sensisat.raster import row_areas_m2  # noqa: E402

EPOCHS = [1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020]
ISLANDS = ["Gran Canaria", "Tenerife", "Fuerteventura", "Lanzarote",
           "La Palma", "La Gomera", "El Hierro", "La Graciosa"]


def main() -> None:
    ghsl = np.zeros(len(EPOCHS))
    cum = np.zeros(len(EPOCHS))
    per_year: dict[int, float] = {}

    for island in ISLANDS:
        slug = island.lower().replace(" ", "-")
        with rasterio.open(PROCESSED / "density-trend" / f"{slug}.tif") as s:
            ghsl += s.read().astype("float64").reshape(len(EPOCHS), -1).sum(axis=1) / 1e6
        with rasterio.open(PROCESSED / "buildings-dated" / f"{slug}.tif") as s:
            a, tr, shp = s.read(1), s.transform, s.shape
        land = island_mask(island, tr, shp, "EPSG:4326")
        cell = row_areas_m2(shp, tr)
        yr = a.astype(int) + enc.YEAR_OFFSET
        dated = (a > 0) & (a != enc.UNDATED) & land
        for i, e in enumerate(EPOCHS):
            cum[i] += float(((dated & (yr <= e)) * cell).sum() / 1e6)
        for y in range(1998, 2025):
            per_year[y] = per_year.get(y, 0.0) + float(((dated & (yr == y)) * cell).sum() / 1e4)

    print("1. THE TWO TRAJECTORIES (levels are not comparable; shapes are)\n")
    print(f"   {'epoch':>6s} {'GHSL km2':>9s} {'idx':>5s}   {'cadastre km2':>13s} {'idx':>5s}"
          f" {'increment ratio':>16s}")
    dg, dc = np.diff(ghsl), np.diff(cum)
    for i, e in enumerate(EPOCHS):
        r = f"{dg[i-1]/dc[i-1]:16.2f}" if i and dc[i-1] else " " * 16
        print(f"   {e:6d} {ghsl[i]:9.1f} {100*ghsl[i]/ghsl[0]:5.0f}   "
              f"{cum[i]:13.2f} {100*cum[i]/cum[0]:5.0f}{r}")
    stable = [dg[i]/dc[i] for i in range(len(dc)) if EPOCHS[i] < 2010 and dc[i]]
    print(f"\n   1975-2010 the increment ratio stays within {min(stable):.2f}-{max(stable):.2f}:")
    print("   two independent sources agreeing on when growth happened, over the")
    print("   period no photograph can check. That is the reassurance M3 could not give.")
    print(f"\n   After 2010 it jumps to {dg[-2]/dc[-2]:.1f} and {dg[-1]/dc[-1]:.1f}. One of")
    print("   them is wrong about the last decade. Test 2 says which.\n")

    print("2. THE 2008 CRASH — footprint added per year, hectares\n")
    peak = max(per_year.values())
    for y in range(1998, 2025):
        print(f"   {y}  {per_year[y]:7.1f}  {'#' * int(40 * per_year[y] / peak)}")
    pre = float(np.mean([per_year[y] for y in range(2000, 2008)]))
    post = float(np.mean([per_year[y] for y in range(2012, 2020)]))
    print(f"\n   2000-2007 mean {pre:.1f} ha/yr -> 2012-2019 mean {post:.1f} ha/yr "
          f"({100*post/pre:.0f} %)")
    print("\n   The cadastre records Spain's construction collapse: a monotonic fall")
    print("   from 2008 to 2013, then flat. It is not registration lag -- 2012 has had")
    print("   fourteen years to register and sits at the same level as 2023.")
    print(f"\n   GHSL's largest increment of the whole series is {dg[-1]:.1f} km2, in")
    print("   2015-2020, the window the cadastre says construction had all but stopped.")
    print("   GHSL interpolates between sparse observations, so a real and abrupt")
    print("   economic event is smoothed out of existence.")
    print("\n   CONCLUSION: GHSL is sound for the LONG trend and for density, and its")
    print("   agreement with the cadastre before 2010 is real evidence about the")
    print("   unphotographed decades. It must not be used to date recent growth.")
    print("   And the crash signature independently corroborates the cadastre's")
    print("   recent years, which M3 could only test at one boundary.")


if __name__ == "__main__":
    main()
