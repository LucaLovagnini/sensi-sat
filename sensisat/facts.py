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
import os
from functools import cache
from pathlib import Path

from .config import PROCESSED

#: `SENSISAT_STATS` points every consumer at a different statistics file. It exists
#: for one reason: `scripts/verify_m4c.py` perturbs a COPY of layers.json and shows
#: that the page, the viewer module and the STAC template all move together — the
#: single most important property of the design, testable without a rebuild.
STATS = Path(os.environ.get("SENSISAT_STATS", PROCESSED / "statistics" / "layers.json"))
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


def prop_sum(layer: str, key: str, island: str | None = None) -> float:
    """Sum of one numeric per-island property — `sealed_km2_including_greenhouses`,
    `greenhouse_removed_km2` — for the figures that compare masked with unmasked."""
    d = stats()[layer]
    rows = [d[island]] if island else list(d.values())
    return sum(v["properties"].get(key, 0.0) for v in rows)


# --- sizes, which is what went stale the first time ------------------------

def size_mib(layer: str) -> float:
    """What a layer costs to publish: its one archipelago COG.

    Not the sum of the per-island files it is built from. Those are still written
    and still what the statistics are measured on, but they are not served any more,
    and a size table that mixed the two would not add up — which is how this was
    noticed.
    """
    from sensisat.catalog import MOSAIC
    path = PROCESSED / layer / f"{MOSAIC}.tif"
    return path.stat().st_size / 2**20


def size_six_layers() -> float:
    return sum(size_mib(x) for x in SIX)


def size_confidence() -> float:
    """The per-pixel confidence companion, the largest object in the project. It is
    a separate STAC asset, so it is not in any layer's file_MiB."""
    return sum(f.stat().st_size for f in (PROCESSED / "density-current").glob("*.confidence.tif")) / 2**20


def size_published() -> float:
    """What a host would actually serve.

    Not simply everything under data/processed: since the archipelago mosaics
    arrived, that folder also holds the per-island COGs they are built from, which
    are no longer published. Counting them would overstate the published total by
    roughly the size of the whole site.
    """
    from sensisat.catalog import is_build_intermediate
    return sum(f.stat().st_size for f in PROCESSED.rglob("*")
               if f.is_file() and not is_build_intermediate(f.name)) / 2**20


# --- shares, which drift faster than totals and are quoted as percentages ---

def dated_share() -> float:
    """% of the cadastral footprint carrying a construction year."""
    d = stats()["buildings-dated"]
    dated = sum(v["properties"]["dated by the source"] for v in d.values())
    return 100 * dated / sum(v["headline_km2"] for v in d.values())


def undated_share(layer: str = "settlement-era-a", island: str | None = None) -> float:
    """% of a settlement layer's footprint that no source can date.

    Published as 43 % from M0, which measured the raw WSF Tracker baseline. The
    layer we actually publish reads lower, because era-a is greenhouse-masked and
    clipped to land. Quoting the M0 figure for our own layer was wrong by six points
    — and it was wrong in three places at once (the page, the viewer's note, and
    every STAC item), which is why this function exists rather than three numbers.
    """
    d = stats()[layer]
    rows = [d[island]] if island else list(d.values())
    und = sum(v["properties"].get("pre-2016, undated", 0) for v in rows)
    return 100 * und / sum(v["headline_km2"] for v in rows)


def growth_pct(layer: str, island: str, y0: int, y1: int) -> float:
    """% growth of a layer's extent between two years, from the slider's own series.

    The viewer said "Gran Canaria grew 9 % between 1995 and 2015" — an M0 figure
    from raw 30 m WSF Evolution. Our published era-a layer, the thing the reader is
    actually looking at, gives about 5 %. Same claim, different instrument, stated
    as one number.
    """
    by = stats()[layer][island]["properties"]["extent_by_year"]
    return 100 * (by[str(y1)] / by[str(y0)] - 1)


def sealed_vs_built_ratio() -> float:
    """Copernicus sealed surface over GHSL built surface, from OUR two layers.

    M0 measured 341.5 / 152.9 = 2.2 on the raw products; the layers we publish are
    greenhouse-masked and land-clipped and give about 2.1. The viewer quoted 2.2 as
    if it described the layers on screen.
    """
    return area("density-current") / area("density-trend")


def crash_pct(layer: str = "buildings-dated") -> float:
    """Cadastral footprint added per year 2012-2019 as a % of the 2000-2007 rate.

    Spain's construction collapse, read from the register's own annual series: it
    falls monotonically from 2008 to 2013 and stays flat (analysis 21). GHSL cannot
    see this event, which is the caveat the density-trend description carries.
    """
    d = stats()[layer]
    def added(y):
        return sum(v["properties"]["extent_by_year"].get(str(y), 0.0)
                   - v["properties"]["extent_by_year"].get(str(y - 1), 0.0) for v in d.values())
    pre = sum(added(y) for y in range(2000, 2008)) / 8
    post = sum(added(y) for y in range(2012, 2020)) / 8
    return 100 * post / pre


# --- the seam --------------------------------------------------------------

def seam_factor(island: str, which: str = "definition_factor_masked") -> float:
    return next(r[which] for r in seam() if r["island"] == island)


#: Islands whose greenhouse-masked 2016 baseline exceeds this many km2 count as
#: "main" for the seam statement. Below it La Gomera (3 km2) GAINS extent at the
#: seam, and quoting a "drop" range that silently excludes it is what the viewer did.
SEAM_MAIN_ISLAND_KM2 = 10.0


def seam_drop_range(min_km2: float = SEAM_MAIN_ISLAND_KM2) -> tuple[float, float, int]:
    """(smallest drop %, largest drop %, number of islands) at the 2015/16 seam.

    From `net_evo_to_tracker_masked` in seam.json: the ratio of the masked 10 m
    Tracker baseline to the 30 m WSF Evolution extent. A ratio of 0.60 is a 40 %
    apparent drop with nothing demolished — resolution and definition, not change.
    """
    rows = [r for r in seam() if r["trk_e1_nogh"] >= min_km2]
    drops = [100 * (1 - r["net_evo_to_tracker_masked"]) for r in rows]
    return min(drops), max(drops), len(rows)


def reload() -> None:
    """Forget cached statistics — for a process that writes them and then reads them."""
    stats.cache_clear()
    seam.cache_clear()


# --- the version a citation names --------------------------------------------

def data_version() -> str:
    """What a reader should cite: the package version and the date the published
    statistics were last committed — the only dated, versioned record of a build.
    (The rasters carry no build date; the STAC items record the software version.)
    Falls back to the statistics file's modification date where git is unavailable."""
    import subprocess
    from importlib.metadata import PackageNotFoundError, version
    try:
        v = version("sensisat")
    except PackageNotFoundError:
        v = "0.1.0"
    try:
        date = subprocess.run(["git", "log", "-1", "--format=%cs", "--", str(STATS)],
                              cwd=STATS.parents[2], capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        date = ""
    if not date:
        import datetime as dt
        date = dt.date.fromtimestamp(STATS.stat().st_mtime).isoformat()
    return f"sensisat {v}, data of {date}"


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
