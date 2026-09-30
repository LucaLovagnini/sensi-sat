"""The viewer's near path against the layers we actually publish.

Every other test of the counting module runs on a synthetic fixture small enough
that the right answer is worked out by hand. That is the correct place to pin a
rule, but it leaves a gap: nothing had ever run the browser's arithmetic over a
real published raster and compared it against the figure the build wrote. The two
are different implementations, in different languages, of one rule —

    near path  : count the full-resolution pixels in the window (count.js, in the
                 browser, below the crossover)
    published  : what build.py measured and publish.py wrote into index.json

— and decision 7 says a second implementation is only allowed while something
proves it is not a second ANSWER. On fixtures it was proved. On the published
layers it was not.

**What "near path" means.** Below roughly a 25 km view the viewer stops summing
per-island totals and reads the real pixels through geotiff.js: it decodes the
window at full resolution, adds up the ground area held by each stored value, and
reads the year series off that histogram. "Extent" here is the ground area of
pixels *containing* a building, not building footprint — the two are different
quantities (CLAUDE.md #3) and only the first is what these layers store.

**The tolerance is the published rounding, not a fudge factor.** `index.json`
stores areas to three decimal places, so 0.887 km² means the true value is within
0.0005 km² of it, and no comparison against a published figure can be tighter than
that. Every one of the six layer-island pairs checked here lands at exactly that
boundary — which is what agreement looks like, not what drift looks like. See
`TOLERANCE_KM2` for the one case that needs a hair more and why.

**What is covered.** Three layers across the two encodings we publish — the
cadastre's years, WSF Evolution's years draped to 10 m, and WSF Tracker's
observation epochs — over two islands whose bounding boxes hold no other island.
The percentage and change layers have no near path at all by design
(`FAR_ONLY_KINDS`), so there is nothing to compare for them.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
import rasterio

from sensisat.config import PROCESSED, ROOT

needs_build = pytest.mark.skipif(
    not (PROCESSED / "index.json").exists(),
    reason="run scripts/build.py --all and scripts/publish.py first")

#: Islands whose bounding box holds no other island, so a rectangular window over
#: that box counts that island and nothing else. See the bbox test below, which is
#: what keeps this list honest if the boxes ever move.
ISOLATED = ["El Hierro", "La Palma"]

#: The series each encoding publishes, and the argument `statsFromHistogram` wants.
#: A layer stores either a YEAR per pixel (the cadastre and WSF Evolution: "first
#: built in 1994") or an EPOCH index (WSF Tracker: "first seen in observation
#: window 3"), and the two are read off the same histogram by different keys.
SERIES = {"year": ("extent_by_year", "years"), "epoch": ("extent_by_epoch", "epochs")}

#: How far the near path may sit from a published figure.
#:
#: `index.json` stores areas to three decimals, so a *correct* near path can differ
#: from a published number by up to half a step — 0.0005 km2 — purely from that
#: rounding, and every one of the six layer-island pairs checked here sits at
#: exactly that boundary, which is the signature of agreement rather than drift.
#: The allowance is a hair more than half a step for one reason: a true value
#: landing exactly on the tie is rounded up by the build and so sits just over
#: 0.0005 from a near answer a square metre below it. That is the real case at
#: `settlement-era-a`/La Palma 2010, where the truth is 4.3125, the build
#: published 4.313, and the near path reads 4.312499 — the two computations agree
#: to about 1 m2 and only the tie makes it look like 501.
#:
#: Measured worst over all six pairs: 0.000501 km2. An error of 2 m2 (0.002) fails
#: this by more than threefold, which the mutation check in the plan confirms.
TOLERANCE_KM2 = 0.0006


def _index() -> dict:
    return json.loads((PROCESSED / "index.json").read_text())


def _near_path(layer_id: str, island: str, tmp_path, kind: str = "year") -> dict[str, float]:
    """Run the viewer's own near path over one island's window of a published COG.

    Returns the cumulative series exactly as the readout would render it. The band
    is handed to node as raw bytes rather than JSON because an island window is
    millions of pixels and JSON would dominate the runtime.

    Band 1 only: `settlement-era-a` carries a second band of provenance (which
    source dated each pixel), and counting it would be counting the same ground
    twice.
    """
    node = shutil.which("node")
    if node is None:
        pytest.fail("node is not on PATH; this FAILS rather than skips (CLAUDE.md #11)")

    index = _index()
    layer = index["layers"][layer_id]
    west, south, east, north = layer["islands"][island]["bbox"]

    with rasterio.open(PROCESSED / layer_id / "archipelago.tif") as src:
        # CLAUDE.md #26: take the window in INTEGER pixels around src.index(). A
        # fractional window from rasterio.windows.from_bounds has a transform that
        # is offset from the array read() returns, which puts a sub-pixel error
        # into the row latitudes and so into every row's ground area.
        row_top, col_left = src.index(west, north)
        row_bot, col_right = src.index(east, south)
        row_top, col_left = max(row_top, 0), max(col_left, 0)
        row_bot, col_right = min(row_bot, src.height), min(col_right, src.width)
        window = rasterio.windows.Window(col_left, row_top, col_right - col_left, row_bot - row_top)
        band = src.read(1, window=window)
        pixel_deg = src.transform.a
        # transform.e is negative (north-up), so this walks DOWN from the file's
        # north edge to the window's own north edge.
        window_north = src.transform.f + row_top * src.transform.e

    height, width = band.shape
    raw = tmp_path / f"{layer_id}-{island.replace(' ', '-')}.bin"
    raw.write_bytes(band.tobytes())

    series_key, argument = SERIES[kind]
    keys = sorted(int(k) for k in layer["islands"][island]["stats"][series_key])
    script = (
        "import {readFileSync} from 'node:fs';"
        "import {rowAreas, areaHistogram, statsFromHistogram} from './count.js';"
        f"const values = new Uint8Array(readFileSync({json.dumps(str(raw))}));"
        f"const areas = rowAreas({json.dumps(index['pixel_area_m2'])}, "
        f"{{north: {window_north!r}, pixelDeg: {pixel_deg!r}, height: {height}}});"
        f"const hist = areaHistogram(values, {{width: {width}, height: {height}, areas}});"
        f"const stats = statsFromHistogram(hist, "
        f"{{kind: {json.dumps(kind)}, {argument}: {json.dumps(keys)}}});"
        f"console.log(JSON.stringify(stats[{json.dumps(series_key)}]));"
    )
    result = subprocess.run([node, "--input-type=module", "-e", script],
                            cwd=ROOT / "viewer", capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


#: Every layer whose near path can be checked against a published series: the
#: cadastre's own years, WSF Evolution's years draped to 10 m, and WSF Tracker's
#: observation epochs. Percentage and change layers are far-only by design
#: (`FAR_ONLY_KINDS`) and have no near path to compare.
CHECKABLE = [("buildings-dated", "year"),
             ("settlement-era-a", "year"),
             ("settlement-era-b", "epoch")]


@needs_build
@pytest.mark.parametrize("layer_id,kind", CHECKABLE, ids=[c[0] for c in CHECKABLE])
@pytest.mark.parametrize("island", ISOLATED)
def test_the_near_path_reproduces_the_published_series_on_a_real_island(
        layer_id, kind, island, tmp_path):
    """Every entry, to the last digit the build published, for all three encodings.

    What it would catch: any drift between the browser's arithmetic and the
    build's over real data — a wrong row-area lookup, an off-by-one in the year
    offset, a histogram bin that starts in the wrong place, the undated class
    leaking into a year, the epoch series accumulating from the wrong end. None of
    those is visible on a hand-made fixture that happens to avoid the case.

    Running it over both a year-coded and an epoch-coded layer matters because the
    two take different branches of `statsFromHistogram`, and only the year branch
    has an undated class to keep out of the series.
    """
    series_key, _ = SERIES[kind]
    published = _index()["layers"][layer_id]["islands"][island]["stats"][series_key]
    near = _near_path(layer_id, island, tmp_path, kind)

    assert set(near) == set(published), (
        f"{layer_id}/{island}: the near path emitted a different set of "
        f"{'years' if kind == 'year' else 'epochs'}"
    )

    wrong = {k: (published[k], near[k]) for k in published
             if abs(published[k] - near[k]) > TOLERANCE_KM2}
    assert not wrong, (
        f"{layer_id}/{island}: {len(wrong)} of {len(published)} entries sit further "
        f"than {TOLERANCE_KM2} km2 from the published series; worst "
        f"{max(abs(a - b) for a, b in wrong.values()):.6f} km2. Sample: "
        + ", ".join(f"{k} published {a} near {b:.6f}" for k, (a, b) in list(wrong.items())[:3])
    )


@needs_build
def test_only_la_graciosa_and_lanzarote_share_a_bounding_box():
    """The premise of the test above, pinned so it cannot rot silently.

    Comparing a rectangular window against a per-island figure is only valid when
    the rectangle holds one island. That is true for seven of the eight boxes and
    false for exactly one pair: La Graciosa's box (29.20-29.32 N) dips into
    Lanzarote's (which reaches 29.30 N), so a window over La Graciosa also covers
    the northern tip of Lanzarote around Orzola.

    What it would catch: a future bbox change that makes another pair overlap,
    which would leave the parity test above quietly comparing a window of two
    islands against the published figure for one.
    """
    boxes = {name: entry["bbox"]
             for name, entry in _index()["layers"]["buildings-dated"]["islands"].items()}

    def overlaps(a, b):
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    names = sorted(boxes)
    pairs = {tuple(sorted((a, b))) for i, a in enumerate(names) for b in names[i + 1:]
             if overlaps(boxes[a], boxes[b])}

    assert pairs == {("La Graciosa", "Lanzarote")}, (
        f"the overlapping bounding-box pairs are {sorted(pairs)}; ISOLATED in this file "
        "names the islands assumed not to overlap and must be revisited"
    )
    assert not set(ISOLATED) & {n for pair in pairs for n in pair}


@needs_build
def test_a_window_over_la_graciosa_counts_lanzarote_too_which_is_correct(tmp_path):
    """The near path is right and the per-island comparison is wrong. Both matter.

    The readout answers "what is on screen". With Lanzarote's northern tip on
    screen, counting it is the correct answer and the published La Graciosa figure
    is a different question. This test exists so that the excess is recorded as a
    property of the comparison rather than rediscovered as a bug: measured, the
    window reads about 0.037 km2 more than La Graciosa's published total, and the
    extra pixels sit at 29.200-29.210 N, south of the strait, cut off at the box
    edge rather than ending at a coastline.
    """
    published = _index()["layers"]["buildings-dated"]["islands"]["La Graciosa"]["stats"]["extent_by_year"]
    near = _near_path("buildings-dated", "La Graciosa", tmp_path)

    last = max(published, key=int)
    assert near[last] > published[last], (
        "a window over La Graciosa no longer picks up Lanzarote; if the mosaic or the "
        "boxes changed, this island may now belong in ISOLATED"
    )
