"""The STAC catalogue: a machine-readable table of contents for the published layers.

STAC — SpatioTemporal Asset Catalog — is a convention for describing geospatial
files with JSON, so that a program can ask "what do you have for Tenerife in 1995,
and where is the file?" without a database or a server. For SensiSat it does three
jobs:

1. It is what the viewer reads on startup to know which layers and years exist,
   instead of having the answer hard-coded in the frontend.
2. It carries the caveats *with* the data. Every number M0 produced came with a
   condition attached — this epoch is interpolated, this product cannot show loss,
   this mask came from a survey in a different year — and a catalogue entry is the
   only place those survive being handed to someone else.
3. It makes the layers usable by other people's tools (QGIS, stackstac, pystac-client)
   without them reading our code.

**Extensions used.** `projection` (which grid the file is on), `raster` (what each
band's values mean and in what units), `classification` (what the class codes are,
for provenance and change), `version`, and the `processing` fields for lineage.
The last is a community extension that pystac does not implement, so its fields
are written directly with its schema declared in `stac_extensions`.

Catalogue shape: one root catalogue, one collection per layer, one item per island
within it, one COG asset per item. Islands rather than one archipelago-wide file
because the grid is 1.4 gigapixels across the whole box, almost all of it ocean,
and because per-island files make the viewer fetch only what is on screen.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pystac
import rasterio
from pystac.extensions.classification import Classification, ClassificationExtension
from pystac.extensions.projection import ProjectionExtension
from pystac.extensions.raster import DataType, RasterBand, RasterExtension
from shapely.geometry import box, mapping

from . import encoding as enc

PROCESSING_EXT = "https://stac-extensions.github.io/processing/v1.1.0/schema.json"

CATALOG_ID = "sensisat"
CATALOG_TITLE = "SensiSat — urban expansion in the Canary Islands"
CATALOG_DESCRIPTION = (
    "Built-up land in the Canary Islands from 1900 to 2026, assembled from open "
    "cadastral and satellite sources. Each layer states what it means by 'built', "
    "because the sources do not agree and none of them is wrong: measured across "
    "the archipelago, CORINE's artificial surfaces come to 469.5 km2, WSF "
    "Evolution's settlement extent 376.9, Copernicus sealed surface 341.5, "
    "GHSL's built surface 152.9 and the cadastre's building footprints 100.3."
)

LICENSES = {
    "Catastro INSPIRE Buildings": "other",
    "WSF Evolution": "CC-BY-4.0",
    "WSF Tracker": "CC-BY-4.0",
    "Mapa de Cultivos": "other",
    "Copernicus Imperviousness Density 2024": "other",
    "Copernicus Impervious Built-Up Change": "other",
    "GHS-BUILT-S R2023A": "CC-BY-4.0",
}

# What the class codes in each band mean, published so a reader never has to guess.
def _class_name(label: str) -> str:
    """A schema-safe identifier for a class.

    The classification extension constrains `name` to an identifier, so the
    human-readable label cannot be reused verbatim: "pre-2016, undated" contains a
    comma and fails validation. The label survives in `description`, which is where
    a reader should be looking anyway.
    """
    safe = re.sub(r"[^A-Za-z0-9]+", "_", label).strip("_").lower()
    return safe or "unnamed"


PROVENANCE_CLASSES = [
    Classification.create(value=code, description=label, name=_class_name(label))
    for code, label in enc.PROVENANCE.items()
]

UNITS = {
    "year first built": "year (uint8, year-1899; 255 = built, year unknown)",
    "epoch first built": "epoch index (1 = 2016-07, 20 = 2026-01)",
    "binary": "1 = present",
    "percent": "%",
    "amount": "m2 per cell",
    "classes": "class code",
}


def _asset_href(layer: str, island: str) -> str:
    return f"{layer}/{_slug(island)}.tif"


def _slug(island: str) -> str:
    return island.lower().replace(" ", "-")


def item_for(spec, island: str, properties: dict, path: Path, *, base_dir: Path,
             companions: dict[str, Path] | None = None) -> pystac.Item:
    """One STAC item: a single layer for a single island, plus everything about it.

    Asset hrefs are set ABSOLUTE here and made relative by `save()` once every item
    knows its final location. Writing them relative to the catalogue root instead
    looks right and validates clean, but resolves to nothing: an item that lands in
    `buildings-dated/buildings-dated-tenerife/` and carries the href
    `buildings-dated/tenerife.tif` points at
    `buildings-dated/buildings-dated-tenerife/buildings-dated/tenerife.tif`. STAC
    schemas do not check that an href resolves, so validation passed for it.
    """
    # Everything geometric is read from the written file rather than from the
    # in-memory arrays, so an item can be rebuilt from disk alone. That is what
    # lets a partial build re-catalogue the layers it did NOT rebuild instead of
    # dropping them from the catalogue entirely.
    with rasterio.open(path) as src:
        shape = [src.height, src.width]
        transform = list(src.transform)[:6]
        epsg = src.crs.to_epsg() if src.crs else None
        dtypes = src.dtypes
        nodata = src.nodata
        descriptions = src.descriptions
        bounds = tuple(src.bounds)
    item = pystac.Item(
        id=f"{spec.name}-{_slug(island)}",
        geometry=mapping(box(*bounds)),
        bbox=list(bounds),
        datetime=None,
        start_datetime=_dt(spec.start),
        end_datetime=_dt(spec.end),
        properties={
            "title": f"{spec.title} — {island}",
            "description": spec.description,
            "island": island,
            # Our own vocabulary, kept under one prefix so it is obviously not STAC.
            "sensisat:layer": spec.name,
            "sensisat:measure": spec.measure,
            "sensisat:encoding": spec.encoding,
            "sensisat:sources": spec.sources,
            "sensisat:statistics": _jsonable(properties),
            # processing extension (community): how this file came to exist.
            "processing:level": "L4",
            "processing:lineage": _lineage(spec, properties),
            "processing:software": {"sensisat": _version()},
        },
    )
    item.stac_extensions.append(PROCESSING_EXT)

    proj = ProjectionExtension.ext(item, add_if_missing=True)
    proj.code = f"EPSG:{epsg}" if epsg else None
    proj.shape = shape
    proj.transform = transform
    proj.bbox = list(bounds)

    asset = pystac.Asset(
        href=str(Path(path).resolve()),
        media_type=pystac.MediaType.COG,
        roles=["data"],
        title=spec.title,
    )
    item.add_asset("data", asset)

    # Companions are published beside the layer and belong in the same item, so a
    # reader can find them without knowing our file-naming convention.
    for key, companion_path in (companions or {}).items():
        item.add_asset(key, pystac.Asset(
            href=str(Path(companion_path).resolve()),
            media_type=pystac.MediaType.COG,
            roles=["metadata"],
            title=f"{spec.title} — {key}",
        ))

    unit = UNITS.get(spec.encoding, "")
    bands = []
    for i in range(len(dtypes)):
        band = RasterBand.create(
            data_type=DataType(dtypes[i]),
            nodata=nodata,
            spatial_resolution=spec.resolution_m,
            unit=unit,
        )
        # `description` is not a constructor argument in pystac's RasterBand, but it
        # is a valid field of the raster extension, so it is set on the underlying
        # properties. It is what tells a reader that band 2 holds provenance codes
        # rather than a second set of years.
        band.properties["description"] = descriptions[i] or spec.title
        bands.append(band)
    RasterExtension.ext(asset, add_if_missing=True).bands = bands

    classes = _classes_for(spec, properties)
    if classes:
        ClassificationExtension.ext(asset, add_if_missing=True).classes = classes
    return item


def _classes_for(spec, properties: dict) -> list[Classification] | None:
    """Class tables for the layers whose values are codes rather than quantities."""
    if spec.encoding == "year first built":
        return PROVENANCE_CLASSES
    if spec.encoding == "classes":
        table = properties.get("classes", {})
        return [Classification.create(value=int(v), description=str(d), name=_class_name(str(d)))
                for v, d in table.items()]
    return None


def _lineage(spec, properties: dict) -> str:
    """A sentence a human can read saying how the file was made, with its caveats."""
    parts = [f"Built from {', '.join(spec.sources)} on SensiSat's shared "
             f"{spec.resolution_m} m grid, clipped to the island boundary."]
    for key in ("caveat", "note", "why_native", "never_do", "why_this_layer_exists"):
        if key in properties:
            parts.append(str(properties[key]))
    if properties.get("greenhouse_masked"):
        parts.append(
            f"Covered agriculture removed (crop survey "
            f"{properties.get('greenhouse_survey_year', 'n/a')}); it is published "
            f"separately as covered-agriculture, so the removal is reversible."
        )
    return " ".join(parts)


def collection_for(spec, items: list[pystac.Item]) -> pystac.Collection:
    """One collection per layer, spanning every island built for it."""
    bboxes = [item.bbox for item in items]
    spatial = pystac.SpatialExtent([[
        min(b[0] for b in bboxes), min(b[1] for b in bboxes),
        max(b[2] for b in bboxes), max(b[3] for b in bboxes),
    ]])
    temporal = pystac.TemporalExtent([[_dt(spec.start), _dt(spec.end)]])
    collection = pystac.Collection(
        id=spec.name,
        title=spec.title,
        description=spec.description,
        extent=pystac.Extent(spatial, temporal),
        license=LICENSES.get(spec.sources[0], "other"),
        extra_fields={
            "sensisat:measure": spec.measure,
            "sensisat:encoding": spec.encoding,
            "sensisat:resolution_m": spec.resolution_m,
            "sensisat:sources": spec.sources,
        },
    )
    for item in items:
        collection.add_item(item)
    return collection


def build_catalog(collections: list[pystac.Collection]) -> pystac.Catalog:
    catalog = pystac.Catalog(id=CATALOG_ID, title=CATALOG_TITLE, description=CATALOG_DESCRIPTION)
    for collection in collections:
        catalog.add_child(collection)
    return catalog


def save(catalog: pystac.Catalog, dest: Path) -> Path:
    """Write the catalogue next to the data, with relative links.

    Self-contained and relative so the whole `data/processed/` tree can be copied
    to any static host and keep working — which is the M4 deployment, in advance.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    catalog.normalize_hrefs(str(dest))
    catalog.make_all_asset_hrefs_relative()
    catalog.save(catalog_type=pystac.CatalogType.SELF_CONTAINED)
    return dest / "catalog.json"


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("sensisat")
    except Exception:
        return "0.1.0"


def _jsonable(obj):
    """Numpy scalars and dict keys that json.dump would refuse."""
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "item") and getattr(obj, "shape", None) == ():
        return obj.item()
    if isinstance(obj, Path):
        return str(obj)
    return obj


def load(dest: Path) -> pystac.Catalog:
    return pystac.Catalog.from_file(str(Path(dest) / "catalog.json"))


def summary(dest: Path) -> str:
    """What the catalogue contains, for the build log."""
    catalog = load(dest)
    lines = []
    for collection in catalog.get_children():
        items = list(collection.get_items())
        lines.append(f"  {collection.id:22s} {len(items):2d} islands  {collection.extra_fields.get('sensisat:measure','')}")
    return "\n".join(lines)
