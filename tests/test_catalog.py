"""The catalogue: does it carry the caveats, and does it validate?"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from rasterio.transform import from_origin

from sensisat import catalog, layers
from sensisat.grid import PIXEL_DEG
from sensisat.raster import write_cog


@pytest.fixture
def built_layer(tmp_path):
    """A minimal buildings-dated layer, written to disk like a real build would."""
    transform = from_origin(-15.5, 28.1, PIXEL_DEG, PIXEL_DEG)
    data = np.zeros((2, 256, 256), "uint8")
    data[0, 10:50, 10:50] = 116           # 2015
    data[1, 10:50, 10:50] = 1             # dated
    built = layers.Built(
        data=data, transform=transform, crs="EPSG:4326",
        band_descriptions=["year first built", "provenance"],
        properties={"footprint_km2": 0.14, "caveat": "demolished buildings vanish"},
    )
    path = write_cog(tmp_path / "test.tif", data, transform, "EPSG:4326",
                     band_descriptions=built.band_descriptions)
    return built, path, tmp_path


def test_item_declares_its_grid_and_bands(built_layer):
    built, path, base = built_layer
    item = catalog.item_for(layers.LAYERS["buildings-dated"], "Gran Canaria",
                            built.properties, path, base_dir=base)
    assert item.properties["proj:code"] == "EPSG:4326"
    assert item.properties["proj:shape"] == [256, 256]
    bands = item.assets["data"].extra_fields["raster:bands"]
    assert len(bands) == 2
    assert bands[1]["description"] == "provenance"


def test_item_carries_the_caveat_into_the_lineage(built_layer):
    """A number without its condition is a number someone will misuse."""
    built, path, base = built_layer
    item = catalog.item_for(layers.LAYERS["buildings-dated"], "Gran Canaria",
                            built.properties, path, base_dir=base)
    assert "demolished buildings vanish" in item.properties["processing:lineage"]
    assert catalog.PROCESSING_EXT in item.stac_extensions


def test_year_layers_publish_their_provenance_classes(built_layer):
    """A reader must be able to learn what 'undated' means without reading our code."""
    built, path, base = built_layer
    item = catalog.item_for(layers.LAYERS["buildings-dated"], "Gran Canaria",
                            built.properties, path, base_dir=base)
    classes = item.assets["data"].extra_fields["classification:classes"]
    described = {c["description"] for c in classes}
    assert "pre-2016, undated" in described


def test_statistics_survive_json_serialisation(built_layer):
    built, path, base = built_layer
    item = catalog.item_for(layers.LAYERS["buildings-dated"], "Gran Canaria",
                            built.properties, path, base_dir=base)
    json.dumps(item.to_dict())          # must not raise on numpy scalars


def test_saved_catalogue_uses_relative_hrefs(built_layer, tmp_path):
    """The whole folder has to be copyable to any static host and still work."""
    built, path, base = built_layer
    item = catalog.item_for(layers.LAYERS["buildings-dated"], "Gran Canaria",
                            built.properties, path, base_dir=base)
    collection = catalog.collection_for(layers.LAYERS["buildings-dated"], [item])
    dest = tmp_path / "out"
    catalog_path = catalog.save(catalog.build_catalog([collection]), dest)
    assert catalog_path.exists()

    text = catalog_path.read_text()
    assert str(tmp_path) not in text, "absolute paths would break on another host"


def test_asset_hrefs_resolve_from_the_item_that_carries_them(built_layer, tmp_path):
    """A valid catalogue is not the same as a usable one.

    STAC schemas check the shape of a document, never whether an href points at
    anything. Hrefs written relative to the catalogue ROOT rather than to the item
    validated clean and resolved into directories that do not exist — an item in
    `buildings-dated/buildings-dated-tenerife/` carrying `buildings-dated/tenerife.tif`
    resolves to `buildings-dated/buildings-dated-tenerife/buildings-dated/tenerife.tif`.
    """
    import pystac

    built, path, base = built_layer
    item = catalog.item_for(layers.LAYERS["buildings-dated"], "Gran Canaria",
                            built.properties, path, base_dir=base)
    collection = catalog.collection_for(layers.LAYERS["buildings-dated"], [item])
    dest = tmp_path / "out"
    catalog.save(catalog.build_catalog([collection]), dest)

    written = pystac.Catalog.from_file(str(dest / "catalog.json"))
    checked = 0
    for child in written.get_children():
        for written_item in child.get_items():
            item_dir = Path(written_item.get_self_href()).parent
            for asset in written_item.assets.values():
                assert not Path(asset.href).is_absolute(), "hrefs must be relative to ship"
                assert (item_dir / asset.href).resolve().exists(), asset.href
                checked += 1
    assert checked


def test_companion_files_are_published_as_their_own_asset(built_layer, tmp_path):
    """The confidence grid is on disk; it has to be findable without guessing names."""
    built, path, base = built_layer
    companion = base / "test.confidence.tif"
    companion.write_bytes(path.read_bytes())

    item = catalog.item_for(layers.LAYERS["density-current"], "Gran Canaria",
                            built.properties, path, base_dir=base,
                            companions={"confidence": companion})
    assert "confidence" in item.assets
    assert item.assets["confidence"].roles == ["metadata"]


def test_a_partial_build_does_not_erase_the_other_layers(built_layer, tmp_path, monkeypatch):
    """Building one layer must not publish a catalogue denying the other six exist.

    This is what a `--layer buildings-dated` run used to do: the catalogue was
    assembled from that run's records alone, so it came out advertising one layer
    out of seven and the viewer's layer picker lost six entries. The catalogue
    describes the folder, so it is built from what is in the folder.
    """
    import rasterio

    built, path, base = built_layer
    published = tmp_path / "processed"
    for name in ("buildings-dated", "covered-agriculture", "density-current"):
        target = published / name / "gran-canaria.tif"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())

    # Catalogue only what a single-layer run would know about...
    items = {}
    for name in ("buildings-dated", "covered-agriculture", "density-current"):
        target = published / name / "gran-canaria.tif"
        with rasterio.open(target):
            pass
        items.setdefault(name, []).append(
            catalog.item_for(layers.LAYERS[name], "Gran Canaria", {}, target, base_dir=published))

    collections = [catalog.collection_for(layers.LAYERS[n], i) for n, i in items.items()]
    dest = tmp_path / "out"
    catalog.save(catalog.build_catalog(collections), dest)

    import pystac
    written = pystac.Catalog.from_file(str(dest / "catalog.json"))
    assert {c.id for c in written.get_children()} == set(items)
