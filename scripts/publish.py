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


def runtime_index() -> dict:
    """One file describing every published layer and island (guardrail G2).

    Deliberately small and flat: the viewer needs to know what exists, where the
    file is, and the per-island headline figures. Everything richer — provenance,
    lineage, licences, band descriptions — stays in the STAC items, which ship
    alongside for anyone using proper tooling.
    """
    stats_path = PROCESSED / "statistics" / "layers.json"
    stats = json.loads(stats_path.read_text()) if stats_path.exists() else {}

    layers: dict[str, dict] = {}
    for name, spec in LAYERS.items():
        islands = {}
        for tif in sorted((PROCESSED / name).glob("*.tif")):
            if ".confidence." in tif.name or tif.stem.count(".") :
                continue                     # companions are fetched on demand
            island = next((i for i in stats.get(name, {})
                           if i.lower().replace(" ", "-") == tif.stem), None)
            entry = stats.get(name, {}).get(island, {}) if island else {}
            islands[island or tif.stem] = {
                # Relative to index.json itself, not to the site root. The viewer
                # lives at a different depth in the repo than in the deployed site,
                # so a root-relative path would resolve correctly in only one of them.
                "asset": f"{name}/{tif.name}",
                "bytes": tif.stat().st_size,
                "stats": entry.get("properties", {}),
                "headline_km2": entry.get("headline_km2"),
            }
        if islands:
            layers[name] = {
                "title": spec.title, "measure": spec.measure, "encoding": spec.encoding,
                "resolution_m": spec.resolution_m, "sources": spec.sources,
                "start": spec.start, "end": spec.end, "islands": islands,
            }
    return {"generated": "sensisat", "stac": "catalog.json", "layers": layers}


def copy_tree() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    SITE.mkdir(parents=True)

    for name in VIEWER_FILES:
        src = VIEWER / name
        if not src.exists():
            raise FileNotFoundError(f"{src} is missing — run `npm run build` in viewer/")
        shutil.copy2(src, SITE / name)

    shutil.copytree(PROCESSED, DATA)


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
