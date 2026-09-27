"""The viewer's counting module, checked from the gate that actually runs.

`viewer/count.js` holds the arithmetic behind the readout — which regime answers a
view, how a window of pixels becomes square kilometres, how published island figures
are summed. It is JavaScript because it has to run in the browser, and rewriting it
in Python to test it would create exactly the second implementation decision 7
forbids (`tests/test_api_parity.py` enforces the same rule for `stats.zonal()`).

So the tests live beside it, in `viewer/count.test.js`, and this file is the bridge
that makes them part of `pytest` rather than a command someone has to remember. Two
kinds of check live here:

1. **Constants that exist in both languages** are compared directly. A duplicated
   constant that drifts is silent by construction: the map keeps drawing, the numbers
   are merely wrong.
2. **The JavaScript suite itself** is run, and a failure fails `pytest`. A test that
   only runs when someone types `npm test` is not part of the lifecycle, and
   `scripts/build.py` and `scripts/publish.py` check an exit code, so a check they
   never reach cannot stop anything.

**Node is required, not optional.** If it is missing these tests FAIL rather than
skip. A skipped check is not a passed check (CLAUDE.md #11) — and a skip would make
`pytest` exit 0, which is the one thing the gates read. Node is already required to
build the bundle, so this adds no dependency the release path did not already have.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess

import pytest

from sensisat.config import EARTH_EQUATORIAL_M_PER_DEG, ROOT
from sensisat.encoding import UNDATED, YEAR_OFFSET
from sensisat.grid import PIXEL_DEG
from sensisat.layers import LAYERS

COUNT_JS = ROOT / "viewer" / "count.js"

# The latitude the crossover is quoted at. The archipelago spans 27.5-29.6 degN and a
# pixel's east-west size follows cos(latitude), so the figure has to name a latitude
# to mean anything at all.
CROSSOVER_LAT = 28.0
CROSSOVER_KM = 2.0


def _const(name: str) -> int:
    """Read an integer constant out of count.js, underscores and all."""
    text = COUNT_JS.read_text()
    match = re.search(rf"^export const {name} = ([0-9_]+);", text, re.MULTILINE)
    assert match, f"{name} is not exported from {COUNT_JS.name}"
    return int(match.group(1).replace("_", ""))


def test_the_year_encoding_is_the_same_number_in_both_languages():
    """A stored value is `year - 1899`. Two copies of that is two chances to be wrong.

    The failure is silent: the map still draws, the slider still moves, and every
    year is simply off by however much the two definitions disagree.
    """
    assert _const("YEAR_OFFSET") == YEAR_OFFSET
    assert _const("UNDATED") == UNDATED


def test_the_crossover_is_a_block_budget_that_matches_the_published_tiling():
    """The budget is in blocks, and the blocks are the ones the build writes.

    A Cloud-Optimized GeoTIFF stores fixed square tiles and a reader cannot fetch
    less than one, so the cost of a count is paid per block, not per pixel on screen.
    Measured on the published mosaic: a 3.2 km view (82,364 px, 4 blocks) and a
    12.6 km view (1,317,818 px, 6 blocks) both took about 280 ms.

    This pins the budget to a view width, so it cannot quietly stop meaning what the
    design decided. If `mosaic_blocksize` is ever changed, the same number of blocks
    covers a different amount of ground, and that is exactly what should fail here.
    """
    budget = _const("NEAR_MAX_BLOCKS")
    block = LAYERS["buildings-dated"].mosaic_blocksize
    assert block == 1024, "the measurements behind NEAR_MAX_BLOCKS assume 1024"

    ew_m = PIXEL_DEG * EARTH_EQUATORIAL_M_PER_DEG * math.cos(math.radians(CROSSOVER_LAT))
    # A square view of `budget` blocks, in the worst case where none is shared.
    side_km = math.sqrt(budget) * block * ew_m / 1000
    assert 15 <= side_km <= 35, (
        f"{budget} blocks of {block} px is about a {side_km:.1f} km view at "
        f"{CROSSOVER_LAT} degN, which is not the 'most of an island' the design chose"
    )


def test_every_layer_with_a_near_path_is_tiled_small_enough_to_count():
    """A layer written in huge blocks could never be counted at any useful zoom.

    density-trend is deliberately 256 (10-band pixel-interleaved, so a 1024 tile
    would inflate 20 MB to read one epoch) and is far-only anyway. The rest must stay
    at a size where a handful of blocks covers a real view.
    """
    for name, spec in LAYERS.items():
        assert spec.mosaic_blocksize <= 1024, f"{name} is tiled too coarsely to count"


def test_the_viewer_unit_tests_run_as_part_of_this_suite():
    """Run `node --test` over viewer/ and fail this suite if anything there fails.

    This is the whole reason the file exists. Without it `viewer/count.test.js` is a
    command someone has to remember, and the documented gate — `pytest && ruff check .`
    — would report success while the arithmetic behind every published number on the
    map went unchecked.
    """
    node = shutil.which("node")
    if node is None:
        pytest.fail(
            "node is not on PATH, so the viewer's tests cannot run. This FAILS rather "
            "than skips on purpose: a skip exits 0, and the build and publish gates "
            "read nothing but the exit code. Install node (it is already needed for "
            "`npm run build`) and run again."
        )
    result = subprocess.run(
        [node, "--test", "--test-reporter=tap"],
        cwd=ROOT / "viewer", capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "the viewer's counting tests failed:\n"
        + "\n".join(line for line in result.stdout.splitlines()
                    if line.startswith(("not ok", "  ---", "    ")))[:4000]
    )


def test_the_shipped_pixel_area_table_agrees_with_the_function_it_came_from():
    """The viewer's ground areas must be the build's ground areas, to the last digit.

    This is the cross-language half of CLAUDE.md #2. The table is generated from
    `raster.row_areas_m2` and interpolated in JavaScript, and those are two different
    pieces of code in two different languages — so the check runs the real JS
    lookup over the real shipped table and compares it against the real Python
    function at the same latitudes.

    What it would catch: a viewer that assumes a "10 m" pixel is 100 m2 lands ~13 %
    high, which is a wrong number that looks entirely reasonable on a map.
    """
    import json
    import sys

    import numpy as np
    from rasterio.transform import Affine

    sys.path.insert(0, str(ROOT / "scripts"))
    from publish import pixel_area_table

    from sensisat.raster import row_areas_m2

    table = pixel_area_table()
    # Latitudes deliberately off the sample points, including both ends and beyond
    # them, because the edges are where an interpolation is wrong.
    lats = [27.5, 27.53, 27.87, 28.0, 28.049, 28.5, 29.111, 29.6]

    script = (
        "import {pixelAreaM2} from './count.js';"
        f"const t = {json.dumps(table)};"
        f"const lats = {json.dumps(lats)};"
        "console.log(JSON.stringify(lats.map((l) => pixelAreaM2(t, l))));"
    )
    result = subprocess.run(
        [shutil.which("node") or "node", "--input-type=module", "-e", script],
        cwd=ROOT / "viewer", capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    from_js = json.loads(result.stdout)

    for lat, js in zip(lats, from_js, strict=True):
        # A one-row raster whose single row CENTRE sits exactly on `lat`.
        transform = Affine(PIXEL_DEG, 0.0, 0.0, 0.0, -PIXEL_DEG, lat + PIXEL_DEG / 2)
        truth = float(row_areas_m2((1, 1), transform)[0, 0])
        assert np.isclose(js, truth, rtol=1e-5), (
            f"at {lat} degN the viewer would use {js:.4f} m2 and the build uses "
            f"{truth:.4f} m2"
        )


def test_the_table_is_small_enough_to_ship_on_every_page_load():
    """It rides in index.json, which is on the critical path (guardrail G2).

    The whole reason a 0.1-degree step is enough is that the quantity is smooth; if
    someone later "improves" accuracy by sampling finely, this says what it costs.
    """
    import json
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from publish import pixel_area_table

    payload = json.dumps(pixel_area_table(), separators=(",", ":"))
    assert len(payload) < 2048, f"the pixel-area table is {len(payload)} bytes"
