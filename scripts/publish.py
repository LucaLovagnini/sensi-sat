"""Assemble the deployable site into dist/ — everything a static host needs, nothing else.

    python scripts/publish.py            # build dist/
    python scripts/upload_r2.py          # dist/data/ -> R2   (only when the data changed)
    npx wrangler deploy                  # dist/site/ -> Workers Assets  (you run this)

Three things happen here that do not happen in `build.py`, and each exists for a
reason measured in `docs/design/scaling.md`:

1. **One runtime index instead of a 64-request STAC walk (guardrail G2).** The
   viewer used to learn what exists by fetching the catalogue, then 7 collections,
   then 56 items. STAC's nested form is right for a catalogue someone browses with
   their own tools; it is wrong for a page load. `index.json` carries the same
   information in one file. **The STAC catalogue is still published** — it is a
   deliverable in its own right, and dropping it would cost interoperability to buy
   speed we can get another way.

2. **Two trees, because they go to two places.** The repository is not the website:
   scripts, docs, raw downloads and notebooks have no business on a public host.
   `dist/site/` is the shell (HTML, CSS, one JS bundle) served by Workers Assets;
   `dist/data/` is the published layers, uploaded to R2. They are split because
   Workers Assets has no way to exclude a directory from upload — `.assetsignore`
   was tried and is NOT honoured by this wrangler, it merely uploads the ignore file
   too — and because the rasters need a host that implements `Range`, which the
   assets platform does not.

3. **A size budget (guardrail G6).** The build fails if dist/ exceeds a threshold,
   so a future layer cannot quietly multiply what every visitor pays for. The
   sealing layer is already more than half the total; this is not hypothetical.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat.config import PROCESSED, ROOT  # noqa: E402
from sensisat.layers import LAYERS  # noqa: E402

DIST = ROOT / "dist"
SITE = DIST / "site"      # -> Workers Assets (wrangler.jsonc points here)
DATA = DIST / "data"      # -> R2 (scripts/upload_r2.py)
VIEWER = ROOT / "viewer"
SIZE_BUDGET_MIB = 100.0

# Files the viewer needs. Anything not listed does not reach the public host.
VIEWER_FILES = ["index.html", "about-the-data.html", "style.css", "about.css",
                "ol.css", "app.bundle.js",
                "_headers"]          # security headers, read by the assets platform


def build_bundle() -> None:
    """Rebuild the JavaScript bundle (guardrail G3) so dist/ is never stale."""
    if not (VIEWER / "node_modules").exists():
        print("  ! node_modules missing — run `npm install` in viewer/ first")
        return
    print("  bundling javascript…")
    subprocess.run(["npm", "run", "build", "--silent"], cwd=VIEWER, check=True,
                   capture_output=True)


#: Series that are CUMULATIVE — a running total, not a per-period amount. The
#: distinction decides what a MISSING entry means, and getting it wrong produces a
#: number that falls when it can only rise. Mirrored in `viewer/count.js`; the two
#: are checked against each other by `tests/test_publish.py`.
CUMULATIVE_SERIES = {"extent_by_year", "extent_by_epoch", "surface_km2"}


def _sum_cumulative(series: list[dict]) -> dict:
    """Sum running totals across islands, carrying each one's last value forward.

    A published per-island series ends at that island's last recorded construction:
    Fuerteventura and La Gomera stop at 2025, La Graciosa at 2023. Adding only the
    islands that HAVE a 2026 entry dropped the others, and the archipelago read
    93.87 km2 at 2026 against 102.96 at 2025.

    Before an island's first entry it contributes nothing; after its last it goes on
    contributing that last total, because the buildings are still standing.
    """
    keys = sorted({k for o in series for k in o}, key=float)
    carried = [0.0] * len(series)
    out: dict = {}
    for k in keys:
        total = 0.0
        for i, o in enumerate(series):
            v = o.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                carried[i] = float(v)
            total += carried[i]
        out[k] = round(total, 6)
    return out


def archipelago_stats(per_island: dict) -> dict:
    """Totals for all eight islands, summed from the published per-island figures.

    **Only extensive quantities are summed**, and percentages are deliberately left
    out rather than averaged. A share of one island is not a share of the
    archipelago, and a footprint-weighted mean of eight shares lands 0.01 off the
    figure `facts.py` publishes — which is precisely the kind of quiet disagreement
    the M4c gate exists to prevent. The viewport-scoped panel computes those properly
    from `stats.zonal()` zones; until then the page says nothing rather than
    something nearly right.
    """
    out: dict = {}
    keys = {k for v in per_island.values() for k in v.get("stats", {})}
    for key in sorted(keys):
        if key.endswith("_pct") or "share" in key:
            continue
        values = [v["stats"][key] for v in per_island.values() if key in v.get("stats", {})]
        first = values[0]
        if isinstance(first, bool) or not isinstance(first, (int, float, dict)):
            out[key] = first                      # labels are the same on every island
        elif isinstance(first, dict) and key in CUMULATIVE_SERIES:
            out[key] = _sum_cumulative(values)
        elif isinstance(first, dict):
            acc: dict = {}
            for v in values:
                for k2, v2 in v.items():
                    if isinstance(v2, (int, float)) and not isinstance(v2, bool):
                        acc[k2] = round(acc.get(k2, 0) + v2, 6)
                    else:
                        acc.setdefault(k2, v2)
            out[key] = acc
        else:
            out[key] = round(sum(values), 6)
    return out


def pixel_area_table(step_deg: float = 0.1) -> dict:
    """Ground area of one pixel at each latitude, as data the viewer looks up.

    A "10 m" pixel is 8.983e-05 degrees on both axes, which at 28 degN is 9.98 m
    north-south but only 8.83 m east-west — about 88 m2, not 100. Counting pixels
    and multiplying by a nominal size overstates area by ~12 % (CLAUDE.md #2).

    The viewer needs that correction to turn a pixel count into square kilometres,
    and the one thing it must NOT do is work the number out for itself: that would
    put a second definition of ground area in the project, in a language where
    nothing checks it, and the wrong answer looks entirely plausible. So the values
    come from `raster.row_areas_m2` — the same function every published figure is
    computed with — and ship in index.json.

    Sampling every 0.1 degrees is enough because the quantity follows cos(latitude)
    and so is smooth: across the archipelago's 27.5–29.6 degN span it moves about
    2 %, and linear interpolation between samples this close is accurate to roughly
    one part in three million. Twenty-two numbers.
    """
    import math

    from rasterio.transform import Affine

    from sensisat.config import CANARIES_BBOX
    from sensisat.grid import PIXEL_DEG
    from sensisat.raster import row_areas_m2

    west, south, _, north = CANARIES_BBOX
    lat0 = math.floor(south / step_deg) * step_deg
    lat1 = math.ceil(north / step_deg) * step_deg

    # One row per real pixel across the whole span, so the values are the ones the
    # build itself would use, then sampled. The array is ~23,000 floats.
    top = lat1 + PIXEL_DEG          # so the first row CENTRE sits above lat1
    height = int(math.ceil((top - lat0) / PIXEL_DEG)) + 1
    transform = Affine(PIXEL_DEG, 0.0, west, 0.0, -PIXEL_DEG, top)
    native = row_areas_m2((height, 1), transform)[:, 0]
    centres = top - PIXEL_DEG * (np.arange(height) + 0.5)

    n = int(round((lat1 - lat0) / step_deg)) + 1
    values = []
    for i in range(n):
        lat = lat0 + i * step_deg
        # The nearest row centre is at most half a pixel (4.5e-05 deg) away, which
        # moves the area by about one part in ten million.
        values.append(round(float(native[int(np.abs(centres - lat).argmin())]), 6))
    return {"lat0": round(lat0, 6), "step": step_deg, "values": values}


def runtime_index() -> dict:
    """One file describing every published layer (guardrail G2).

    **One asset per layer, not one per island.** The viewer draws the whole
    archipelago from a single COG, because OpenLayers cannot composite several
    GeoTIFF sources into one layer — multiple `sources` become BANDS of one image.
    Per-island entries stay, carrying each island's bbox and published statistics:
    they are what a zone panel sums, and what the STAC items describe.

    Deliberately small and flat. Everything richer — provenance, lineage, licences,
    band descriptions — stays in the STAC items, which ship alongside.
    """
    from sensisat.catalog import MOSAIC
    from sensisat.config import ISLAND_BBOX

    stats_path = PROCESSED / "statistics" / "layers.json"
    stats = json.loads(stats_path.read_text()) if stats_path.exists() else {}

    layers: dict[str, dict] = {}
    for name, spec in LAYERS.items():
        asset = PROCESSED / name / f"{MOSAIC}.tif"
        if not asset.exists():
            continue
        islands = {}
        for island, entry in sorted(stats.get(name, {}).items()):
            if island not in ISLAND_BBOX:
                continue
            islands[island] = {
                "bbox": list(ISLAND_BBOX[island]),
                "stats": entry.get("properties", {}),
                "headline_km2": entry.get("headline_km2"),
            }
        headline = [v["headline_km2"] for v in islands.values() if v["headline_km2"] is not None]
        layers[name] = {
            "title": spec.title, "measure": spec.measure, "encoding": spec.encoding,
            "resolution_m": spec.resolution_m, "sources": spec.sources,
            "start": spec.start, "end": spec.end,
            # Relative to index.json itself, not to the site root: the viewer sits at
            # a different depth in the repo than in the deployed site, so a
            # root-relative path would resolve correctly in only one of them.
            "asset": f"{name}/{MOSAIC}.tif",
            "bytes": asset.stat().st_size,
            "stats": archipelago_stats(islands),
            "headline_km2": round(sum(headline), 4) if headline else None,
            "islands": islands,
        }
    return {"generated": "sensisat", "stac": "catalog.json",
            "pixel_area_m2": pixel_area_table(), "layers": layers}


def _build_intermediates(directory: str, names: list[str]) -> set[str]:
    """The per-island COGs, which are no longer published.

    They are still built, still gated and still the thing statistics are computed
    from — but every STAC item now names the archipelago mosaic, and the viewer
    reads that one file. Shipping both would put dist/ at roughly 101 MiB against
    the 100 MiB budget (G6), to publish the same pixels twice.

    The confidence companions stay: they are per-island by nature, they are separate
    STAC assets, and nothing fetches them until asked.
    """
    from sensisat.catalog import is_build_intermediate
    return {n for n in names if is_build_intermediate(n)}


def copy_tree() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    SITE.mkdir(parents=True)

    for name in VIEWER_FILES:
        src = VIEWER / name
        if not src.exists():
            raise FileNotFoundError(f"{src} is missing — run `npm run build` in viewer/")
        shutil.copy2(src, SITE / name)

    shutil.copytree(PROCESSED, DATA, ignore=_build_intermediates)


def report() -> float:
    files = [f for f in DIST.rglob("*") if f.is_file()]
    total = sum(f.stat().st_size for f in files) / 1048576
    by_kind: dict[str, list] = {}
    for f in files:
        kind = f.suffix.lstrip(".") or "other"
        row = by_kind.setdefault(kind, [0, 0])
        row[0] += 1
        row[1] += f.stat().st_size
    print(f"\n  {len(files)} files, {total:.1f} MiB")
    for kind, (n, b) in sorted(by_kind.items(), key=lambda kv: -kv[1][1]):
        print(f"    {kind:6s} {n:4d} files  {b / 1048576:7.2f} MiB")
    largest = max(files, key=lambda f: f.stat().st_size)
    print(f"    largest: {largest.relative_to(DIST)} "
          f"({largest.stat().st_size / 1048576:.2f} MiB)")
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-bundle", action="store_true")
    ap.add_argument("--budget-mib", type=float, default=SIZE_BUDGET_MIB)
    args = ap.parse_args()

    if not (PROCESSED / "catalog.json").exists():
        print("data/processed/ has no catalogue — run scripts/build.py --all first")
        return 1

    # A stale figure only does harm once it is public, and this is the last moment
    # to stop it. Checked before anything is copied, so a failure costs nothing.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sync_docs import figure_gate
    from sync_docs import run as sync_documents
    if sync_documents(check=True) != 0:
        print("\n  refusing to assemble dist/ — run `python scripts/sync_docs.py` first")
        return 3
    # Then the whole gate: every figure accounted for, no live value typed by hand,
    # every quantity word carrying its digits. dist/ is what the public reads.
    if figure_gate() != 0:
        print("\n  refusing to assemble dist/ while a figure is unaccounted for")
        return 3
    # And the judgement the gate cannot make: a named reviewer has read the generated
    # figures against their facts, the registry against the layers, the declarations
    # against their sources — for THIS set of figures (scripts/review_figures.py).
    review = subprocess.run([sys.executable, str(ROOT / "scripts" / "review_figures.py"), "--check"])
    if review.returncode != 0:
        print("\n  refusing to assemble dist/ until the figure review is current (/verify-figures)")
        return 3

    print(f"Assembling {DIST}")
    if not args.skip_bundle:
        build_bundle()
    copy_tree()

    index = runtime_index()
    # Written into data/ so the path is identical locally and deployed: the viewer
    # asks for `<data>/index.json` in both, with no build-time path rewriting.
    payload = json.dumps(index, separators=(",", ":"))
    (PROCESSED / "index.json").write_text(payload)
    (DATA / "index.json").write_text(payload)
    n_islands = sum(len(v["islands"]) for v in index["layers"].values())
    print(f"  index.json: {len(index['layers'])} layers, {n_islands} island entries, "
          f"{(DATA / 'index.json').stat().st_size / 1024:.1f} KiB "
          f"(replaces a 64-request STAC walk)")

    total = report()
    if total > args.budget_mib:
        print(f"\n  FAIL: {total:.1f} MiB exceeds the {args.budget_mib:.0f} MiB budget (G6)")
        return 2
    print(f"\n  within the {args.budget_mib:.0f} MiB budget (G6)")
    print("\nDeploy in two steps. They are independent, and the first is skipped unless")
    print("the layers themselves changed — the rasters are immutable and rarely move:")
    print("  python scripts/upload_r2.py   # dist/data/  -> R2")
    print("  npx wrangler deploy           # dist/site/  -> Workers Assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
