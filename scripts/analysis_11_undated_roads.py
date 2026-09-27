"""M0 analysis 11 — what is the 'pre-2016, undated' class made of?

43 % of WSF Tracker's July-2016 footprint lies on land WSF Evolution never flagged
(docs/design/seam-harmonization.md, section 2). Tracker's inputs include road
networks and building footprints that Evolution, built from Landsat spectral indices
alone, never used - so the hypothesis is that the undated pixels are mostly roads and
small dispersed structures.

Cheap first test, before spending manual-sampling time on it (decision 15): the share
of undated pixels within a short distance of an OpenStreetMap road, against the same
share for the DATED pixels as a control. If roads explain the class, the two shares
differ strongly.

Outputs
  docs/figures/data/m0_undated_roads.csv

    python scripts/analysis_11_undated_roads.py [--island "Gran Canaria"] [--buffer-m 15]
"""

from __future__ import annotations

import argparse
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from rasterio.features import geometry_mask
from shapely.geometry import LineString
from shapely.ops import unary_union

warnings.filterwarnings("ignore")

from sensisat import zones  # noqa: E402
from sensisat.config import FIGURES, HTTP_HEADERS, ISLAND_BBOX, ZONES  # noqa: E402
from sensisat.datasets import wsf, wsf_tracker as wt  # noqa: E402
from sensisat.raster import area_km2, resample_to  # noqa: E402
from sensisat.stats import zone_masks  # noqa: E402

OUT_CSV = FIGURES / "data" / "m0_undated_roads.csv"
OVERPASS = "https://overpass-api.de/api/interpreter"


def osm_roads(bbox, key: str) -> gpd.GeoDataFrame:
    """Every OSM highway way in bbox as lines (cached under data/zones/)."""
    cache = ZONES / f"{key}.geojson"
    if cache.exists():
        return gpd.read_file(cache)
    minx, miny, maxx, maxy = bbox
    query = f"""
    [out:json][timeout:300];
    way["highway"]({miny},{minx},{maxy},{maxx});
    out geom;
    """
    r = requests.post(OVERPASS, data={"data": query}, headers=HTTP_HEADERS, timeout=400)
    r.raise_for_status()
    rows = []
    for el in r.json().get("elements", []):
        pts = [(p["lon"], p["lat"]) for p in el.get("geometry", [])]
        if len(pts) >= 2:
            rows.append({"highway": el.get("tags", {}).get("highway", ""), "geometry": LineString(pts)})
    gdf = gpd.GeoDataFrame(rows, crs="EPSG:4326")
    gdf.to_file(cache, driver="GeoJSON")
    return gdf


def run(island: str, buffer_m: float) -> pd.DataFrame:
    bbox = ISLAND_BBOX[island]
    isl = zones.islands()
    z = isl[isl["name"] == island]

    trk, tt, tc = wt.load(bbox)
    evo, te, ec = wsf.load("wsf_evolution", bbox)
    evo10 = resample_to(evo, te, ec, tt, trk.shape, tc)
    island_mask = zone_masks(z, tt, trk.shape, tc)[island]

    baseline = (trk == 1) & island_mask
    dated = baseline & (evo10 > 0)
    undated = baseline & (evo10 == 0)

    print(f"{island}: fetching OSM roads …")
    roads = osm_roads(bbox, key=f"osm_roads_{island.replace(' ', '_')}")
    print(f"  {len(roads):,} highway ways")
    # Buffer in a metric CRS (UTM 28N covers the Canaries), rasterise onto the Tracker grid.
    buffered = unary_union(roads.to_crs("EPSG:32628").buffer(buffer_m).values)
    road_mask = ~geometry_mask(
        [gpd.GeoSeries([buffered], crs="EPSG:32628").to_crs(tc).iloc[0]],
        out_shape=trk.shape, transform=tt, invert=False,
    )

    def share(mask):
        a = area_km2(mask, tt)
        return a, (area_km2(mask & road_mask, tt) / a if a else np.nan)

    a_dated, s_dated = share(dated)
    a_undated, s_undated = share(undated)
    a_all, s_all = share(island_mask)

    # Which road classes sit under the undated pixels? (rough: buffer per class, count hits)
    by_class = []
    for cls, grp in roads.to_crs("EPSG:32628").groupby("highway"):
        if len(grp) < 20:
            continue
        buf = unary_union(grp.buffer(buffer_m).values)
        m = ~geometry_mask([gpd.GeoSeries([buf], crs="EPSG:32628").to_crs(tc).iloc[0]],
                           out_shape=trk.shape, transform=tt, invert=False)
        by_class.append((cls, area_km2(undated & m, tt)))
    by_class.sort(key=lambda t: -t[1])

    print(f"\n  buffer {buffer_m:.0f} m around OSM roads")
    print(f"  whole island          {a_all:8.2f} km2   {100 * s_all:5.1f} % within reach of a road  (background)")
    print(f"  DATED   (has Evo year){a_dated:8.2f} km2   {100 * s_dated:5.1f} %   <- control")
    print(f"  UNDATED (no Evo year) {a_undated:8.2f} km2   {100 * s_undated:5.1f} %   <- hypothesis: roads")
    print("\n  undated area near each road class (km2):")
    for cls, a in by_class[:8]:
        print(f"    {cls:16s} {a:6.2f}")

    df = pd.DataFrame([{
        "island": island, "buffer_m": buffer_m,
        "island_km2": round(a_all, 2), "island_share_near_road_pct": round(100 * s_all, 1),
        "dated_km2": round(a_dated, 2), "dated_share_near_road_pct": round(100 * s_dated, 1),
        "undated_km2": round(a_undated, 2), "undated_share_near_road_pct": round(100 * s_undated, 1),
        "top_road_classes": "; ".join(f"{c}={a:.2f}" for c, a in by_class[:5]),
    }])
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    if OUT_CSV.exists():
        old = pd.read_csv(OUT_CSV)
        df = pd.concat([old[old.island != island], df], ignore_index=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nwrote {OUT_CSV}")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--island", default="Gran Canaria")
    ap.add_argument("--buffer-m", type=float, default=15.0)
    a = ap.parse_args()
    run(a.island, a.buffer_m)
