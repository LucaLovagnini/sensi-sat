"""The judgement checks the figure gate cannot make — listed, then attested.

Three questions only a reader can answer, per `docs/design/figure-provenance.md`:

  1. Is each GENERATED figure generated from the right fact? `area("buildings-dated")`
     in a sentence about sealed surface passes every mechanical check and carries
     the authority of being generated. The most dangerous hole in the design.
  2. Is anything in the REGISTRY (`sensisat/provenance.HISTORICAL`) actually a live
     claim about our layers, mis-filed as a historical measurement? That is how
     "43 %" survived two builds.
  3. Does each section DECLARATION name a source that plausibly produces the
     section's numbers?

    python scripts/review_figures.py --list         # everything to read, side by side
    python scripts/review_figures.py --attest --reviewer "…" \
        --generated "…" --registry "…" --declarations "…"
    python scripts/review_figures.py --check        # exit 5 if the review is stale
    python scripts/review_figures.py --fingerprint

The attestation, `docs/figures-review.json`, carries a hash over the SET of figures
(tokens, generated regions, registry keys, declarations, live values) — so
rewording prose leaves it valid and changing one figure expires it. `publish.py`
refuses to assemble dist/ while it is stale; `.githooks/pre-push` refuses to push.
Neither can force the reading to have been careful: this records that a human (or
an agent, named) looked, and at what.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat.config import ROOT  # noqa: E402
from sensisat.figures import (  # noqa: E402
    COG_REGION,
    DECLARATION,
    PROSE_SURFACES,
    SECTION_SURFACES,
    figure_set,
    fingerprint,
    generated_regions,
    live_values,
    sections,
)
from sensisat.provenance import HISTORICAL  # noqa: E402

REVIEW = ROOT / "docs" / "figures-review.json"


def _context(text: str, start: int, end: int, width: int = 160) -> tuple[str, str]:
    """The prose either side of a region, tags and newlines removed — the sentence
    the figure lands in, which is what judgement 1 is about."""
    clean = lambda s: re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()  # noqa: E731
    return clean(text[max(0, start - width):start])[-width:], clean(text[end:end + width])[:width]


def listing() -> str:
    out = ["# 1. GENERATED figures — is each one generated from the RIGHT fact?", ""]
    for rel in PROSE_SURFACES:
        text = (ROOT / rel).read_text()
        for m, (code, output) in zip(COG_REGION.finditer(text), generated_regions(text), strict=True):
            before, after = _context(text, m.start(), m.end())
            out += [f"## {rel}", "    code:   " + code.replace("\n", "\n            "),
                    "    output: " + output.replace("\n", "\n            ")[:400],
                    f"    in:     …{before} [[{output[:60]}]] {after}…", ""]
    out += ["# 2. REGISTRY — is any of these a LIVE claim about our layers?", ""]
    out += [f"    {k!r:22} {v}" for k, v in HISTORICAL.items()] + [""]
    # A registry key equal to a current live value is a blind spot: the collision
    # check trusts the registry, so a hand-typed copy of that live value would pass
    # as the historical figure. Shown every review, so the reviewer knows to look.
    try:
        unit_of = {"km2": "km²", "mib": "MiB", "pct": "%", "x": "×"}
        coincide = []
        for k in HISTORICAL:
            m = re.fullmatch(r"(.+?)\s?(km²|%|×|MiB)?", k)
            number, unit = m.group(1), m.group(2)
            for name, v, u in live_values():
                same_unit = unit is None or unit == unit_of[u]      # a bare key can be anything
                if same_unit and number in {f"{v:,.0f}", f"{v:,.1f}", f"{v:,.2f}"}:
                    coincide.append(f"    {k!r} = {name} ({v:.2f})")
    except FileNotFoundError:
        coincide = ["    (no build on disk — cannot compare)"]
    out += ["## Registry keys that coincide with a live value today — a hand-typed copy of the live",
            "## figure would hide behind them; check each use in the prose is the historical one", ""]
    out += (coincide or ["    none"]) + [""]
    out += ["# 3. DECLARATIONS — does each source plausibly produce the section's numbers?", ""]
    for rel in SECTION_SURFACES:
        md = (ROOT / rel).read_text()
        for heading, body in sections(md):
            m = DECLARATION.search(body)
            if m:
                out += [f"    {rel} :: {heading[:60]}", f"        {m.group('sources')} @ {m.group('date')}"]
    return "\n".join(out)


def counts(fs: dict) -> dict:
    return {
        "token_level_figures": sum(len(v) for v in fs["tokens"].values()),
        "sections_with_figures": sum(len(v) for v in fs["sections"].values()),
        "generated_regions": sum(len(v) for v in fs["generated"].values()),
        "registry_entries": len(fs["registry"]),
        "declarations": sum(len(v) for v in fs["declarations"].values()),
    }


def check() -> int:
    if not REVIEW.exists():
        print(f"  no figure review on record ({REVIEW.relative_to(ROOT)} missing) — run /verify-figures")
        return 5
    rec = json.loads(REVIEW.read_text())
    now = fingerprint()
    if rec.get("fingerprint") == now:
        print(f"  figure review current: {rec['reviewed']} by {rec['reviewer']}")
        return 0
    print(f"  STALE: the figure review of {rec['reviewed']} no longer describes the documents.")
    then, fs = rec.get("figures", {}), figure_set()
    for kind in ("tokens", "generated", "declarations"):
        for rel in sorted(set(then.get(kind, {})) | set(fs[kind])):
            a, b = then.get(kind, {}).get(rel), fs[kind].get(rel)
            if a != b:
                print(f"    {kind} changed in {rel}")
    for rel in sorted(set(then.get("sections", {})) | set(fs["sections"])):
        a, b = then.get("sections", {}).get(rel, {}), fs["sections"].get(rel, {})
        for h in sorted(set(a) | set(b)):
            if a.get(h) != b.get(h):
                print(f"    section figures changed: {rel} :: {h[:60]}")
    if then.get("registry") != fs["registry"]:
        print("    registry entries changed")
    if then.get("live") != fs["live"]:
        print("    live values changed (a rebuild)")
    print("  Re-run the three judgements and attest again: see .claude/skills/verify-figures")
    return 5


def attest(reviewer: str, judgements: dict[str, str]) -> int:
    fs = figure_set()
    rec = {"fingerprint": fingerprint(), "reviewed": dt.date.today().isoformat(), "reviewer": reviewer,
           "judgements": judgements, "counts": counts(fs), "figures": fs}
    REVIEW.write_text(json.dumps(rec, indent=1, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"  attested {rec['fingerprint'][:12]}… on {rec['reviewed']} by {reviewer}: {counts(fs)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true")
    g.add_argument("--fingerprint", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--attest", action="store_true")
    ap.add_argument("--reviewer")
    ap.add_argument("--generated", help="judgement 1: generated figures come from the right facts")
    ap.add_argument("--registry", help="judgement 2: nothing in the registry is a live claim")
    ap.add_argument("--declarations", help="judgement 3: declared sources plausibly produce their numbers")
    a = ap.parse_args()
    if a.list:
        print(listing())
        return 0
    if a.fingerprint:
        print(fingerprint())
        return 0
    if a.check:
        return check()
    if not (a.reviewer and a.generated and a.registry and a.declarations):
        ap.error("--attest needs --reviewer and all three judgements, written out")
    return attest(a.reviewer, {"generated_from_right_fact": a.generated,
                               "registry_holds_no_live_claim": a.registry,
                               "declarations_plausible": a.declarations})


if __name__ == "__main__":
    raise SystemExit(main())
