"""M0 analysis 12 — how much of the 'pre-2016, undated' class is covered agriculture?

Analysis 11 ruled out roads; the map in docs/figures/undated_pixels_gran_canaria.png
showed greenhouses and covered banana plantations. This quantifies it with the
Gobierno de Canarias Mapa de Cultivos (1:2 000, field survey 2023-24), whose
TECNICA_NA field marks 'Invernadero' (greenhouse) parcels and whose CULTIVO_NA marks
'Platanera' (banana, often under mesh in the north).

For each class of Tracker's July-2016 footprint - DATED (has a WSF Evolution year)
and UNDATED (has none) - we report the share of its area inside:
  greenhouse parcels · banana parcels · any agricultural parcel (cultivated, fallow
  or abandoned) · none of the above.
The dated class is the control: settlements should sit mostly outside parcels.

Caveat: the crop map is 2023-24 and Tracker's baseline is 2016; parcels change.
Treated as a first quantification, not a final number.

Outputs
  docs/figures/data/m0_undated_vs_crops.csv

    python scripts/analysis_12_undated_vs_crops.py [--island "Gran Canaria"]
"""

from __future__ import annotations

import argparse
import glob
import warnings
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.features import rasterize

warnings.filterwarnings("ignore")

from sensisat import zones  # noqa: E402
from sensisat.config import FIGURES, ISLAND_BBOX, RAW  # noqa: E402
from sensisat.datasets import wsf, wsf_tracker as wt  # noqa: E402
from sensisat.download import fetch  # noqa: E402
from sensisat.raster import area_km2, resample_to  # noqa: E402
from sensisat.stats import zone_masks  # noqa: E402

OUT_CSV = FIGURES / "data" / "m0_undated_vs_crops.csv"
CROPS_URL = "https://opendata.sitcan.es/upload/medio-rural/gobcan_mapa-cultivos_{code}_shp.zip"
ISLAND_CODE = {"El Hierro": "eh", "La Palma": "lp", "La Gomera": "lg", "Tenerife": "tf",
               "Gran Canaria": "gc", "Fuerteventura": "fv", "Lanzarote": "lz"}


def crop_map(island: str) -> gpd.GeoDataFrame:
    code = ISLAND_CODE[island]
    d = RAW / "mapa_cultivos"
    z = fetch(CROPS_URL.format(code=code), d / f"{code}_shp.zip", quiet=True).path
    out = d / code
    if not out.exists():
        with zipfile.ZipFile(z) as zf:
            zf.extractall(out)
    shp = glob.glob(str(out / "**" / "*.shp"), recursive=True)[0]
    return gpd.read_file(shp)


def burn(gdf: gpd.GeoDataFrame, shape, transform, crs) -> np.ndarray:
    if gdf.empty:
        return np.zeros(shape, dtype=bool)
    geoms = gdf.to_crs(crs).geometry.values
    return rasterize(((g, 1) for g in geoms), out_shape=shape, transform=transform, fill=0, dtype="uint8").astype(bool)


def run(island: str) -> pd.DataFrame:
    bbox = ISLAND_BBOX[island]
    isl = zones.islands()
    z = isl[isl["name"] == island]

    trk, tt, tc = wt.load(bbox)
    evo, te, ec = wsf.load("wsf_evolution", bbox)
    evo10 = resample_to(evo, te, ec, tt, trk.shape, tc)
    m = zone_masks(z, tt, trk.shape, tc)[island]
    baseline = (trk == 1) & m
    classes = {"dated (has Evo year)": baseline & (evo10 > 0), "undated (no Evo year)": baseline & (evo10 == 0)}

    crops = crop_map(island)
    print(f"{island}: {len(crops):,} parcels; CATEGORIA values: {crops['CATEGORIA'].value_counts().to_dict()}")
    greenhouse = burn(crops[crops["TECNICA_NA"] == "Invernadero"], trk.shape, tt, tc)
    banana = burn(crops[crops["CULTIVO_NA"] == "Platanera"], trk.shape, tt, tc)
    any_parcel = burn(crops, trk.shape, tt, tc)
    print(f"  greenhouse parcels {area_km2(greenhouse & m, tt):.2f} km2 · banana {area_km2(banana & m, tt):.2f} km2 · "
          f"any parcel {area_km2(any_parcel & m, tt):.2f} km2 of {area_km2(m, tt):.0f} km2 island")

    rows = []
    print(f"\n  {'class':24s} {'km2':>7s} {'greenhouse':>11s} {'banana':>8s} {'any parcel':>11s} {'outside parcels':>16s}")
    for name, mask in classes.items():
        a = area_km2(mask, tt)
        g = area_km2(mask & greenhouse, tt) / a
        b = area_km2(mask & banana & ~greenhouse, tt) / a
        p = area_km2(mask & any_parcel, tt) / a
        rows.append({"island": island, "class": name, "km2": round(a, 2),
                     "in_greenhouse_pct": round(100 * g, 1), "in_banana_pct": round(100 * b, 1),
                     "in_any_parcel_pct": round(100 * p, 1), "outside_parcels_pct": round(100 * (1 - p), 1)})
        print(f"  {name:24s} {a:7.2f} {100 * g:10.1f}% {100 * b:7.1f}% {100 * p:10.1f}% {100 * (1 - p):15.1f}%")

    # What crops sit under the undated pixels that are inside parcels but not greenhouses?
    und = classes["undated (no Evo year)"] & any_parcel & ~greenhouse
    if und.any():
        crops_r = crops.to_crs(tc)
        top = []
        for cult, grp in crops_r.groupby("CULTIVO_NA"):
            if len(grp) < 30:
                continue
            mm = burn(grp, trk.shape, tt, tc)
            top.append((cult, area_km2(und & mm, tt)))
        top.sort(key=lambda t: -t[1])
        print("\n  undated area inside non-greenhouse parcels, by crop (km2):")
        for c, a in top[:8]:
            print(f"    {c:44s} {a:6.2f}")

    df = pd.DataFrame(rows)
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
    run(ap.parse_args().island)
