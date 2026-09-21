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
_DATE = r"(?:18|19|20)\d\d-\d\d(?:-\d\d)?"

#: Every run of digits a reader could read as a number — as the reader reads it.
#: Composite claims are ONE token, tried first: "98 times in 100", "463 ± 83 km²",
#: "26–52 %". Splitting them into bare integers would leave the registry keyed by
#: "7" and "26", which match anything. The negative lookbehind stops identifiers
#: being read as numbers: M3, km2, EPSG4326 are names, not figures.
TOKEN = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    rf"{_DATE}"                                                        # a date, exempted below
    rf"|\d{{1,3}} (?:to \d{{1,3}} )?times in \d{{1,3}}"          # accuracy in words
    rf"|{_NUM}\s?±\s?{_NUM}(?:\s?{_UNIT})?"                        # value ± interval
    rf"|{_NUM}\s?[–-]\s?{_NUM}(?:\s?{_UNIT})?"                     # a range
    rf"|{_NUM}(?:\s?{_UNIT})?"                                        # a plain figure
    r")")

#: Exceptions — every one defined by WHERE the token sits or what it plainly is,
#: never by a shape a real figure could share. `^\d{1,2}\.$` once exempted the `12.`
#: in "reached 12."; `^\d{1,3}$` would exempt a bare `377` in a table.
YEAR = re.compile(r"^(?:18|19|20)\d\d(?:-\d\d(?:-\d\d)?|\s?[–-]\s?(?:18|19|20)\d\d)?[.,]?$")
LIST_MARKER_AT_LINE_START = re.compile(r"(?:^|\n)\s{0,3}(?:#{1,6}\s+)?(\d{1,2}\.)(?=\s)")
#: A number that names something rather than measuring it: a cross-reference, an
#: epoch index, a coordinate system, a hash length. Matched with its context so the
#: same digits elsewhere are still a figure.
REFERENCE = re.compile(
    r"(?:[Ss]ection|§|[Ee]poch|EPSG:?|SHA-|analysis[ _]|[Dd]ecisions?\s?(?:M\d\.)?|[Gg]uardrail G)\s?\d+\.?")
#: Structure a reader never sees as a number: identifiers, DOIs, URLs, HTML
#: entities, footnote superscripts, CSS colour tuples and angles, and code inside a
#: template literal's `${…}`. Removed before tokenising.
STRUCTURE = {
    "doi": re.compile(r"doi:\S+"), "url": re.compile(r"https?://\S+"),
    "entity": re.compile(r"&#\d+;"), "css": re.compile(r"rgba?\([^)]*\)|\d+deg\b"),
    "interpolation": re.compile(r"\$\{[^}]*\}"), "licence": re.compile(r"CC BY(?:-SA)? \d\.\d"),
    "issue": re.compile(r"#\d+\b"),
    # a comment is invisible to the reader, so nothing in it is a claim — this is
    # also what makes the section declarations below cost nothing
    "comment": re.compile(r"<!--.*?-->", re.S),
}
SUPERSCRIPT = re.compile(r"<sup>.*?</sup>", re.S)
#: How many tokens each exception exempts, per surface. A pattern that starts
#: matching more than it did is the fail-open failure this whole test guards
#: against, so the counts are pinned and change only by editing the fixture.
EXEMPTIONS_BASELINE = ROOT / "tests" / "fixtures" / "figure_exemptions.json"


def strip_generated(text: str) -> str:
    return COG_REGION.sub("", text)


def _prose(text: str, *, html: bool) -> str:
    body = strip_generated(text)
    if html:
        body = SUPERSCRIPT.sub("", body)
        # Tags become newlines, not spaces, so a heading's "1." begins a line for
        # the list-marker rule — and so `</td>` never sits beside a cell's number.
        body = re.sub(r"<[^>]+>", "\n", body)
    for rx in STRUCTURE.values():
        body = rx.sub(" ", body)
    body = REFERENCE.sub(" ", body)
    return body


def exemption_counts(text: str, *, html: bool) -> dict[str, int]:
    """What each exception removed, counting only matches that carried a digit."""
    digits = lambda ms: sum(1 for m in ms if re.search(r"\d", m.group()))  # noqa: E731
    body = strip_generated(text)
    counts = {"generated": len(COG_REGION.findall(text))}
    if html:
        counts["superscript"] = digits(SUPERSCRIPT.finditer(body))
        body = SUPERSCRIPT.sub("", body)
        body = re.sub(r"<[^>]+>", "\n", body)
    for name, rx in STRUCTURE.items():
        counts[name] = digits(rx.finditer(body))
        body = rx.sub(" ", body)
    counts["reference"] = len(REFERENCE.findall(body))
    body = REFERENCE.sub(" ", body)
    exempt_at = set() if html else {m.start(1) for m in LIST_MARKER_AT_LINE_START.finditer(body)}
    counts["year"] = sum(1 for m in TOKEN.finditer(body) if YEAR.match(normalise(m.group())))
    counts["list_marker"] = sum(1 for m in TOKEN.finditer(body) if m.start() in exempt_at)
    return counts


