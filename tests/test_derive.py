"""The drape: what it is allowed to claim, and what it must refuse to claim."""

from __future__ import annotations

import numpy as np

from sensisat import derive
from sensisat import encoding as enc


def _coarse_years():
    """A 4x4 coarse grid: the left half dated 1990, the right half never dated."""
    years = np.zeros((4, 4), dtype="int32")
    years[:, :2] = 1990
    return years


def test_drape_never_invents_a_footprint(tiny_transform, coarse_transform):
    """A dated coarse pixel must not switch on fine ground no fine product saw.

    This is the property that makes the drape defensible at all: the 30 m product
    decides *when*, never *where*.
    """
    footprint = np.zeros((12, 12), dtype=bool)
    footprint[0:2, 0:2] = True          # only a 2x2 corner is really built
    years, provenance = derive.drape(_coarse_years(), coarse_transform, "EPSG:4326",
                                     footprint, tiny_transform, "EPSG:4326")
    assert (years > 0).sum() == footprint.sum()
    assert not (years > 0)[~footprint].any()
    assert not (provenance > 0)[~footprint].any()


def test_drape_dates_what_it_can_and_flags_what_it_cannot(tiny_transform, coarse_transform):
    footprint = np.ones((12, 12), dtype=bool)
    years, provenance = derive.drape(_coarse_years(), coarse_transform, "EPSG:4326",
                                     footprint, tiny_transform, "EPSG:4326")

    dated = provenance == enc.P_DATED
    undated = provenance == enc.P_UNDATED
    assert dated.sum() + undated.sum() == footprint.sum()

    # The dated half carries the real year, not a nearby one.
    assert set(enc.decode_year(years[dated]).tolist()) == {1990}
    # The undated half is marked, never given a year.
    assert (years[undated] == enc.UNDATED).all()
    assert (enc.decode_year(years[undated]) == -1).all()


def test_undated_pixels_never_appear_in_a_dated_query(tiny_transform, coarse_transform):
    """115 km2 of real settlement has no year; a time slider must not show it early."""
    footprint = np.ones((12, 12), dtype=bool)
    years, _ = derive.drape(_coarse_years(), coarse_transform, "EPSG:4326",
                            footprint, tiny_transform, "EPSG:4326")
    assert enc.built_by(years, 2015).sum() == 72        # only the dated half
    assert enc.built_by(years, None).sum() == 144       # everything, when undated counts


def test_provenance_summary_reports_the_split(tiny_transform, coarse_transform):
    footprint = np.ones((12, 12), dtype=bool)
    _, provenance = derive.drape(_coarse_years(), coarse_transform, "EPSG:4326",
                                 footprint, tiny_transform, "EPSG:4326")
    summary = derive.provenance_summary(provenance, tiny_transform)
    assert summary["dated_share_pct"] == 50.0


def test_apply_mask_removes_only_the_masked_ground():
    arr = np.arange(9, dtype="uint8").reshape(3, 3)
    mask = np.zeros((3, 3), dtype=bool)
    mask[1, 1] = True
    out = derive.apply_mask(arr, mask)
    assert out[1, 1] == 0
    assert out.sum() == arr.sum() - 4
    assert out.dtype == arr.dtype
