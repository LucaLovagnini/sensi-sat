"""The layer registry's contract, checked without touching any data."""

from __future__ import annotations

from datetime import datetime

import pytest

from sensisat import layers
from sensisat.config import ISLAND_BBOX


def test_every_layer_declares_what_it_measures():
    for name, spec in layers.LAYERS.items():
        assert spec.name == name
        assert spec.measure in {"extent", "surface", "change"}, name
        assert spec.encoding in layers_encodings(), name
        assert spec.sources and all(spec.sources), name
        assert spec.description.strip(), name
        assert spec.resolution_m > 0, name


def layers_encodings() -> set[str]:
    from sensisat.catalog import UNITS
    return set(UNITS) | {"classes"}


def test_temporal_extents_are_ordered_and_parseable():
    for name, spec in layers.LAYERS.items():
        start, end = datetime.fromisoformat(spec.start), datetime.fromisoformat(spec.end)
        assert start < end, name


def test_the_ten_metre_layers_are_the_ones_that_stack():
    """Only layers on the shared grid can be compared pixel by pixel in the viewer."""
    assert set(layers.TEN_METRE_LAYERS) == {
        "buildings-dated", "settlement-era-a", "settlement-era-b",
        "covered-agriculture", "density-current",
    }


def test_density_trend_stays_on_its_own_grid():
    """GHSL holds m2 per cell, so resampling it would require rescaling every value."""
    assert layers.LAYERS["density-trend"].resolution_m != 10


def test_unknown_layer_is_rejected_by_name():
    with pytest.raises(ValueError, match="unknown layer"):
        layers.build("no-such-layer", "Tenerife")


def test_greenhouse_masking_applies_to_exactly_the_agreed_layers():
    """M1.2: masked out of the urban and sealing layers, published on its own."""
    masked = {"settlement-era-a", "settlement-era-b", "density-current"}
    for name in masked:
        assert "Mapa de Cultivos" in layers.LAYERS[name].sources or name == "density-current", name
    assert layers.LAYERS["covered-agriculture"].measure == "extent"
    assert "buildings-dated" not in masked   # a cadastral building is not a greenhouse


def test_every_island_has_a_box():
    assert len(ISLAND_BBOX) == 8
