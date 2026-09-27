"""M0 analysis 13 — real built-up loss, from Copernicus Impervious Built-Up Change 2018-2021.

This is the product the plan waited for: the only one in hand that records GAIN and
LOSS separately, from a producer with a stated >= 90 % accuracy target and explicit
Canary coverage. Every WSF product and GHSL are growth-only by construction and
cannot answer this (docs/data-evaluation.md, sections 5-6).

Classes (from the shipped SLD style):
    0  unchanged non-built-up      10  unchanged built-up
    1  new cover (new built-up)    11  increased built-up density
    2  loss of cover               12  decreased built-up density
    255 outside area
20 m pixels in EPSG:3035 (European LAEA), so a pixel is exactly 400 m2 - no
latitude correction needed, unlike the WSF/GHSL degree grids.

Caveat: the 'Change Support' layer (technical vs real change) was not in this
download; the loss figure here is therefore an upper bound on real loss.

Input: data/raw/hrl/110241/Results/*/CLMS_HRLNVLCC_IBUC_C2018-2021_R20m_*.tif
Output: docs/figures/data/m0_hrl_change_2018_2021.csv

    python scripts/analysis_13_hrl_change.py
"""

from __future__ import annotations

import glob
import warnings

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from rasterio.merge import merge

warnings.filterwarnings("ignore")

from sensisat import zones  # noqa: E402
from sensisat.config import FIGURES, RAW  # noqa: E402

OUT_CSV = FIGURES / "data" / "m0_hrl_change_2018_2021.csv"
CLASSES = {0: "unchanged_non_built", 1: "new_built", 2: "loss_built",
           10: "unchanged_built", 11: "increased_density", 12: "decreased_density"}
PX_KM2 = 0.02 * 0.02  # 20 m x 20 m
YEARS = 3


def load_mosaic():
    tifs = sorted(glob.glob(str(RAW / "hrl" / "110241" / "Results" / "*" / "*IBUC*.tif")))
    if not tifs:
        raise FileNotFoundError("Copernicus IBUC tiles not found under data/raw/hrl/110241/")
    srcs = [rasterio.open(t) for t in tifs]
    arr, transform = merge(srcs, nodata=255)
    crs = srcs[0].crs
    for s in srcs:
        s.close()
    return arr[0], transform, crs


def run() -> pd.DataFrame:
    arr, transform, crs = load_mosaic()
    isl = zones.islands().to_crs(crs)
    rows = []
    for _, r in isl.iterrows():
        m = ~geometry_mask([r.geometry], out_shape=arr.shape, transform=transform, invert=False)
        vals = arr[m]
        counts = {name: int((vals == code).sum()) for code, name in CLASSES.items()}
        km2 = {k: v * PX_KM2 for k, v in counts.items()}
        built_2018 = km2["unchanged_built"] + km2["loss_built"] + km2["increased_density"] + km2["decreased_density"]
        built_2021 = km2["unchanged_built"] + km2["new_built"] + km2["increased_density"] + km2["decreased_density"]
        rows.append({
            "island": r["name"],
            **{f"{k}_km2": round(v, 3) for k, v in km2.items()},
            "built_2018_km2": round(built_2018, 2), "built_2021_km2": round(built_2021, 2),
            "loss_pct_of_2018": round(100 * km2["loss_built"] / built_2018, 3) if built_2018 else np.nan,
            "loss_pct_per_year": round(100 * km2["loss_built"] / built_2018 / YEARS, 3) if built_2018 else np.nan,
            "gain_pct_per_year": round(100 * km2["new_built"] / built_2018 / YEARS, 3) if built_2018 else np.nan,
        })
        print(f"  {r['name']:14s} built 2018 {built_2018:7.2f} -> 2021 {built_2021:7.2f} km2 | "
              f"new {km2['new_built']:5.3f} | LOSS {km2['loss_built']:5.3f} ({100 * km2['loss_built'] / built_2018 / YEARS if built_2018 else 0:.3f} %/yr)")

    df = pd.DataFrame(rows)
    tot = df.sum(numeric_only=True)
    b18 = tot["built_2018_km2"]
    print("\n--- archipelago (Copernicus Impervious Built-Up Change 2018-2021, 20 m) ---")
    print(f"  built 2018            {b18:8.2f} km2")
    print(f"  built 2021            {tot['built_2021_km2']:8.2f} km2")
    print(f"  new built-up          {tot['new_built_km2']:8.3f} km2  = {100 * tot['new_built_km2'] / b18 / YEARS:.3f} %/yr")
    print(f"  LOSS of built-up      {tot['loss_built_km2']:8.3f} km2  = {100 * tot['loss_built_km2'] / b18 / YEARS:.3f} %/yr")
    print(f"  density up / down     {tot['increased_density_km2']:.3f} / {tot['decreased_density_km2']:.3f} km2")
    rate = 100 * tot["loss_built_km2"] / b18 / YEARS
    print(f"\n  Cost of a growth-only encoding over 40 years at this loss rate: {40 * rate:.1f} % of built pixels.")
    print("  (Upper bound: the 'technical vs real change' support layer was not downloaded.)")
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nwrote {OUT_CSV}")
    return df


if __name__ == "__main__":
    run()
