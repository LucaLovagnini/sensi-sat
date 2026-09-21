"""The figure gate as tests — every number a reader can see is accounted for.

The mechanism lives in `sensisat/figures.py` (one definition, so `build.py`,
`publish.py`, the review script and the pre-push hook cannot check different
things). This file turns it into tests and holds the fixtures that keep the
exceptions honest: a shape that once exempted `"reached 12."`, a rule that once
swallowed the ladder table, each pinned so it cannot come back.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sync_docs import DOCUMENTS, FACTS_JS, run  # noqa: E402

from sensisat.facts import STATS  # noqa: E402
from sensisat.figures import (  # noqa: E402
    APP_JS,
    COLLISIONS_ALLOWED,
    DATA_DIR,
    EXEMPTIONS_BASELINE,
    LIST_MARKER_AT_LINE_START,
    MANIFEST,
    PAGE,
    PROSE_SURFACES,
    README,
    SECTION_SURFACES,
    TOKEN,
    YEAR,
    _prose,
    code_referring_to,
    current_exemptions,
    declaration_problems,
    figures_in,
    fingerprint,
    hand_typed_live_figures,
    js_user_facing_strings,
    quantity_words_without_digits,
    token_level_figures,
)

needs_build = pytest.mark.skipif(
    not STATS.exists(), reason="run scripts/build.py --all first")


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

def test_exemption_counts_match_the_baseline() -> None:
    """The exceptions are the fail-open surface of this gate; pin what they do.

    A year rule that one day also matches `2015.5`, or a reference rule widened to
    swallow `section 7 %`, would exempt real figures without any test failing —
    exactly how the ladder table vanished twice. So the number of tokens each
    exception removes, per file, is recorded and any change has to be made on
    purpose: python tests/test_documented_numbers.py --write-baseline
    """
    assert EXEMPTIONS_BASELINE.exists(), "tests/fixtures/figure_exemptions.json missing"
    baseline = json.loads(EXEMPTIONS_BASELINE.read_text())
    now = current_exemptions()
    diffs = [f"  {f}.{k}: baseline {baseline.get(f, {}).get(k)} -> now {v}"
             for f, counts in now.items() for k, v in counts.items()
             if baseline.get(f, {}).get(k) != v]
    assert not diffs, (
        "an exception exempts a different number of tokens than it did:\n"
        + "\n".join(diffs)
        + "\n\nIf you edited the prose and the change is what you meant, run\n"
          "  python tests/test_documented_numbers.py --write-baseline\n"
          "and review the diff of tests/fixtures/figure_exemptions.json. If you did "
          "NOT touch that file, an exception pattern has widened — look there first.")


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


def test_quantity_words_carry_their_digits() -> None:
    """CLAUDE.md #23: "three in ten (31 %)", never "three in ten".

    The figure gate would otherwise create a perverse incentive — a number written
    as words is invisible to it, so the path of least resistance under a strict gate
    is to stop writing digits. This closes that path. Applied to every prose surface
    and to the viewer's strings; comments and code are not prose.
    """
    problems = []
    for rel in PROSE_SURFACES:
        hits = quantity_words_without_digits((ROOT / rel).read_text(), html=rel.endswith(".html"))
        problems += [f"  {rel} {h}" for h in hits]
    for s in js_user_facing_strings(APP_JS.read_text()):
        problems += [f"  viewer/app.js {h}" for h in quantity_words_without_digits(s, html=False)]
    assert not problems, (
        "a quantity word with no figure beside it:\n" + "\n".join(problems)
        + "\n\nWrite the digits next to the word — \"a quarter to a third (24–33 %)\" — or "
          "replace the word with the figure. If it is an ordinal or an idiom "
          "(\"a third party\"), add it to NOT_A_QUANTITY in this file.")


@pytest.mark.parametrize("text,ok", [
    ("the undated class is about a quarter empty.", False),
    ("about a quarter (28 %) empty.", True),
    ("three in ten (31 %) cells are missing", True),
    ("three in ten cells are missing", False),
    ("31 % — three in ten — are missing", True),           # digits before the word
    ("that is a third party on the critical path", True),  # idiom
    ("the mode as a third number", True),                   # ordinal
    ("a third of these already stood in 2015", False),      # a year is not the figure
    ("gain is 0.394 %/yr, about a third of Tracker's rate", True),
    ('write "three in ten (31 %)", not "three in ten".', True),  # mentioned, not used
    ("six-fold (2,700 m² against 450 m²)", True),
    ("overstates it six-fold.", False),
    ("Growth ×7.5 in the table.\n\nOverstates it six-fold.", False),  # not across paragraphs
])
def test_quantity_word_rule_fixtures(text: str, ok: bool) -> None:
    assert (quantity_words_without_digits(text, html=False) == []) is ok, text


def test_page_headings_are_numbered_by_css_not_by_hand() -> None:
    """A typed "3." in a heading is a digit the gate must either except or account
    for. Rendered by a CSS counter it is neither — it is not in the source at all."""
    assert not re.search(r"<h2>\s*\d", PAGE.read_text()), "a page heading carries a typed number"
    css = (ROOT / "viewer" / "about.css").read_text()
    assert "counter-increment: section" in css and "content: counter(section)" in css


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
# Section-level surfaces: docs/*.md and CLAUDE.md declare where their numbers came from
# ---------------------------------------------------------------------------

def test_every_section_with_a_figure_declares_its_source() -> None:
    """docs/ holds ~1,700 figures, overwhelmingly historical; a registry entry each
    would be abandoned in a week. So the unit is the section: every section that
    states a figure names the script or data file that produced it, under its heading.
    The declaration records origin — what verifies digits is cog and the collision
    check below. A historical digit mis-typed once is caught by nothing mechanical."""
    problems = [f"  {rel}: {p}" for rel in SECTION_SURFACES
                for p in declaration_problems((ROOT / rel).read_text())]
    assert not problems, (
        "sections stating figures with no declared source, or a source that does not exist:\n"
        + "\n".join(problems)
        + "\n\nAdd under the heading: <!-- figures: scripts/analysis_NN_x.py; "
          "docs/figures/data/m0_x.csv @ YYYY-MM-DD -->  (or external:<what> / measured:<how>)")


@pytest.mark.parametrize("md,ok", [
    ("# T\n\nintro\n\n## A\n<!-- figures: scripts/build.py @ 2026-09-19 -->\n12 km² built\n", True),
    ("# T\n\n## A\n\n12 km² built with no declaration\n", False),
    ("# T\n\n12 km² in the preamble, undeclared\n\n## A\ntext\n", False),           # H1 preamble
    ("# T\n<!-- figures: scripts/build.py @ 2026-09-19 -->\n12 km²\n\n## A\ntext\n", True),
    ("## A\n<!-- figures: scripts/nope.py @ 2026-09-19 -->\n12 km²\n", False),          # missing file
    ("## A\n<!-- figures: external:Cloudflare price list, read 2026-09-20; scripts/build.py @ 2026-09-20 -->\n$4\n", True),
    ("## A\n<!-- figures: scripts/build.py, scripts/nope.py @ 2026-09-20 -->\n$4\n", False),  # comma is not a separator
    ("## A\n<!-- figures: measured:Chrome DevTools @ 2026-09-20 -->\n150 KiB\n", True),
    ("## A\n\nno figures, no declaration needed\n", True),
    ("## A\n\nyears alone: 1985 to 2015, decision 7\n", True),                          # excepted only
])
def test_section_declaration_fixtures(md: str, ok: bool) -> None:
    assert (declaration_problems(md) == []) is ok, declaration_problems(md)


def test_markdown_cog_regions_stand_alone() -> None:
    """In Markdown a comment line ends the paragraph it interrupts, so a region set
    mid-sentence renders as three paragraphs. A region must be preceded and followed
    by a blank line (or a file boundary) and generate whole lines."""
    problems = []
    for rel in [d for d in DOCUMENTS if d.endswith(".md")]:
        lines = (ROOT / rel).read_text().splitlines()
        for i, ln in enumerate(lines):
            if ln.lstrip().startswith("<!--[[[cog") and i > 0 and lines[i - 1].strip():
                problems.append(f"  {rel}:{i + 1} region opens mid-paragraph")
            if ln.strip() == "<!--[[[end]]]-->" and i + 1 < len(lines) and lines[i + 1].strip():
                problems.append(f"  {rel}:{i + 1} region closes mid-paragraph")
    assert not problems, "Markdown cog regions must stand alone:\n" + "\n".join(problems)


# ---------------------------------------------------------------------------
# The collision check: a live value typed by hand anywhere in prose
# ---------------------------------------------------------------------------

@needs_build
def test_no_live_figure_is_typed_by_hand() -> None:
    """The check that closes the docs/ drift hole without 1,700 registry entries.
    A figure the build computes, found typed in prose, is a copy that the next build
    will silently orphan — unless a human has decided, once, that it is a historical
    measurement which happens to coincide (recorded with its reason in the fixture)."""
    allowed = {(e["file"], e["figure"]): e["why"] for e in json.loads(COLLISIONS_ALLOWED.read_text())}
    hits = hand_typed_live_figures()
    new = [f"  {rel}: {fig}  (= {', '.join(names)})" for (rel, fig), names in sorted(hits.items())
           if (rel, fig) not in allowed]
    dead = [f"  {rel}: {fig}" for (rel, fig) in allowed if (rel, fig) not in hits]
    assert not new, (
        "a figure the build computes is typed by hand in prose:\n" + "\n".join(new)
        + "\n\nEither generate it (a cog region calling sensisat/facts.py) or, if it is a "
          "historical measurement that coincides with the current build, add it to "
          "tests/fixtures/figure_collisions.json saying why.")
    assert not dead, "allowed collisions no longer present — delete them:\n" + "\n".join(dead)


# ---------------------------------------------------------------------------
# The evidence files: every table under docs/figures/data has a known origin
# ---------------------------------------------------------------------------

def test_every_data_file_has_a_producer_or_a_manifest_entry() -> None:
    """The declarations above point at these files as evidence. A CSV that nothing
    writes cannot be regenerated, so it must at least say which commit introduced it
    and what it is — eight M0 tables and the four label files are of that kind."""
    manifest = {e["file"]: e for e in json.loads(MANIFEST.read_text())}
    problems = []
    for p in sorted(DATA_DIR.iterdir()):
        if p.suffix not in (".csv", ".json") or p.name == MANIFEST.name:
            continue
        if code_referring_to(p.name):
            continue
        e = manifest.get(p.name)
        if not e:
            problems.append(f"  {p.name}: no code names it and no manifest entry")
        elif not re.fullmatch(r"[0-9a-f]{7,40}", e.get("introduced", "")) or not e.get("why"):
            problems.append(f"  {p.name}: manifest entry needs 'introduced' (a commit) and 'why'")
    for name in manifest:
        if not (DATA_DIR / name).exists():
            problems.append(f"  {name}: in the manifest but not on disk — delete the entry")
    assert not problems, ("data files with no known origin:\n" + "\n".join(problems)
                          + "\n\nName the file in the script that writes it, or add it to "
                            "docs/figures/data/manifest.json with the commit that introduced it.")


# ---------------------------------------------------------------------------
# The attestation fingerprint moves with figures, not with prose
# ---------------------------------------------------------------------------

def test_fingerprint_ignores_rewording_and_notices_a_figure() -> None:
    """The human review is attested with a hash over the SET of figures. Rewording a
    sentence must leave it valid; changing one figure, one declaration or one
    registry key must expire it — otherwise the attestation is either nagging or
    meaningless."""
    page = PAGE.read_text()
    base = fingerprint()
    reworded = page.replace("Every number on the map", "Each figure on the map", 1)
    assert reworded != page
    assert fingerprint({"viewer/about-the-data.html": reworded}) == base, "rewording changed the hash"
    with_figure = page.replace("</p>", " Another 42.7 km² here.</p>", 1)
    assert fingerprint({"viewer/about-the-data.html": with_figure}) != base, "a new figure left the hash unchanged"
    md = (ROOT / "docs/pipeline.md").read_text()
    redeclared = md.replace("@ 2026-09-19 -->", "@ 2026-09-20 -->", 1)
    assert redeclared != md
    assert fingerprint({"docs/pipeline.md": redeclared}) != base, "an edited declaration left the hash unchanged"


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
    ("status: proposal, 2026-09-19.", set()),            # a date
    ("decision 7 says; guardrail G6 holds", set()),      # references
    ("maplibre-gl-js#4479 is open", set()),              # an issue number
    ("see analysis_01_totals.py", set()),                # an identifier
    ("<!-- figures: scripts/analysis_01_totals.py; x.csv @ 2026-09-19 --> 12 km²", {"12 km²"}),
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


if __name__ == "__main__":
    if "--write-baseline" not in sys.argv:
        raise SystemExit(__doc__ + "\n\nusage: python tests/test_documented_numbers.py --write-baseline")
    EXEMPTIONS_BASELINE.parent.mkdir(exist_ok=True)
    EXEMPTIONS_BASELINE.write_text(json.dumps(current_exemptions(), indent=2) + "\n")
    print(f"wrote {EXEMPTIONS_BASELINE.relative_to(ROOT)}")
