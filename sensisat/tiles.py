"""Web-Mercator tile arithmetic and basemap mosaics — for figures only.

Basemap tiles are streamed from a third-party provider when a figure is rendered
and never stored. They are not our data; see docs/concepts.md section 1.
"""

from __future__ import annotations

import io
import math

import requests
from PIL import Image

from .config import HTTP_HEADERS

R_EARTH = 6378137.0


def tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    la = math.radians(lat)
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.log(math.tan(la) + 1 / math.cos(la)) / math.pi) / 2 * n)
    return x, y


def tile_bounds_3857(x0: int, y0: int, x1: int, y1: int, z: int) -> tuple[float, float, float, float]:
    """Web-Mercator bounds of an inclusive tile range."""
    n = 2 ** z

    def lon(x):
        return x / n * 360 - 180

    def lat(y):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))

    def mx(lo):
        return math.radians(lo) * R_EARTH

    def my(la):
        return math.log(math.tan(math.pi / 4 + math.radians(la) / 2)) * R_EARTH

    return mx(lon(x0)), my(lat(y1 + 1)), mx(lon(x1 + 1)), my(lat(y0))


def mosaic(url_fmt: str, x0: int, y0: int, x1: int, y1: int, z: int) -> Image.Image:
    im = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256), (235, 235, 235))
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            try:
                r = requests.get(url_fmt.format(z=z, x=x, y=y), headers=HTTP_HEADERS, timeout=30)
                r.raise_for_status()
                im.paste(Image.open(io.BytesIO(r.content)).convert("RGB"), ((x - x0) * 256, (y - y0) * 256))
            except Exception as exc:  # a missing tile leaves a grey square; the figure still renders
                print("basemap tile failed", z, x, y, type(exc).__name__)
    return im


def basemap_window(bbox, z: int, url_fmt: str):
    """Tiles covering a lon/lat bbox. Returns (image, bounds_3857, imshow_extent)."""
    x0, y0 = tile_xy(bbox[0], bbox[3], z)
    x1, y1 = tile_xy(bbox[2], bbox[1], z)
    b = tile_bounds_3857(x0, y0, x1, y1, z)
    return mosaic(url_fmt, x0, y0, x1, y1, z), b, (b[0], b[2], b[1], b[3])


def ground_resolution_m(lat: float, z: int) -> float:
    """Metres per screen pixel, for choosing a zoom that shows one data pixel per screen pixel."""
    return 156543.03392804097 * math.cos(math.radians(lat)) / (2 ** z)
