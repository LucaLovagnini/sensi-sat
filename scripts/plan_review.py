"""List the sentences in the plan that have most likely outlived their truth.

    python scripts/plan_review.py            # read the plan CLAUDE.md names
    python scripts/plan_review.py --plan PATH

The plan (`~/.claude/plans/…`) is the one document nothing checks: it is outside
the repository on purpose — it holds what we *intend*, including options we
rejected, while the repository holds what is verified — so the figure gate does
not apply to it and never should. Reviewed by hand on 2026-09-21 it held nine stale
statements, and they were stale in a pattern worth automating:

  * **five of the nine carried a tell** — a phrase written facing forwards ("must
    decide", "provisional", "not yet fetched", "pending", "will … for now"). A plan
    is written in the future tense; the sentences that age are the ones that
    promised something.
  * **the ranking is the point.** Such a phrase inside an open section is a plan
    doing its job. Inside a section whose heading says COMPLETE, DONE or CLOSED it
    contradicts the heading, and that is where the day's two worst finds lived:
    "Provisional" in a table of settled decisions, and a "NOT met" row under a
    heading already marked complete.
  * **four carried no tell at all** — a guardrail's status, a figure the build had
    moved past (54.1 MiB against today's 60.2), a requirement list quoting a
    superseded share. Grammar cannot see those. The second half of this script does
    not find them either; it answers the *neighbouring* question — see `figures()`.

So: this prints a list to read. It never edits the plan, never judges whether a
number is wrong (that needs meaning, not grammar), and **always exits 0** — it is
not a gate, and it is not run by pytest, because no other clone of this repository
has the plan at all.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat.figures import live_figures_in, live_values  # noqa: E402

#: The path CLAUDE.md records. `SENSISAT_PLAN` overrides it; so does `--plan`.
DEFAULT_PLAN = Path(os.environ.get(
    "SENSISAT_PLAN", Path.home() / ".claude/plans/ok-i-think-that-purrfect-horizon.md"))

#: Phrases that promise something. Each is a sentence written facing forwards, which
#: is exactly the kind that stops being true without anyone editing it. Kept narrow:
#: a bare "will" or "should" fires on ordinary prose and would bury the signal.
TELLS = {
    "undecided": re.compile(r"\bmust decide\b|\bto be decided\b|\bopen question\b|\bTBD\b|\bTODO\b", re.I),
    # not "recommended": it fires on "the recommended dataset per period" and buries
    # the signal. Not a bare "remains" either — "remains the intent of criterion 21"
    # is ordinary English; only "remains open / to be" promises anything.
    "provisional": re.compile(r"\bprovisional\b|\bproposal\b|\bprototype .{0,20}\bat M\d", re.I),
    "not done yet": re.compile(r"\bnot yet\b|\bstill to do\b|\bpending\b|\bis next\b"
                               r"|\bnext milestone\b|\bremains? (?:open|unresolved|to be|undone)\b", re.I),
    "blocked": re.compile(r"\bblocked\b|\bdeferred\b|\bwaits? on\b|\bwaiting on\b", re.I),
    "future tense": re.compile(r"\bwill (?:be|need|decide|register|have to|replace|add)\b|\bM\d[a-z]? (?:must|will)\b", re.I),
}
#: A heading that claims the work behind it is finished.
SETTLED = re.compile(r"\b(COMPLETE|DONE|CLOSED|IMPLEMENTED|SETTLED|✅)\b")
HEADING = re.compile(r"^(#{1,4})\s+(.*)$")


def scan(text: str) -> list[dict]:
    """Every line carrying a tell, with the section it sits in and whether that
    section claims to be finished."""
    out, section, settled, in_code = [], "(preamble)", False, False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if (m := HEADING.match(line)):
            section = re.sub(r"[*`]", "", m.group(2))[:58]
            settled = bool(SETTLED.search(line))
            # a heading may itself be the stale thing, so it is scanned too
        fired = [name for name, rx in TELLS.items() if rx.search(line)]
        if fired:
            out.append({"line": n, "section": section, "settled": settled,
                        "tells": fired, "text": re.sub(r"\s+", " ", line.strip())})
    return out


def report(hits: list[dict], width: int = 96) -> None:
    contradictions = [h for h in hits if h["settled"]]
    open_items = [h for h in hits if not h["settled"]]

    if contradictions:
        print("SUSPICIOUS — a forward-looking phrase inside a section that says it is finished.")
        print("Most will be historical records of a question that was then answered; read for")
        print("the one that is not.\n")
        for h in contradictions:
            print(f"  line {h['line']:<5} §{h['section']}")
            print(f"    [{', '.join(h['tells'])}] {h['text'][:width]}")
        print()
    if open_items:
        print("OPEN — forward-looking, in sections that are still open. Read for the ones")
        print("that quietly came true.\n")
        for h in open_items:
            print(f"  line {h['line']:<5} [{', '.join(h['tells'])}] {h['text'][:width]}")
        print()


def figures(text: str) -> None:
    """Values the build computes today, found typed into the plan by hand.

    **This is a drift warning, not a staleness check, and the difference matters.**
    The collision check searches for figures that match the CURRENT build, so a
    number the build has already moved past — the plan's old 54.1 MiB against
    today's 60.2 — matches nothing and is not reported. What is reported is the
    opposite: the places where the plan states today's value and will therefore
    quietly stop being true the next time the pipeline runs.

    Reported, never corrected. A figure in the plan is often a deliberate record of
    what was measured *then*, which must not track the build (CLAUDE.md #24); only
    a human knows which kind each one is.
    """
    hits = live_figures_in(text)
    print(f"LIVE FIGURES TYPED IN THE PLAN — {len(hits)} found")
    if not hits:
        print("  none: no headline value of the current build appears typed here.\n")
        return
    print("  Each equals a value the build computes now, so each will drift when it moves.")
    print("  If the plan means it as a dated measurement, leave it and let the date carry")
    print("  it; if it means it as the current state, it needs a date or a pointer.\n")
    current = {name: v for name, v, _ in live_values()}
    for fig, names in sorted(hits.items()):
        print(f"  {fig:>14}  = " + ", ".join(f"{n} ({current[n]:.2f})" for n in names))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    ap.add_argument("--no-figures", action="store_true", help="skip the collision half")
    args = ap.parse_args()

    if not args.plan.exists():
        print(f"no plan at {args.plan} — nothing to review.")
        print("(Expected: this file lives outside the repository. Set SENSISAT_PLAN or --plan.)")
        return 0

    text = args.plan.read_text()
    print(f"Plan review — {args.plan}\n{len(text.splitlines())} lines\n")
    hits = scan(text)
    report(hits)
    if not args.no_figures:
        figures(text)

    n_contra = sum(1 for h in hits if h["settled"])
    print(f"{len(hits)} lines to read ({n_contra} inside sections marked finished). "
          "Nothing was changed; this never fails.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
