"""The published figures, as functions — the single source for every number in prose.

Numbers about this project live in three kinds of place: `docs/*.md`, the public
`viewer/about-the-data.html`, and layer descriptions in code. All of them are copies
of something the pipeline computed, and a rebuild makes every copy stale in silence:
nothing on disk is wrong, no QA gate applies, and the only symptom is a document
asserting last week's measurement. It has happened twice — `pipeline.md` carried
54.1 MiB for a day after the output became 60.2, and CLAUDE.md held M3's superseded
accuracy figures.

So the documents do not hold numbers. They hold a one-line call to this module,
inside an HTML comment, and `cog` writes the answer next to it (see
`scripts/sync_docs.py`). The number a reader sees is plain text; it simply was not
typed by a human.

**What belongs here.** Only LIVE figures — things derived from the current build.
Most of the ~1,300 numbers in `docs/` are historical findings ("Dynamic World
reported 308 km² on Gran Canaria", "WSF Evolution misses ~50 % of cells") that
record why a decision was taken. Those must never track the pipeline; rewriting them
would falsify the reasoning they exist to preserve.

Source of truth: `data/processed/statistics/layers.json`, committed for exactly this
reason — 83 KB, versioned, so a reader of the repo can check any figure we publish
without rebuilding 13 GB of rasters.
"""

from __future__ import annotations

import json
from functools import cache

from .config import PROCESSED

STATS = PROCESSED / "statistics" / "layers.json"
SEAM = PROCESSED / "statistics" / "seam.json"

ISLANDS = 8
#: Every layer except the sealing map, which is an order of magnitude larger and is
#: always reported on its own line.
SIX = ("buildings-dated", "settlement-era-a", "settlement-era-b",
       "covered-agriculture", "density-trend", "loss-events")


@cache
def stats() -> dict:
    if not STATS.exists():
        raise FileNotFoundError(
            f"{STATS} missing — run `python scripts/build.py --all` before syncing docs")
    return json.loads(STATS.read_text())


@cache
def seam() -> list[dict]:
    return json.loads(SEAM.read_text())


# --- areas -----------------------------------------------------------------

def area(layer: str, island: str | None = None) -> float:
    """km² of the layer's headline measure: footprint for the built layers, sealed
    surface for density-current, and so on. Archipelago total unless an island is
    named."""
    d = stats()[layer]
    return d[island]["headline_km2"] if island else sum(v["headline_km2"] for v in d.values())


def area_by(layer: str, year: int, island: str | None = None) -> float:
    """Cumulative km² built by `year` — the series the viewer's slider reads."""
    def one(v):
        return v["properties"].get("extent_by_year", {}).get(str(year), 0.0)
    d = stats()[layer]
    return one(d[island]) if island else sum(one(v) for v in d.values())


# --- sizes, which is what went stale the first time ------------------------

def size_mib(layer: str) -> float:
    return sum(v.get("file_MiB", 0.0) for v in stats()[layer].values())


def size_six_layers() -> float:
    return sum(size_mib(x) for x in SIX)


def size_confidence() -> float:
    """The per-pixel confidence companion, the largest object in the project. It is
    a separate STAC asset, so it is not in any layer's file_MiB."""
    return sum(f.stat().st_size for f in (PROCESSED / "density-current").glob("*.confidence.tif")) / 2**20


def size_published() -> float:
    """Everything under data/processed, which is what a host would serve."""
    return sum(f.stat().st_size for f in PROCESSED.rglob("*") if f.is_file()) / 2**20


# --- the seam --------------------------------------------------------------

def seam_factor(island: str, which: str = "definition_factor_masked") -> float:
    return next(r[which] for r in seam() if r["island"] == island)


# --- formatting ------------------------------------------------------------

def km2(value: float, dp: int = 2) -> str:
    """A figure for English prose. The viewer formats in the reader's locale; these
    documents are written in English, so the convention here is the English one."""
    return f"{value:,.{dp}f}" if value >= 10_000 else f"{value:.{dp}f}"


# --- the contract every document states about its own numbers ---------------

def contract(html: bool = False) -> str:
    """The standard note about which figures are guaranteed current and which are not.

    The reason this exists. Cog guarantees the figures it generates; it cannot
    guarantee the ones nobody marked, and most numbers in `docs/` are deliberately
    NOT marked because they are historical — a measurement that justified a decision,
    which must stay as it was or the reasoning it supports becomes unverifiable.
    That is a defensible design, but it is invisible to a reader, who then cannot
    tell a frozen measurement from one that quietly went out of date. So every
    document says so, in the same words, in a block that is itself generated.
    """
    n = len(stats())
    body = [
        "**About the numbers in this document.** Figures fall into two kinds.",
        "",
        "*Live figures* are generated from the current build — the same "
        f"`data/processed/statistics/layers.json` that produced the {n} published "
        "layers — by `scripts/sync_docs.py`. They cannot be stale: `scripts/build.py` "
        "regenerates them, `pytest` checks them, and `scripts/publish.py` refuses to "
        "assemble the site while any disagrees.",
        "",
        "*Historical measurements* are recorded as they were when they were taken, "
        "and are deliberately NOT updated. They are the evidence for a decision — "
        "the number that disqualified a dataset, or justified a threshold — and "
        "rewriting them to match a later build would destroy the reasoning they "
        "exist to support. Where one is reported, its analysis script is named, so "
        "it can be re-run and compared rather than trusted.",
    ]
    if html:
        out = []
        for para in " \n".join(body).split(" \n \n "):
            out.append("<p>" + para.replace("**", "").replace("*", "") + "</p>")
        return "\n".join(out)
    return "\n".join(body)
