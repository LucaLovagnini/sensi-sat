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
from pathlib import Path

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


def test_the_per_island_asset_is_gone_and_the_per_island_statistics_are_not():
    """The CONTRACT of expand-migrate-contract, done 2026-10-06.

    This test replaces `test_the_index_serves_both_viewers_so_there_is_no_flag_day`,
    whose docstring said deleting it is how this decision gets made deliberately.
    So: it was made. index.json sits at ONE URL every viewer fetches, and between
    2026-09-25 and 2026-10-06 it carried BOTH shapes — `layers[id].asset` for the
    archipelago viewer and `layers[id].islands[island].asset` for the one deployed
    before it — so the data and the bundle could be deployed in either order. On
    2026-10-06 production was verified serving the archipelago viewer (bundle
    byte-identical to the build, `allIslands` present in it and absent from the
    previous one), which left the per-island asset with no reader.

    The DANGEROUS half of this test is the second assertion, not the first. The
    per-island `bbox` and `stats` are not compatibility shims: the far regime sums
    the published figures of the islands a view touches, so deleting the islands
    dict along with the asset would silently empty every zoomed-out readout — the
    2026-09-24 failure again, in the other direction. Asset out, statistics in.
    """
    from publish import runtime_index

    from sensisat.layers import LAYERS
    index = runtime_index()
    assert index["shape"] == "archipelago", "the shape field still advertises the shim"

    stray, missing = [], []
    for name in LAYERS:
        layer = index["layers"].get(name)
        if layer is None:
            continue                      # not built in this checkout
        if not layer.get("asset"):
            missing.append(f"  {name}: no layer-level asset — the viewer draws nothing")
        for island, entry in layer["islands"].items():
            if "asset" in entry:
                stray.append(f"  {name}/{island}: per-island asset survived the contract")
            if "bbox" not in entry or "stats" not in entry:
                missing.append(f"  {name}/{island}: lost bbox or stats — the far regime needs both")
    assert not stray, "\n".join(stray)
    assert not missing, "\n".join(missing)

def test_one_rule_decides_the_island_slug():
    """"Gran Canaria" is stored as gran-canaria.tif, and ONE rule must decide that.

    A second naming rule resolves for the islands whose name happens to match and
    404s for the rest — which is how this was first written, and it gave three of
    eight.

    It used to be asserted on the per-island asset href in index.json. The contract
    of 2026-10-06 removed that href, and the `_slug` import from publish.py with it,
    so the duplication cannot recur there. The rule still decides where the
    catalogue writes items, so that is where it is checked now.
    """
    from sensisat.catalog import _slug
    from sensisat.config import ISLAND_BBOX

    layer_dir = PROCESSED / "buildings-dated"
    if not layer_dir.exists():
        pytest.skip("buildings-dated is not built in this checkout")

    slugs = {_slug(i) for i in ISLAND_BBOX}
    found = {d.name.removeprefix("buildings-dated-")
             for d in layer_dir.iterdir() if d.is_dir()}
    assert found, "no per-island item directories on disk"
    assert found <= slugs, f"item directories no island slug explains: {sorted(found - slugs)}"

    # publish.py must not grow its own copy of the rule again.
    assert "_slug" not in (ROOT / "scripts" / "publish.py").read_text(), (
        "publish.py imports _slug again — it has no per-island paths left to build")


def test_every_item_links_only_to_files_that_are_published():
    """The published catalogue must not link to a build intermediate.

    Found 2026-10-07. Every STAC item named its own island's COG — Tenerife's item
    carried `href: ../tenerife.tif` — while `publish.py` ships one raster per layer,
    `archipelago.tif`. So the published items linked to files the published tree does
    not contain. On the live bucket those links answered 200 only because the objects
    uploaded before the archipelago migration had never been deleted; pruning them as
    orphans, which is what prompted this check, would have 404'd every item at once.

    `assets-resolve` cannot see it. That gate runs inside build.py against
    `data/processed/`, where the intermediates are present by construction — they
    were just written. It proves the catalogue is usable WHERE IT WAS BUILT, which is
    not the claim a reader needs. CLAUDE.md #14 says a valid catalogue is not a usable
    one; this adds that one usable in the source tree is not a published one.

    So the invariant is asserted against the predicate that decides what ships, not
    against a directory listing: no item may resolve to a file `publish.py` would
    leave behind. That holds whether or not dist/ has been assembled.
    """
    import pystac

    from sensisat.catalog import is_build_intermediate

    root = PROCESSED / "catalog.json"
    if not root.exists():
        pytest.skip("no catalogue in this checkout")

    unpublished = []
    checked = 0
    for child in pystac.Catalog.from_file(str(root)).get_children():
        for item in child.get_items():
            item_dir = Path(item.get_self_href()).parent
            for key, asset in item.assets.items():
                target = (item_dir / asset.href).resolve()
                checked += 1
                if is_build_intermediate(target.name):
                    unpublished.append(f"  {item.id}.{key} -> {target.name}")
    assert checked, "no assets found to check"
    assert not unpublished, (
        "published items link to files publish.py does not ship:\n"
        + "\n".join(unpublished[:12]))
