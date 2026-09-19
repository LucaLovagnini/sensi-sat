"""Copernicus Land Monitoring Service — Impervious Built-Up, its change layers,
and Imperviousness Density.

Three products from one producer (the EEA), each answering a question no other
source in the roster can.

**Impervious Built-Up (IBU), 10 m, 2018 / 2021 / 2024** — buildings, as a yes/no
per pixel. Its value to us is precision: tested against the cadastre it is the
most trustworthy of the satellite products (57-80 % of the cells it flags contain
a real building), and unlike the radar-based WSF family it does not mistake
greenhouses for structures (9.5 % of Gran Canaria's greenhouse parcels flagged,
against WSF Tracker's 72 %).

**IBU Change (IBUC), 20 m, 2018-2021 and 2021-2024** — the only layers in the
whole project that measure *loss*. Everything else here is growth-only by
construction: WSF Evolution, WSF Tracker and GHSL can each only ever add. The
change layers recorded the Tajogaite eruption burying Todoque - built-up inside
the lava went 0.909 km2 (2018) to 0.084 (2021) to 0.011 (2024) - and they are
what feeds the `loss-events` layer.

**Imperviousness Density (IMD), 10 m, 2024** — percent of each pixel sealed, by
anything: buildings, roads, car parks, paving. It measures 341.5 km2 across the
archipelago, about 2.2x GHSL's built *surface*, and that gap is the roads and
paving GHSL never counted. It drives the current-density layer (M1.3).

**The rule that governs all of this.** Never subtract two status layers from
different releases. Read on their own the three IBU years say 215 -> 185 -> 259
km2, which would mean the Canaries demolished 30 km2 of buildings and then built
74 km2 back. They did not: the 2018, 2021 and 2024 layers were produced by
different processing chains, and the difference between them is mostly method.
Change is only ever read from the purpose-built IBUC layers, which are produced
by comparing the two dates *within one chain*. This mistake was made three times
in one day during M0, in three different forms, which is why it is written here
next to the code that could make it a fourth.

**Class codes are read, not remembered.** Every download ships an SLD stylesheet
naming its own classes, so `legend()` parses that file rather than trusting a
constant typed from a PDF. If the EEA renumbers a class, the code follows.

Acquisition: these files sit behind a free Copernicus account and arrive as
numbered zips (110241, 110252, 110281, 110282), so unlike every other adapter here
there is no fetch URL - they are placed in data/raw/hrl/ by hand.

License: Copernicus / EEA, free reuse with attribution.
Source: https://land.copernicus.eu
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.transform import Affine
from rasterio.warp import Resampling, transform_bounds

from ..config import ISLAND_BBOX, RAW
from ..grid import for_island
from ..raster import resample_to

NAME = "Copernicus Land Monitoring Service (EEA)"
LICENSE = "Copernicus / EEA, free reuse with attribution"
SOURCE_URL = "https://land.copernicus.eu"
NATIVE_CRS = "EPSG:3035"  # ETRS89 / LAEA Europe — metres, so pixels are exactly 10 m

ROOT = RAW / "hrl"

# Each product: where its tiles are, what its nodata value is, and what it means.
# `order` is the download bundle it arrived in, kept so the provenance is traceable.
PRODUCTS: dict[str, dict] = {
    "ibu_2018": {
        "order": "110252", "glob": "IBU_2018_010m_eu_03035_v011.tif", "nodata": 240,
        "res_m": 10, "kind": "status", "year": 2018, "measure": "extent",
        "note": "EU-wide clipped file; a different packaging from the 2021/2024 tiles",
    },
    "ibu_2021": {
        "order": "110252", "glob": "*IBU_S2021_R10m*.tif", "nodata": 255,
        "res_m": 10, "kind": "status", "year": 2021, "measure": "extent",
    },
    "ibu_2024": {
        "order": "110252", "glob": "*IBU_S2024_R10m*.tif", "nodata": 255,
        "res_m": 10, "kind": "status", "year": 2024, "measure": "extent",
    },
    "ibuc_2018_2021": {
        "order": "110241", "glob": "*IBUC_C2018-2021_R20m*.tif", "nodata": 255,
        "res_m": 20, "kind": "change", "year": (2018, 2021), "measure": "change",
    },
    "ibuc_2021_2024": {
        "order": "110252", "glob": "*IBUC_C2021-2024_R20m*.tif", "nodata": 255,
        "res_m": 20, "kind": "change", "year": (2021, 2024), "measure": "change",
    },
    "imd_2024": {
        "order": "110281", "glob": "*IMD_S2024_R10m*.tif", "nodata": 255,
        "res_m": 10, "kind": "density", "year": 2024, "measure": "surface",
    },
    "imdcl_2024": {
        "order": "110282", "glob": "*IMDCL_S2024_R10m*.tif", "nodata": 255,
        "res_m": 10, "kind": "confidence", "year": 2024, "measure": "confidence",
    },
}

# Names for the change classes, used by the loss layer. The numbers themselves are
# verified against the shipped SLD by `legend()`; these are only the short labels.
CHANGE_CLASSES = {
    0: "unchanged non-built-up",
    1: "new cover",
    2: "loss of cover",
    10: "unchanged built-up",
    11: "increased built-up density",
    12: "decreased built-up density",
}
NEW_COVER, LOSS_OF_COVER = 1, 2

# The two CLMS vintages order their SLD attributes differently - the 2021 files
# write quantity before label, the 2024 files write label, colour, then quantity -
# so the entry is matched as a whole and its attributes read by name.
_SLD_ENTRY = re.compile(r"<[^>]*ColorMapEntry\b[^>]*/?>")
_SLD_ATTR = re.compile(r'(\w+)="([^"]*)"')


def tiles(product: str) -> list[Path]:
    """Every GeoTIFF belonging to a product, in its download bundle."""
    spec = _spec(product)
    found = sorted((ROOT / spec["order"]).rglob(spec["glob"]))
    if not found:
        raise FileNotFoundError(
            f"no files matching {spec['glob']!r} under {ROOT / spec['order']}. "
            f"The Copernicus layers need a free land.copernicus.eu account; "
            f"place the unzipped order {spec['order']} there."
        )
    # The same tile can appear twice inside a bundle (documentation copies).
    return sorted({p.name: p for p in found}.values(), key=lambda p: p.name)


def _spec(product: str) -> dict:
    if product not in PRODUCTS:
        raise ValueError(f"unknown product {product!r}; expected one of {sorted(PRODUCTS)}")
    return PRODUCTS[product]


def legend(product: str) -> dict[int, str]:
    """Class values and labels, parsed from the product's own SLD stylesheet.

    For the class products (IBU, IBUC) this is the small table of codes. For the
    continuous ones (IMD, IMD confidence) it is 0-100 as percentages plus the
    special codes, so `special_codes()` is the useful call there.
    """
    spec = _spec(product)
    sld = next((p for p in sorted((ROOT / spec["order"]).rglob("*.sld"))
                if _matches_product(p, product)), None)
    if sld is None:
        return {}
    out: dict[int, str] = {}
    for entry in _SLD_ENTRY.findall(sld.read_text(errors="ignore")):
        attrs = dict(_SLD_ATTR.findall(entry))
        value, label = attrs.get("quantity"), attrs.get("label", "")
        if value is None or not value.isdigit():
            continue
        # Unused slots are labelled with the bare number; skip those.
        if label.strip() != value:
            out[int(value)] = label.split(":", 1)[-1].strip()
    return out


def _matches_product(sld: Path, product: str) -> bool:
    stem = sld.parent.name
    spec = _spec(product)
    token = spec["glob"].strip("*").split("*")[0]
    return token in stem or token in sld.name


def special_codes(product: str) -> dict[int, str]:
    """Just the non-measurement codes of a continuous product (nodata, outside area).

    These are the values that must never be read as data: on IMD, 255 means "not
    measured", and treating it as 255 % sealed - or even as 100 % - would invent
    sealing that was never observed.
    """
    return {v: label for v, label in legend(product).items()
            if not re.match(r"^\d+%", label.strip())}


def load(product: str, bbox=None, *, island: str | None = None):
    """Mosaic a product over a lon/lat bbox. Returns (array, transform, crs) in EPSG:3035.

    The bbox is given in lon/lat for consistency with every other adapter, and
    transformed into the product's own metre-based CRS to window the read, so only
    the tiles and bytes covering the area are touched.
    """
    spec = _spec(product)
    if bbox is None:
        bbox = ISLAND_BBOX[island] if island else None
    paths = tiles(product)
    srcs = [rasterio.open(p) for p in paths]
    try:
        bounds = transform_bounds("EPSG:4326", srcs[0].crs, *bbox, densify_pts=21) if bbox else None
        arr, transform = merge(srcs, bounds=bounds, nodata=spec["nodata"])
        return arr[0], transform, srcs[0].crs
    finally:
        for s in srcs:
            s.close()


def built_mask(product: str, bbox=None, *, island: str | None = None):
    """Boolean built-up mask for an IBU status layer, on its native grid."""
    spec = _spec(product)
    if spec["kind"] != "status":
        raise ValueError(f"{product!r} is a {spec['kind']} layer, not a status layer")
    arr, transform, crs = load(product, bbox, island=island)
    return arr == 1, transform, crs


def on_grid(product: str, island: str, *, transform: Affine | None = None,
            shape: tuple[int, int] | None = None, resampling: Resampling | None = None):
    """Put a product onto SensiSat's shared 10 m grid for an island.

    This is the one reprojection in the pipeline: Copernicus is the only source
    not already in EPSG:4326. Categorical layers (built-up, change classes) move
    with nearest-neighbour, because averaging a class code invents classes that
    were never measured. The IMD percentage moves with bilinear, because a
    percentage is a continuous quantity and averaging it is meaningful.
    """
    spec = _spec(product)
    if transform is None or shape is None:
        transform, shape = for_island(island)
    arr, src_transform, src_crs = load(product, ISLAND_BBOX[island])
    if resampling is None:
        resampling = Resampling.bilinear if spec["kind"] == "density" else Resampling.nearest
    dtype = "float32" if spec["kind"] == "density" else arr.dtype.name
    out = resample_to(arr.astype(dtype), src_transform, src_crs, transform, shape, "EPSG:4326",
                      nodata=spec["nodata"], resampling=resampling)
    return out, transform, "EPSG:4326"


def sealed_fraction(island: str, *, transform: Affine | None = None,
                    shape: tuple[int, int] | None = None):
    """Imperviousness Density as a 0..1 fraction on the shared grid.

    Values above 100 are the nodata and outside-area codes, not extreme sealing,
    so they are cleared rather than clipped - a pixel of 255 is "not measured",
    and turning it into 100 % sealed would invent the densest city in Europe.
    """
    arr, transform, crs = on_grid("imd_2024", island, transform=transform, shape=shape)
    arr = np.where(arr > 100, 0, arr)
    return (arr / 100.0).astype("float32"), transform, crs
