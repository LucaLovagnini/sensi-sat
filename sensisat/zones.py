"""Polygons we measure things inside: islands, protected areas, negative controls.

Sources are OpenStreetMap via Nominatim (boundaries) and Overpass (infrastructure
inside the negative controls). Both are cached to data/zones/ as GeoJSON so a
notebook re-runs offline and so we stay within the services' usage policies.

A note on the negative controls. The point of Timanfaya National Park and the
La Palma 2021 lava field is that they contain no settlement, so any pixel a
product calls "built" there is a false positive. But both DO contain some real
built structures — Timanfaya has the LZ-67 road, the El Diablo restaurant, a car
park and the camel station; a road was rebuilt across the La Palma lava. So the
control is the polygon MINUS a buffer around known roads and buildings, and the
expected value is "approximately zero outside that infrastructure", not "zero".
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import geopandas as gpd
from shapely.geometry import shape
from shapely.ops import unary_union

# The cached negative-control infrastructure is a single unioned geometry covering
# every road and building inside an island's protected areas. On Tenerife and Gran
# Canaria that one feature exceeds GDAL's default 200 MB-equivalent complexity
# guard for a GeoJSON object, and reading it back fails with "GeoJSON object too
# complex/large". Lifting the limit is the documented remedy; 0 means no limit.
# Without this the control could not be loaded on exactly the two islands that
# hold most of the built-up area — and the gate correctly reported a FAILURE
# rather than skipping, which is how it was found.
os.environ.setdefault("OGR_GEOJSON_MAX_OBJ_SIZE", "0")

from .config import ISLAND_BBOX, ZONES
from .download import fetch_json

NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = "https://overpass-api.de/api/interpreter"
_LAST_CALL = {"t": 0.0}


def _polite_pause(min_interval: float = 1.1) -> None:
    """Nominatim's usage policy allows at most one request per second."""
    elapsed = time.time() - _LAST_CALL["t"]
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    _LAST_CALL["t"] = time.time()


def _cache_path(key: str) -> Path:
    return ZONES / f"{key}.geojson"


def _load_cached(key: str) -> gpd.GeoDataFrame | None:
    p = _cache_path(key)
    if p.exists():
        return gpd.read_file(p)
    return None


