"""Delete objects from the R2 bucket — but never one that something still links to.

    python scripts/prune_r2.py --per-island            # dry run: what would go, and why
    python scripts/prune_r2.py --per-island --yes      # delete

**Why this exists.** On 2026-10-06 the plan said to prune "the ~56 orphaned
per-island objects" left over from the archipelago migration. They were not
orphans: every published STAC item linked to its island's COG, and those links
resolved only because the objects were still there. Deleting them on the plan's
word would have 404'd the whole catalogue at once. What stopped it was someone
happening to check with HEAD requests first. This script makes that check the
mechanism rather than a habit.

**It checks the LIVE site, not only the build.** The fix that freed those objects
was to point every item at the archipelago mosaic. But until the corrected items
are uploaded, the live ones still link to the per-island files — so a guard that
looked only at dist/ would call them free and delete what production still needs.
The order "upload the new items, then prune" is enforced here by refusing any key
the live catalogue or the live index.json still references.

A key is refused if any of these holds:
  * it is a file in dist/data/ — it is published, so it is not an orphan;
  * a link in dist/data/ points at it;
  * a link in the LIVE catalogue or LIVE index.json points at it.

Reads are serial (one request at a time), never concurrent: production is sampled,
not load-tested. Deletes pass `--remote`, for the reason upload_r2.py gives.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from publish import DATA  # noqa: E402

from sensisat.catalog import _slug  # noqa: E402
from sensisat.config import ISLAND_BBOX  # noqa: E402
from sensisat.layers import LAYERS  # noqa: E402

LIVE = "https://data.sensisat.org"
BUCKET = "sensisat-data"


def per_island_keys() -> list[str]:
    """The COGs every item linked to before 2026-10-07: one per layer per island."""
    return [f"{name}/{_slug(island)}.tif" for name in LAYERS for island in sorted(ISLAND_BBOX)]


def link_targets(read, root: str) -> set[str]:
    """Every key a catalogue + index tree links to, as bucket-relative paths.

    `read(path)` returns the text of a file relative to the tree's root, so the same
    walk serves the local dist/ tree and the live bucket. Hrefs are resolved the way
    a browser would: relative to the document that carries them.
    """
    import posixpath

    keys: set[str] = set()

    def walk(doc_path: str) -> None:
        doc = json.loads(read(doc_path))
        here = posixpath.dirname(doc_path)
        for asset in doc.get("assets", {}).values():
            keys.add(posixpath.normpath(posixpath.join(here, asset["href"])))
        for link in doc.get("links", []):
            if link.get("rel") in ("child", "item"):
                walk(posixpath.normpath(posixpath.join(here, link["href"])))

    walk("catalog.json")
    index = json.loads(read("index.json"))
    for layer in index.get("layers", {}).values():
        if layer.get("asset"):
            keys.add(posixpath.normpath(layer["asset"]))
        # The per-island asset was removed from index.json in the contract step, but
        # an index published BEFORE that step still carries one per island — and the
        # live one does until the contracted index is uploaded. Reading only the
        # current shape would call those files free while the live index links to
        # them (CodeRabbit, PR #14). A key linked from ANY index shape is a link.
        for entry in layer.get("islands", {}).values():
            if entry.get("asset"):
                keys.add(posixpath.normpath(entry["asset"]))
    return keys


#: Cloudflare's bot protection answers Python's default User-Agent
#: ("Python-urllib/3.x") with 403 even where curl gets 200, so the script says what
#: it is instead of looking like an anonymous scraper.
HEADERS = {"User-Agent": "sensisat-prune/1 (+https://sensisat.org)"}


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:          # noqa: S310 (fixed host)
        return r.read().decode()


def _exists(key: str) -> bool:
    """True on 200, False ONLY on a confirmed 404; anything else stops the prune.

    It used to return False on any failure, so a 403 or a timeout read as "already
    gone" and a dry run could finish green having checked nothing (CodeRabbit,
    PR #14). That is not hypothetical here: Cloudflare answered this script's first
    run with 403 for every request, because of its User-Agent. Absence must be a
    fact the server stated, never an inference from not hearing back.
    """
    import urllib.error

    req = urllib.request.Request(f"{LIVE}/{key}", method="HEAD", headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30):          # noqa: S310
            return True
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return False
        raise SystemExit(f"HEAD {key} answered {err.code}; refusing to guess whether it exists") from err
    except OSError as err:
        raise SystemExit(f"HEAD {key} failed ({err}); refusing to guess whether it exists") from err


def refusals(candidates: list[str], published: set[str], local_links: set[str],
             live_links: set[str]) -> dict[str, str]:
    """Why each refused key must stay. Pure, so it is tested without a network."""
    why = {}
    for key in candidates:
        if key in published:
            why[key] = "published in dist/data"
        elif key in live_links:
            why[key] = "the LIVE catalogue or index still links to it — upload first"
        elif key in local_links:
            why[key] = "a link in dist/data points at it"
    return why


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--per-island", action="store_true",
                    help="the 56 per-island COGs the catalogue linked to before 2026-10-07")
    ap.add_argument("keys", nargs="*", help="explicit bucket keys to consider")
    ap.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    args = ap.parse_args()

    candidates = list(args.keys) + (per_island_keys() if args.per_island else [])
    if not candidates:
        ap.error("name keys, or pass --per-island")

    published = {str(p.relative_to(DATA)) for p in DATA.rglob("*") if p.is_file()}
    local_links = link_targets(lambda rel: (DATA / rel).read_text(), str(DATA))
    print(f"reading the live catalogue from {LIVE} (serial)…")
    live_links = link_targets(lambda rel: _get(f"{LIVE}/{rel}"), LIVE)

    refused = refusals(candidates, published, local_links, live_links)
    free = [k for k in candidates if k not in refused]
    for key, why in sorted(refused.items()):
        print(f"  KEEP    {key:50} {why}")
    present = [k for k in free if _exists(k)]
    for key in free:
        print(f"  {'DELETE ' if key in present else 'absent '} {key}")
    print(f"\n{len(refused)} kept, {len(present)} to delete, {len(free) - len(present)} already gone")

    if refused and any("LIVE" in w for w in refused.values()):
        print("\nThe live site still links to some of these. Upload the corrected catalogue")
        print("first (python scripts/upload_r2.py), then run this again.")
    if not args.yes:
        print("\ndry run — nothing deleted. Re-run with --yes to delete the DELETE lines.")
        return 0

    failed = 0
    for key in present:
        r = subprocess.run(["npx", "wrangler", "r2", "object", "delete",
                            f"{BUCKET}/{key}", "--remote"], capture_output=True, text=True)
        ok = r.returncode == 0
        failed += not ok
        print(f"  {'deleted' if ok else 'FAILED '} {key}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
