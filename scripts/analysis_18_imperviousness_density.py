"""M0/M1 analysis 18 — Copernicus Imperviousness Density 2024 (10 m, % sealed).

Density measures ALL sealed surface - buildings, roads, car parks, paved yards - as a
percentage per pixel. That may be the closest match in the whole stack to decision 2's
definition of urban ("buildings + roads + paved areas"), which makes it a candidate to
drive the density layer (M1.4) and possibly to reframe what we call "built".

Tests:
  1. Sealed surface per island (sum of percentages x pixel area) vs GHSL built surface
     and the cadastral footprint - all three are SURFACE measures and should be
     orderable: cadastre (buildings) < GHSL (built surface) <= Copernicus (all sealing).
  2. Thresholded extent (>= 30 %, >= 50 % sealed) vs the extent products.
  3. Greenhouses: does Density flag them like Impervious Built-Up (9.5 %) or like the
     Sentinel-1 products (67-72 %)?
  4. Cadastre cell test.
  5. What the confidence layer says, and where it is low.

Outputs: docs/figures/data/m0_imd_2024.csv
    python scripts/analysis_18_imperviousness_density.py
"""
from __future__ import annotations
import glob, warnings
import geopandas as gpd, numpy as np, pandas as pd, rasterio
from rasterio.features import geometry_mask, rasterize
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject
warnings.filterwarnings("ignore")
from sensisat import zones
from sensisat.config import FIGURES, ISLAND_BBOX, RAW
from sensisat.datasets import ghsl, wsf, wsf_tracker as wt
from sensisat.evaluate import MINCOY
from sensisat.raster import area_km2, resample_to
from sensisat.stats import zone_masks

PX_KM2 = 0.01 * 0.01   # 10 m LAEA pixel

def mosaic(pattern):
    tifs = sorted((RAW / "hrl").rglob(pattern))
    if not tifs: raise FileNotFoundError(pattern)
    srcs = [rasterio.open(t) for t in tifs]
    arr, tr = merge(srcs, nodata=255); crs = srcs[0].crs
    for s in srcs: s.close()
    return arr[0], tr, crs

def main():
    imd, tr, crs = mosaic("*IMD_S2024_R10m*.tif")
    cl, tcl, ccl = mosaic("*IMDCL_S2024_R10m*.tif")
    valid = imd <= 100
    print(f"IMD 2024: {imd.shape} · valid pixels {valid.sum():,} · sealed>0 {(valid & (imd > 0)).sum():,}")
    print(f"confidence: min {cl[cl <= 100].min()} max {cl[cl <= 100].max()} mean {cl[cl <= 100].mean():.1f}")

    isl = zones.islands().to_crs(crs)
    rows = []
    print(f"\n{'island':14s} {'sealed km2':>10s} {'>=30% km2':>10s} {'>=50% km2':>10s} | {'GHSL surf':>9s} {'cadastre':>8s} | {'mean conf':>9s} {'low-conf %':>10s}")
    for _, r in isl.iterrows():
        m = ~geometry_mask([r.geometry], out_shape=imd.shape, transform=tr, invert=False) & valid
        sealed = float(imd[m].sum()) / 100 * PX_KM2          # sum of fractions x pixel area
        e30 = (m & (imd >= 30)).sum() * PX_KM2
        e50 = (m & (imd >= 50)).sum() * PX_KM2
        conf = cl[m & (cl <= 100)]
        rows.append({"island": r["name"], "sealed_km2": round(sealed, 2), "extent_ge30_km2": round(e30, 2),
                     "extent_ge50_km2": round(e50, 2), "mean_confidence": round(float(conf.mean()), 1) if conf.size else np.nan,
                     "low_confidence_pct": round(100 * float((conf < 80).mean()), 1) if conf.size else np.nan})
        print(f"{r['name']:14s} {sealed:10.2f} {e30:10.2f} {e50:10.2f} | {'':9s} {'':8s} | "
              f"{rows[-1]['mean_confidence']:9.1f} {rows[-1]['low_confidence_pct']:9.1f}%")
    df = pd.DataFrame(rows)
    print(f"{'archipelago':14s} {df.sealed_km2.sum():10.2f} {df.extent_ge30_km2.sum():10.2f} {df.extent_ge50_km2.sum():10.2f}")
    print(f"\ncompare (archipelago): GHSL built surface 2020 152.9 · cadastre footprint 2020 100.3 · "
          f"Copernicus Built-Up 2024 259.3 (extent) · CORINE artificial 469.5")

    # ---- Gran Canaria detail: greenhouses, cadastre, cross-product ----
    gc = ISLAND_BBOX["Gran Canaria"]; z = zones.islands(); zg = z[z.name == "Gran Canaria"]
    trk, tt, tc = wt.load(gc); mt = zone_masks(zg, tt, trk.shape, tc)["Gran Canaria"]
    imd_t = np.zeros(trk.shape, "float32")
    reproject(np.where(valid, imd, 0).astype("float32"), imd_t, src_transform=tr, src_crs=crs,
              dst_transform=tt, dst_crs=tc, resampling=Resampling.average, src_nodata=None, dst_nodata=None)
    crops = gpd.read_file(glob.glob(str(RAW / "mapa_cultivos" / "gc" / "**" / "*.shp"), recursive=True)[0])
    gh = rasterize(((g, 1) for g in crops[crops["TECNICA_NA"] == "Invernadero"].to_crs(tc).geometry),
                   out_shape=trk.shape, transform=tt, fill=0, dtype="uint8").astype(bool) & mt
    gh_area = area_km2(gh, tt)
    print(f"\nGreenhouse parcels, Gran Canaria ({gh_area:.1f} km2):")
    print(f"  mean sealing inside them: {imd_t[gh].mean():.1f} %  | share of parcel area with IMD >= 30 %: "
          f"{100 * area_km2(gh & (imd_t >= 30), tt) / gh_area:.1f} %  | >= 50 %: {100 * area_km2(gh & (imd_t >= 50), tt) / gh_area:.1f} %")
    print(f"  for comparison: Impervious Built-Up 2021 flagged 9.5 %, WSF Tracker 71.5 %, WSF 2019 67.3 %")
    # cadastre cell test at >= 30 %
    with rasterio.open(MINCOY) as s: coy, ct, cc = s.read(1), s.transform, s.crs
    frac = np.zeros(coy.shape, "float32")
    reproject((np.where(valid, imd, 0) >= 30).astype("float32"), frac, src_transform=tr, src_crs=crs,
              dst_transform=ct, dst_crs=cc, resampling=Resampling.average, src_nodata=None, dst_nodata=None)
    mcad = zone_masks(zones.islands(), ct, coy.shape, cc)
    print(f"\nCadastre cell test, IMD 2024 >= 30 % (cells with a building <= 2020):")
    for name in ("Gran Canaria", "Tenerife", "La Gomera", "Fuerteventura"):
        m = mcad[name]; cells = m & (coy > 0) & (coy <= 2020); n = cells.sum(); flagged = m & (frac > 0)
        print(f"  {name:14s} recall {100 * (cells & (frac > 0)).sum() / n:5.1f} % | precision {100 * (flagged & (coy > 0)).sum() / max(flagged.sum(), 1):5.1f} %")
    df.to_csv(FIGURES / "data" / "m0_imd_2024.csv", index=False)
    print(f"\nwrote {FIGURES / 'data' / 'm0_imd_2024.csv'}")

if __name__ == "__main__":
    main()
