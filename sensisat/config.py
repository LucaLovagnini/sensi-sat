"""Paths, geographic constants and conventions shared by every module.

Nothing here talks to the network. Keeping it import-light means notebooks can
`from sensisat.config import CANARIES_BBOX` without pulling in rasterio.
"""

from __future__ import annotations

import math
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths. Everything downloaded or derived lives under data/ which is gitignored;
# everything a reader should see lives under docs/.
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"              # untouched downloads, one folder per dataset
INTERIM = DATA / "interim"      # clipped/reprojected working copies
PROCESSED = DATA / "processed"  # outputs we would publish (M2 onward)
ZONES = DATA / "zones"          # island / protected-area polygons
DOCS = ROOT / "docs"
FIGURES = DOCS / "figures"

for _p in (RAW, INTERIM, PROCESSED, ZONES, FIGURES):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Geography
# ---------------------------------------------------------------------------
# Whole archipelago, with a small margin. (lon_min, lat_min, lon_max, lat_max)
CANARIES_BBOX = (-18.50, 27.50, -13.20, 29.60)

# Per-island bounding boxes, used to window rasters before any heavy work.
# Values are generous by ~0.05 deg so coastlines are never clipped.
ISLAND_BBOX: dict[str, tuple[float, float, float, float]] = {
    "El Hierro":      (-18.20, 27.60, -17.85, 27.90),
    "La Palma":       (-18.05, 28.40, -17.70, 28.90),
    "La Gomera":      (-17.40, 27.99, -17.05, 28.25),
    "Tenerife":       (-16.95, 27.95, -16.05, 28.65),
    "Gran Canaria":   (-15.90, 27.68, -15.30, 28.25),
    "Fuerteventura":  (-14.60, 27.99, -13.75, 28.80),
    "Lanzarote":      (-13.95, 28.80, -13.35, 29.30),
    "La Graciosa":    (-13.55, 29.20, -13.42, 29.32),
}

# Published land areas (km2), for sanity-checking anything we compute.
# Source: Instituto Canario de Estadistica / standard references.
ISLAND_AREA_KM2: dict[str, float] = {
    "El Hierro": 268.7,
    "La Palma": 708.3,
    "La Gomera": 369.8,
    "Tenerife": 2034.4,
    "Gran Canaria": 1560.1,
    "Fuerteventura": 1659.7,
    "Lanzarote": 845.9,
    "La Graciosa": 29.0,
}
CANARIES_LAND_KM2 = sum(ISLAND_AREA_KM2.values())

# ---------------------------------------------------------------------------
# Pixel geometry
# ---------------------------------------------------------------------------
# WSF products are on a geographic grid: their pixels are a fixed number of
# DEGREES, so their ground area shrinks with latitude. A "30 m" WSF Evolution
# pixel is 0.00026949 deg on both axes, which at 28 deg N is ~29.9 m north-south
# but only ~26.4 m east-west -> ~790 m2, not 900 m2. Counting pixels and
# multiplying by 900 overstates area by ~14 %.
EARTH_MERIDIONAL_M_PER_DEG = 111_132.0
EARTH_EQUATORIAL_M_PER_DEG = 111_320.0


def pixel_area_m2(pixel_size_deg: float, latitude_deg: float) -> float:
    """Ground area of one square-in-degrees pixel at a given latitude."""
    ns = pixel_size_deg * EARTH_MERIDIONAL_M_PER_DEG
    ew = pixel_size_deg * EARTH_EQUATORIAL_M_PER_DEG * math.cos(math.radians(latitude_deg))
    return ns * ew


# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------
USER_AGENT = "SensiSat/0.1 (research prototype; github.com/LucaLovagnini/sensi-sat)"
HTTP_HEADERS = {"User-Agent": USER_AGENT}

# Basemap tile services, used only to render figures. Nothing is stored.
ESRI_SATELLITE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_LIGHT_GRAY = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
