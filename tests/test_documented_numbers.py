"""Every figure a reader can see is generated, declared, or excepted — nothing else.

The mechanism, because it is unusual. Numbers reach readers through three kinds of
surface, and every one is a copy of something the pipeline computed:

  * prose — `viewer/about-the-data.html`, `README.md`, `docs/*.md`, `CLAUDE.md`;
  * the viewer — strings in `viewer/app.js` rendered into the UI;
  * the catalogue — `LayerSpec.description` published in 56 STAC items.

A copy goes stale in silence: nothing on disk is wrong, no QA gate applies, and the
only symptom is a document asserting last week's measurement. It happened with the
settlement layer's undated share, which read 43 % on the page, in the viewer and in
every STAC item while the layer we publish holds 37 % — and fixing the page left the
other two wrong for a day.

So live figures are GENERATED from one key store, `sensisat/facts.py`: by cog into
HTML comments, by `scripts/sync_docs.py` into `viewer/facts.generated.js`, and by
`catalog._fill` into STAC descriptions at write time. Historical figures — the
number that disqualified a dataset, frozen on purpose — are DECLARED in
`sensisat/provenance.py`. Two narrow, positional EXCEPTIONS cover years and list
markers. A token that is none of the three fails the build, naming itself.

Fail-closed, deliberately. An earlier version let a regex decide what counted as a
figure, and it silently exempted the whole ladder-of-definitions table twice.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_docs import DOCUMENTS, FACTS_JS, run  # noqa: E402

from sensisat.facts import STATS  # noqa: E402

needs_build = pytest.mark.skipif(
    not STATS.exists(), reason="run scripts/build.py --all first")

# ---------------------------------------------------------------------------
# Extraction — one definition, used by every test below
# ---------------------------------------------------------------------------

#: A cog region in ANY comment syntax: the markers are the same, only the comment
#: characters around them differ. What sits between them was generated.
COG_REGION = re.compile(r"\[\[\[cog.*?\[\[\[end\]\]\]", re.S)

_UNIT = r"(?:km²|km2|m²|MiB|GiB|%|×|ha\b|cm\b|m\b|-?metres?\b|years?\b)"
_NUM = r"\d[\d.,]*"

#: Every run of digits a reader could read as a number — as the reader reads it.
#: Composite claims are ONE token, tried first: "98 times in 100", "463 ± 83 km²",
#: "26–52 %". Splitting them into bare integers would leave the registry keyed by
#: "7" and "26", which match anything. The negative lookbehind stops identifiers
#: being read as numbers: M3, km2, EPSG4326 are names, not figures.
TOKEN = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    rf"\d{{1,3}} (?:to \d{{1,3}} )?times in \d{{1,3}}"           # accuracy in words
    rf"|{_NUM}\s?±\s?{_NUM}(?:\s?{_UNIT})?"                        # value ± interval
    rf"|{_NUM}\s?[–-]\s?{_NUM}(?:\s?{_UNIT})?"                     # a range
    rf"|{_NUM}(?:\s?{_UNIT})?"                                        # a plain figure
    r")")

#: Exceptions — every one defined by WHERE the token sits or what it plainly is,
#: never by a shape a real figure could share. `^\d{1,2}\.$` once exempted the `12.`
#: in "reached 12."; `^\d{1,3}$` would exempt a bare `377` in a table.
YEAR = re.compile(r"^(?:18|19|20)\d\d(?:\s?[–-]\s?(?:18|19|20)\d\d)?[.,]?$")
LIST_MARKER_AT_LINE_START = re.compile(r"(?:^|\n)\s{0,3}(?:#{1,6}\s+)?(\d{1,2}\.)(?=\s)")
#: A number that names something rather than measuring it: a cross-reference, an
#: epoch index, a coordinate system, a hash length. Matched with its context so the
#: same digits elsewhere are still a figure.
REFERENCE = re.compile(r"(?:[Ss]ection|§|[Ee]poch|EPSG:?|SHA-|analysis[ _])\s?\d+\.?")
#: Structure a reader never sees as a number: identifiers, DOIs, URLs, HTML
#: entities, footnote superscripts, CSS colour tuples and angles, and code inside a
#: template literal's `${…}`. Removed before tokenising.
STRUCTURE = [
    re.compile(r"doi:\S+"), re.compile(r"https?://\S+"), re.compile(r"&#\d+;"),
    re.compile(r"rgba?\([^)]*\)"), re.compile(r"\d+deg\b"),
    re.compile(r"\$\{[^}]*\}"), re.compile(r"CC BY(?:-SA)? \d\.\d"),
]
SUPERSCRIPT = re.compile(r"<sup>.*?</sup>", re.S)


def strip_generated(text: str) -> str:
    return COG_REGION.sub("", text)


def _prose(text: str, *, html: bool) -> str:
    body = strip_generated(text)
    if html:
        body = SUPERSCRIPT.sub("", body)
        # Tags become newlines, not spaces, so a heading's "1." begins a line for
        # the list-marker rule — and so `</td>` never sits beside a cell's number.
        body = re.sub(r"<[^>]+>", "\n", body)
    for rx in STRUCTURE:
        body = rx.sub(" ", body)
    body = REFERENCE.sub(" ", body)
    return body


def figures_in(text: str, *, html: bool) -> set[str]:
    """Tokens a reader sees that are NOT generated and NOT excepted."""
    body = _prose(text, html=html)
    exempt_at = {m.start(1) for m in LIST_MARKER_AT_LINE_START.finditer(body)}
    out = set()
    for m in TOKEN.finditer(body):
        tok = normalise(m.group())
        if not re.search(r"\d", tok) or YEAR.match(tok) or m.start() in exempt_at:
            continue
        out.add(tok)
    return out


def normalise(token: str) -> str:
    """One spelling per figure: "30 metres", "30-metre" and "30 m" are the same
    claim, and the registry should say so once."""
    tok = re.sub(r"\s+", " ", token.strip())
    return re.sub(r"\s?-?metres?$", " m", tok)


def js_user_facing_strings(js: str) -> list[str]:
    """String literals in JavaScript, after comments are removed.

    Comments are developer-facing; strings are what the UI renders. Cog regions go
    first so a generated literal is never mistaken for a hand-typed one.
    """
    body = strip_generated(js)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"^\s*//.*$", "", body, flags=re.M)
    return re.findall(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|`(?:[^`\\]|\\.)*`", body)


# ---------------------------------------------------------------------------
# The generated figures match the build
# ---------------------------------------------------------------------------

@needs_build
def test_documents_match_the_build() -> None:
    assert run(check=True) == 0, (
        "a generated figure no longer matches the build — run `python "
        "scripts/sync_docs.py`, then check the prose around each changed number "
        "still says something true.")


@needs_build
def test_the_statistics_file_is_not_git_ignored() -> None:
    """The whole arrangement rests on this file being in the repo (CLAUDE.md #11)."""
    import subprocess
    out = subprocess.run(["git", "check-ignore", str(STATS)], cwd=ROOT, capture_output=True)
    assert out.returncode != 0, (
        "data/processed/statistics/layers.json is git-ignored again, so every check "
        "here silently starts skipping. Restore '!/data/processed/statistics/'.")


def test_every_listed_document_exists() -> None:
    missing = [d for d in DOCUMENTS if not (ROOT / d).exists()]
    assert not missing, f"listed in sync_docs.DOCUMENTS but absent: {missing}"


# ---------------------------------------------------------------------------
# Token-level surfaces: the page, the viewer, the README
# ---------------------------------------------------------------------------

PAGE = ROOT / "viewer" / "about-the-data.html"
APP_JS = ROOT / "viewer" / "app.js"
README = ROOT / "README.md"


def token_level_figures() -> dict[str, set[str]]:
    js = APP_JS.read_text()
    return {
        "viewer/about-the-data.html": figures_in(PAGE.read_text(), html=True),
        "viewer/app.js": {t for s in js_user_facing_strings(js) for t in figures_in(s, html=False)},
        "README.md": figures_in(README.read_text(), html=False),
    }


def test_no_unaccounted_figure_on_any_published_surface() -> None:
    """Per file, so a regression names where it is rather than that it exists."""
    from sensisat.provenance import HISTORICAL

    problems = []
    for surface, toks in token_level_figures().items():
        unaccounted = sorted(toks - set(HISTORICAL))
        if unaccounted:
            problems.append(f"  {surface}: {', '.join(unaccounted)}")
    assert not problems, (
        "figures with no declared source:\n" + "\n".join(problems) + "\n\n"
        "Every number a reader sees must be one of two things. If it comes from the "
        "current build, generate it (a cog marker calling sensisat/facts.py in prose; "
        "a key in viewer/facts.generated.js for the viewer). If it is a historical "
        "measurement, add it to sensisat/provenance.HISTORICAL saying what it is and "
        "which analysis produced it.")


def test_the_registry_has_no_dead_entries() -> None:
    """An entry for a figure on no surface is a claim nobody makes any more."""
    from sensisat.provenance import HISTORICAL

    present = set().union(*token_level_figures().values())
    dead = sorted(set(HISTORICAL) - present)
    assert not dead, ("registered in sensisat/provenance but on no published surface: "
                      + ", ".join(dead) + " — delete the entries.")


def test_no_cog_marker_inside_a_string_literal() -> None:
    """In code, "//" or "#" inside a string is TEXT the user would see.

    The first design put cog markers "inside the note: strings". Tested, that would
    have rendered the marker to the reader — and cog cannot parse JavaScript at all
    when a nested array literal ends in its own "]]]" token. Hence the generated
    module. This keeps anyone from reintroducing either.
    """
    for path in (APP_JS, ROOT / "sensisat" / "layers.py"):
        text = path.read_text()
        assert "[[[cog" not in text, f"{path.name} carries a cog marker; use facts.generated.js / catalog._fill"


def test_generated_facts_module_is_current() -> None:
    from sync_docs import render_facts_js
    assert FACTS_JS.exists(), "viewer/facts.generated.js missing — run scripts/sync_docs.py"
    assert FACTS_JS.read_text() == render_facts_js(), (
        "viewer/facts.generated.js is stale — run scripts/sync_docs.py, then npm run build")


# ---------------------------------------------------------------------------
# The catalogue: descriptions filled at write time, from that run's own numbers
# ---------------------------------------------------------------------------

@needs_build
def test_stac_descriptions_are_filled_from_the_same_run() -> None:
    """The item states ITS island's figure; the collection the archipelago's.

    `LayerSpec.description` is read from the module imported when the build began,
    so a number written into layers.py lags the build by one run forever. The
    description is therefore a template that `catalog._fill` completes from the
    statistics this run just computed. This checks the number in the text equals
    the number in the same item's `sensisat:statistics` — same file, same run.
    """
    items = sorted((ROOT / "data/processed/settlement-era-a").glob("*/settlement-era-a-*.json"))
    assert items, "no settlement-era-a items on disk"
    for item_path in items:
        item = json.loads(item_path.read_text())
        desc = item["properties"]["description"]
        assert "{" not in desc, f"{item_path.name}: unfilled placeholder in description"
        stats = item["properties"]["sensisat:statistics"]
        expected = round(100 * stats["pre-2016, undated"] / stats["footprint_km2"])
        stated = int(re.search(r"The (\d+) % that cannot inherit", desc).group(1))
        assert stated == expected, f"{item_path.name}: description says {stated} %, its own statistics give {expected} %"

    coll = json.loads((ROOT / "data/processed/settlement-era-a/collection.json").read_text())
    assert "{" not in coll["description"]
    for name in ("density-trend",):
        c = json.loads((ROOT / f"data/processed/{name}/collection.json").read_text())
        assert "{" not in c["description"], f"{name}: unfilled placeholder"


# ---------------------------------------------------------------------------
# The exceptions stay narrow
# ---------------------------------------------------------------------------

def test_no_exception_matches_a_token_carrying_a_unit() -> None:
    """If it has km² or % beside it, it is a measurement whatever its shape."""
    for surface, text, html in (("page", PAGE.read_text(), True),
                                ("README", README.read_text(), False)):
        for m in TOKEN.finditer(_prose(text, html=html)):
            tok = m.group().strip()
            if re.search(r"(km²|km2|m²|MiB|%|×)$", tok):
                assert not YEAR.match(tok), f"{surface}: year rule swallowed {tok!r}"


@pytest.mark.parametrize("text,kept", [
    ("see section 7 for the numbers", set()),          # cross-reference
    ("Epoch 1 is a baseline", set()),                   # an index
    ("projected to EPSG:4326", set()),                  # a coordinate system
    ("recorded with a SHA-256", set()),                 # a hash length
    ("it was M3 that found it", set()),                 # an identifier
    ("doi:10.1016/j.rse.2014.02.015 .", set()),         # a DOI
    ("rgba(255,190,90,.9) and 90deg", set()),           # CSS
    ("a 30-metre square, 30 metres wide", {"30 m"}),   # one figure, three spellings
    ("released under CC BY 4.0", set()),                # a licence version
    ("right 6 to 7 times in 10", {"6 to 7 times in 10"}),
    ("about 463 ± 83 km² of land", {"463 ± 83 km²"}),
    ("drops by 26–52 % at the join", {"26–52 %"}),
    ("between 1985-2015 and 2016", set()),               # a year range, a year
])
def test_structure_is_not_a_figure_and_composites_are_one_token(text: str, kept: set) -> None:
    assert figures_in(text, html=False) == kept


@pytest.mark.parametrize("text,exempt", [
    ("1. There is no single number", True),
    ("## 3. The result", True),
    ("   2. a nested list item", True),
    ("the total reached 12.", False),      # the case the shape rule got wrong
    ("it fell to 7.", False),
    ("the ratio was 1.234", False),
])
def test_list_marker_rule_is_positional(text: str, exempt: bool) -> None:
    exempt_at = {m.start(1) for m in LIST_MARKER_AT_LINE_START.finditer(text)}
    toks = list(TOKEN.finditer(text))
    assert toks, text
    assert (toks[0].start() in exempt_at) is exempt, f"{text!r}: exempt={not exempt} — wrong"
