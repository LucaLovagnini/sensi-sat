"""M0 analysis 7 — how much built-up land actually disappears?

The plan's growth-only encoding (one "year first built" raster, so the time slider
is a threshold) cannot represent demolition. Its cost equals the real rate at which
built-up land stops being built-up. This measures that rate.

The intended source, Copernicus HRL Built-up Change 2018-2021, needs a free
account. A substitute is available with no login and is arguably better for our
purpose: WSF 2015 and WSF 2019 are independent binary snapshots at 10 m from the
same producer, four years apart. Pixels built in 2015 but not in 2019 are either

  - real loss (demolition, clearance, burial), or
  - classification noise ("flicker"),

and the two are separated by geometry: real loss happens in compact blocks, noise
appears as isolated pixels at the edges of settlements. We report both, filtering
isolated pixels with binary erosion, so the plan gets an upper and a lower bound.

Caveat: this is NOT an official change product. WSF 2015 and 2019 were produced
with different sensors (Landsat-8+Sentinel-1 vs Sentinel-1+Sentinel-2), so some
apparent change is method change. Treated as an upper bound on true loss.

Outputs
  docs/figures/data/m0_loss_rate.csv

    python scripts/analysis_07_loss_rate.py
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import ndimage

warnings.filterwarnings("ignore")

from sensisat import zones  # noqa: E402
from sensisat.config import FIGURES, ISLAND_BBOX  # noqa: E402
from sensisat.datasets import wsf  # noqa: E402
from sensisat.raster import area_km2, resample_to  # noqa: E402

OUT_CSV = FIGURES / "data" / "m0_loss_rate.csv"
YEARS_BETWEEN = 4  # 2015 -> 2019


def compact_only(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    """Keep only pixels in blocks that survive erosion — drops isolated flicker."""
    if not mask.any():
        return mask
    eroded = ndimage.binary_erosion(mask, structure=np.ones((3, 3)), iterations=iterations)
    # Re-grow the surviving cores so partial blocks keep their true size.
    return ndimage.binary_propagation(eroded, mask=mask)


def run(island_names: list[str]) -> pd.DataFrame:
    isl = zones.islands()
    rows = []

    for name in island_names:
        bbox = ISLAND_BBOX[name]
        z = isl[isl["name"] == name]
        if z.empty:
            continue
        try:
            m15, t15, c15 = wsf.built_mask("wsf2015", bbox)
            m19, t19, c19 = wsf.built_mask("wsf2019", bbox)
        except Exception as exc:
            print(f"  ! {name}: {type(exc).__name__}: {exc}")
            continue

        # Put 2019 on the 2015 grid so pixels line up exactly.
        if (t15 != t19) or (m15.shape != m19.shape):
            m19 = resample_to(m19.astype("uint8"), t19, c19, t15, m15.shape, c15).astype(bool)

        # Restrict to the island polygon so ocean and neighbouring islands are out.
        from sensisat.stats import zone_masks
        island_mask = zone_masks(z, t15, m15.shape, c15)[name]
        b15 = m15 & island_mask
        b19 = m19 & island_mask

        lost = b15 & ~b19
        gained = b19 & ~b15
        lost_compact = compact_only(lost)

        a15 = area_km2(b15, t15)
        a19 = area_km2(b19, t15)
        a_lost = area_km2(lost, t15)
        a_lost_c = area_km2(lost_compact, t15)
        a_gain = area_km2(gained, t15)

        rows.append({
            "island": name,
            "built_2015_km2": round(a15, 3), "built_2019_km2": round(a19, 3),
            "lost_km2": round(a_lost, 3), "lost_compact_km2": round(a_lost_c, 3),
            "gained_km2": round(a_gain, 3),
            "loss_pct_of_2015": round(100 * a_lost / a15, 2) if a15 else np.nan,
            "loss_pct_per_year": round(100 * a_lost / a15 / YEARS_BETWEEN, 3) if a15 else np.nan,
            "compact_loss_pct_per_year": round(100 * a_lost_c / a15 / YEARS_BETWEEN, 3) if a15 else np.nan,
            "isolated_share_of_loss_pct": round(100 * (1 - a_lost_c / a_lost), 1) if a_lost else np.nan,
        })
        print(f"  {name:16s} 2015 {a15:7.2f} -> 2019 {a19:7.2f} km2 | "
              f"lost {a_lost:6.2f} ({100 * a_lost / a15:4.1f} %), of which "
              f"{100 * (1 - a_lost_c / a_lost) if a_lost else 0:4.1f} % isolated pixels | gained {a_gain:6.2f}")

    df = pd.DataFrame(rows)
    if len(df):
        tot15 = df["built_2015_km2"].sum()
        tot_lost = df["lost_km2"].sum()
        tot_lost_c = df["lost_compact_km2"].sum()
        print("\n--- archipelago ---")
        print(f"  built 2015           {tot15:8.2f} km2")
        print(f"  built 2019           {df['built_2019_km2'].sum():8.2f} km2")
        print(f"  apparent loss        {tot_lost:8.2f} km2 = {100 * tot_lost / tot15:.2f} % "
              f"= {100 * tot_lost / tot15 / YEARS_BETWEEN:.3f} %/yr  (upper bound)")
        print(f"  compact loss only    {tot_lost_c:8.2f} km2 = {100 * tot_lost_c / tot15:.2f} % "
              f"= {100 * tot_lost_c / tot15 / YEARS_BETWEEN:.3f} %/yr  (plausible real loss)")
        print(f"  gained               {df['gained_km2'].sum():8.2f} km2")
        print()
        years = 40
        print(f"  Cost of a growth-only view over {years} years, if the compact rate held:")
        print(f"    {100 * tot_lost_c / tot15 / YEARS_BETWEEN * years:.1f} % of built pixels would be "
              f"shown as built when they are not.")
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT_CSV, index=False)
        print(f"\nwrote {OUT_CSV}")
    return df


if __name__ == "__main__":
    run(list(ISLAND_BBOX))
