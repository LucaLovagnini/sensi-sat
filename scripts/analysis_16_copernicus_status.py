"""M0 analysis 16 — Copernicus Impervious Built-Up status layers 2018 / 2021 / 2024.

The status layers (built-up yes/no per year, 10 m, EPSG:3035) and the 2021-2024 change
layer arrived on 2026-09-19. They enable the tests nothing else could:
  1. THE LOSS TEST: Todoque and the Tajogaite lava (eruption Sep-Dec 2021). Built-up
     inside the lava polygon in 2021 vs 2024, and 'loss of cover' in the change layer.
  2. Real loss rate for a second period, 2021-2024, per island.
  3. An independent 10 m footprint from a third producer at the seam years.
  4. Does Copernicus count greenhouses? (overlap with crop-map parcels, Gran Canaria)
  5. Does Copernicus see dispersed buildings? (cadastre cell test, 2018)

Outputs: docs/figures/data/m0_copernicus_status.csv, m0_copernicus_loss_2021_2024.csv
    python scripts/analysis_16_copernicus_status.py
"""
from __future__ import annotations
import glob, warnings, zipfile
import geopandas as gpd, numpy as np, pandas as pd, rasterio
from rasterio.features import geometry_mask, rasterize
from rasterio.merge import merge
from rasterio.warp import Resampling, reproject
warnings.filterwarnings("ignore")
from sensisat import zones
from sensisat.config import FIGURES, ISLAND_BBOX, RAW
from sensisat.datasets import wsf, wsf_tracker as wt
from sensisat.evaluate import MINCOY
from sensisat.raster import area_km2, resample_to
from sensisat.stats import zone_masks

ROOT = RAW / "hrl" / "110252"
PX_KM2_10 = 0.01 * 0.01   # 10 m LAEA pixel = 100 m2
PX_KM2_20 = 0.02 * 0.02

def mosaic(pattern, nodata):
    tifs = sorted(ROOT.rglob(pattern))
    srcs = [rasterio.open(t) for t in tifs]
    arr, tr = merge(srcs, nodata=nodata); crs = srcs[0].crs
    for s in srcs: s.close()
    return arr[0], tr, crs

