"""Where every published number comes from — the extractor behind the figure gate.

Numbers reach readers through three kinds of surface, and every one is a copy of
something the pipeline computed: prose (`viewer/about-the-data.html`, `README.md`,
`docs/*.md`, `CLAUDE.md`), the viewer's strings (`viewer/app.js`), and the STAC
descriptions. A copy goes stale in silence, so every figure a reader can see must be
one of three things:

  * GENERATED from one key store, `sensisat/facts.py` — by cog into HTML comments, by
    `scripts/sync_docs.py` into `viewer/facts.generated.js`, by `catalog._fill` into
    STAC descriptions at write time;
  * DECLARED — historical measurements frozen on purpose, in `sensisat/provenance.py`
    (token by token, for the public page, the viewer and the README) or per section
    (`<!-- figures: … @ date -->` under the heading, for docs/ and CLAUDE.md);
  * EXCEPTED by a narrow, positional rule: a year, a date, a Markdown list marker, a
    cross-reference ("section 7", "decision 4"), or structure a reader never reads
    as a number (a DOI, a URL, a CSS colour, a licence version, an HTML comment).

Anything else fails the build, naming the token and the file. Fail-closed on
purpose: an earlier version let a regex decide what counted as a figure and it
silently exempted the whole ladder-of-definitions table, twice.

This module is the one definition of all that. `tests/test_documented_numbers.py`
turns it into tests (and holds the fixtures that keep the exceptions honest);
`scripts/sync_docs.figure_gate` runs those tests for `build.py` and `publish.py`;
`scripts/review_figures.py` lists what a human must still judge and fingerprints
the set of figures for the attestation the pre-push hook checks.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .config import ROOT

# ---------------------------------------------------------------------------
# Extraction
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
    "regulation": re.compile(r"Regulation \(EU\) (?:No )?\d+/\d{4}|Directive \d{4}/\d+/E[CU]"),
    "version": re.compile(r"\bv\d+(?:\.\d+)+\b"),
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


def generated_regions(text: str) -> list[list[str]]:
    """(code, output) for every cog region — what a reviewer must read side by side:
    the fact each figure was generated FROM, and the sentence it landed in."""
    out = []
    for m in COG_REGION.finditer(text):
        region = m.group()
        code = re.search(r"\[\[\[cog(.*?)\]\]\]", region, re.S).group(1).strip()
        out.append([code, _generated_output(region).strip()])   # lists: JSON round-trips them unchanged
    return out


# ---------------------------------------------------------------------------
# The surfaces
# ---------------------------------------------------------------------------

PAGE = ROOT / "viewer" / "about-the-data.html"
APP_JS = ROOT / "viewer" / "app.js"
README = ROOT / "README.md"
PROSE_SURFACES = [
    "viewer/about-the-data.html", "README.md", "CLAUDE.md",
    *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").rglob("*.md")),
]
SECTION_SURFACES = ["CLAUDE.md",
                    *sorted(str(p.relative_to(ROOT)) for p in (ROOT / "docs").rglob("*.md"))]


def read(rel: str, texts: dict[str, str] | None = None) -> str:
    """A surface's text — from `texts` when a caller supplies it (tests, fingerprint
    experiments), from disk otherwise."""
    return texts[rel] if texts and rel in texts else (ROOT / rel).read_text()


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


# ---------------------------------------------------------------------------
# The evidence files
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


# ---------------------------------------------------------------------------
# The fingerprint: the set of figures, for the human attestation
# ---------------------------------------------------------------------------

def figure_set(texts: dict[str, str] | None = None) -> dict:
    """Everything a review judged, as data — so rewording prose leaves the attestation
    valid and changing one figure, one declaration or one registry key expires it.

    Per token-level surface: its figures. Per section-level surface: each section's
    figures, keyed by heading. Every generated region's code and output. Every
    registry key. Every declaration. Every live value the build currently gives.
    """
    from .provenance import HISTORICAL
    page, app, readme = (read(r, texts) for r in ("viewer/about-the-data.html", "viewer/app.js", "README.md"))
    out: dict = {
        "tokens": {
            "viewer/about-the-data.html": sorted(figures_in(page, html=True)),
            "viewer/app.js": sorted({t for s in js_user_facing_strings(app) for t in figures_in(s, html=False)}),
            "README.md": sorted(figures_in(readme, html=False)),
        },
        "sections": {}, "generated": {}, "declarations": {},
        "registry": sorted(HISTORICAL),
    }
    for rel in SECTION_SURFACES:
        md = read(rel, texts)
        out["sections"][rel] = {h: sorted(figures_in(b, html=False)) for h, b in sections(md)
                                if figures_in(b, html=False)}
        out["declarations"][rel] = [m.group("sources") + " @ " + m.group("date")
                                    for m in DECLARATION.finditer(md)]
    for rel in ["viewer/about-the-data.html", "README.md", *SECTION_SURFACES]:
        regions = generated_regions(read(rel, texts))
        if regions:
            out["generated"][rel] = regions
    try:
        out["live"] = {name: round(v, 3) for name, v, _ in live_values()}
    except FileNotFoundError:
        out["live"] = None
    return out


def fingerprint(texts: dict[str, str] | None = None) -> str:
    return hashlib.sha256(json.dumps(figure_set(texts), sort_keys=True, ensure_ascii=False)
                          .encode()).hexdigest()
