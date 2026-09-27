"""M0 analysis 1 — how much is built, per island, per dataset, per year.

Answers the first question of Milestone 0: do the candidate datasets produce
plausible numbers for the Canary Islands, and do they agree on the growth rate?

Two quantities are reported and never mixed (docs/concepts.md section 3):
  EXTENT  km2 of pixels containing settlement   (WSF Evolution / 2015 / 2019)
  SURFACE km2 of actual built cover              (GHSL GHS-BUILT-S)

Outputs
  docs/figures/data/m0_totals.csv      tidy table, one row per island x dataset x year
  docs/figures/m0_totals.png           per-island series and growth indexed to 1990

    python scripts/analysis_01_totals.py [--islands "Gran Canaria,Tenerife"]
"""

from __future__ import annotations

import argparse
import warnings

import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

from sensisat import zones  # noqa: E402
from sensisat.config import CANARIES_LAND_KM2, FIGURES, ISLAND_AREA_KM2, ISLAND_BBOX  # noqa: E402
from sensisat.datasets import ghsl, wsf  # noqa: E402
from sensisat.stats import zonal  # noqa: E402

OUT_CSV = FIGURES / "data" / "m0_totals.csv"

# Dynamic World numbers from the original prototype notebook
# (geeLocalTesting/urban_expansion_canarias.ipynb), for comparison only.
DW_GRAN_CANARIA = {2016: 307.8, 2025: 327.9}

# Published context for plausibility: official statistics put artificial land at
# roughly 6 % of the archipelago, and the most urbanised coastal strip (<500 m
# from the sea) at "casi el 18 %". An island-wide figure above ~10 % is suspect.
OFFICIAL_ARTIFICIAL_SHARE_PCT = 6.0

WSF_EVO_YEARS = list(range(1985, 2016))


def island_zones(names: list[str]):
    gdf = zones.islands()
    return gdf[gdf["name"].isin(names)].copy()


def run(island_names: list[str]) -> pd.DataFrame:
    rows: list[dict] = []
    all_zones = island_zones(island_names)

    for name in island_names:
        bbox = ISLAND_BBOX[name]
        z = all_zones[all_zones["name"] == name]
        if z.empty:
            print(f"  ! no polygon for {name}, skipping")
            continue
        print(f"\n=== {name} ({ISLAND_AREA_KM2[name]:.0f} km2) ===")

        # ---- WSF Evolution: extent, one value per year 1985..2015 -------------
        try:
            arr, transform, crs = wsf.load("wsf_evolution", bbox)
            for year in WSF_EVO_YEARS:
                mask = (arr > 0) & (arr <= year)
                df = zonal(mask, transform, crs, z, kind="binary", label="built")
                rows.append({
                    "island": name, "dataset": "WSF Evolution", "measure": "extent",
                    "resolution_m": 30, "year": year,
                    "built_km2": float(df["built_km2"].iloc[0]),
                    "island_km2": float(df["zone_km2"].iloc[0]),
                    "note": "baseline year" if year == 1985 else "",
                })
            first, last = rows[-len(WSF_EVO_YEARS)], rows[-1]
            print(f"  WSF Evolution  1985 {first['built_km2']:7.2f} -> 2015 {last['built_km2']:7.2f} km2 "
                  f"({100 * first['built_km2'] / last['built_km2']:.0f} % already in the 1985 baseline)")
        except Exception as exc:
            print(f"  ! WSF Evolution failed: {type(exc).__name__}: {exc}")

        # ---- WSF 2015 / 2019: extent at 10 m ---------------------------------
        for product, year in (("wsf2015", 2015), ("wsf2019", 2019)):
            try:
                mask, transform, crs = wsf.built_mask(product, bbox)
                df = zonal(mask, transform, crs, z, kind="binary", label="built")
                rows.append({
                    "island": name, "dataset": f"WSF {year}", "measure": "extent",
                    "resolution_m": 10, "year": year,
                    "built_km2": float(df["built_km2"].iloc[0]),
                    "island_km2": float(df["zone_km2"].iloc[0]), "note": "",
                })
                print(f"  WSF {year}       {df['built_km2'].iloc[0]:7.2f} km2 (10 m)")
            except Exception as exc:
                print(f"  ! {product} failed: {type(exc).__name__}: {exc}")

        # ---- GHSL: surface, per epoch ----------------------------------------
        for epoch in ghsl.EPOCHS:
            if epoch > 2020:  # 2025 / 2030 are projections, not measurements
                continue
            try:
                arr, transform, crs = ghsl.load(epoch, bbox)
                df = zonal(arr, transform, crs, z, kind="amount", label="built")
                rows.append({
                    "island": name, "dataset": "GHSL built surface", "measure": "surface",
                    "resolution_m": 92, "year": epoch,
                    "built_km2": float(df["built_km2"].iloc[0]),
                    "island_km2": float(df["zone_km2"].iloc[0]),
                    "note": ghsl.is_observed(epoch),
                })
            except Exception as exc:
                print(f"  ! GHSL {epoch} failed: {type(exc).__name__}: {exc}")
        ghsl_rows = [r for r in rows if r["island"] == name and r["dataset"] == "GHSL built surface"]
        if ghsl_rows:
            print(f"  GHSL surface   1975 {ghsl_rows[0]['built_km2']:7.2f} -> 2020 {ghsl_rows[-1]['built_km2']:7.2f} km2")

    df = pd.DataFrame(rows)
    df["share_of_island_pct"] = (100 * df["built_km2"] / df["island_km2"]).round(2)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nwrote {OUT_CSV} ({len(df)} rows)")
    return df


