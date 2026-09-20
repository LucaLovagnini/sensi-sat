"""The gates: each one must fire on the failure it was written for, and not otherwise."""

from __future__ import annotations

import numpy as np

from sensisat import encoding as enc
from sensisat import qa


def test_totals_gate_accepts_a_definitional_difference():
    """The cadastre is a fifth of CORINE's artificial surfaces. That is not a bug."""
    assert qa.totals_in_band("buildings-dated", "Gran Canaria", 34.1).passed


def test_totals_gate_rejects_a_dynamic_world_sized_inflation():
    """Dynamic World reported 308 km2 for Gran Canaria — twice CORINE's total."""
    gate = qa.totals_in_band("settlement-era-b", "Gran Canaria", 307.8)
    assert not gate.passed
    assert gate.value > 2


def test_totals_gate_skips_islands_too_small_to_police():
    gate = qa.totals_in_band("density-current", "La Graciosa", 0.5)
    assert gate.passed and "too small" in gate.expected


def test_growth_only_gate_catches_an_impossible_year(tiny_transform):
    sane = enc.encode_year(np.array([[1985, 2015], [0, 2000]]))
    assert qa.growth_only("x", "Tenerife", sane).passed

    broken = np.array([[250, 0], [0, 0]], dtype="uint8")   # 250 + 1899 = 2149
    assert not qa.growth_only("x", "Tenerife", broken).passed


def test_growth_only_gate_ignores_the_undated_code(tiny_transform):
    """255 is 'built, year unknown', not the year 2154."""
    arr = np.array([[enc.UNDATED, 116], [0, 0]], dtype="uint8")
    gate = qa.growth_only("x", "Tenerife", arr)
    assert gate.passed and gate.value == 2015


def test_loss_rate_gate_accepts_measured_reality():
    """M0 measured 0.052 %/yr over 2018-2021 from a purpose-built change layer."""
    assert qa.loss_rate("loss-events", "Tenerife", 0.03, 100.0, 3).passed


def test_loss_rate_gate_rejects_a_method_change():
    """Copernicus's own status layers imply 30 km2 'lost' between releases."""
    gate = qa.loss_rate("loss-events", "Tenerife", 30.0, 215.0, 3)
    assert not gate.passed


def test_loss_rate_gate_whitelists_the_eruption():
    """Tajogaite really did bury Todoque; the loss layer exists to show it."""
    assert qa.loss_rate("loss-events", "La Palma", 30.0, 215.0, 3).passed


def test_agreement_gate_uses_iou_not_plain_agreement():
    """95 % of pixels are 'neither built', so plain agreement would pass anything."""
    ours = np.zeros((100, 100), bool)
    ours[0:10, 0:10] = True
    theirs = np.zeros((100, 100), bool)
    theirs[50:60, 50:60] = True
    assert (ours == theirs).mean() > 0.95      # plain agreement would say 98 %
    assert not qa.agreement("x", "Tenerife", ours, theirs).passed
    assert qa.agreement("x", "Tenerife", ours, ours).passed


def test_grid_alignment_gate_catches_a_slip():
    from rasterio.transform import Affine

    from sensisat.grid import for_island

    transform, shape = for_island("La Gomera")
    good = qa.grid_alignment("La Gomera", {"a": (transform, shape), "b": (transform, shape)})
    assert all(g.passed for g in good)

    slipped = transform * Affine.translation(0.5, 0)
    bad = qa.grid_alignment("La Gomera", {"a": (transform, shape), "b": (slipped, shape)})
    assert not any(g.passed for g in bad)


def test_a_skipped_gate_is_not_counted_as_a_pass():
    """A check that did not run must not inflate the score.

    The build once reported "217/217 gates passed" when 49 of those had never run —
    28 of them the lava control, which is on Lanzarote and can say nothing about
    the other seven islands. That claims more assurance than the build has.
    """
    ran = qa.totals_in_band("buildings-dated", "Gran Canaria", 34.1)
    did_not = qa.negative_control("x", "Tenerife", np.zeros((4, 4), bool), None)

    assert not ran.skipped
    assert did_not.skipped and did_not.passed      # passed, but only vacuously

    passed, measured, skipped = qa.summarise([ran, did_not])
    assert (passed, measured, skipped) == (1, 1, 1)
    assert "SKIP" in str(did_not)


def test_an_unavailable_negative_control_fails_rather_than_skipping():
    """The distinction that matters: 'does not apply' vs 'could not be checked'.

    Timanfaya is genuinely irrelevant to Tenerife — that is a skip. But a control
    that should apply and cannot be loaded is a failure, because this is the only
    gate that catches settlement hallucinated onto bare lava, and it once skipped
    silently on the one island it applies to.
    """
    import sensisat.zones as zones

    original = zones.timanfaya
    try:
        zones.timanfaya = lambda: (_ for _ in ()).throw(LookupError("nominatim returned nothing"))
        gate = qa.negative_control("x", "Lanzarote", np.zeros((4, 4), bool), None)
    finally:
        zones.timanfaya = original

    assert not gate.passed
    assert not gate.skipped
