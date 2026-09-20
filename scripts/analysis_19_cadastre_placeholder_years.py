"""Analysis 19 — are the cadastre's construction years real, or administrative buckets?

Prompted by Caleta de Famara (Lanzarote): the viewer showed **two** buildings
standing by 1949 in a village that Wikipedia dates to the late 1700s, with
permanent settlement from 1888 and "tres edificios, veinticuatro almacenes y
veinticinco habitantes" by 1909. The raw feed explains it — those two are dated
`1900-01-01`, and the next block is dated exactly `1950-01-01`.

Round dates are what a register writes when it does not know. This measures how
much of the cadastre is bucketed that way, and then asks the harder question:
are the bucket years actually WRONG, or merely suspiciously round?

The test for that uses WSF Evolution, which is independent of the cadastre and
records the year a 30 m pixel first showed settlement, 1985-2015. For buildings
dated in a spike year we compare the satellite's year against the register's; a
genuine date should agree far more often than a bucket does.

Outputs
  docs/figures/data/m0_cadastre_year_histogram.csv
  docs/figures/data/m0_cadastre_spike_years.csv
    python scripts/analysis_19_cadastre_placeholder_years.py
"""
from __future__ import annotations

import collections
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from sensisat.config import FIGURES, ISLAND_BBOX  # noqa: E402
from sensisat.datasets import cadastre  # noqa: E402

SPIKE_RATIO = 3.0        # a year holding >3x its neighbours' average is suspicious
WINDOW = (-3, -2, -1, 1, 2, 3)


def histogram() -> tuple[collections.Counter, dict[str, collections.Counter], int]:
    """Construction years, archipelago-wide and per island."""
    overall: collections.Counter = collections.Counter()
    per_island: dict[str, collections.Counter] = {i: collections.Counter() for i in ISLAND_BBOX}
    index = cadastre.build_index()
    total = 0
    for n, code in enumerate(sorted(index), 1):
        print(f"\r  reading {n:3d}/{len(index)}  {code}", end="", flush=True)
        try:
            g = cadastre.buildings(code)
        except Exception:
            continue
        years = g.loc[g["year"] > 0, "year"].tolist()
        overall.update(years)
        total += len(g)
        island = index[code].get("island")
        if island in per_island:
            per_island[island].update(years)
    print()
    return overall, per_island, total


def spikes(hist: collections.Counter) -> pd.DataFrame:
    rows = []
    for year in range(cadastre.YEAR_MIN, 2027):
        n = hist.get(year, 0)
        if not n:
            continue
        neighbours = [hist.get(year + d, 0) for d in WINDOW]
        avg = sum(neighbours) / len(neighbours)
        ratio = n / avg if avg else float("inf")
        rows.append({"year": year, "buildings": n, "neighbour_mean": round(avg, 1),
                     "ratio": round(ratio, 1) if np.isfinite(ratio) else None,
                     "is_spike": ratio >= SPIKE_RATIO})
    return pd.DataFrame(rows)


def wsf_agreement(spike_years: list[int]) -> pd.DataFrame:
    """Do the satellite and the register agree about when a building appeared?

    Only 1986-2014 can be tested: WSF Evolution runs 1985-2015, and its first year
    is a baseline carrying everything built before satellite record, so it cannot
    date anything. For each testable spike year we compare against the two adjacent
    non-spike years, which are the control.
    """
    import rasterio
    from rasterio.features import geometry_mask

    from sensisat.datasets import wsf

    island = "Gran Canaria"
    evo, transform, crs = wsf.load("wsf_evolution", ISLAND_BBOX[island])
    codes = cadastre.codes_for(island)

    frames = []
    for code in codes:
        g = cadastre.buildings(code).to_crs(crs)
        frames.append(g[["year", "geometry"]])
    gdf = pd.concat(frames, ignore_index=True)

    testable = [y for y in spike_years if 1986 <= y <= 2014]
    controls = sorted({y + d for y in testable for d in (-1, 1)} - set(spike_years))

    rows = []
    for label, years in (("spike", testable), ("control", controls)):
        for year in years:
            sub = gdf[gdf["year"] == year]
            if len(sub) < 200:
                continue
            mask = ~geometry_mask(sub.geometry, out_shape=evo.shape, transform=transform,
                                  invert=False)
            seen = evo[mask & (evo > 0)]
            if seen.size < 100:
                continue
            rows.append({
                "kind": label, "year": year, "buildings": len(sub), "pixels": int(seen.size),
                "wsf_median_year": int(np.median(seen)),
                "offset_years": int(np.median(seen)) - year,
                "within_3_years_pct": round(100 * float(np.mean(np.abs(seen - year) <= 3)), 1),
            })
    return pd.DataFrame(rows)


def main() -> int:
    overall, per_island, total = histogram()
    df = spikes(overall)
    out = FIGURES / "data"
    df.to_csv(out / "m0_cadastre_year_histogram.csv", index=False)

    spike_df = df[df["is_spike"]].sort_values("buildings", ascending=False)
    dated = int(sum(overall.values()))
    in_spikes = int(spike_df["buildings"].sum())

    print(f"\n{total:,} buildings, {dated:,} dated")
    print(f"{len(spike_df)} spike years hold {in_spikes:,} buildings "
          f"= {100 * in_spikes / dated:.1f} % of everything dated\n")
    print("The ten biggest:")
    print(spike_df.head(10).to_string(index=False))

    print("\nShare of each island's dated buildings sitting in a spike year:")
    rows = []
    for island, hist in per_island.items():
        n = sum(hist.values())
        if not n:
            continue
        s = sum(hist.get(int(y), 0) for y in spike_df["year"])
        rows.append({"island": island, "dated": n, "in_spike_year": s,
                     "share_pct": round(100 * s / n, 1)})
    island_df = pd.DataFrame(rows).sort_values("share_pct", ascending=False)
    print(island_df.to_string(index=False))

    print("\nDoes an independent satellite agree with the register's year?")
    print("(WSF Evolution, Gran Canaria; 'offset' is satellite median minus register year)")
    agree = wsf_agreement(spike_df["year"].astype(int).tolist())
    if len(agree):
        print(agree.to_string(index=False))
        summary = agree.groupby("kind")[["within_3_years_pct", "offset_years"]].mean().round(1)
        print("\nmean by kind:")
        print(summary.to_string())
    else:
        print("  not enough buildings in the testable range to compare")

    spike_df.assign().to_csv(out / "m0_cadastre_spike_years.csv", index=False)
    island_df.to_csv(out / "m0_cadastre_spike_by_island.csv", index=False)
    if len(agree):
        agree.to_csv(out / "m0_cadastre_spike_vs_wsf.csv", index=False)
    print(f"\nwrote {out / 'm0_cadastre_year_histogram.csv'} and companions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
