"""M0 analysis 3 — the seam, per island, with the greenhouse mask applied.

For the 2015/2016 join we need, per island: the resolution factor (same producer,
same year, 30 m vs 10 m), the definition factor (same resolution, 18 months apart)
before and after masking greenhouse parcels out of Tracker, and how well the two
eras agree SPATIALLY once both are put on one 100 m grid.

A note on the fraction grid, correcting an earlier claim in the plan: averaging a
binary mask to 100 m fractions preserves total area, so it does NOT remove the
extent inflation of coarse pixels. What it gives is a common support on which two
products can be compared cell by cell. Only surface products (GHSL, HRL, cadastre)
are free of the pixel-size effect.

Outputs
  docs/figures/data/m0_seam_factors.csv
    python scripts/analysis_03_seam_factors.py
"""
from __future__ import annotations
import glob, warnings, zipfile
import geopandas as gpd, numpy as np, pandas as pd, rasterio
from rasterio.features import rasterize
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject
warnings.filterwarnings("ignore")
from sensisat import zones
from sensisat.config import FIGURES, ISLAND_BBOX, RAW
from sensisat.datasets import ghsl, wsf, wsf_tracker as wt
from sensisat.raster import area_km2, resample_to
from sensisat.stats import zone_masks
CODE = {"Gran Canaria":"gc","Tenerife":"tf","Fuerteventura":"fv","Lanzarote":"lz","La Palma":"lp"}

def greenhouse_mask(island, shape, transform, crs):
    d = RAW/"mapa_cultivos"; code = CODE[island]
    z = d/f"{code}_shp.zip"
    if not z.exists():
        from sensisat.download import fetch
        fetch(f"https://opendata.sitcan.es/upload/medio-rural/gobcan_mapa-cultivos_{code}_shp.zip", z, quiet=True)
    out = d/code
    if not out.exists():
        with zipfile.ZipFile(z) as zf: zf.extractall(out)
    g = gpd.read_file(glob.glob(str(out/"**"/"*.shp"), recursive=True)[0])
    g = g[g["TECNICA_NA"] == "Invernadero"].to_crs(crs)
    if g.empty: return np.zeros(shape, bool)
    return rasterize(((geom,1) for geom in g.geometry), out_shape=shape, transform=transform, fill=0, dtype="uint8").astype(bool)

def to_fraction(mask, tr, crs, ref_tr, ref_shape, ref_crs):
    """Share of each coarse cell covered by True pixels (area-preserving average)."""
    dst = np.zeros(ref_shape, "float32")
    reproject(mask.astype("float32"), dst, src_transform=tr, src_crs=crs, dst_transform=ref_tr, dst_crs=ref_crs,
              resampling=Resampling.average, src_nodata=None, dst_nodata=None)
    return dst

rows=[]
isl = zones.islands()
for island in CODE:
    bbox = ISLAND_BBOX[island]; z = isl[isl.name==island]
    evo, te, ec = wsf.load("wsf_evolution", bbox)
    w15, t15, c15 = wsf.built_mask("wsf2015", bbox)
    trk, tt, tc = wt.load(bbox)
    # common 100 m grid = GHSL 3-arcsecond grid clipped to the island bbox
    g, tg, cg = ghsl.load(2015, bbox)
    mi = zone_masks(z, te, evo.shape, ec)[island]; m15 = zone_masks(z, t15, w15.shape, c15)[island]; mt = zone_masks(z, tt, trk.shape, tc)[island]
    evo15 = (evo>0)&(evo<=2015)&mi; w15 = w15&m15
    e1 = (trk==1)&mt; gh = greenhouse_mask(island, trk.shape, tt, tc); e1m = e1 & ~gh
    A = dict(evo30=area_km2(evo15,te), wsf15=area_km2(w15,t15), trk_e1=area_km2(e1,tt), trk_e1_nogh=area_km2(e1m,tt))
    # spatial agreement on the common grid
    f_evo = to_fraction(evo15, te, ec, tg, g.shape, cg); f_trk = to_fraction(e1m, tt, tc, tg, g.shape, cg)
    mg = zone_masks(z, tg, g.shape, cg)[island]
    a, b = f_evo[mg], f_trk[mg]
    both = ((a>=0.1)&(b>=0.1)).sum(); either=((a>=0.1)|(b>=0.1)).sum()
    r = float(np.corrcoef(a, b)[0,1]) if a.std()>0 and b.std()>0 else np.nan
    row = dict(island=island, **{k:round(v,2) for k,v in A.items()},
        resolution_factor=round(A["evo30"]/A["wsf15"],2), definition_factor_raw=round(A["trk_e1"]/A["wsf15"],2),
        definition_factor_masked=round(A["trk_e1_nogh"]/A["wsf15"],2), greenhouse_removed_km2=round(A["trk_e1"]-A["trk_e1_nogh"],2),
        net_evo_to_tracker_masked=round(A["trk_e1_nogh"]/A["evo30"],2),
        cell_jaccard_100m=round(both/either,3) if either else np.nan, cell_corr_100m=round(r,3))
    rows.append(row)
    print(f"{island:14s} Evo30 {A['evo30']:6.1f} | WSF15 {A['wsf15']:6.1f} | Trk-e1 {A['trk_e1']:6.1f} -> masked {A['trk_e1_nogh']:6.1f} "
          f"| res x{row['resolution_factor']} def x{row['definition_factor_raw']}->x{row['definition_factor_masked']} "
          f"| Evo->Trk(masked) x{row['net_evo_to_tracker_masked']} | 100 m Jaccard {row['cell_jaccard_100m']} r {row['cell_corr_100m']}")
df = pd.DataFrame(rows); df.to_csv(FIGURES/"data"/"m0_seam_factors.csv", index=False); print("wrote m0_seam_factors.csv")
