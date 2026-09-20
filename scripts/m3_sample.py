"""Draw the stratified sample for the accuracy assessment (M3, plan §7 level 3).

Why stratified: the interesting classes are vanishingly rare. Across the eight
islands the map calls 7,344 km² not built and **2.23 km² newly built between 2015
and 2024** — 0.03 % of the land. A simple random sample of 650 points would put
about *one fifth of one point* on new construction, which is the class the whole
exercise exists to measure. So each class is sampled separately and weighted back
by its true area when the results are scored.

**How many points.** Olofsson et al. 2014 eq. 13 gives the sample size for a target
standard error on overall accuracy:

    n = ( Σ Wᵢ·Sᵢ / S(Ô) )²        Sᵢ = √(Uᵢ(1−Uᵢ))

with Wᵢ the area share of stratum i and Uᵢ its expected user's accuracy. That
number turns out small — overall accuracy is dominated by "not built", which is
98.6 % of the land and easy to get right, so it is precise almost for free. It is
also the least interesting number in the report.

What actually costs points is **per-class** accuracy for the rare classes, whose
precision depends only on how many points that class gets, not on its area. So the
allocation is: enough overall to hit the target, then a floor under every rare
class so its own accuracy has a usable interval.

**The interpreter will not be able to judge every point.** In the twelve-point
trial, two of three "new built" points came back "unsure" — the class the
assessment exists to measure is also the hardest to read from a photograph. The
sample is inflated to allow for that, or the usable count lands under the design.

    python scripts/m3_sample.py --plan            # show the design, draw nothing
    python scripts/m3_sample.py --out data/processed/m3
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
from sensisat.config import ISLAND_BBOX, PROCESSED  # noqa: E402
from sensisat.raster import row_areas_m2  # noqa: E402

STRATA = {
    "built_before_2015": "the map says a building stood here by 2015",
    "new_2015_2024": "the map says a building appeared here between 2015 and 2024",
    "undated": "the map says something is built here but cannot say when",
    "not_built": "the map says nothing is built here",
}

# Expected user's accuracy per stratum, used only to size the sample. Deliberately
# pessimistic for the rare classes: underestimating accuracy oversizes the sample,
# which wastes a little time, while overestimating it undersizes the sample and
# wastes all of it.
EXPECTED_USERS = {
    "not_built": 0.99,
    "built_before_2015": 0.90,
    "new_2015_2024": 0.70,
    "undated": 0.60,
}

# Points below which a class's own accuracy interval is too wide to be worth
# quoting. 100 is the figure decision 15 fixed for the undated class, and the same
# floor is right for new-built for the same reason.
MIN_PER_RARE_STRATUM = 100
RARE = ("new_2015_2024", "undated")

# Share of points expected to come back "unsure" and be excluded from scoring.
UNSURE_ALLOWANCE = 0.20


def strata_masks(year: np.ndarray, land: np.ndarray) -> dict[str, np.ndarray]:
    """The four claims the map makes, each restricted to land.

    `land` is not optional. "Not built" means "no building here", which is true of
    every square metre of the Atlantic inside the raster's bounding box — and PNOA
    has no imagery over water. An unrestricted sample sends the interpreter to look
    at open sea, where the answer is blank in both years, so the point scores as a
    correct "not built" and quietly inflates the accuracy with the easiest question
    anyone could be asked. Measured on Gran Canaria, 58 % of that stratum was sea.
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


def survey(islands: list[str]) -> tuple[dict[str, float], dict[str, list]]:
    """Area per stratum, and the pixels available to sample, across every island."""
    from sensisat.derive import island_mask

    areas: dict[str, float] = {s: 0.0 for s in STRATA}
    pools: dict[str, list] = {s: [] for s in STRATA}
    for island in islands:
        slug = island.lower().replace(" ", "-")
        path = PROCESSED / "buildings-dated" / f"{slug}.tif"
        with rasterio.open(path) as src:
            year, transform, crs = src.read(1), src.transform, src.crs
            land = island_mask(island, transform, year.shape, crs)
        cell = row_areas_m2(year.shape, transform)
        for name, mask in strata_masks(year, land).items():
            areas[name] += float((mask * cell).sum() / 1e6)
            rows, cols = np.nonzero(mask)
            if len(rows):
                pools[name].append((island, transform, rows, cols))
    return areas, pools