def report(df: pd.DataFrame) -> str:
    """Markdown summary for docs/data-evaluation.md."""
    lines = []
    lines.append("### Built-up per island: extent vs surface\n")
    lines.append("EXTENT counts pixels containing any settlement; SURFACE counts square metres of")
    lines.append("actual built cover. They are different quantities and are never compared to each")
    lines.append("other. Official statistics put artificial land near "
                 f"{OFFICIAL_ARTIFICIAL_SHARE_PCT:.0f} % of the archipelago.\n")

    snap = []
    for island in df["island"].unique():
        d = df[df["island"] == island]
        row = {"island": island, "island_km2": round(d["island_km2"].iloc[0], 1)}
        for label, ds, yr in (("WSF Evo 2015", "WSF Evolution", 2015),
                              ("WSF 2015 (10 m)", "WSF 2015", 2015),
                              ("WSF 2019 (10 m)", "WSF 2019", 2019),
                              ("GHSL surface 2020", "GHSL built surface", 2020)):
            sel = d[(d["dataset"] == ds) & (d["year"] == yr)]
            row[label] = round(float(sel["built_km2"].iloc[0]), 1) if len(sel) else None
            if len(sel):
                row[f"{label} %"] = round(float(sel["share_of_island_pct"].iloc[0]), 1)
        snap.append(row)
    lines.append(pd.DataFrame(snap).to_markdown(index=False))

    tot = df[df["island"].isin(ISLAND_AREA_KM2)].copy()
    lines.append(f"\nArchipelago land area used: {CANARIES_LAND_KM2:.0f} km2.\n")
    for ds, yr in (("WSF Evolution", 2015), ("WSF 2019", 2019), ("GHSL built surface", 2020)):
        sel = tot[(tot["dataset"] == ds) & (tot["year"] == yr)]
        if len(sel):
            s = sel["built_km2"].sum()
            lines.append(f"- **{ds} {yr}**: {s:.1f} km2 across all islands "
                         f"= {100 * s / CANARIES_LAND_KM2:.1f} % of land")
    lines.append(f"- **Dynamic World (prototype)**: {DW_GRAN_CANARIA[2016]:.1f} km2 for Gran Canaria alone "
                 f"= {100 * DW_GRAN_CANARIA[2016] / ISLAND_AREA_KM2['Gran Canaria']:.1f} % of that island")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--islands", default=",".join(ISLAND_BBOX))
    args = ap.parse_args()
    names = [s.strip() for s in args.islands.split(",") if s.strip()]
    frame = run(names)
    print()
    print(report(frame))
