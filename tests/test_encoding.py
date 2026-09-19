"""The year encoding — the contract every era-a implementation has to honour."""

from __future__ import annotations

import numpy as np

from sensisat import encoding as enc


def test_roundtrip_preserves_years():
    years = np.array([1900, 1985, 2015, 2020, 2099])
    assert list(enc.decode_year(enc.encode_year(years))) == list(years)


def test_zero_means_not_built_not_year_zero():
    assert enc.encode_year(np.array([0]))[0] == enc.NOT_BUILT
    assert enc.decode_year(np.array([enc.NOT_BUILT], dtype="uint8"))[0] == 0


def test_years_outside_the_range_are_clamped_not_wrapped():
    """uint8 arithmetic would silently wrap 1899 to 255, which is the UNDATED code."""
    assert enc.encode_year(np.array([1850]))[0] == enc.YEAR_MIN - enc.YEAR_OFFSET
    assert enc.encode_year(np.array([2200]))[0] == enc.YEAR_MAX - enc.YEAR_OFFSET
    assert enc.encode_year(np.array([1850]))[0] != enc.UNDATED


def test_undated_is_built_but_never_dated():
    arr = np.array([enc.UNDATED], dtype="uint8")
    assert enc.built_by(arr, None)[0]          # something is there
    assert not enc.built_by(arr, 2020)[0]      # but we cannot say it was there by 2020
    assert enc.decode_year(arr)[0] == -1


def test_merge_keeps_the_older_year():
    a = enc.encode_year(np.array([2000, 0, 1990]))
    b = enc.encode_year(np.array([1980, 1995, 0]))
    assert list(enc.decode_year(enc.merge_oldest(a, b))) == [1980, 1995, 1990]


def test_merge_does_not_let_not_built_win():
    """NOT_BUILT is 0, the smallest value, so a plain minimum would erase every year."""
    a = enc.encode_year(np.array([1950]))
    b = np.array([enc.NOT_BUILT], dtype="uint8")
    assert enc.decode_year(enc.merge_oldest(a, b))[0] == 1950
    assert enc.decode_year(enc.merge_oldest(b, a))[0] == 1950


def test_merge_lets_a_dated_pixel_beat_an_undated_one():
    dated = enc.encode_year(np.array([2010]))
    undated = np.array([enc.UNDATED], dtype="uint8")
    assert enc.decode_year(enc.merge_oldest(dated, undated))[0] == 2010
    assert enc.decode_year(enc.merge_oldest(undated, dated))[0] == 2010
