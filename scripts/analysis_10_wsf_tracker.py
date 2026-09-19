"""M0 analysis 10 — is WSF Tracker plausible?

Plan decision 10 makes WSF Tracker the spine for 2016 onward, but it was published
in June 2026 with no accuracy figures, so nothing about it was tested. This does
the testing that is possible without reference imagery:

  1. Epoch histogram per island. Real construction is spread across epochs; a
     product driven by method changes shows spikes.
  2. Baseline share. Epoch 1 means "already built by July 2016" and carries the
     bulk of the footprint, exactly as 1985 does in WSF Evolution.
  3. Continuity with the older products. WSF 2015 (10 m) and Tracker epoch 1
     (2016-07) are 18 months apart and should nearly agree. WSF Evolution ends in
     2015 at 30 m and should be larger, by the extent-inflation factor only.
  4. Timanfaya negative control.
  5. Tajogaite 2021 lava. Tracker cannot show the burial - its encoding keeps the
     earliest epoch forever - but built-up first detected there AFTER epoch 11
     (2021-07) would be reconstruction or error.

Outputs
  docs/figures/data/m0_wsf_tracker.csv

    python scripts/analysis_10_wsf_tracker.py
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from sensisat import zones  # noqa: E402
from sensisat.config import FIGURES, ISLAND_BBOX  # noqa: E402
from sensisat.datasets import wsf_tracker as wt  # noqa: E402
from sensisat.raster import area_km2  # noqa: E402
from sensisat.stats import zone_masks  # noqa: E402

OUT_CSV = FIGURES / "data" / "m0_wsf_tracker.csv"
ERUPTION_EPOCH = 11  # 2021-07: the Tajogaite eruption began 2021-09-19


def per_island() -> pd.DataFrame:
    isl = zones.islands()
    rows = []
    for name, bbox in ISLAND_BBOX.items():
        z = isl[isl["name"] == name]
        if z.empty:
            continue
        data, transform, crs = wt.load(bbox)
        mask_island = zone_masks(z, transform, data.shape, crs)[name]
        data = np.where(mask_island, data, 0)

        total = area_km2(data > 0, transform)
        by_epoch = {e: area_km2(data == e, transform) for e in range(1, wt.N_EPOCHS + 1)}
        baseline = by_epoch[1]
        rows.append({
            "island": name,
            "total_2026_km2": round(total, 3),
            "baseline_2016_07_km2": round(baseline, 3),
            "baseline_share_pct": round(100 * baseline / total, 1) if total else np.nan,
            "added_2016_2026_km2": round(total - baseline, 3),
            "growth_pct_over_9y": round(100 * (total - baseline) / baseline, 1) if baseline else np.nan,
            "growth_pct_per_year": round(100 * (total - baseline) / baseline / 9.5, 2) if baseline else np.nan,
            **{f"epoch_{e:02d}_km2": round(by_epoch[e], 4) for e in range(1, wt.N_EPOCHS + 1)},
        })
        print(f"  {name:16s} total {total:7.2f} km2 | baseline(2016-07) {baseline:7.2f} "
              f"({100 * baseline / total if total else 0:4.1f} %) | added {total - baseline:6.2f} km2 "
              f"= {100 * (total - baseline) / baseline / 9.5 if baseline else 0:.2f} %/yr")
    return pd.DataFrame(rows)


def continuity(df: pd.DataFrame) -> pd.DataFrame:
    """Does Tracker's 2016 baseline line up with WSF 2015 and WSF Evolution?"""
    totals = pd.read_csv(FIGURES / "data" / "m0_totals.csv")
    rows = []
    for _, r in df.iterrows():
        isl = r["island"]
        sel = totals[totals.island == isl]
        w15 = sel[(sel.dataset == "WSF 2015")]["built_km2"]
        w19 = sel[(sel.dataset == "WSF 2019")]["built_km2"]
        evo = sel[(sel.dataset == "WSF Evolution") & (sel.year == 2015)]["built_km2"]
        rows.append({
            "island": isl,
            "WSF2015_10m": round(float(w15.iloc[0]), 2) if len(w15) else None,
            "Tracker_epoch1_2016_07": round(r["baseline_2016_07_km2"], 2),
            "ratio_tracker_over_wsf2015": round(r["baseline_2016_07_km2"] / float(w15.iloc[0]), 2) if len(w15) else None,
            "WSF2019_10m": round(float(w19.iloc[0]), 2) if len(w19) else None,
            "Tracker_2026": round(r["total_2026_km2"], 2),
            "WSFevo2015_30m": round(float(evo.iloc[0]), 2) if len(evo) else None,
        })
    return pd.DataFrame(rows)


