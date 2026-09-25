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

from sensisat.config import EARTH_EQUATORIAL_M_PER_DEG, EARTH_MERIDIONAL_M_PER_DEG, ROOT
from sensisat.encoding import UNDATED, YEAR_OFFSET
from sensisat.grid import PIXEL_DEG

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


def test_the_crossover_really_is_the_two_kilometre_view_it_claims_to_be():
    """The budget is in pixels; the decision was in kilometres. They must agree.

    A pixel is 8.983e-05 degrees on both axes, which at 28 degN is 9.98 m north-south
    and 8.83 m east-west (CLAUDE.md #2 — never assume 10). A 2 km square view is
    therefore about 226 x 200 = 45,379 pixels. If someone later retunes the budget
    for speed without revisiting the decision, this is what notices.
    """
    ns_m = PIXEL_DEG * EARTH_MERIDIONAL_M_PER_DEG
    ew_m = PIXEL_DEG * EARTH_EQUATORIAL_M_PER_DEG * math.cos(math.radians(CROSSOVER_LAT))
    expected = (CROSSOVER_KM * 1000 / ew_m) * (CROSSOVER_KM * 1000 / ns_m)

    budget = _const("NEAR_MAX_PIXELS")
    ratio = budget / expected
    assert 1.0 <= ratio <= 1.05, (
        f"NEAR_MAX_PIXELS is {budget:,}, which is {math.sqrt(ratio) * CROSSOVER_KM:.2f} km "
        f"square at {CROSSOVER_LAT} degN, not the {CROSSOVER_KM} km the design decided on"
    )


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
        [node, "--test", "--test-reporter=tap", "count.test.js"],
        cwd=ROOT / "viewer", capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        "the viewer's counting tests failed:\n"
        + "\n".join(line for line in result.stdout.splitlines()
                    if line.startswith(("not ok", "  ---", "    ")))[:4000]
    )