def figures_in(text: str, *, html: bool) -> set[str]:
    """Tokens a reader sees that are NOT generated and NOT excepted."""
    body = _prose(text, html=html)
    # HTML has no list markers in its source: <ol> numbers itself and the page's
    # section numbers are CSS counters (about.css). So the exception is Markdown-only.
    exempt_at = set() if html else {m.start(1) for m in LIST_MARKER_AT_LINE_START.finditer(body)}
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


#: Words that stand in for a figure. Deliberately narrow — "half", "twice",
#: "double" and "most" are ordinary English far more often than they are numbers
#: (measured: 14 false hits on the real prose), and a lint that cries wolf gets
#: switched off. These six shapes are almost always a measurement in disguise.
QUANTITY_WORD = re.compile(
    r"\b(?:a (?:third|quarter|fifth|tenth)|two[- ]thirds|three[- ]quarters"
    r"|(?:one|two|three|four|five|six|seven|eight|nine) in (?:ten|five|four|three)"
    r"|[a-z]+-fold)\b", re.I)
#: Ordinals and idioms that share a spelling with a fraction. Each is here because
#: it occurred in the prose; extend this list, never loosen the rule above.
NOT_A_QUANTITY = re.compile(r"third part(?:y|ies)|as a third\b|a third surface", re.I)
#: A quoted phrase is mentioned, not used — CLAUDE.md #23 quotes the wrong form to
#: forbid it, and validation.md quotes what a reviewer was told.
MENTION = re.compile(r"[\"“][^\"“”\n]{1,80}[\"”]")
#: How far from the word its digits may sit, within the same paragraph.
DIGIT_REACH = 60


def _generated_output(region: str) -> str:
    """The text cog wrote — what the reader sees — without the code that wrote it."""
    body = re.sub(r"\[\[\[cog.*?\]\]\](?:-->|\*/)?", "", region, count=1, flags=re.S)
    return re.sub(r"(?:<!--|/\*|//|#)?\s*\[\[\[end\]\]\].*$", "", body, flags=re.S)


def quantity_words_without_digits(text: str, *, html: bool) -> list[str]:
    """Every quantity word with no figure beside it. Years do not count as figures."""
    body = COG_REGION.sub(lambda m: _generated_output(m.group()), text)
    if html:
        body = re.sub(r"<[^>]+>", " ", body)
    body = MENTION.sub(lambda m: " " * len(m.group()), body)
    idioms = [(m.start(), m.end()) for m in NOT_A_QUANTITY.finditer(body)]
    out = []
    for m in QUANTITY_WORD.finditer(body):
        if any(s < m.end() and m.start() < e for s, e in idioms):  # spans overlap
            continue
        lo, hi = max(0, m.start() - DIGIT_REACH), m.end() + DIGIT_REACH
        window = body[lo:hi]
        # stay inside the paragraph
        before, after = window[:m.start() - lo], window[m.start() - lo:]
        before = before.rsplit("\n\n", 1)[-1]
        after = after.split("\n\n", 1)[0]
        window = before + after
        if not any(re.search(r"\d", normalise(t.group())) and not YEAR.match(normalise(t.group()))
                   for t in TOKEN.finditer(window)):
            line = body.count("\n", 0, m.start()) + 1
            out.append(f"line {line}: …{body[max(0, m.start()-30):m.end()+30].strip()}…".replace("\n", " "))
    return out


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


def current_exemptions() -> dict[str, dict[str, int]]:
    js_strings = "\n".join(js_user_facing_strings(APP_JS.read_text()))
    return {
        "viewer/about-the-data.html": exemption_counts(PAGE.read_text(), html=True),
        "viewer/app.js": exemption_counts(js_strings, html=False),
        "README.md": exemption_counts(README.read_text(), html=False),
    }


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


PROSE_SURFACES = [
    "viewer/about-the-data.html", "README.md", "CLAUDE.md",
    *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").rglob("*.md")),
]


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

