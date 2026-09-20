"""Draw a stratified random sample for the accuracy assessment (M3, plan §7 level 3).

Why stratified rather than simple random: the interesting classes are rare. Built
land is about 6 % of the archipelago and *new* built land is a fraction of that, so
a few hundred points scattered at random would land almost entirely on empty ground
and tell us nothing about the class we most want to check. Sampling each map class
separately, then weighting the results back by how much area each class covers, is
the standard remedy (Olofsson et al. 2014).

The interpreter must not be able to tell what the map claims, so the output carries
the map's answer in a separate file from the one used for labelling.

    python scripts/m3_sample.py --per-stratum 3 --out data/processed/m3_demo
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import rasterio  # noqa: E402

from sensisat import encoding as enc  # noqa: E402
from sensisat.config import PROCESSED  # noqa: E402
from sensisat.raster import row_areas_m2  # noqa: E402

# The classes we sample separately. Each is a claim the map makes; the point of the
# exercise is to find out how often each claim is true.
STRATA = {
    "built_before_2015": "the map says a building stood here by 2015",
    "new_2015_2024": "the map says a building appeared here between 2015 and 2024",
    "undated": "the map says something is built here but cannot say when",
    "not_built": "the map says nothing is built here",
}


def strata_masks(year: np.ndarray, land: np.ndarray) -> dict[str, np.ndarray]:
    """The four claims the map makes, each restricted to land.

    `land` is not optional. "Not built" means "no building here", which is true of
    every square metre of the Atlantic inside the raster's bounding box — and since
    that is most of the box, an unrestricted sample sends the interpreter to look at
    open sea, where the aerial photography is blank. Worse, it would be blank in
    both years, so the point counts as a correct "not built" and quietly inflates
    the accuracy with the easiest question anyone could be asked.
    """
    dated = (year > 0) & (year != enc.UNDATED)
    by_2015 = dated & (year <= 2015 - enc.YEAR_OFFSET)
    by_2024 = dated & (year <= 2024 - enc.YEAR_OFFSET)
    return {
        "built_before_2015": by_2015 & land,
        "new_2015_2024": (by_2024 & ~by_2015) & land,
        "undated": (year == enc.UNDATED) & land,
        "not_built": (year == 0) & land,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--island", default="Gran Canaria")
    ap.add_argument("--per-stratum", type=int, default=3)
    ap.add_argument("--seed", type=int, default=20260920)
    ap.add_argument("--out", default="data/processed/m3_demo")
    args = ap.parse_args()

    slug = args.island.lower().replace(" ", "-")
    path = PROCESSED / "buildings-dated" / f"{slug}.tif"
    with rasterio.open(path) as src:
        year = src.read(1)
        transform = src.transform

    from sensisat.derive import island_mask

    with rasterio.open(path) as src:
        land = island_mask(args.island, transform, year.shape, src.crs)
    masks = strata_masks(year, land)
    areas = row_areas_m2(year.shape, transform)
    rng = np.random.default_rng(args.seed)

    points, truth = [], []
    counter = 0
    for name, mask in masks.items():
        rows, cols = np.nonzero(mask)
        if len(rows) == 0:
            print(f"  {name}: empty, skipped")
            continue
        take = min(args.per_stratum, len(rows))
        pick = rng.choice(len(rows), size=take, replace=False)
        km2 = float((mask * areas).sum() / 1e6)
        print(f"  {name:20s} {len(rows):9,d} pixels  {km2:8.2f} km2  -> {take} points")
        for k in pick:
            r, c = int(rows[k]), int(cols[k])
            lon, lat = transform * (c + 0.5, r + 0.5)
            # An OPAQUE id. An earlier version used f"{name}-{r}-{c}", which put the
            # stratum in a string the browser loads — an interpreter who glanced at
            # the sample file would know what the map claimed before judging it,
            # and the independence the whole exercise rests on would be gone.
            counter += 1
            pid = f"p{counter:05d}"
            # What the interpreter sees: a location and nothing else.
            points.append({"id": pid, "lon": round(lon, 7), "lat": round(lat, 7)})
            # What the map claims, kept apart so the interpreter stays blind to it.
            truth.append({"id": pid, "stratum": name, "stratum_km2": round(km2, 3),
                          "map_year": int(enc.decode_year(np.array([year[r, c]]))[0])})

    rng.shuffle(points)          # so the strata are not labelled in blocks
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "points.json").write_text(json.dumps(
        {"island": args.island, "pixel_m": 10,
         # PNOA flies the Canaries roughly every three years, not annually: over
         # Gran Canaria only 2005, 2009, 2012, 2015, 2018, 2021 and 2024 have
         # imagery, and every other year returns a blank white frame.
         "imagery_years": [2015, 2024], "points": points}, indent=1))
    (out / "map_claims.json").write_text(json.dumps(
        {"strata": STRATA, "claims": truth}, indent=1))
    print(f"\n{len(points)} points -> {out / 'points.json'}")
    print(f"map's own answers held back in {out / 'map_claims.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
