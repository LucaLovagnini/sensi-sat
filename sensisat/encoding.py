"""How a "year first built" raster stores its values, and what each state means.

This is deliberately its own module rather than a constant inside one adapter,
because decision M1.1 makes the pre-2016 era a *plug-in*: the Canaries are carried
by the cadastre, anywhere without a cadastre is carried by WSF Evolution. Two
implementations of the same slot can only be interchangeable if a viewer reading
one cannot tell which produced it, and that means one encoding, defined once.

    0          not built
    1..200     the year it was first built, offset by 1899 (1 = 1900, 121 = 2020)
    255        built, but the year is unknown

**Why 255 exists.** Two different sources arrive with the same problem from
opposite directions. The cadastre has 1.3 % of buildings whose date field is
malformed. WSF Evolution can only date 57 % of the 10 m footprint that existed in
2016, leaving 115 km2 of real settlement with no year. In both cases the honest
answer is "something is here and I cannot tell you when" - which is a third state,
not a missing value and not a guess. A viewer draws it in its own colour and a
time slider simply never switches it on.

**Why uint8 and not a year.** One byte per pixel keeps the published layers in the
single-digit megabytes for the whole archipelago, which is the property that lets
SensiSat be a set of static files with no tile server. The offset of 1899 buys the
range 1900-2099, which covers the cadastre's full span with room to spare.
"""

from __future__ import annotations

import numpy as np

YEAR_OFFSET = 1899
YEAR_MIN, YEAR_MAX = 1900, 2099
NOT_BUILT = 0
UNDATED = 255
DTYPE = "uint8"

# Provenance is a second band answering "where did this pixel's year come from?".
# It is what lets the map say `pre-2016 undated` in its own colour instead of
# quietly folding unknowns into a year nobody measured.
# Exactly three states, because exactly three occur. A fourth was defined here at
# first ("dated by a later epoch source") and never emitted by anything — which
# would have published, in every catalogue entry, a class no pixel can carry.
PROVENANCE = {
    0: "not built",
    1: "dated by the source",
    2: "pre-2016, undated",
}
P_NOT_BUILT, P_DATED, P_UNDATED = 0, 1, 2


def encode_year(year: np.ndarray | int) -> np.ndarray:
    """Calendar years to stored values, clamped to the representable range."""
    y = np.asarray(year)
    return np.where(y <= 0, NOT_BUILT,
                    np.clip(y, YEAR_MIN, YEAR_MAX) - YEAR_OFFSET).astype(DTYPE)


def decode_year(arr: np.ndarray) -> np.ndarray:
    """Stored values back to calendar years: 0 not built, -1 built but undated."""
    year = np.where(arr == NOT_BUILT, 0, arr.astype("int32") + YEAR_OFFSET)
    return np.where(arr == UNDATED, -1, year)


def built_by(arr: np.ndarray, year: int | None = None) -> np.ndarray:
    """Boolean "was built by `year`".

    Undated pixels are counted when asking "is anything here" (`year=None`) and
    excluded from any dated question, because claiming they existed by a given
    year would be inventing the fact the encoding exists to avoid inventing.
    """
    if year is None:
        return arr > NOT_BUILT
    return (arr > NOT_BUILT) & (arr != UNDATED) & (arr <= year - YEAR_OFFSET)


def merge_oldest(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Combine two encoded rasters, keeping the earlier evidence per pixel.

    A plain `minimum` would be wrong in one specific way: NOT_BUILT is 0, the
    smallest value, so it would win against every real year. Zero has to mean
    "absent" rather than "very early", so it is handled before the comparison.
    UNDATED at 255 needs no special case - it is the largest value, so any dated
    pixel beats it, which is exactly right.
    """
    out = np.where(a == NOT_BUILT, b, a)
    both = (a > NOT_BUILT) & (b > NOT_BUILT)
    return np.where(both, np.minimum(a, b), out).astype(DTYPE)
