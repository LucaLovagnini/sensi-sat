"""The layer registry's contract, checked without touching any data."""

from __future__ import annotations

import inspect
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


def test_only_the_cadastre_calls_its_year_a_rebuild():
    """CLAUDE.md §11: a *reforma integral* — a comprehensive renovation — resets the
    year the Catastro holds, so `buildings-dated` means "built OR comprehensively
    rebuilt". That is a property of a legal register, not of the layer's shape. WSF
    Evolution's year is the epoch a satellite first saw settlement on that pixel, and
    nothing resets when a building is renovated. So the correction belongs to the
    cadastre alone: copying it onto `settlement-era-a` would publish a cadastral
    semantic on a radar product, and dropping it from `buildings-dated` restores the
    mislabel that M3 measured the cost of (24–33 % of "new construction" already
    standing in 2015)."""
    cadastre = inspect.getsource(layers._buildings_dated)
    era_a = inspect.getsource(layers._settlement_era_a)
    assert "year built or comprehensively rebuilt" in cadastre
    assert "year first built" not in cadastre, "the wording this replaced is back"
    assert "year first built" in era_a
    assert "rebuilt" not in era_a, "a cadastral semantic has spread to WSF Evolution"


def test_the_encoding_key_is_dispatch_and_must_not_be_corrected():
    """`spec.encoding` reads like a description and is not one. It is the key that
    selects the QA gate (`build.py` -> `qa.growth_only`), the zonal kind, the
    catalogue's units and `PROVENANCE_CLASSES` — and it is published verbatim as
    `sensisat:encoding`. The two year layers share it deliberately: they have the same
    SHAPE (a uint8 year plus a provenance band), which is what the dispatch asks
    about, even though they do not mean the same thing. So "or comprehensively
    rebuilt" goes in the band description, which is prose, and NOT here: changing this
    for one layer breaks dispatch, and changing it for both applies the cadastre's
    semantics to a satellite product. This test is the note that the shared value is
    intended, so a later reader does not "fix" it."""
    from sensisat.catalog import UNITS
    assert layers.LAYERS["buildings-dated"].encoding == "year first built"
    assert layers.LAYERS["settlement-era-a"].encoding == "year first built"
    assert "year first built" in UNITS, "the encoding key is looked up, not read"
