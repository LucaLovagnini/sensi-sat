"""stats.series_by_year reads the ENCODED year, as every published layer stores it."""
from __future__ import annotations

import numpy as np

from sensisat import encoding as enc
from sensisat.stats import series_by_year


def test_undated_and_later_pixels_stay_out_of_an_early_year(tiny_transform, zones_gdf):
    # Encoded years: calendar year minus YEAR_OFFSET. 255 is built-but-undated. A
    # raw `<= 1990` comparison would count all three pixels in 1990, because every
    # encoded value is far below 1990.
    arr = np.zeros((10, 10), np.uint8)
    arr[0, 0] = 1985 - enc.YEAR_OFFSET
    arr[0, 1] = 2005 - enc.YEAR_OFFSET
    arr[0, 2] = enc.UNDATED
    df = series_by_year(arr, tiny_transform, "EPSG:4326", zones_gdf, [1990, 2010])
    # The zone is 50 pixels, so one pixel is 2 %. km2 rounds to nothing this small.
    by = dict(zip(df["year"], df["share_pct"], strict=True))
    assert by[1990] == 2.0                              # only the 1985 pixel
    assert by[2010] == 4.0                              # the 2005 one arrives; undated never