def _save(key: str, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf.to_file(_cache_path(key), driver="GeoJSON")
    return gdf


def nominatim_polygon(query: str, key: str, *, want: str | None = None) -> gpd.GeoDataFrame:
    """Fetch one named boundary from Nominatim as a GeoDataFrame (cached).

    `want` optionally filters the candidates by osm 'type' (e.g. 'island',
    'national_park'), because a place name often matches several features.
    """
    cached = _load_cached(key)
    if cached is not None:
        return cached

    _polite_pause()
    url = f"{NOMINATIM}?q={requests_quote(query)}&format=jsonv2&polygon_geojson=1&limit=10"
    results = fetch_json(url)
    if not results:
        raise LookupError(f"Nominatim found nothing for {query!r}")

    chosen = None
    for r in results:
        if not r.get("geojson"):
            continue
        if want and r.get("type") != want:
            continue
        if r["geojson"]["type"] in {"Polygon", "MultiPolygon"}:
            chosen = r
            break
    if chosen is None:
        chosen = next((r for r in results
                       if r.get("geojson", {}).get("type") in {"Polygon", "MultiPolygon"}), None)
    if chosen is None:
        raise LookupError(f"no polygon geometry for {query!r}")

    gdf = gpd.GeoDataFrame(
        {"name": [key], "osm_type": [chosen.get("osm_type")], "osm_id": [chosen.get("osm_id")],
         "display_name": [chosen.get("display_name")], "category": [chosen.get("category")],
         "type": [chosen.get("type")]},
        geometry=[shape(chosen["geojson"])], crs="EPSG:4326",
    )
    return _save(key, gdf)


def requests_quote(s: str) -> str:
    from urllib.parse import quote
    return quote(s)


def islands(names: list[str] | None = None) -> gpd.GeoDataFrame:
    """Boundaries of the Canary Islands, one row per island (cached)."""
    cached = _load_cached("islands")
    if cached is not None and (names is None or set(names) <= set(cached["name"])):
        return cached[cached["name"].isin(names)] if names else cached

    wanted = names or list(ISLAND_BBOX)
    frames = []
    for island in wanted:
        query = f"{island}, Canary Islands, Spain"
        try:
            gdf = nominatim_polygon(query, key=f"island_{island.replace(' ', '_')}", want="island")
        except LookupError as exc:
            print(f"  ! {island}: {exc}")
            continue
        gdf = gdf.assign(name=island)
        frames.append(gdf)
    out = gpd.GeoDataFrame(__import__("pandas").concat(frames, ignore_index=True), crs="EPSG:4326")
    return _save("islands", out)


# ---------------------------------------------------------------------------
# Negative controls: ground where "built" is an error by definition
# ---------------------------------------------------------------------------
# Source: Red Canaria de Espacios Naturales Protegidos (Gobierno de Canarias),
# 147 protected areas with their official protection category. This replaced
# looking parks up by name in Nominatim, which was fragile twice over — a stale
# query once made the whole gate skip silently, and OSM has no polygon at all for
# several of these areas.
#
# The category is what decides whether a polygon can be a control, and the
# categories are NOT interchangeable:
#
#   Tier 1  Parque Nacional, Reserva Natural Integral, Reserva Natural Especial
#           Settlement is forbidden outright. Any built-up pixel is an error.
#   Tier 2  Monumento Natural, Sitio de Interés Científico
#           Protect a specific feature — a volcanic cone, a cliff, a dune field.
#           Usually unbuilt, but small and often close to towns, so they are used
#           only where an island has no Tier 1 area at all. Measured: adding them
#           everywhere raised Tenerife's reading from 0.023 % to 0.085 %.
#   Tier 3  Parque Natural, Paisaje Protegido, Parque Rural
#           EXPLICITLY include inhabited land. A product finding buildings inside
#           one is RIGHT, so these can never be controls however scenic.
ENP_URL = "https://opendata.sitcan.es/upload/medio-ambiente/eennpp.zip"
ENP_TIER1 = ("Parque Nacional", "Reserva Natural Integral", "Reserva Natural Especial")
ENP_TIER2 = ("Monumento Natural", "Sitio de Interés Científico")

# La Graciosa has no Tier 1 or Tier 2 area: its only protected area is the Chinijo
# Parque Natural, which covers nearly the whole island INCLUDING Caleta de Sebo.
# Cleaning it would mean trusting OSM to know where the village is, and OSM holds
# 299 of the island's 539 cadastral buildings — 55 %. A control that leaves 240
# real buildings unsubtracted would flag correct detections as errors, which is
# worse than having no control. So La Graciosa has none, and the gate says so.
NO_CONTROL = ("La Graciosa",)

TIMANFAYA_QUERY = "Parque Nacional de Timanfaya"
TIMANFAYA_KEY = "timanfaya_np"


def timanfaya() -> gpd.GeoDataFrame:
    """Timanfaya National Park, Lanzarote — a lava desert with no settlement."""
    return nominatim_polygon(TIMANFAYA_QUERY, key=TIMANFAYA_KEY, want="national_park")


def protected_areas() -> gpd.GeoDataFrame:
    """All 147 Canary protected areas with their official category (cached)."""
    import zipfile

    from .config import RAW
    from .download import fetch

    dest = RAW / "enp"
    shp = dest / "eennpp.shp"
    if not shp.exists():
        archive = fetch(ENP_URL, dest / "eennpp.zip", quiet=True).path
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
    return gpd.read_file(shp).to_crs("EPSG:4326")


def control_areas_for(island: str) -> tuple[str, gpd.GeoDataFrame]:
    """The protected polygons usable as a control on one island, before cleaning.

    Tier 1 where it exists; Tier 2 only as a fallback, because an island with no
    strictly protected ground is better served by several small feature reserves
    than by nothing. Clipped to the island's own land, which matters for the
    coastal and marine areas whose polygons run far out to sea.
    """
    if island in NO_CONTROL:
        raise LookupError(f"no protected area qualifies as a control on {island!r}")

    areas = protected_areas()
    land = unary_union(islands().query("name == @island").geometry.values)
    for tier, label in ((ENP_TIER1, "tier 1"), (ENP_TIER1 + ENP_TIER2, "tier 1+2")):
        chosen = areas[areas["categoria"].isin(tier) & areas.geometry.intersects(land)]
        if len(chosen):
            geom = unary_union(chosen.geometry.values).intersection(land)
            name = f"{len(chosen)} protected areas ({label})"
            return name, gpd.GeoDataFrame({"name": [island]}, geometry=[geom], crs="EPSG:4326")
    raise LookupError(f"no protected area qualifies as a control on {island!r}")


def has_negative_control(island: str) -> bool:
    """Is there ground on this island where built-up would be an error by definition?"""
    if island in NO_CONTROL:
        return False
    try:
        control_areas_for(island)
        return True
    except LookupError:
        return False


def negative_control_for(island: str) -> tuple[str, gpd.GeoDataFrame]:
    """(label, protected ground minus buffered infrastructure) for one island.

    The subtraction is the whole point. Teide National Park contains the Parador
    hotel, mountain refuges, cable-car stations and visitor centres — 127 buildings
    in OSM. Those are real, so a product detecting them is correct, and leaving
    them in would turn the control into a source of false alarms. What remains
    after removing a 30 m buffer around every known road and building is ground
    where nothing should be found.

    Raises LookupError when the island has no control — the caller must
    distinguish that from a control that exists but could not be loaded.
    """
    label, polygon = control_areas_for(island)
    key = f"enp_{island.replace(' ', '_')}"
    infra = infrastructure_in(unary_union(polygon.geometry.values), key=f"{key}_infra")
    return label, negative_control(polygon, infra, f"{key}_control")


def infrastructure_in(polygon, *, key: str, buffer_m: float = 30.0,
                      clip: bool = True) -> gpd.GeoDataFrame:
    """Buildings and roads inside a polygon, from OSM Overpass, buffered (cached).

    Used to carve real structures out of a negative control so that what remains
    genuinely should contain nothing built.

    Overpass can only be queried by bounding box, and the bounding box of an
    island's protected areas is most of the island — so the raw result is a 30 m
    buffer around every road on Tenerife, which cached to 80 MB of GeoJSON and was
    mostly ground the control never touches. `clip` intersects it with the polygon
    before caching, which is both what the caller means and two orders of
    magnitude smaller.
    """
    cached = _load_cached(key)
    if cached is not None:
        return cached

    minx, miny, maxx, maxy = polygon.bounds
    query = f"""
    [out:json][timeout:120];
    (
      way["building"]({miny},{minx},{maxy},{maxx});
      way["highway"~"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|track)$"]({miny},{minx},{maxy},{maxx});
      way["aeroway"]({miny},{minx},{maxy},{maxx});
    );
    out geom;
    """
    _polite_pause(2.0)
    import requests

    from .config import HTTP_HEADERS
    r = requests.post(OVERPASS, data={"data": query}, headers=HTTP_HEADERS, timeout=180)
    r.raise_for_status()
    elements = r.json().get("elements", [])

    from shapely.geometry import LineString, Polygon
    geoms = []
    for el in elements:
        pts = [(p["lon"], p["lat"]) for p in el.get("geometry", [])]
        if len(pts) < 2:
            continue
        if el.get("tags", {}).get("building") and pts[0] == pts[-1] and len(pts) >= 4:
            geoms.append(Polygon(pts))
        else:
            geoms.append(LineString(pts))
    if not geoms:
        gdf = gpd.GeoDataFrame({"name": []}, geometry=[], crs="EPSG:4326")
        return _save(key, gdf)

    # Buffer in a metric CRS, then return to lon/lat.
    gs = gpd.GeoSeries(geoms, crs="EPSG:4326").to_crs("EPSG:32628")
    merged = unary_union(gs.buffer(buffer_m).values)
    gdf = gpd.GeoDataFrame({"name": [key]}, geometry=[merged], crs="EPSG:32628").to_crs("EPSG:4326")
    if clip:
        gdf = gpd.GeoDataFrame({"name": [key]},
                               geometry=[gdf.geometry.iloc[0].intersection(polygon)],
                               crs="EPSG:4326")
    return _save(key, gdf)


def negative_control(polygon_gdf: gpd.GeoDataFrame, infra_gdf: gpd.GeoDataFrame, name: str) -> gpd.GeoDataFrame:
    """polygon minus buffered infrastructure — where 'built' must be ~0."""
    poly = unary_union(polygon_gdf.geometry.values)
    if len(infra_gdf):
        poly = poly.difference(unary_union(infra_gdf.geometry.values))
    return gpd.GeoDataFrame({"name": [name]}, geometry=[poly], crs="EPSG:4326")


def load_geojson(path: str | Path, name: str) -> gpd.GeoDataFrame:
    """Read a GeoJSON supplied by hand (e.g. a Copernicus EMS lava outline)."""
    gdf = gpd.read_file(path)
    if "name" not in gdf.columns:
        gdf = gdf.assign(name=name)
    return gdf.to_crs("EPSG:4326")


def save_manual(name: str, geojson: dict) -> gpd.GeoDataFrame:
    """Persist a polygon we constructed or downloaded outside Nominatim."""
    gdf = gpd.GeoDataFrame({"name": [name]}, geometry=[shape(geojson)], crs="EPSG:4326")
    return _save(name, gdf)


def summary() -> str:
    files = sorted(ZONES.glob("*.geojson"))
    if not files:
        return "no zones cached yet"
    lines = []
    for f in files:
        try:
            gdf = gpd.read_file(f)
            lines.append(f"  {f.stem:28s} {len(gdf):3d} feature(s)")
        except Exception as exc:
            lines.append(f"  {f.stem:28s} unreadable ({type(exc).__name__})")
    return "\n".join(lines)


def _geojson_dict(gdf: gpd.GeoDataFrame) -> dict:
    return json.loads(gdf.to_json())
