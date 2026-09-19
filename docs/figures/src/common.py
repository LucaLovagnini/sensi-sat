"""Shared helpers for the documentation figures.

Everything here is deliberately small: download a public raster if missing,
cut out the Gran Canaria window, fetch a few basemap tiles, and reproject our
overlay onto the tile grid so both can be drawn in the same picture.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np
import rasterio
import requests
from PIL import Image
from rasterio.merge import merge
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parents[3]          # repository root
DATA = ROOT / "data" / "raw" / "wsf_evo"            # gitignored download cache
FIG = ROOT / "docs" / "figures"

UA = {"User-Agent": "SensiSat-docs/0.1 (research prototype; github.com/LucaLovagnini/sensi-sat)"}

# DLR World Settlement Footprint Evolution: 2°x2° tiles named by their lower-left corner.
WSF_EVO_BASE = "https://download.geoservice.dlr.de/WSF_EVO/files"
GRAN_CANARIA_TILES = ["WSFevolution_v1_-16_26", "WSFevolution_v1_-16_28"]
GC_BBOX = (-15.87, 27.71, -15.33, 28.20)            # lon_min, lat_min, lon_max, lat_max
# A WSF Evolution pixel is 0.00026949° on both axes: ~30 m north-south but only
# ~26.5 m east-west at 28° N, hence ~793 m² rather than 900 m².
PX_AREA_M2 = 793.0

# Basemap tile services (streamed for the figure only; nothing is stored).
ESRI_SAT = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_GRAY = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
ATTRIBUTION = "Basemaps: Esri World Light Gray · Esri World Imagery (streamed, not stored). Overlay: WSF Evolution © DLR, CC-BY-4.0."


def fetch_wsf_evo(tiles=GRAN_CANARIA_TILES) -> list[Path]:
    DATA.mkdir(parents=True, exist_ok=True)
    out = []
    for t in tiles:
        p = DATA / f"{t}.tif"
        if not p.exists():
            r = requests.get(f"{WSF_EVO_BASE}/{t}/{t}.tif", headers=UA, timeout=180)
            r.raise_for_status()
            p.write_bytes(r.content)
        out.append(p)
    return out


def load_wsf_evo(bbox=GC_BBOX):
    """Return (array, transform, crs) of 'year first built' (0 = not built) for the bbox."""
    srcs = [rasterio.open(p) for p in fetch_wsf_evo()]
    arr, tr = merge(srcs, bounds=bbox, nodata=0)
    return arr[0], tr, srcs[0].crs


def built_by(arr, year):
    return (arr > 0) & (arr <= year)


def km2(mask) -> float:
    return float(mask.sum()) * PX_AREA_M2 / 1e6


# ---- Web-Mercator tile arithmetic -------------------------------------------------
def tile_xy(lon, lat, z):
    n = 2 ** z
    la = math.radians(lat)
    return int((lon + 180) / 360 * n), int((1 - math.log(math.tan(la) + 1 / math.cos(la)) / math.pi) / 2 * n)


def tile_bounds_3857(x0, y0, x1, y1, z):
    n, R = 2 ** z, 6378137.0
    lon = lambda x: x / n * 360 - 180
    lat = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    mx = lambda lo: math.radians(lo) * R
    my = lambda la: math.log(math.tan(math.pi / 4 + math.radians(la) / 2)) * R
    return mx(lon(x0)), my(lat(y1 + 1)), mx(lon(x1 + 1)), my(lat(y0))


def mosaic(url_fmt, x0, y0, x1, y1, z):
    im = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256), (235, 235, 235))
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            try:
                r = requests.get(url_fmt.format(z=z, x=x, y=y), headers=UA, timeout=30)
                r.raise_for_status()
                im.paste(Image.open(io.BytesIO(r.content)).convert("RGB"), ((x - x0) * 256, (y - y0) * 256))
            except Exception as e:  # a missing tile leaves a grey square; the figure still renders
                print("tile failed", z, x, y, type(e).__name__)
    return im


def basemap_window(bbox, z, url_fmt):
    """Tiles covering bbox at zoom z → (image, bounds_3857, extent_for_imshow)."""
    x0, y0 = tile_xy(bbox[0], bbox[3], z)
    x1, y1 = tile_xy(bbox[2], bbox[1], z)
    b = tile_bounds_3857(x0, y0, x1, y1, z)
    return mosaic(url_fmt, x0, y0, x1, y1, z), b, (b[0], b[2], b[1], b[3])


def overlay_on(arr, tr, crs, bounds_3857, width, height):
    """Nearest-neighbour reprojection of the overlay onto a Web-Mercator tile mosaic."""
    dst = np.zeros((height, width), dtype=arr.dtype)
    reproject(arr, dst, src_transform=tr, src_crs=crs, dst_transform=from_bounds(*bounds_3857, width, height),
              dst_crs="EPSG:3857", resampling=Resampling.nearest, src_nodata=0, dst_nodata=0)
    return dst
