"""A blind second pass over whole strata, to measure the interpreter against himself.

Why whole strata and not just the disagreements. Showing someone only the points a
map disputed, while telling them these are the disputed ones, finds errors in one
direction: a wrong "not built" gets caught and a wrong "built" never does, because
nobody goes looking for it. Corrections made that way do not clean the reference
data, they tilt it toward the map. So the recheck contains every judged point in the
chosen strata, shuffled, with no marking of any kind.

What it buys beyond corrections. Two independent passes by the same reader measure
**repeatability**, which the assessment has never had. No accuracy figure can be
tighter than the interpreter's own consistency, so if the two passes disagree on 8 %
of points then 8 % is the floor under every number in docs/validation.md. The plan
listed a second interpreter as optional and none was available; a second pass by the
same person is weaker -- it shares any systematic bias -- but it does bound the
random part.

The output is an ordinary sample directory, so the normal tool labels it:

    python scripts/m3_recheck.py --strata new_2015_2024 undated
    # then open /viewer/label.html?sample=m3_30m_recheck

Labels are keyed by a fingerprint of the point list, so the recheck starts empty
rather than inheriting the first pass -- which is the point.

Afterwards:

    python scripts/m3_recheck.py --compare --pass1 <first.json> --pass2 <second.json>
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat.config import PROCESSED  # noqa: E402


def judged(rows: dict, pid: str) -> bool:
    r = rows.get(pid)
    return bool(r and (r.get("label_2015") or r.get("label_2024")))


def build(args) -> None:
    src = PROCESSED / args.sample
    pts = {p["id"]: p for p in json.loads((src / "points.json").read_text())["points"]}
    doc = json.loads((src / "map_claims.json").read_text())
    rows = {r["id"]: r for r in json.loads(Path(args.labels).read_text())["labels"]}

    keep = [c for c in doc["claims"]
            if c["stratum"] in args.strata and judged(rows, c["id"])]
    random.Random(args.seed).shuffle(keep)

    out = PROCESSED / args.out
    out.mkdir(parents=True, exist_ok=True)
    head = json.loads((src / "points.json").read_text())
    (out / "points.json").write_text(json.dumps(
        {**{k: v for k, v in head.items() if k != "points"},
         "points": [pts[c["id"]] for c in keep]}, indent=1))
    (out / "map_claims.json").write_text(json.dumps(
        {**{k: v for k, v in doc.items() if k != "claims"}, "claims": keep}, indent=1))

    from collections import Counter
    print(f"{len(keep)} points -> {out}")
    for s, n in Counter(c["stratum"] for c in keep).most_common():
        print(f"   {s:22s} {n:4d}")
    print(f"\nOpen /viewer/label.html?sample={args.out}")
    print("Shuffled, unmarked, and the store starts empty — judge them as if new.")


def compare(args) -> None:
    a = {r["id"]: r for r in json.loads(Path(args.pass1).read_text())["labels"]}
    b = {r["id"]: r for r in json.loads(Path(args.pass2).read_text())["labels"]}
    doc = json.loads((PROCESSED / args.sample / "map_claims.json").read_text())
    stratum = {c["id"]: c["stratum"] for c in doc["claims"]}

    both = [p for p in b if p in a and judged(a, p) and judged(b, p)]
    print(f"{len(both)} points judged in both passes\n")

    from collections import Counter
    changed: list[tuple] = []
    same = 0
    for p in both:
        x = (a[p].get("label_2015"), a[p].get("label_2024"))
        y = (b[p].get("label_2015"), b[p].get("label_2024"))
        if x == y:
            same += 1
        else:
            changed.append((p, stratum.get(p, "?"), x, y))
    print(f"identical in both passes : {same:4d}  ({100 * same / len(both):.1f} %)")
    print(f"changed                  : {len(changed):4d}  ({100 * len(changed) / len(both):.1f} %)")
    print("\nThe change rate is the floor under every figure in docs/validation.md:")
    print("no accuracy can be measured more tightly than the reader repeats himself.\n")

    by = Counter(s for _, s, _, _ in changed)
    for s, n in by.most_common():
        tot = sum(1 for p in both if stratum.get(p) == s)
        print(f"   {s:22s} {n:3d} of {tot:3d} changed ({100 * n / tot:4.1f} %)")

    # Did the changes move toward the map or away from it? A blind pass should be
    # roughly even; a strong tilt either way would mean the blinding leaked.
    print("\nDirection of the changes (a blind pass should be roughly even):")
    toward = sum(1 for _, s, x, y in changed
                 if (y[0] == "built") == (s in ("built_before_2015", "undated"))
                 and (x[0] == "built") != (s in ("built_before_2015", "undated")))
    away = sum(1 for _, s, x, y in changed
               if (x[0] == "built") == (s in ("built_before_2015", "undated"))
               and (y[0] == "built") != (s in ("built_before_2015", "undated")))
    print(f"   toward what the map claims : {toward}")
    print(f"   away from it               : {away}")
    if args.verbose:
        print("\nEvery change:")
        for p, s, x, y in sorted(changed, key=lambda t: t[1]):
            print(f"   {p}  {s:20s} {x[0]}/{x[1]}  ->  {y[0]}/{y[1]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", default="m3_30m")
    ap.add_argument("--labels", help="the first pass, to know which points were judged")
    ap.add_argument("--strata", nargs="+", default=["new_2015_2024", "undated"])
    ap.add_argument("--out", default="m3_30m_recheck")
    ap.add_argument("--seed", type=int, default=31)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--pass1")
    ap.add_argument("--pass2")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.compare:
        args.sample = args.out if (PROCESSED / args.out).exists() else args.sample
        compare(args)
    else:
        build(args)


if __name__ == "__main__":
    main()