def main():
    ibu18, t18, c18 = mosaic("IBU_2018_010m_eu_03035_v011.tif", 240)
    ibu21, t21, c21 = mosaic("*IBU_S2021_R10m*.tif", 255)
    ibu24, t24, c24 = mosaic("*IBU_S2024_R10m*.tif", 255)
    chg, tch, cch = mosaic("*IBUC_C2021-2024_R20m*.tif", 255)
    for name, a in (("IBU 2018", ibu18), ("IBU 2021", ibu21), ("IBU 2024", ibu24), ("change 21-24", chg)):
        v, c = np.unique(a, return_counts=True); print(f"{name:13s} values: {dict(zip(v.tolist(), c.tolist()))}")
    b18, b21, b24 = ibu18 == 1, ibu21 == 1, ibu24 == 1
    # 2018 comes on its own grid (clipped EU file); put it on the 2021 grid
    if ibu18.shape != ibu21.shape or t18 != t21:
        b18 = resample_to(b18.astype("uint8"), t18, c18, t21, ibu21.shape, c21).astype(bool)

    isl = zones.islands().to_crs(c21)
    rows, lrows = [], []
    print(f"\n{'island':14s} {'IBU 2018':>9s} {'IBU 2021':>9s} {'IBU 2024':>9s} | {'21->24 new':>10s} {'21->24 LOSS':>11s} {'loss %/yr':>9s}")
    for _, r in isl.iterrows():
        m = ~geometry_mask([r.geometry], out_shape=ibu21.shape, transform=t21, invert=False)
        a18, a21, a24 = (m & b18).sum() * PX_KM2_10, (m & b21).sum() * PX_KM2_10, (m & b24).sum() * PX_KM2_10
        mc = ~geometry_mask([r.geometry], out_shape=chg.shape, transform=tch, invert=False)
        new, lost = (mc & (chg == 1)).sum() * PX_KM2_20, (mc & (chg == 2)).sum() * PX_KM2_20
        rows.append({"island": r["name"], "ibu_2018_km2": round(a18, 2), "ibu_2021_km2": round(a21, 2), "ibu_2024_km2": round(a24, 2)})
        lrows.append({"island": r["name"], "built_2021_km2": round(a21, 2), "new_2021_2024_km2": round(new, 3), "lost_2021_2024_km2": round(lost, 3),
                      "loss_pct_per_year": round(100 * lost / a21 / 3, 3) if a21 else np.nan})
        print(f"{r['name']:14s} {a18:9.2f} {a21:9.2f} {a24:9.2f} | {new:10.3f} {lost:11.3f} {100 * lost / a21 / 3 if a21 else 0:8.3f}%")
    tot = pd.DataFrame(lrows).sum(numeric_only=True)
    print(f"{'archipelago':14s} {sum(x['ibu_2018_km2'] for x in rows):9.2f} {tot['built_2021_km2']:9.2f} {sum(x['ibu_2024_km2'] for x in rows):9.2f} | "
          f"{tot['new_2021_2024_km2']:10.3f} {tot['lost_2021_2024_km2']:11.3f} {100 * tot['lost_2021_2024_km2'] / tot['built_2021_km2'] / 3:8.3f}%")

    # ---- 1. THE LOSS TEST: Tajogaite lava, La Palma -------------------------------
    lava = zones.nominatim_polygon("Tajogaite", key="tajogaite_lava_2021", want="bare_rock").to_crs(c21)
    ml = ~geometry_mask([lava.geometry.iloc[0]], out_shape=ibu21.shape, transform=t21, invert=False)
    mlc = ~geometry_mask([lava.geometry.iloc[0]], out_shape=chg.shape, transform=tch, invert=False)
    l18, l21, l24 = (ml & b18).sum() * PX_KM2_10, (ml & b21).sum() * PX_KM2_10, (ml & b24).sum() * PX_KM2_10
    lost_lava = (mlc & (chg == 2)).sum() * PX_KM2_20
    print(f"\nTAJOGAITE LAVA (eruption 2021-09-19 → 2021-12-13), built-up inside the flow:")
    print(f"  Copernicus IBU 2018: {l18:.3f} km2 | IBU 2021: {l21:.3f} km2 | IBU 2024: {l24:.3f} km2 | change layer 'loss of cover' 2021→2024: {lost_lava:.3f} km2")
    print(f"  -> {100 * (1 - l24 / l21) if l21 else 0:.0f} % of the 2021 built-up inside the lava is GONE in 2024. "
          f"(WSF Evolution, WSF 2015/2019, Tracker and GHSL all still show it - growth-only by construction.)")

    # ---- 3. independent footprint vs WSF / Tracker at the seam years (Gran Canaria) ----
    gc = ISLAND_BBOX["Gran Canaria"]; z = zones.islands(); zg = z[z.name == "Gran Canaria"]
    trk, tt, tc = wt.load(gc); mt = zone_masks(zg, tt, trk.shape, tc)["Gran Canaria"]
    ibu21_t = resample_to(b21.astype("uint8"), t21, c21, tt, trk.shape, tc).astype(bool) & mt
    ibu18_t = resample_to(b18.astype("uint8"), t21, c21, tt, trk.shape, tc).astype(bool) & mt
    trk21 = (trk > 0) & (trk <= 11) & mt   # built by 2021-07
    w19, tw, cw = wsf.built_mask("wsf2019", gc); w19t = resample_to(w19.astype("uint8"), tw, cw, tt, trk.shape, tc).astype(bool) & mt
    def iou(a, b): u = (a | b).sum(); return (a & b).sum() / u if u else np.nan
    print(f"\nGran Canaria, 10 m footprints on Tracker's grid:")
    print(f"  Copernicus IBU 2018 {area_km2(ibu18_t, tt):6.2f} km2 | WSF 2019 {area_km2(w19t, tt):6.2f} | Copernicus IBU 2021 {area_km2(ibu21_t, tt):6.2f} | Tracker by 2021-07 {area_km2(trk21, tt):6.2f}")
    print(f"  IoU  IBU2018 vs WSF2019 {iou(ibu18_t, w19t):.2f} | IBU2021 vs Tracker-2021 {iou(ibu21_t, trk21):.2f} | WSF2019 vs Tracker-2021 {iou(w19t, trk21):.2f}")
    print(f"  Tracker-2021 pixels NOT in Copernicus 2021: {area_km2(trk21 & ~ibu21_t, tt):.2f} km2 | Copernicus-2021 NOT in Tracker: {area_km2(ibu21_t & ~trk21, tt):.2f} km2")

    # ---- 4. greenhouses in Copernicus? -----------------------------------------------
    crops = gpd.read_file(glob.glob(str(RAW / "mapa_cultivos" / "gc" / "**" / "*.shp"), recursive=True)[0])
    gh = rasterize(((g, 1) for g in crops[crops["TECNICA_NA"] == "Invernadero"].to_crs(tc).geometry), out_shape=trk.shape, transform=tt, fill=0, dtype="uint8").astype(bool)
    print(f"\nGreenhouse parcels, Gran Canaria ({area_km2(gh & mt, tt):.1f} km2): share flagged built-up by")
    print(f"  Copernicus IBU 2021 {100 * area_km2(ibu21_t & gh, tt) / area_km2(gh & mt, tt):5.1f} % | Tracker by 2021 {100 * area_km2(trk21 & gh, tt) / area_km2(gh & mt, tt):5.1f} % | WSF 2019 {100 * area_km2(w19t & gh, tt) / area_km2(gh & mt, tt):5.1f} %")

    # ---- 5. does Copernicus see dispersed buildings? cadastre cell test, 2018 ----------
    with rasterio.open(MINCOY) as s: coy, ct, cc = s.read(1), s.transform, s.crs
    mcad = zone_masks(zones.islands(), ct, coy.shape, cc)
    frac = np.zeros(coy.shape, "float32"); reproject(b18.astype("float32"), frac, src_transform=t21, src_crs=c21, dst_transform=ct, dst_crs=cc, resampling=Resampling.average, src_nodata=None, dst_nodata=None)
    print(f"\nCadastre cell test, Copernicus IBU 2018 (cells with a building <= 2018):")
    for name in ("Gran Canaria", "Tenerife", "La Gomera", "Fuerteventura"):
        m = mcad[name]; cells = m & (coy > 0) & (coy <= 2018); n = cells.sum(); flagged = m & (frac > 0)
        print(f"  {name:14s} recall {100 * (cells & (frac > 0)).sum() / n:5.1f} % | precision (flagged cells with any building) {100 * (flagged & (coy > 0)).sum() / max(flagged.sum(), 1):5.1f} %")
    pd.DataFrame(rows).to_csv(FIGURES / "data" / "m0_copernicus_status.csv", index=False)
    pd.DataFrame(lrows).to_csv(FIGURES / "data" / "m0_copernicus_loss_2021_2024.csv", index=False)
    pd.DataFrame([{"polygon": "Tajogaite lava 2021", "ibu_2018_km2": round(l18, 3), "ibu_2021_km2": round(l21, 3), "ibu_2024_km2": round(l24, 3), "change_loss_2021_2024_km2": round(lost_lava, 3)}]).to_csv(FIGURES / "data" / "m0_copernicus_tajogaite.csv", index=False)

if __name__ == "__main__":
    main()
