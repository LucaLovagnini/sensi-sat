"""What gets published, and the arithmetic that assembles it.

`scripts/publish.py` turns the per-island statistics the build measured into the
archipelago figures the viewer reads. That sum is not a simple addition, and the
tests here exist because it was wrong in a way nothing else could see.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from sensisat.config import PROCESSED, ROOT

sys.path.insert(0, str(ROOT / "scripts"))
from publish import CUMULATIVE_SERIES, _sum_cumulative, archipelago_stats  # noqa: E402

needs_build = pytest.mark.skipif(
    not (PROCESSED / "index.json").exists(),
    reason="run scripts/build.py --all and scripts/publish.py first")

#: Three islands with series of different lengths — the shape that broke it.
UNEVEN = [
    {"2024": 1, "2025": 2, "2026": 3},      # records new building every year
    {"2024": 10, "2025": 20},               # nothing new in 2026
    {"2024": 100},                          # nothing new since 2024
]


def test_a_running_total_carries_forward_when_an_island_stops_recording():
    """The defect, at fixture size.

    A published per-island series ends at that island's last recorded construction.
    Adding only the islands that HAVE an entry for a year silently drops the rest,
    so the archipelago total FALLS — 93.87 km2 at 2026 against 102.96 at 2025, with
    Fuerteventura's 7.622 and La Gomera's 1.522 simply absent.

    An island with no new building in 2026 still has all the ones it had in 2025.
    """
    assert _sum_cumulative(UNEVEN) == {"2024": 111.0, "2025": 122.0, "2026": 123.0}


def test_a_cumulative_sum_can_never_decrease():
    """The invariant that would have caught it without anyone noticing the shape."""
    out = _sum_cumulative(UNEVEN)
    values = [out[k] for k in sorted(out, key=float)]
    assert values == sorted(values), f"a running total went down: {values}"


def test_a_per_period_series_is_not_carried_forward():
    """Gains and losses per period are NOT a running total.

    `change_km2` holds what happened during each period. Carrying it forward would
    invent a repeat of the previous period's construction, which is the opposite
    error and just as invisible.
    """
    assert "change_km2" not in CUMULATIVE_SERIES
    out = archipelago_stats({
        "a": {"stats": {"change_km2": {"2018-2021": {"new_cover_km2": 1.0}}}},
        "b": {"stats": {"change_km2": {"2021-2024": {"new_cover_km2": 2.0}}}},
    })
    assert out["change_km2"] == {"2018-2021": {"new_cover_km2": 1.0},
                                 "2021-2024": {"new_cover_km2": 2.0}}


def test_the_javascript_and_python_sums_agree():
    """Two implementations of one rule, so they are checked against each other.

    The viewer sums islands in the browser (`count.js`) and the build sums them for
    `index.json` (`publish.py`). Both are needed — one runs where there is no Python,
    the other where there is no browser — so the guard is parity, the same guard
    `tests/test_api_parity.py` puts on `stats.zonal()`.
    """
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is not on PATH; this FAILS rather than skips (CLAUDE.md #11)")

    islands = {chr(97 + i): {"stats": {"extent_by_year": s}} for i, s in enumerate(UNEVEN)}
    script = (
        "import {sumStats} from './count.js';"
        f"const per = {json.dumps([{'extent_by_year': s} for s in UNEVEN])};"
        "console.log(JSON.stringify(sumStats(per).extent_by_year));"
    )
    result = subprocess.run([node, "--input-type=module", "-e", script],
                            cwd=ROOT / "viewer", capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    from_js = {k: float(v) for k, v in json.loads(result.stdout).items()}
    from_py = {k: float(v) for k, v in archipelago_stats(islands)["extent_by_year"].items()}
    assert from_js == from_py, f"js {from_js} != python {from_py}"


@needs_build
def test_every_published_running_total_rises():
    """The same invariant, over what is actually published.

    A fixture proves the function; this proves the file a reader will be served.
    """
    index = json.loads((PROCESSED / "index.json").read_text())
    problems = []
    for name, layer in index["layers"].items():
        for series in CUMULATIVE_SERIES:
            values = layer.get("stats", {}).get(series)
            if not isinstance(values, dict):
                continue
            ordered = [values[k] for k in sorted(values, key=float)]
            for before, after in zip(ordered, ordered[1:], strict=False):
                if after < before - 1e-9:
                    problems.append(f"  {name}.{series}: {before} -> {after}")
                    break
    assert not problems, "a published running total decreases:\n" + "\n".join(problems)
