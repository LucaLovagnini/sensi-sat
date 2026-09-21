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

import re
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


# ---------------------------------------------------------------------------
# The published page: no figure may be unaccounted for
# ---------------------------------------------------------------------------

PAGE = ROOT / "viewer" / "about-the-data.html"
COG_REGION = re.compile(r"<!--\[\[\[cog.*?<!--\[\[\[end\]\]\]-->", re.S)

# What counts as a figure a reader would quote. An earlier version required a unit
# immediately after the number, which silently exempted the whole ladder-of-
# definitions table — six of the most-quoted totals on the page — because their
# unit lives in a column header. It also missed the confidence intervals ("± 2.7")
# and the counts ("25,971 buildings"). So: anything with a decimal point, anything
# with a thousands separator, or anything carrying a unit.
FIGURE = re.compile(
    r"\b\d[\d,]*\.\d+\s*(?:km²|m²|MiB|%|×)?"     # 469.5, 0.052 %, 4.7×
    r"|\b\d{1,3}(?:,\d{3})+\b"                     # 474,292
    r"|\b\d+\s*(?:km²|m²|MiB|%)")                   # 308 km², 72 %

#: Years are dates, not measurements.
_YEAR = re.compile(r"^(?:19|20)\d\d$")
#: DOIs and licence versions look like decimals and are neither ours nor figures.
_NOT_A_FIGURE = re.compile(r"doi:|/|CC BY ")


def page_figures(text: str) -> set[str]:
    """Every figure a reader sees, excluding the regions cog generates."""
    # Tags must go before the exclusions run: a closing </td> puts a "/" two
    # characters after every table cell's number, which silently exempted the whole
    # ladder-of-definitions table the first time this was written.
    body = re.sub(r"<[^>]+>", " ", COG_REGION.sub("", text))
    out = set()
    for m in FIGURE.finditer(body):
        token = m.group().strip()
        around = body[max(0, m.start() - 8):m.end() + 2]
        if _YEAR.match(token) or _NOT_A_FIGURE.search(around):
            continue
        out.add(token)
    return out


def test_no_unaccounted_figure_on_the_published_page() -> None:
    """Every figure a reader sees is either generated or has a declared source.

    Cog guarantees what it generates and is blind to everything else, so on its own
    it leaves the page open to a number typed in tomorrow with no provenance at all.
    This is the other half: strip the regions cog owns, and require each surviving
    figure to be registered in `sensisat.provenance` with what it is and which
    analysis produced it.

    This is the check that makes the coverage total. It already caught two live
    figures published wrong — the cadastre's dated share, and the undated share of
    the settlement layer, which said 43 % when the layer we actually publish holds
    37 %.
    """
    from sensisat.provenance import HISTORICAL

    unaccounted = sorted(page_figures(PAGE.read_text()) - set(HISTORICAL))
    assert not unaccounted, (
        "figures on the published page with no declared source: "
        + ", ".join(unaccounted) + "\n\n"
        "Every number a reader sees must be one of two things. If it comes from the "
        "current build, wrap it in a cog marker so it is generated and cannot go "
        "stale — see sensisat/facts.py. If it is a historical measurement, add it to "
        "sensisat/provenance.HISTORICAL saying what it is and which analysis "
        "produced it.")


def test_the_registry_has_no_dead_entries() -> None:
    """A figure removed from the page should not keep a registry entry.

    Otherwise the registry slowly becomes a list of claims the page no longer makes,
    and stops being readable as what it is: the provenance of what we publish.
    """
    from sensisat.provenance import HISTORICAL

    dead = sorted(set(HISTORICAL) - page_figures(PAGE.read_text()))
    assert not dead, (
        "registered in sensisat/provenance but no longer on the page: "
        + ", ".join(dead) + " — delete the entries.")
