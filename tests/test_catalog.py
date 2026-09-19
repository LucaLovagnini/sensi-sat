"""The catalogue: does it carry the caveats, and does it validate?"""

from __future__ import annotations

import json

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
                            built, path, base_dir=base)
    assert item.properties["proj:code"] == "EPSG:4326"
    assert item.properties["proj:shape"] == [256, 256]
    bands = item.assets["data"].extra_fields["raster:bands"]
    assert len(bands) == 2
    assert bands[1]["description"] == "provenance"


def test_item_carries_the_caveat_into_the_lineage(built_layer):
    """A number without its condition is a number someone will misuse."""
    built, path, base = built_layer
    item = catalog.item_for(layers.LAYERS["buildings-dated"], "Gran Canaria",
                            built, path, base_dir=base)
    assert "demolished buildings vanish" in item.properties["processing:lineage"]
    assert catalog.PROCESSING_EXT in item.stac_extensions


def test_year_layers_publish_their_provenance_classes(built_layer):
    """A reader must be able to learn what 'undated' means without reading our code."""
    built, path, base = built_layer
    item = catalog.item_for(layers.LAYERS["buildings-dated"], "Gran Canaria",
                            built, path, base_dir=base)
    classes = item.assets["data"].extra_fields["classification:classes"]
    described = {c["description"] for c in classes}
    assert "pre-2016, undated" in described


def test_statistics_survive_json_serialisation(built_layer):
    built, path, base = built_layer
    item = catalog.item_for(layers.LAYERS["buildings-dated"], "Gran Canaria",
                            built, path, base_dir=base)
    json.dumps(item.to_dict())          # must not raise on numpy scalars


def test_saved_catalogue_uses_relative_hrefs(built_layer, tmp_path):
    """The whole folder has to be copyable to any static host and still work."""
    built, path, base = built_layer
    item = catalog.item_for(layers.LAYERS["buildings-dated"], "Gran Canaria",
                            built, path, base_dir=base)
    collection = catalog.collection_for(layers.LAYERS["buildings-dated"], [item])
    dest = tmp_path / "out"
    catalog_path = catalog.save(catalog.build_catalog([collection]), dest)
    assert catalog_path.exists()

    text = catalog_path.read_text()
    assert str(tmp_path) not in text, "absolute paths would break on another host"
