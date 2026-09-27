"""M0 analysis 2 — lava fields: one negative control, one loss test case.

Two polygons, testing OPPOSITE things. Conflating them produces a wrong verdict,
so the distinction is enforced in code by the `expectation` field.

  Timanfaya National Park (Lanzarote) — NEGATIVE CONTROL.
      52 km2 of 1730-1736 and 1824 lava with no settlement. Dark bare rock is the
      documented confuser for built-up in optical classifiers, so anything a
      product reports here is commission error. It does contain the LZ-67 road,
      the El Diablo restaurant and visitor facilities, which are subtracted first.
      Expectation: ~0 %.

  Tajogaite / Cumbre Vieja 2021 lava field (La Palma) — LOSS TEST CASE, NOT a
      negative control. This lava buried the town of Todoque and part of La
      Laguna in Sep-Dec 2021 (1,676 buildings per Catastro). Every dataset
      evaluated here predates the eruption, so built-up land inside this polygon
      is CORRECT, and measures what was destroyed. The polygon only becomes a
      test once a product covers 2022+: those pixels must switch from built to
      not-built. Expectation: >0 before 2022, and a drop to ~0 after.

Outputs
  docs/figures/data/m0_negative_controls.csv

    python scripts/analysis_02_negative_controls.py
"""

from __future__ import annotations

import warnings

import geopandas as gpd
import pandas as pd
from shapely.ops import unary_union

warnings.filterwarnings("ignore")

from sensisat import zones  # noqa: E402
from sensisat.config import FIGURES  # noqa: E402
from sensisat.datasets import ghsl, wsf  # noqa: E402
from sensisat.stats import zonal  # noqa: E402

OUT_CSV = FIGURES / "data" / "m0_negative_controls.csv"

# Nominatim queries for the controls, with the OSM feature type to disambiguate.
# Verified 2026-09-19: "Timanfaya" alone also matches a hotel and a bus stop, and
# "Tajogaite" matches the volcano summit node before the lava field, so the type
# filter is doing real work. Adding ", Lanzarote, Spain" makes the search FAIL.
#   Timanfaya NP        -> OSM relation 1157737  (boundary=national_park)
#   Tajogaite lava 2021 -> OSM relation 13249829 (natural=bare_rock,
#                          "Lava de la erupcion volcanica de Tajogaite de 2021")
CONTROLS = {
    # name: (query, osm type, role, expectation for a PRE-2022 dataset)
    "Timanfaya NP": ("Parque Nacional de Timanfaya", "national_park",
                     "negative control", "near_zero"),
    "Tajogaite lava 2021": ("Tajogaite", "bare_rock",
                            "loss test case", "positive_before_2022"),
}


def verdict(role: str, share_pct: float, year: int) -> str:
    """Whether a measurement is good news, bad news, or not yet testable."""
    if role == "negative control":
        if share_pct < 1:
            return "PASS (clean)"
        return "SUSPECT" if share_pct < 5 else "FAIL (commission error)"
    # loss test case
    if year < 2022:
        return "baseline (built-up here is correct; this is what the lava buried)"
    return "PASS (loss detected)" if share_pct < 1 else "FAIL (still shows built after burial)"


def control_polygons() -> dict[str, gpd.GeoDataFrame]:
    out = {}
    for name, (query, want, role, _) in CONTROLS.items():
        key = name.lower().replace(" ", "_")
        try:
            gdf = zones.nominatim_polygon(query, key=key, want=want).assign(name=name)
            out[name] = gdf
            area = gdf.to_crs("EPSG:32628").area.sum() / 1e6
            print(f"  {name} [{role}]: {area:.1f} km2  "
                  f"{str(gdf['display_name'].iloc[0])[:55]}")
        except Exception as exc:
            print(f"  ! {name}: unavailable ({type(exc).__name__}: {exc})")
    return out


def carve_infrastructure(name: str, gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, float]:
    """Subtract buffered OSM roads/buildings; returns (control, km2 removed)."""
    poly = unary_union(gdf.geometry.values)
    key = name.lower().replace(" ", "_") + "_infra"
    try:
        infra = zones.infrastructure_in(poly, key=key, buffer_m=30.0)
    except Exception as exc:
        print(f"    ! infrastructure lookup failed ({type(exc).__name__}); using raw polygon")
        return gdf.assign(name=name), 0.0
    control = zones.negative_control(gdf, infra, name)
    before = gpd.GeoSeries([poly], crs="EPSG:4326").to_crs("EPSG:32628").area.sum() / 1e6
    after = control.to_crs("EPSG:32628").area.sum() / 1e6
    return control, before - after


def measure(control: gpd.GeoDataFrame, bbox) -> list[dict]:
    rows = []
    for product, year, res in (("wsf_evolution", 2015, 30), ("wsf2015", 2015, 10), ("wsf2019", 2019, 10)):
        try:
            mask, transform, crs = wsf.built_mask(product, bbox)
            df = zonal(mask, transform, crs, control, kind="binary", label="built")
            rows.append({"dataset": f"WSF {'Evolution' if product == 'wsf_evolution' else year}",
                         "measure": "extent", "resolution_m": res, "year": year,
                         "built_km2": float(df["built_km2"].iloc[0]),
                         "control_km2": float(df["zone_km2"].iloc[0]),
                         "share_pct": float(df["share_pct"].iloc[0])})
        except Exception as exc:
            print(f"    ! {product}: {type(exc).__name__}: {exc}")
    for epoch in (2015, 2020):
        try:
            arr, transform, crs = ghsl.load(epoch, bbox)
            df = zonal(arr, transform, crs, control, kind="amount", label="built")
            rows.append({"dataset": "GHSL built surface", "measure": "surface", "resolution_m": 92,
                         "year": epoch, "built_km2": float(df["built_km2"].iloc[0]),
                         "control_km2": float(df["zone_km2"].iloc[0]),
                         "share_pct": float(df["share_pct"].iloc[0])})
        except Exception as exc:
            print(f"    ! GHSL {epoch}: {type(exc).__name__}: {exc}")
    return rows


def run() -> pd.DataFrame:
    print("Negative control polygons:")
    polys = control_polygons()

    rows = []
    for name, gdf in polys.items():
        print(f"\n=== {name} ===")
        control, removed = carve_infrastructure(name, gdf)
        area = control.to_crs("EPSG:32628").area.sum() / 1e6
        print(f"  control area after removing infrastructure: {area:.2f} km2 (removed {removed:.2f})")
        minx, miny, maxx, maxy = control.total_bounds
        pad = 0.02
        bbox = (minx - pad, miny - pad, maxx + pad, maxy + pad)
        role = CONTROLS[name][2]
        for r in measure(control, bbox):
            r.update({"control": name, "role": role, "control_km2": round(area, 2),
                      "infra_removed_km2": round(removed, 2)})
            r["verdict"] = verdict(role, r["share_pct"], r["year"])
            rows.append(r)
            print(f"  {r['dataset']:20s} {r['year']}  {r['built_km2']:7.3f} km2  "
                  f"{r['share_pct']:5.2f} % -> {r['verdict']}")

    df = pd.DataFrame(rows)
    if len(df):
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT_CSV, index=False)
        print(f"\nwrote {OUT_CSV} ({len(df)} rows)")
    return df


if __name__ == "__main__":
    run()