def lava_checks() -> pd.DataFrame:
    rows = []
    for key, query, want, role in (
        ("Timanfaya NP", "Parque Nacional de Timanfaya", "national_park", "negative control"),
        ("Tajogaite lava 2021", "Tajogaite", "bare_rock", "loss test case"),
    ):
        gdf = zones.nominatim_polygon(query, key=key.lower().replace(" ", "_"), want=want).assign(name=key)
        minx, miny, maxx, maxy = gdf.total_bounds
        pad = 0.02
        data, transform, crs = wt.load((minx - pad, miny - pad, maxx + pad, maxy + pad))
        mask = zone_masks(gdf, transform, data.shape, crs)[key]
        inside = np.where(mask, data, 0)
        total = area_km2(inside > 0, transform)
        control_km2 = area_km2(mask, transform)
        before = area_km2((inside > 0) & (inside <= ERUPTION_EPOCH), transform)
        after = area_km2(inside > ERUPTION_EPOCH, transform)
        rows.append({
            "polygon": key, "role": role, "polygon_km2": round(control_km2, 2),
            "tracker_built_km2": round(total, 3),
            "share_pct": round(100 * total / control_km2, 2) if control_km2 else np.nan,
            "first_seen_before_2021_07_km2": round(before, 3),
            "first_seen_after_2021_07_km2": round(after, 3),
        })
        print(f"  {key:22s} [{role:16s}] built {total:7.3f} km2 = {100 * total / control_km2:5.2f} % | "
              f"first seen <=2021-07 {before:6.3f} | >2021-07 {after:6.3f}")
    return pd.DataFrame(rows)


def run() -> None:
    print("WSF Tracker array metadata:")
    meta = wt.describe()
    print(f"  shape {meta['shape']}, dtype {meta['dtype']}, valid {meta['valid_range']}")
    print(f"  {meta['long_name']}")

    print("\n--- per island ---")
    df = per_island()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    print("\n--- continuity with the older WSF products ---")
    print(continuity(df).to_string(index=False))

    print("\n--- lava polygons ---")
    lav = lava_checks()

    print("\n--- archipelago epoch histogram (km2 first detected in each epoch) ---")
    ep_cols = [c for c in df.columns if c.startswith("epoch_")]
    tot = df[ep_cols].sum()
    for i, c in enumerate(ep_cols, start=1):
        bar = "#" * int(min(60, tot[c] * (60 / max(tot.max(), 1e-9))))
        flag = "  <- baseline" if i == 1 else ""
        print(f"  {i:2d} {wt.epoch_to_label(i)}  {tot[c]:7.2f} km2 {bar}{flag}")
    print(f"\n  archipelago total 2026: {df['total_2026_km2'].sum():.2f} km2")
    print(f"  baseline (2016-07):     {df['baseline_2016_07_km2'].sum():.2f} km2 "
          f"({100 * df['baseline_2016_07_km2'].sum() / df['total_2026_km2'].sum():.1f} %)")
    print(f"  added 2016-2026:        {df['added_2016_2026_km2'].sum():.2f} km2 "
          f"= {100 * df['added_2016_2026_km2'].sum() / df['baseline_2016_07_km2'].sum() / 9.5:.2f} %/yr")
    lav.to_csv(FIGURES / "data" / "m0_wsf_tracker_lava.csv", index=False)
    print(f"\nwrote {OUT_CSV}")


if __name__ == "__main__":
    run()
