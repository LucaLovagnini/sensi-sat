"""Regenerate — or verify — every live figure embedded in the documents.

The documents do not contain hand-typed numbers where it matters. They contain a
call to `sensisat.facts` inside an HTML comment, and cog writes the answer next to
it. This script is the only place that knows which files carry such figures.

    python scripts/sync_docs.py            # rewrite the numbers from the build
    python scripts/sync_docs.py --check    # fail if any is stale, change nothing

Where it runs, and why each one differs:

  * `scripts/build.py` REGENERATES, because a rebuild is what makes documents
    stale. The thing that breaks them should fix them, and the change then shows up
    as a reviewable git diff rather than a silent drift.
  * `pytest` CHECKS, so the normal edit loop catches it in under a second.
  * `scripts/publish.py` CHECKS and refuses to assemble `dist/`, because a stale
    number only does harm once it is published, and that is the last moment to stop
    it.

Markers are HTML comments, so they are invisible in rendered Markdown and in the
published page. A reader sees only the number.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Files carrying live figures. Adding one here is all it takes for its numbers to
#: be regenerated and guarded; a file not listed is simply never touched.
DOCUMENTS = [
    "viewer/about-the-data.html",
    "docs/pipeline.md",
    "docs/validation.md",
    "docs/data-evaluation.md",
    "CLAUDE.md",
]

PRELUDE = ("import sensisat.facts as f; "
           "from sensisat.facts import km2, area, area_by")


def run(check: bool) -> int:
    present = [d for d in DOCUMENTS if (ROOT / d).exists()]
    cmd = [sys.executable, "-m", "cogapp", "-p", PRELUDE]
    cmd += ["--check", "--diff"] if check else ["-r"]
    cmd += [str(ROOT / d) for d in present]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()

    if proc.returncode == 0:
        print(f"  documents {'verified' if check else 'synced'}: {len(present)} files")
        return 0
    if check:
        print("  FAIL: a document's numbers no longer match the build.\n")
        print(out)
        print("\n  Either the document is stale — run `python scripts/sync_docs.py` —")
        print("  or the pipeline changed and the surrounding prose needs rewriting.")
        print("  This check cannot tell which; it only knows they disagree.")
    else:
        print(out)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify without writing; non-zero exit if anything is stale")
    return run(ap.parse_args().check)


if __name__ == "__main__":
    raise SystemExit(main())
