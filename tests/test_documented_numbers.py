"""The documents' live figures must still match the build.

Design note, because the mechanism is unusual. The documents do not contain
hand-typed numbers where it matters: they contain a call to `sensisat.facts` inside
an HTML comment, and `cog` writes the answer beside it. A figure therefore cannot
drift — it is generated, not remembered. This test is the early-warning half of
that arrangement; `scripts/build.py` regenerates and `scripts/publish.py` blocks.

What it deliberately does NOT cover: the ~1,300 historical figures in `docs/`, which
record why a decision was taken and must never track the pipeline. Each document
states that distinction to its reader in a generated block, so nobody has to guess
which kind of number they are looking at.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_docs import DOCUMENTS, run  # noqa: E402

from sensisat.facts import STATS  # noqa: E402

needs_build = pytest.mark.skipif(
    not STATS.exists(), reason="run scripts/build.py --all first")


@needs_build
def test_documents_match_the_build() -> None:
    assert run(check=True) == 0, (
        "a document's live figures no longer match the build — run "
        "`python scripts/sync_docs.py`, then check that the prose around each "
        "changed number still says something true.")


@needs_build
def test_the_statistics_file_is_not_git_ignored() -> None:
    """The whole arrangement rests on this file being in the repo.

    `.gitignore` excludes `/data/` wholesale, which is right for 13 GB of rasters
    and wrong for the 83 KB that holds every published figure. If the exception is
    removed, every check above starts skipping — and a skipped check is not a passed
    check (CLAUDE.md #11).
    """
    import subprocess
    out = subprocess.run(["git", "check-ignore", str(STATS)], cwd=ROOT, capture_output=True)
    assert out.returncode != 0, (
        "data/processed/statistics/layers.json is git-ignored again, so the document "
        "guard silently stops working. Restore '!/data/processed/statistics/'.")


def test_every_listed_document_exists() -> None:
    """A renamed file would be skipped in silence, taking its figures with it."""
    missing = [d for d in DOCUMENTS if not (ROOT / d).exists()]
    assert not missing, f"listed in sync_docs.DOCUMENTS but absent: {missing}"
