"""Upload dist/data/ to the R2 bucket that serves the rasters.

    python scripts/upload_r2.py                 # only what changed
    python scripts/upload_r2.py --force         # everything
    python scripts/upload_r2.py --bucket NAME

**Why this exists at all.** Cloudflare's Workers Assets platform ignores the `Range`
header, and a Cloud-Optimized GeoTIFF is defined by being read in slices — so the
rasters cannot live beside the shell. They go to R2, which honours ranges at the
storage layer, and the shell keeps going to Workers Assets. `publish.py` writes the
two trees; this uploads one of them.

**Only what changed, because most runs change nothing.** The rasters are immutable
and a typical deploy touches only the shell. Every uploaded object's SHA-256 is
recorded in `.r2-manifest.json` (gitignored, one per clone) and compared on the next
run, so a no-op upload costs one hash of each file and no network at all.

**`--remote` is not optional.** `wrangler r2 object put` defaults to a LOCAL
simulated bucket and prints "Upload complete" either way. Eight uploads went into a
directory on this laptop before `bucket info` reading `object_count: 0` gave it away
(2026-09-24). Every call here passes `--remote`.

A bulk `aws s3 sync` against R2's S3-compatible endpoint would be faster, but it
needs an R2 API token created in the dashboard; this needs nothing beyond the
wrangler login that deploys the site.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat.config import ROOT  # noqa: E402

DATA = ROOT / "dist" / "data"
MANIFEST = ROOT / ".r2-manifest.json"
BUCKET = "sensisat-data"

#: Served content types. R2 does not guess, and a .tif sent as application/octet-stream
#: still decodes, but the catalogue and index must be JSON or the viewer's fetch fails.
CONTENT_TYPES = {".tif": "image/tiff", ".json": "application/json",
                 ".csv": "text/csv", ".txt": "text/plain"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def put(path: Path, bucket: str, prefix: str = "") -> tuple[Path, bool, str]:
    key = path.relative_to(DATA).as_posix()
    if prefix:
        key = f"{prefix.strip('/')}/{key}"
    ctype = CONTENT_TYPES.get(path.suffix, "application/octet-stream")
    cmd = ["npx", "wrangler", "r2", "object", "put", f"{bucket}/{key}",
           f"--file={path}", f"--content-type={ctype}", "--remote"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = (r.stderr or r.stdout).strip().splitlines()
    return path, r.returncode == 0, lines[-1] if lines else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bucket", default=BUCKET)
    ap.add_argument("--prefix", default="", help="upload under a key prefix, e.g. v2")
    ap.add_argument("--force", action="store_true", help="re-upload every object")
    ap.add_argument("--allow-index", action="store_true",
                    help="permit overwriting index.json (see SHARED below)")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()

    if not DATA.exists():
        print(f"no {DATA} — run `python scripts/publish.py` first.")
        return 1

    known = {} if args.force else json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    files = sorted(f for f in DATA.rglob("*") if f.is_file())

    # SHARED: index.json is the one object BOTH the deployed viewer and any preview
    # read, and its shape is a contract between them. The rasters are additive -- a
    # new file cannot disturb an old one -- but overwriting index.json with a shape
    # the deployed bundle does not understand takes the live map down while the page
    # still returns 200 and nothing errors server-side. That happened on 2026-09-24.
    # So it is refused unless asked for by name, or written under a prefix where the
    # deployed viewer will not look.
    if not args.prefix and not args.allow_index:
        shared = [f for f in files if f.name == "index.json" and f.parent == DATA]
        for f in shared:
            key = f.relative_to(DATA).as_posix()
            if known.get(key) != digest(f):
                print(f"REFUSING to overwrite {key}: the deployed viewer reads it, and a "
                      f"shape it does not understand breaks the live map silently.\n"
                      f"  --allow-index   if the viewer that reads it is being deployed too\n"
                      f"  --prefix v2     to publish alongside it instead")
                return 3
    if args.prefix:
        print(f"uploading under prefix {args.prefix!r} — production keys untouched")
    todo, now = [], {}
    for f in files:
        key = f.relative_to(DATA).as_posix()
        now[key] = digest(f)
        if known.get(key) != now[key]:
            todo.append(f)

    mib = sum(f.stat().st_size for f in todo) / 1048576
    print(f"{len(files)} objects in {DATA}; {len(todo)} to upload ({mib:.1f} MiB)")
    if not todo:
        print("  nothing changed — the rasters are immutable, so this is the normal case.")
        return 0

    failed = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for i, (path, ok, msg) in enumerate(pool.map(lambda f: put(f, args.bucket, args.prefix), todo), 1):
            key = path.relative_to(DATA).as_posix()
            print(f"  [{i:3d}/{len(todo)}] {'ok  ' if ok else 'FAIL'} {key}"
                  + ("" if ok else f"  — {msg}"))
            if not ok:
                failed.append(key)
                now.pop(key, None)          # never record an object that did not land

    if not args.prefix:
        MANIFEST.write_text(json.dumps(now, indent=1, sort_keys=True))
    if failed:
        print(f"\n  {len(failed)} failed; re-run to retry only those.")
        return 2
    print(f"\n  uploaded {len(todo)} objects to {args.bucket}.")
    print("  verify a range before trusting it:  "
          "curl -sI -H 'Range: bytes=0-1023' https://data.sensisat.org/index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
