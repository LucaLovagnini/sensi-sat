"""Turn the interpreter's labels into an accuracy figure (M3, plan §7 level 3).

The estimator is Olofsson et al. 2014, and the reason it is not just "count the
right answers" is worth stating. The sample is stratified, so the classes are
deliberately NOT represented in proportion to their real extent: "new built"
covers 0.69 km² of Gran Canaria and "not built" covers 1,530, yet both get the
same number of points. Counting raw agreement would therefore weight a
half-square-kilometre class as heavily as half the island.

Every cell of the matrix is instead weighted back by the true area share of the
map class it came from. That yields three things worth having:

  user's accuracy      of the area we CALL X, how much really is X
  producer's accuracy  of the area that really IS X, how much did we find
  error-adjusted area  what the area of X actually is, with a confidence interval
                       — which is usually NOT what the map says it is

    python scripts/m3_score.py --labels ~/Downloads/m3-labels.json
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# What the pair of photo judgements implies about the ground.
#
# "Built" here means A BUILDING — a roofed structure — and deliberately not "any
# artificial surface". The layer under test is the cadastre, which rasterises
# `building.gml` and nothing else: it holds no roads, and its open-air structures
# (87 swimming pools in the one municipality checked) are in a file we do not use.
# Labelling a road or a paved yard as built would score an omission against a map
# that never claimed them, measuring the definition rather than the accuracy.
#
# Partial cover is judged at the CENTRE, because that is the rule the map itself
# was drawn by: `rasterize(..., all_touched=False)` marks a pixel built when a
# footprint covers its centre point, not when it merely overlaps the pixel. Scoring
# by how much of the square is filled would compare against a quantity the map
# never claimed.
def reference_class(l2015: str, l2024: str) -> str | None:
    if l2015 == "unsure" or l2024 == "unsure" or not l2015 or not l2024:
        return None                       # excluded, and reported separately
    if l2015 == "built" and l2024 == "built":
        return "built_before_2015"
    if l2015 == "not" and l2024 == "built":
        return "new_2015_2024"
    if l2015 == "not" and l2024 == "not":
        return "not_built"
    if l2015 == "built" and l2024 == "not":
        return "lost_2015_2024"           # real demolition, or an error
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--claims", default="data/processed/m3/map_claims.json")
    args = ap.parse_args()

    labels = {r["id"]: r for r in json.loads(Path(args.labels).read_text())["labels"]}
    claims_doc = json.loads(Path(args.claims).read_text())
    claims = {c["id"]: c for c in claims_doc["claims"]}

    strata = sorted({c["stratum"] for c in claims.values()})
    areas = {s: next(c["stratum_km2"] for c in claims.values() if c["stratum"] == s)
             for s in strata}
    total_km2 = sum(areas.values())

    # counts[map class][reference class]
    counts: dict[str, dict[str, int]] = {s: {} for s in strata}
    n: dict[str, int] = {s: 0 for s in strata}
    excluded = []
    for pid, claim in claims.items():
        lab = labels.get(pid)
        if not lab:
            continue
        ref = reference_class(lab.get("label_2015"), lab.get("label_2024"))
        if ref is None:
            excluded.append((pid, claim["stratum"], lab.get("label_2015"), lab.get("label_2024")))
            continue
        s = claim["stratum"]
        counts[s][ref] = counts[s].get(ref, 0) + 1
        n[s] += 1

    ref_classes = sorted({r for row in counts.values() for r in row})

    design = claims_doc.get("design", {})
    planned = design.get("usable", {})
    total_planned = sum(planned.values()) if planned else 0

    print(f"Reference: {len(labels)} points labelled, {sum(n.values())} usable, "
          f"{len(excluded)} excluded as unsure or incomplete")
    if total_planned:
        pct = 100 * sum(n.values()) / total_planned
        print(f"Progress against the design: {sum(n.values())}/{total_planned} usable "
              f"({pct:.0f} %)\n")
        print(f"{'stratum':22s} {'usable':>7s} {'planned':>8s}  status")
        for st in strata:
            want = planned.get(st, 0)
            enough = n[st] >= 30
            note = ("fine" if n[st] >= want else
                    "usable, interval still wide" if enough else
                    "TOO FEW to say anything")
            print(f"{st:22s} {n[st]:7d} {want:8d}  {note}")
        print()
    else:
        print()

    print("Confusion matrix — rows are what the MAP says, columns what the PHOTOS show")
    head = f"{'map class':22s} {'n':>3s} " + " ".join(f"{c[:14]:>15s}" for c in ref_classes)
    print(head)
    for s in strata:
        row = " ".join(f"{counts[s].get(c, 0):15d}" for c in ref_classes)
        print(f"{s:22s} {n[s]:3d} {row}")

    # ---- Olofsson: weight each row by the map class's true area share ----------
    W = {s: areas[s] / total_km2 for s in strata}
    p: dict[str, dict[str, float]] = {}
    for s in strata:
        p[s] = {c: (W[s] * counts[s].get(c, 0) / n[s]) if n[s] else 0.0 for c in ref_classes}

    overall = sum(p[s].get(s, 0.0) for s in strata if s in ref_classes)
    print(f"\nOverall accuracy (area-weighted): {100 * overall:.1f} %")

    print(f"\n{'class':22s} {'users':>8s} {'producers':>10s} "
          f"{'map km2':>10s} {'adjusted km2':>14s} {'95% CI':>14s}")
    for c in ref_classes:
        p_dot_c = sum(p[s].get(c, 0.0) for s in strata)
        users = (p[c][c] / sum(p[c].values())) if c in p and sum(p[c].values()) else None
        producers = (p[c][c] / p_dot_c) if c in p and p_dot_c else None
        # SE of the area proportion, stratified (Olofsson eq. 10)
        var = 0.0
        for s in strata:
            if n[s] < 2:
                continue
            phat = counts[s].get(c, 0) / n[s]
            var += W[s] ** 2 * phat * (1 - phat) / (n[s] - 1)
        se_km2 = total_km2 * math.sqrt(var)
        fmt = lambda v: f"{100 * v:7.1f} %" if v is not None else "      —"   # noqa: E731
        print(f"{c:22s} {fmt(users):>8s} {fmt(producers):>10s} "
              f"{areas.get(c, 0):10.2f} {total_km2 * p_dot_c:14.2f} "
              f"{'±' + format(1.96 * se_km2, '.2f'):>14s}")

    if excluded:
        print("\nExcluded:")
        for pid, s, a, b in excluded:
            print(f"  {pid}  map said {s:22s} labels {a}/{b}")

    # How much narrower the interval gets if the sample is finished. The standard
    # error falls as 1/sqrt(n), so this is the honest projection rather than a promise.
    if total_planned and sum(n.values()) < total_planned:
        ratio = math.sqrt(sum(n.values()) / total_planned)
        print(f"\nFinishing the sample would narrow these intervals by roughly "
              f"{1 / ratio:.1f}x — the standard error falls as 1/sqrt(n), so the "
              f"remaining {total_planned - sum(n.values())} usable points are worth "
              f"about that much.")

    print("\nA caution about scoring part-way. Checking progress is sound: every "
          "stratum's labelled points are still a random subset of that stratum, so "
          "the estimator is valid at any n. What is NOT sound is deciding to stop "
          "because the number currently looks good — that turns an honest estimate "
          "into a chosen one. Look in order to catch problems, not to pick a moment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