def design(areas: dict[str, float], target_pct: float) -> dict[str, int]:
    """Points per stratum for a target +/- on overall accuracy, with rare-class floors."""
    total = sum(areas.values())
    W = {s: areas[s] / total for s in areas}
    se_target = target_pct / 100 / 1.96
    sigma = sum(W[s] * np.sqrt(EXPECTED_USERS[s] * (1 - EXPECTED_USERS[s])) for s in areas)
    n_total = int(np.ceil((sigma / se_target) ** 2))

    # Proportional allocation first, then raise the rare classes to their floor.
    alloc = {s: max(1, int(round(n_total * W[s]))) for s in areas}
    for s in RARE:
        alloc[s] = max(alloc[s], MIN_PER_RARE_STRATUM)
    # "Built before 2015" carries the headline pre-2016 claim; give it a real floor too.
    alloc["built_before_2015"] = max(alloc["built_before_2015"], MIN_PER_RARE_STRATUM)
    # And "not built" needs enough to bound omission over 98 % of the land.
    alloc["not_built"] = max(alloc["not_built"], MIN_PER_RARE_STRATUM)

    inflated = {s: int(np.ceil(n / (1 - UNSURE_ALLOWANCE))) for s, n in alloc.items()}
    return {"n_formula": n_total, "usable": alloc, "draw": inflated,
            "W": W, "sigma": float(sigma)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--islands", nargs="*", default=sorted(ISLAND_BBOX))
    ap.add_argument("--target-pct", type=float, default=2.0,
                    help="target +/- on overall accuracy at 95 %% confidence")
    ap.add_argument("--plan", action="store_true", help="show the design and stop")
    ap.add_argument("--seed", type=int, default=20260920)
    ap.add_argument("--out", default="data/processed/m3")
    args = ap.parse_args()

    print(f"Surveying {len(args.islands)} islands…")
    areas, pools = survey(args.islands)
    d = design(areas, args.target_pct)
    total_area = sum(areas.values())

    print(f"\n{'stratum':22s} {'km2':>10s} {'share':>8s} {'pixels':>12s} "
          f"{'usable':>7s} {'draw':>6s}")
    for s in sorted(areas, key=lambda k: -areas[k]):
        px = sum(len(r) for _, _, r, _ in pools[s])
        print(f"{s:22s} {areas[s]:10.2f} {100 * d['W'][s]:7.2f} % {px:12,d} "
              f"{d['usable'][s]:7d} {d['draw'][s]:6d}")
    print(f"{'TOTAL':22s} {total_area:10.2f} {'':9s} {'':12s} "
          f"{sum(d['usable'].values()):7d} {sum(d['draw'].values()):6d}")

    print(f"\nOlofsson eq. 13 for ±{args.target_pct} % on overall accuracy: "
          f"n = {d['n_formula']} points.")
    print(f"That is small because 'not built' is {100 * d['W']['not_built']:.1f} % of the land "
          f"and easy to classify, so overall accuracy is cheap — and the least "
          f"interesting number here.")
    print(f"Floors of {MIN_PER_RARE_STRATUM} per class raise it to "
          f"{sum(d['usable'].values())}, so each class gets its own usable interval; "
          f"a {100 * UNSURE_ALLOWANCE:.0f} % allowance for 'unsure' makes it "
          f"{sum(d['draw'].values())} to draw.")
    print(f"At 1-2 minutes a point that is roughly "
          f"{sum(d['draw'].values()) * 1.5 / 60:.1f} hours of interpretation.")

    if args.plan:
        return 0

    rng = np.random.default_rng(args.seed)
    points, truth, counter = [], [], 0
    for s, want in d["draw"].items():
        avail = [(isl, tr, r, c) for isl, tr, r, c in pools[s]]
        sizes = np.array([len(r) for _, _, r, _ in avail], dtype=float)
        if sizes.sum() == 0:
            continue
        # Spread the stratum's points across islands in proportion to where it occurs.
        per = rng.multinomial(want, sizes / sizes.sum())
        for (island, transform, rows, cols), take in zip(avail, per, strict=True):
            take = min(int(take), len(rows))
            if not take:
                continue
            for k in rng.choice(len(rows), size=take, replace=False):
                r, c = int(rows[k]), int(cols[k])
                lon, lat = transform * (c + 0.5, r + 0.5)
                counter += 1
                pid = f"p{counter:05d}"
                points.append({"id": pid, "lon": round(lon, 7), "lat": round(lat, 7)})
                truth.append({"id": pid, "island": island, "stratum": s,
                              "stratum_km2": round(areas[s], 3),
                              "map_year": int(enc.decode_year(np.array([0]))[0])})

    rng.shuffle(points)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "points.json").write_text(json.dumps(
        {"island": "Canary Islands", "pixel_m": 10,
         "imagery_years": [2015, 2024], "points": points}, indent=1))
    (out / "map_claims.json").write_text(json.dumps(
        {"strata": STRATA, "design": {k: v for k, v in d.items() if k != "W"},
         "claims": truth}, indent=1))
    print(f"\n{len(points)} points -> {out / 'points.json'}")
    print(f"map's own answers held back in {out / 'map_claims.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
