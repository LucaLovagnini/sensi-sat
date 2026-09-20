"""Is the dating problem real, judged WITHOUT the interpreter's labels?

M3 measured the `new 2015-2024` class at 58.5 % user's accuracy. That number is
computed from the manual interpretation, so on its own it cannot separate "the map
is wrong" from "the interpreter is wrong" -- the reference IS the interpreter, and
Olofsson's estimator assumes the reference is truth rather than testing it.

This script asks the same question using no labels at all.

**The instrument.** WSF 2015 (DLR, 10 m, single date) states whether settlement was
present in 2015. It is built from satellite imagery, knows nothing about the
Spanish cadastre, and is at our own resolution -- which matters, because the 30 m
WSF Evolution would light up for a *neighbouring* building and confound everything.

**The confound this is designed to kill.** A genuinely new infill building in an
old town is surrounded by old buildings, so any "is there settlement nearby" test
fires for it regardless. Comparing the `new` class against the archipelago average
therefore proves nothing. Instead, every comparison here is made at MATCHED LOCAL
DENSITY of pre-2015 cadastral buildings:

    f(d) = [ rate_new(d) - rate_empty(d) ] / [ rate_old(d) - rate_empty(d) ]

At each density d, `rate_empty` is how often WSF 2015 fires on ground the cadastre
says is empty -- what a pixel that was genuinely empty in 2015 looks like -- and
`rate_old` is how often it fires on a building the cadastre dates before 2015. A
`new` pixel that was really new should resemble the first; one that was already
built should resemble the second. f is the share resembling the second.

This is the project's standing rule applied to itself: never compare unlike things.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject
from scipy.ndimage import uniform_filter

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat import encoding as enc  # noqa: E402
from sensisat.config import PROCESSED, RAW  # noqa: E402
from sensisat.derive import island_mask  # noqa: E402

ISLANDS = ["Gran Canaria", "Tenerife", "Fuerteventura", "Lanzarote",
           "La Palma", "La Gomera", "El Hierro", "La Graciosa"]
BINS = [0.0, 0.02, 0.05, 0.10, 0.20, 0.35, 1.01]      # local pre-2015 built share


def wsf2015_on_grid(transform, shape, crs) -> np.ndarray:
    """WSF 2015 (10 m) resampled onto our grid. Nearest only — it is a category."""
    tiles = sorted(Path(RAW / "wsf2015").glob("WSF2015_v2_*.tif"))
    out = np.zeros(shape, dtype="uint8")
    for t in tiles:
        with rasterio.open(t) as src:
            buf = np.zeros(shape, dtype="uint8")
            reproject(source=rasterio.band(src, 1), destination=buf,
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=transform, dst_crs=crs,
                      resampling=Resampling.nearest)
        out = np.maximum(out, buf)
    return out > 0


def main() -> None:
    num = np.zeros(len(BINS) - 1)
    den = np.zeros(len(BINS) - 1)
    rows: list[tuple] = []
    grand = {"new": [0, 0], "old": [0, 0], "empty": [0, 0]}

    for island in ISLANDS:
        slug = island.lower().replace(" ", "-")
        path = PROCESSED / "buildings-dated" / f"{slug}.tif"
        if not path.exists():
            continue
        with rasterio.open(path) as src:
            cad, transform, shape, crs = src.read(1), src.transform, src.shape, src.crs
        land = island_mask(island, transform, shape, crs)
        wsf = wsf2015_on_grid(transform, shape, crs)

        dated = (cad > 0) & (cad != enc.UNDATED)
        old = dated & (cad <= 2015 - enc.YEAR_OFFSET) & land
        new = dated & ~old & (cad > 0) & (cad != enc.UNDATED) & land
        empty = (cad == 0) & land

        # local density of PRE-2015 buildings — independent of the new/empty split
        dens = uniform_filter(old.astype("float32"), size=7, mode="constant")

        for key, m in (("new", new), ("old", old), ("empty", empty)):
            grand[key][0] += int((m & wsf).sum())
            grand[key][1] += int(m.sum())

        for i in range(len(BINS) - 1):
            band = (dens >= BINS[i]) & (dens < BINS[i + 1])
            n_m, o_m, e_m = new & band, old & band, empty & band
            if n_m.sum() < 50 or o_m.sum() < 50 or e_m.sum() < 50:
                continue
            r_n = (n_m & wsf).sum() / n_m.sum()
            r_o = (o_m & wsf).sum() / o_m.sum()
            r_e = (e_m & wsf).sum() / e_m.sum()
            if r_o - r_e < 0.05:          # no contrast here, the bin says nothing
                continue
            f = (r_n - r_e) / (r_o - r_e)
            num[i] += f * n_m.sum()
            den[i] += n_m.sum()
            rows.append((island, BINS[i], BINS[i + 1], int(n_m.sum()), r_n, r_o, r_e, f))

    print("UNMATCHED (the naive comparison, shown to be discarded):")
    for k, lbl in (("new", "cadastre says NEW 2016-2024"),
                   ("old", "cadastre says built by 2015"),
                   ("empty", "cadastre says nothing built")):
        h, n = grand[k]
        print(f"   {lbl:32s} WSF 2015 fires on {100*h/n:5.1f} %  ({h:,} / {n:,})")
    print("   -> useless on its own: a new infill building sits in an old town.\n")

    print("MATCHED by local pre-2015 building density. In each band, how often does")
    print("WSF 2015 fire, and where does the NEW class sit between the two anchors?\n")
    print(f"   {'density band':>14s} {'new px':>9s} {'new':>7s} {'old':>7s} {'empty':>7s} "
          f"{'implied already built':>22s}")
    for i in range(len(BINS) - 1):
        sel = [r for r in rows if r[1] == BINS[i]]
        if not sel:
            continue
        w = sum(r[3] for r in sel)
        def agg(j, sel=sel, w=w):
            return sum(r[j] * r[3] for r in sel) / w
        print(f"   {BINS[i]:5.0%}-{BINS[i+1]:<7.0%} {w:9,} {agg(4):6.1%} {agg(5):6.1%} "
              f"{agg(6):6.1%} {agg(7):21.1%}")

    if den.sum():
        f = float(num.sum() / den.sum())
        print(f"\n   Pooled over all bands, weighted by pixel count: {f:.1%} of the")
        print("   'new 2016-2024' class already had settlement in 2015.")
        print("   The interpreter's sample said 29 %.")


if __name__ == "__main__":
    main()
