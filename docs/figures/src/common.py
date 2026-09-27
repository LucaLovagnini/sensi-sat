"""Shared helpers for the documentation figures.

This is now a thin layer over the `sensisat` package so there is one download
cache and one implementation of the geometry maths. It keeps the names the figure
scripts already use.

Install the package once (editable) so these imports resolve from anywhere:

    pip install -e .
"""

from __future__ import annotations

import numpy as np

from sensisat.config import (
    CANARIES_BBOX,
    ESRI_LIGHT_GRAY as ESRI_GRAY,
    ESRI_SATELLITE as ESRI_SAT,
    FIGURES as FIG,
    HTTP_HEADERS as UA,
    ISLAND_BBOX,
    RAW,
    ROOT,
    pixel_area_m2,
)
from sensisat.datasets import wsf
from sensisat.raster import area_km2, read_window, row_areas_m2, to_web_mercator
from sensisat.tiles import basemap_window, mosaic, tile_bounds_3857, tile_xy

DATA = RAW / "wsf_evolution"
GC_BBOX = ISLAND_BBOX["Gran Canaria"]
GRAN_CANARIA_TILES = [(-16, 26), (-16, 28)]

# A WSF Evolution pixel is 0.00026949 deg square: ~29.9 m north-south but only
# ~26.4 m east-west at 28 N, so ~790 m2 rather than the nominal 900 m2.
PX_AREA_M2 = pixel_area_m2(0.00026949458523585647, 27.95)

ATTRIBUTION = (
    "Basemaps: Esri World Light Gray / Esri World Imagery (streamed, not stored). "
    "Overlay: WSF Evolution © DLR, CC-BY-4.0."
)

__all__ = [
    "ROOT", "DATA", "FIG", "UA", "GC_BBOX", "GRAN_CANARIA_TILES", "PX_AREA_M2", "ATTRIBUTION",
    "ESRI_SAT", "ESRI_GRAY", "CANARIES_BBOX",
    "fetch_wsf_evo", "load_wsf_evo", "built_by", "km2",
    "tile_xy", "tile_bounds_3857", "mosaic", "basemap_window", "overlay_on",
]


def fetch_wsf_evo(tiles=None):
    """Download the WSF Evolution tiles covering Gran Canaria (cached)."""
    return wsf.fetch_tiles("wsf_evolution", GC_BBOX, tiles=tiles or GRAN_CANARIA_TILES, quiet=True)


def load_wsf_evo(bbox=GC_BBOX):
    """(array of 'year first built' with 0 = never, transform, crs) for bbox."""
    return wsf.load("wsf_evolution", bbox, paths=fetch_wsf_evo())


def built_by(arr, year):
    return (arr > 0) & (arr <= year)


def km2(mask, transform=None) -> float:
    """Area of a mask in km2.

    With a transform, the area is integrated row by row (correct). Without one,
    the older flat approximation is used so existing figure captions stay
    reproducible; pass the transform in new code.
    """
    if transform is not None:
        return area_km2(mask, transform)
    return float(np.asarray(mask).sum()) * PX_AREA_M2 / 1e6


def overlay_on(arr, tr, crs, bounds_3857, width, height):
    """Nearest-neighbour reprojection of the overlay onto a Web-Mercator mosaic."""
    return to_web_mercator(arr, tr, crs, bounds_3857, width, height)
