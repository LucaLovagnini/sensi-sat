"""Mapa de Cultivos (Gobierno de Canarias) — the greenhouse layer.

**Why a crop map is in a settlement project.** Radar sees a greenhouse as a
structure. The plastic sheeting and metal frames of covered agriculture scatter
Sentinel-1's signal much the way a roof does, so the products built on radar
classify greenhouse belts as built-up. Measured on Gran Canaria's 27.1 km2 of
greenhouse parcels: WSF Tracker flags 72 % of that area as built-up and WSF 2019
flags 67 %, while Copernicus Impervious Built-Up - which leans on optical imagery
- flags only 9.5 %. The disagreement is not noise; the two families are answering
different questions about the same plastic.

**What we do about it (M1.2).** Greenhouses are removed from "urban" and published
as their own layer. Removing them keeps SensiSat's headline numbers comparable
with CORINE and with official statistics, which count covered agriculture as
agricultural land. Publishing them separately keeps the information, because for a
conservation audience the soil under a greenhouse is no less lost than the soil
under a car park - it is simply lost to farming rather than to a town. Which of
those two framings matters is the reader's call, and a separate layer lets them
make it.

**The caveat that cannot be engineered away.** This is a survey, not a time
series, and each island was surveyed in a different year: Tenerife 2021, El Hierro
and La Palma 2022, La Gomera 2023, Gran Canaria 2024, Fuerteventura and Lanzarote
2025 (read from each file's own name). A single-date parcel
map is used to mask footprints from other years, so a greenhouse built in 2023 is
masked out of the 2016 footprint too. The error this introduces is bounded by how
much the greenhouse belt itself moved, and it is recorded per island in the STAC
item rather than smoothed over.

License: open data, Gobierno de Canarias. Source: opendata.sitcan.es
"""

from __future__ import annotations

import re
import warnings
import zipfile
from pathlib import Path

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import Affine

from ..config import RAW
from ..download import fetch
from ..grid import for_island

NAME = "Mapa de Cultivos de Canarias (Gobierno de Canarias)"
MEASURE = "extent"
ENCODING = "binary"
RESOLUTION_M = 10
LICENSE = "Open data, Gobierno de Canarias"
SOURCE_URL = "https://opendata.sitcan.es/dataset/mapa-de-cultivos"

BASE = "https://opendata.sitcan.es/upload/medio-rural/gobcan_mapa-cultivos_{key}_shp.zip"
DEST = RAW / "mapa_cultivos"

GREENHOUSE = "Invernadero"          # the TECNICA_NA value meaning "under glass/plastic"
FIELD = "TECNICA_NA"

# Which island is covered by which island file, and the year that file was surveyed.
# La Graciosa has no file of its own: it is administratively part of Lanzarote and
# the Lanzarote survey extends to 29.28 N, which covers it (verified from bounds).
SOURCE_FOR: dict[str, str] = {
    "Gran Canaria": "gc", "Tenerife": "tf", "Fuerteventura": "fv",
    "Lanzarote": "lz", "La Graciosa": "lz", "La Palma": "lp",
    "La Gomera": "lg", "El Hierro": "eh",
}
# Survey years are NOT hard-coded: each island's shapefile carries its year in its
# own filename (GC_MCultivos_2024.shp, TF_MCultivos_2021.shp, ...), so reading it
# from there keeps the metadata true when the Gobierno publishes a new survey.
_YEAR_IN_NAME = re.compile(r"(19|20)\d{2}")


def fetch_island(key: str, *, quiet: bool = True) -> Path:
    """Download and unzip one island's crop map. Returns its .shp path."""
    zip_path = fetch(BASE.format(key=key), DEST / f"{key}_shp.zip", quiet=quiet).path
    out_dir = DEST / key
    if not any(out_dir.glob("*.shp")):
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(out_dir)
    shps = sorted(out_dir.rglob("*.shp"))
    if not shps:
        raise FileNotFoundError(f"no shapefile inside {zip_path}")
    return shps[0]


def parcels(island: str, *, greenhouse_only: bool = True):
    """Crop parcels covering an island, as a GeoDataFrame in EPSG:4326."""
    import geopandas as gpd

    key = SOURCE_FOR[island]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gdf = gpd.read_file(fetch_island(key))
    if greenhouse_only:
        if FIELD not in gdf.columns:
            raise KeyError(f"{FIELD} missing from the {key} crop map; columns: {list(gdf.columns)}")
        gdf = gdf[gdf[FIELD] == GREENHOUSE]
    return gdf.to_crs("EPSG:4326")


def greenhouse_mask(island: str, *, transform: Affine | None = None,
                    shape: tuple[int, int] | None = None) -> tuple[np.ndarray, Affine, str]:
    """Boolean greenhouse raster on the shared 10 m grid: 1 where covered agriculture."""
    if transform is None or shape is None:
        transform, shape = for_island(island)
    gdf = parcels(island)
    geoms = [g for g in gdf.geometry if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros(shape, dtype="uint8"), transform, "EPSG:4326"
    arr = rasterize(((g, 1) for g in geoms), out_shape=shape, transform=transform,
                    fill=0, dtype="uint8")
    return arr, transform, "EPSG:4326"


def survey_year(island: str) -> int:
    """The year this island's crop map was surveyed — the caveat, as a number.

    Read from the shapefile's own name rather than a table, because the surveys
    are staggered (Tenerife 2021, El Hierro 2022, La Gomera 2023, Gran Canaria
    2024, Fuerteventura and Lanzarote 2025) and will be refreshed island by island.
    """
    name = fetch_island(SOURCE_FOR[island]).name
    match = _YEAR_IN_NAME.search(name)
    if not match:
        raise ValueError(f"no survey year in crop map filename {name!r}")
    return int(match.group(0))
