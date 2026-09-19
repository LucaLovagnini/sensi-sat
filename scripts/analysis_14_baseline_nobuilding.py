"""M0 analysis 14 — what is WSF Evolution's 1985 baseline where the cadastre has no building?

25-31 % of WSF Evolution's "built by 1985" area sits in 100 m cells with no cadastral
building at all (analysis 8). Built-up under OUR definition includes roads and paved
infrastructure, which the cadastre does not register, so this is not automatically
error. This classifies that area with OpenStreetMap features and the crop map:
roads (buffered 15 m), airports/ports/industrial/commercial land use, quarries, and
greenhouse parcels. What is left is candidate bare-soil commission for the M3 sample.

Output: docs/figures/data/m0_baseline_nobuilding.csv
    python scripts/analysis_14_baseline_nobuilding.py [--island "Gran Canaria"]
"""
from __future__ import annotations
import argparse, glob, warnings, zipfile
import geopandas as gpd, numpy as np, pandas as pd, rasterio, requests
from rasterio.features import rasterize
from shapely.geometry import LineString, Polygon
warnings.filterwarnings("ignore")
from sensisat import zones
from sensisat.config import FIGURES, HTTP_HEADERS, ISLAND_BBOX, RAW, ZONES
from sensisat.datasets import wsf
from sensisat.raster import area_km2, resample_to
from sensisat.stats import zone_masks
CODE = {"Gran Canaria":"gc","Tenerife":"tf","Fuerteventura":"fv","Lanzarote":"lz","La Palma":"lp"}

def overpass(query, key):
    cache = ZONES/f"{key}.geojson"
    if cache.exists(): return gpd.read_file(cache)
    r = requests.post("https://overpass-api.de/api/interpreter", data={"data": query}, headers=HTTP_HEADERS, timeout=400); r.raise_for_status()
    rows=[]
    for el in r.json().get("elements", []):
        pts=[(p["lon"],p["lat"]) for p in el.get("geometry",[])]; tags=el.get("tags",{})
        if len(pts)>=4 and pts[0]==pts[-1]: rows.append({"kind":tags.get("landuse") or tags.get("aeroway") or tags.get("industrial") or "area","geometry":Polygon(pts)})
        elif len(pts)>=2: rows.append({"kind":tags.get("highway","line"),"geometry":LineString(pts)})
    g = gpd.GeoDataFrame(rows, crs="EPSG:4326"); g.to_file(cache, driver="GeoJSON"); return g

def burn(gdf, shape, tr, crs, buffer_m=0):
    if gdf.empty: return np.zeros(shape, bool)
    g = gdf.to_crs("EPSG:32628")
    geoms = g.buffer(buffer_m).values if buffer_m else g.geometry.values
    geoms = gpd.GeoSeries(geoms, crs="EPSG:32628").to_crs(crs).values
    return rasterize(((x,1) for x in geoms), out_shape=shape, transform=tr, fill=0, dtype="uint8").astype(bool)

def run(island):
    bbox = ISLAND_BBOX[island]; minx,miny,maxx,maxy = bbox
    isl = zones.islands(); z = isl[isl.name==island]
    evo, te, ec = wsf.load("wsf_evolution", bbox); m = zone_masks(z, te, evo.shape, ec)[island]
    with rasterio.open(RAW/"hisdac_es"/"canary"/"can_regcan_age"/"hisdac_es_age_mincoy_v1_100.tif") as s: coy = resample_to(s.read(1), s.transform, s.crs, te, evo.shape, ec, nodata=0)
    with rasterio.open(RAW/"hisdac_es"/"canary"/"can_regcan_physical"/"hisdac_es_phys_bunits_sum_v1_100.tif") as s: bun = resample_to(s.read(1), s.transform, s.crs, te, evo.shape, ec, nodata=0)
    target = (evo==1985) & m & (coy==0) & (bun<=0)          # WSF 1985 pixels in cells with no building at all
    a_t = area_km2(target, te)
    bb = f"({miny},{minx},{maxy},{maxx})"
    roads = overpass(f'[out:json][timeout:300];way["highway"]{bb};out geom;', f"osm_roads_{island.replace(' ','_')}")
    infra = overpass(f'[out:json][timeout:300];(way["aeroway"]{bb};relation["aeroway"]{bb};way["landuse"~"^(industrial|commercial|retail|quarry|port|harbour|military|landfill|construction)$"]{bb};way["man_made"~"^(pier|breakwater|works|wastewater_plant|water_works)$"]{bb};way["leisure"~"^(marina|golf_course)$"]{bb};way["power"="plant"]{bb};);out geom;', f"osm_infra_{island.replace(' ','_')}")
    code = CODE[island]; d = RAW/"mapa_cultivos"; out = d/code
    if not out.exists():
        with zipfile.ZipFile(d/f"{code}_shp.zip") as zf: zf.extractall(out)
    crops = gpd.read_file(glob.glob(str(out/"**"/"*.shp"), recursive=True)[0])
    layers = {
        "roads (15 m buffer)": burn(roads, evo.shape, te, ec, 15),
        "airport/port/industrial/quarry etc. (OSM)": burn(infra[infra.geometry.geom_type.isin(["Polygon","MultiPolygon"])], evo.shape, te, ec),
        "greenhouse parcels (crop map)": burn(crops[crops["TECNICA_NA"]=="Invernadero"], evo.shape, te, ec),
        "any agricultural parcel (crop map)": burn(crops, evo.shape, te, ec),
    }
    print(f"{island}: WSF 1985 pixels in cells with NO cadastral building = {a_t:.2f} km2 "
          f"(of {area_km2((evo==1985)&m, te):.2f} km2 baseline)")
    covered = np.zeros_like(target); rows=[]
    for name, lay in layers.items():
        hit = target & lay; share = area_km2(hit, te)/a_t if a_t else np.nan
        excl = target & lay & ~covered; share_excl = area_km2(excl, te)/a_t if a_t else np.nan
        covered |= lay
        rows.append(dict(island=island, explanation=name, share_pct=round(100*share,1), share_excl_pct=round(100*share_excl,1)))
        print(f"  {name:44s} {100*share:5.1f} %   (adds {100*share_excl:5.1f} % not already explained)")
    rest = area_km2(target & ~covered, te)
    rows.append(dict(island=island, explanation="UNEXPLAINED (candidate bare-soil commission)", share_pct=round(100*rest/a_t,1), share_excl_pct=round(100*rest/a_t,1)))
    print(f"  {'UNEXPLAINED -> M3 stratum':44s} {100*rest/a_t:5.1f} %   = {rest:.2f} km2")
    df = pd.DataFrame(rows); p = FIGURES/"data"/"m0_baseline_nobuilding.csv"
    if p.exists(): old = pd.read_csv(p); df = pd.concat([old[old.island!=island], df], ignore_index=True)
    df.to_csv(p, index=False)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--island", default="Gran Canaria"); run(ap.parse_args().island)
