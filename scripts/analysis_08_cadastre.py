"""M0 analysis 8 — the cadastre as an independent witness.

Spain's cadastre records a construction year for every building. HISDAC-ES (Uhl et
al. 2023, CC BY 4.0) turns that into 100 m grids: `mincoy` = the earliest construction
year of any building in the cell (0 = no building), and `bufa_<year>` = building
footprint area per cell for every 5-year epoch 1900-2020. It is independent of every
satellite product - different data, different failure modes (renovations can reset
the year; demolished buildings vanish) - which is exactly what makes it useful here.

Three questions:
  1. Is WSF Evolution's 1985 baseline real? For pixels it calls "built by 1985", does
     the cadastre have a building in that cell dated <= 1985, dated later, or none?
  2. Does the cadastre agree with WSF Evolution's later dating (1986-2015)?
  3. What is Tracker's 'pre-2016 undated' class, seen from the cadastre? A cell with
     no building at all under a Tracker pixel points to non-building structures
     (greenhouses, roads, walls) or Tracker commission.
Plus a bonus: the cadastral footprint-area series 1975-2020 per island, a third
SURFACE product spanning the 2015/2016 seam, for comparison with GHSL.

Outputs
  docs/figures/data/m0_cadastre_vs_wsf.csv
  docs/figures/data/m0_cadastre_bufa_series.csv

    python scripts/analysis_08_cadastre.py [--tracker-islands "Gran Canaria,Tenerife,Fuerteventura"]
"""

from __future__ import annotations

import argparse
import warnings

import numpy as np
import pandas as pd
import rasterio

warnings.filterwarnings("ignore")

from sensisat import zones  # noqa: E402
from sensisat.config import FIGURES, ISLAND_BBOX, RAW  # noqa: E402
from sensisat.datasets import wsf, wsf_tracker as wt  # noqa: E402
from sensisat.raster import area_km2, resample_to  # noqa: E402
from sensisat.stats import zone_masks  # noqa: E402

HIS = RAW / "hisdac_es" / "canary"
MINCOY = HIS / "can_regcan_age" / "hisdac_es_age_mincoy_v1_100.tif"
BUFA = HIS / "can_regcan_evolution" / "hisdac_es_evol_bufa_v1_100_{year}.tif"
OUT_WSF = FIGURES / "data" / "m0_cadastre_vs_wsf.csv"
OUT_BUFA = FIGURES / "data" / "m0_cadastre_bufa_series.csv"
TOL = 5  # years of tolerance when comparing WSF's year with the cadastre's


def coy_on_grid(transform, shape, crs) -> np.ndarray:
    """Cadastre min construction year, nearest-neighbour onto a target grid."""
    with rasterio.open(MINCOY) as s:
        return resample_to(s.read(1), s.transform, s.crs, transform, shape, crs, nodata=0)


def wsf_vs_cadastre(island: str) -> dict:
    bbox = ISLAND_BBOX[island]
    isl = zones.islands()
    z = isl[isl["name"] == island]
    evo, te, ec = wsf.load("wsf_evolution", bbox)
    m = zone_masks(z, te, evo.shape, ec)[island]
    coy = coy_on_grid(te, evo.shape, ec)

    base = (evo == 1985) & m
    later = (evo > 1985) & m
    never = (evo == 0) & m

    def share(mask, cond):
        a = area_km2(mask, te)
        return area_km2(mask & cond, te) / a if a else np.nan

    row = {
        "island": island,
        "wsf_1985_km2": round(area_km2(base, te), 2),
        # Q1 - the 1985 baseline
        "base_cadastre_le1985_pct": round(100 * share(base, (coy > 0) & (coy <= 1985)), 1),
        "base_cadastre_after1985_pct": round(100 * share(base, coy > 1985), 1),
        "base_cadastre_nobuilding_pct": round(100 * share(base, coy == 0), 1),
        # Q2 - later dating: cadastre first building within +-TOL of the WSF year, earlier, later, or none
        "later_km2": round(area_km2(later, te), 2),
        "later_agree_pct": round(100 * share(later, (coy > 0) & (np.abs(coy - evo) <= TOL)), 1),
        "later_cadastre_earlier_pct": round(100 * share(later, (coy > 0) & (coy < evo - TOL)), 1),
        "later_cadastre_later_pct": round(100 * share(later, coy > evo + TOL), 1),
        "later_cadastre_nobuilding_pct": round(100 * share(later, coy == 0), 1),
        # omission check: cadastre says a building existed by 1985, WSF says never built
        "never_but_cadastre_le1985_km2": round(area_km2(never & (coy > 0) & (coy <= 1985), te), 2),
    }
    print(f"  {island:14s} 1985 baseline {row['wsf_1985_km2']:6.2f} km2: cadastre <=1985 {row['base_cadastre_le1985_pct']:5.1f} % | "
          f"after 1985 {row['base_cadastre_after1985_pct']:5.1f} % | no building {row['base_cadastre_nobuilding_pct']:5.1f} %"
          f"   || 1986-2015 dated: agree±{TOL} {row['later_agree_pct']:4.1f} %, cadastre earlier {row['later_cadastre_earlier_pct']:4.1f} %, "
          f"later {row['later_cadastre_later_pct']:4.1f} %, none {row['later_cadastre_nobuilding_pct']:4.1f} %")
    return row


