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
import time
from pathlib import Path

import geopandas as gpd
from shapely.geometry import shape
from shapely.ops import unary_union

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
# One per island, chosen on protection category and then VERIFIED by measurement
# rather than assumed. Two rules decided this list:
#
#   1. Protection category matters. A "Reserva Natural Integral" (strict reserve)
#      and a "Parque Nacional" forbid settlement. A "Paisaje Protegido" (protected
#      landscape) and a "Parque Rural" explicitly include inhabited land, so they
#      are useless as controls no matter how scenic — a product finding buildings
#      inside one would be right.
#   2. The polygon minus known infrastructure must still be large and empty.
#      Every candidate here was measured against the published layers before
#      adoption; all came in at or below 0.05 % built, the worst being Timanfaya.
#
# Two islands have no entry, and that is reported rather than papered over:
# El Hierro's only protected areas in OSM are a protected landscape (which permits
# settlement) and an archaeological site, and no protected-area polygon for La
# Graciosa resolves at all. Those islands have no commission check.
#
# Queries are exact. M0 learned the hard way that "Timanfaya" alone also matches a
# hotel and a bus stop, and that adding ", Lanzarote, Spain" makes the search
# return NOTHING — the suffix that looks helpful is the one that breaks it.
NEGATIVE_CONTROLS: dict[str, tuple[str, str, str | None]] = {
    # island: (label, Nominatim query, osm type filter)
    "Lanzarote":     ("Timanfaya NP", "Parque Nacional de Timanfaya", "national_park"),
    "Tenerife":      ("Teide NP", "Parque Nacional del Teide", "national_park"),
    "La Palma":      ("Caldera de Taburiente NP",
                      "Parque Nacional de la Caldera de Taburiente", "national_park"),
    "La Gomera":     ("Garajonay NP", "Parque Nacional de Garajonay", "national_park"),
    "Gran Canaria":  ("Inagua strict reserve", "Reserva Natural Integral de Inagua", None),
    "Fuerteventura": ("Jandia natural park", "Parque Natural de Jandia", None),
}

TIMANFAYA_QUERY = "Parque Nacional de Timanfaya"
TIMANFAYA_KEY = "timanfaya_np"


def timanfaya() -> gpd.GeoDataFrame:
    """Timanfaya National Park, Lanzarote — a lava desert with no settlement."""
    return nominatim_polygon(TIMANFAYA_QUERY, key=TIMANFAYA_KEY, want="national_park")


def has_negative_control(island: str) -> bool:
    """Is there ground on this island where built-up would be an error by definition?"""
    return island in NEGATIVE_CONTROLS


def negative_control_for(island: str) -> tuple[str, gpd.GeoDataFrame]:
    """(label, polygon minus buffered infrastructure) for one island's control.

    The subtraction is the whole point. Teide National Park contains the Parador
    hotel, mountain refuges, cable-car stations and visitor centres — 127 buildings
    in OSM. Those are real, so a product detecting them is correct, and leaving
    them in would turn the control into a source of false alarms. What remains
    after removing a 30 m buffer around every known road and building is ground
    where nothing should be found.

    Raises LookupError when the island has no control defined — the caller must
    distinguish that from a control that exists but could not be loaded.
    """
    if island not in NEGATIVE_CONTROLS:
        raise LookupError(f"no negative control defined for {island!r}")
    label, query, want = NEGATIVE_CONTROLS[island]
    key = query.lower().replace(" ", "_")[:44]
    polygon = nominatim_polygon(query, key=key, want=want)
    infra = infrastructure_in(unary_union(polygon.geometry.values), key=f"{key}_infra")
    return label, negative_control(polygon, infra, f"{key}_control")


def infrastructure_in(polygon, *, key: str, buffer_m: float = 30.0) -> gpd.GeoDataFrame:
    """Buildings and roads inside a polygon, from OSM Overpass, buffered (cached).

    Used to carve real structures out of a negative control so that what remains
    genuinely should contain nothing built.
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