SECTION_SURFACES = ["CLAUDE.md",
                    *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").rglob("*.md"))]
#: `<!-- figures: <source>[; <source>…] @ <YYYY-MM-DD> -->` — a source is a repository
#: file that must exist, or `external:<what>` for a published source outside the
#: repository (a price list, a paper), or `measured:<how>` for a hand measurement
#: that left no file (a browser's network panel). The labels are the honest form
#: for numbers that have no script; they are counted, and the design doc says how many.
DECLARATION = re.compile(
    r"<!--\s*figures:\s*(?P<sources>.+?)\s*@\s*(?P<date>\d{4}-\d{2}-\d{2})\s*-->", re.S)
LABELLED_SOURCE = re.compile(r"^(?:external|measured):\s*\S")


def sections(md: str) -> list[tuple[str, str]]:
    """(heading, text) per section: the H1 preamble, then each `## ` block with its
    `###` children. The preamble counts because two documents state figures there."""
    return [(p.splitlines()[0].strip(), p) for p in re.split(r"(?m)^(?=## )", md) if p.strip()]


def declaration_problems(md: str, *, root: Path = ROOT) -> list[str]:
    """A section needs a declaration iff it holds a figure that is neither generated
    nor excepted. Declared sources must exist (or be labelled external/measured)."""
    out = []
    for heading, body in sections(md):
        toks = figures_in(body, html=False)
        decl = DECLARATION.search(body)
        if toks and not decl:
            out.append(f"{heading!r}: {len(toks)} undeclared figures "
                       f"({', '.join(sorted(toks)[:4])}{'…' if len(toks) > 4 else ''})")
        elif decl:
            for src in (s.strip() for s in decl.group("sources").split(";")):
                if not LABELLED_SOURCE.match(src) and not (root / src).exists():
                    out.append(f"{heading!r}: declared source {src!r} does not exist")
    return out


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

COLLISIONS_ALLOWED = ROOT / "tests" / "fixtures" / "figure_collisions.json"
_UNIT_TEXT = {"km2": ("km²", r"\**\s?(?:km²|km2)"), "mib": ("MiB", r"\**\s?MiB"),
              "pct": ("%", r"\**\s?%"), "x": ("×", r"\**\s?×")}


def live_values() -> list[tuple[str, float, str]]:
    """Every headline figure facts.py can produce, with the unit prose would attach.
    Not the seam record's per-island fields: the M2 seam reproduces M0's CSV to the
    published decimal, so every one of them collides with the M0 tables by design."""
    import sensisat.facts as f
    out = []
    for layer in f.stats():
        out += [(f"area({layer})", f.area(layer), "km2"), (f"size_mib({layer})", f.size_mib(layer), "mib")]
        out += [(f"area({layer}, {isl})", f.area(layer, isl), "km2") for isl in f.stats()[layer]]
    out += [("size_six_layers()", f.size_six_layers(), "mib"), ("size_confidence()", f.size_confidence(), "mib"),
            ("size_published()", f.size_published(), "mib"), ("dated_share()", f.dated_share(), "pct"),
            ("undated_share()", f.undated_share(), "pct"), ("sealed_vs_built_ratio()", f.sealed_vs_built_ratio(), "x"),
            ("crash_pct()", f.crash_pct(), "pct"),
            ("growth_pct(era-a, Gran Canaria, 1995, 2015)", f.growth_pct("settlement-era-a", "Gran Canaria", 1995, 2015), "pct")]
    return out


def hand_typed_live_figures() -> dict[tuple[str, str], list[str]]:
    """(file, figure) -> facts that produce it, for every live value found in prose
    outside a cog region and not declared historical in the registry. Values below 1
    are skipped — at two decimals they collide by coincidence ($0.36/million matched
    La Graciosa's extent) — and a unit must be attached, so a bare table cell is not
    seen. Both limits are recorded in the design doc."""
    from sensisat.provenance import HISTORICAL
    declared = {re.sub(r"\s?(km²|%|×|MiB)$", "", k) for k in HISTORICAL}
    hits: dict[tuple[str, str], list[str]] = {}
    for rel in PROSE_SURFACES:
        body = strip_generated((ROOT / rel).read_text())
        for name, v, u in live_values():
            if v < 1:
                continue
            unit, unit_rx = _UNIT_TEXT[u]
            for s in {f"{v:,.2f}", f"{v:,.1f}"}:
                if s in declared:
                    continue
                if re.search(rf"(?<![\d.]){re.escape(s)}{unit_rx}", body):
                    hits.setdefault((rel, f"{s} {unit}"), []).append(name)
    return hits


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

DATA_DIR = ROOT / "docs" / "figures" / "data"
MANIFEST = DATA_DIR / "manifest.json"
CODE_DIRS = ("scripts", "sensisat", "docs/figures/src", "viewer", "tests")


def code_referring_to(basename: str) -> list[str]:
    """Code files that name the data file — the mechanical notion of 'produced by'.
    Grep cannot tell a read from a write, so a file only READ by code (the CORINE
    band) passes here; the manifest still records it, for honesty."""
    out = []
    for d in CODE_DIRS:
        for p in (ROOT / d).rglob("*.py"):
            if basename in p.read_text():
                out.append(str(p.relative_to(ROOT)))
        for p in (ROOT / d).rglob("*.js"):
            if basename in p.read_text():
                out.append(str(p.relative_to(ROOT)))
    return out


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