def tracker_undated_vs_cadastre(island: str) -> dict:
    bbox = ISLAND_BBOX[island]
    isl = zones.islands()
    z = isl[isl["name"] == island]
    trk, tt, tc = wt.load(bbox)
    evo, te, ec = wsf.load("wsf_evolution", bbox)
    evo10 = resample_to(evo, te, ec, tt, trk.shape, tc)
    m = zone_masks(z, tt, trk.shape, tc)[island]
    coy = coy_on_grid(tt, trk.shape, tc)
    dated = (trk == 1) & m & (evo10 > 0)
    undated = (trk == 1) & m & (evo10 == 0)

    def share(mask, cond):
        a = area_km2(mask, tt)
        return area_km2(mask & cond, tt) / a if a else np.nan

    row = {"island": island,
           "dated_in_cell_with_building_pct": round(100 * share(dated, coy > 0), 1),
           "undated_in_cell_with_building_pct": round(100 * share(undated, coy > 0), 1),
           "undated_in_cell_built_le2016_pct": round(100 * share(undated, (coy > 0) & (coy <= 2016)), 1)}
    print(f"  {island:14s} Tracker 2016 pixels in a 100 m cell that has ANY cadastral building: "
          f"dated {row['dated_in_cell_with_building_pct']:5.1f} % | undated {row['undated_in_cell_with_building_pct']:5.1f} %")
    return row


def bufa_series(islands: list[str]) -> pd.DataFrame:
    """Cadastral building footprint area per island per epoch (km2) - a surface series."""
    isl = zones.islands()
    rows = []
    with rasterio.open(str(BUFA).format(year=2020)) as ref:
        masks = zone_masks(isl, ref.transform, (ref.height, ref.width), ref.crs)
    for year in range(1975, 2021, 5):
        with rasterio.open(str(BUFA).format(year=year)) as s:
            a = s.read(1).astype("float64")
            a[a < 0] = 0
        for name, mk in masks.items():
            rows.append({"island": name, "year": year, "cadastre_footprint_km2": round(float(a[mk].sum()) / 1e6, 3)})
    df = pd.DataFrame(rows)
    piv = df.pivot(index="island", columns="year", values="cadastre_footprint_km2")
    print("\n  cadastral building footprint, km2 (surviving buildings, by construction year):")
    print(piv.round(2).to_string())
    tot = df.groupby("year")["cadastre_footprint_km2"].sum()
    print(f"\n  archipelago: 1975 {tot[1975]:.1f} -> 1990 {tot[1990]:.1f} -> 2015 {tot[2015]:.1f} -> 2020 {tot[2020]:.1f} km2 "
          f"| growth 1990->2015 {100 * (tot[2015] / tot[1990] - 1):+.0f} %  (GHSL surface: +42 %, WSF Evo extent: +36 %)")
    return df


def main(tracker_islands: list[str]):
    print("Q1/Q2 - WSF Evolution against the cadastre (30 m grid, cadastre cells 100 m):")
    rows = [wsf_vs_cadastre(i) for i in ISLAND_BBOX]
    df = pd.DataFrame(rows)
    OUT_WSF.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_WSF, index=False)

    print("\nQ3 - WSF Tracker's 2016 classes against the cadastre:")
    trows = [tracker_undated_vs_cadastre(i) for i in tracker_islands]
    pd.DataFrame(trows).to_csv(FIGURES / "data" / "m0_cadastre_vs_tracker.csv", index=False)

    print("\nBonus - cadastral surface series:")
    bufa_series(list(ISLAND_BBOX)).to_csv(OUT_BUFA, index=False)
    print(f"\nwrote {OUT_WSF}, {OUT_BUFA}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tracker-islands", default="Gran Canaria,Tenerife,Fuerteventura")
    main([s.strip() for s in ap.parse_args().tracker_islands.split(",") if s.strip()])
