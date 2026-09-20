"""Build a contact sheet of M3 points so the interpreter can re-check his own work.

Why this is blind by default. Reviewing only the points the map disputed, while
knowing they are disputed, corrects errors in one direction only: a wrong "not
built" gets found and a wrong "built" does not, because nobody goes looking for it.
That does not clean the reference data, it tilts it. So the sheet shows every point
in the stratum, shuffled, with the original answer and the map's claim hidden until
the reviewer asks for them.

Re-judging blind also measures something the assessment never had: how repeatable
one interpreter is. Two passes that disagree on 5 % of points put a floor under the
whole exercise -- no accuracy figure can be tighter than the interpreter's own
consistency. The plan listed this as an optional second-interpreter check.

Run: python scripts/m3_review.py --labels ~/Downloads/m3-labels.json --stratum undated
Then open viewer/m3-review.html (no server needed; imagery comes from IGN).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat.config import PROCESSED  # noqa: E402

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>M3 review — %(stratum)s</title>
<style>
  :root { --bg:#12151a; --fg:#e8eaed; --dim:#9aa3ad; --line:#2a303a; --hit:#7ee081; --miss:#ff8f6b; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
  header { position:sticky; top:0; background:var(--bg); border-bottom:1px solid var(--line);
           padding:14px 20px; z-index:5; }
  h1 { margin:0 0 4px; font-size:17px; font-weight:600; }
  p { margin:4px 0; color:var(--dim); font-size:13px; max-width:70ch; }
  button { background:#1d2430; color:var(--fg); border:1px solid var(--line); border-radius:6px;
           padding:6px 12px; font:inherit; cursor:pointer; margin-right:8px; }
  button:hover { border-color:#3d4654; }
  .grid { display:grid; gap:22px; padding:20px; }
  .card { border:1px solid var(--line); border-radius:10px; overflow:hidden; background:#161b22; }
  .pair { display:grid; grid-template-columns:1fr 1fr; gap:2px; background:var(--line); }
  .cell { position:relative; aspect-ratio:1; background:#0b0d11; }
  .cell img { width:100%%; height:100%%; display:block; object-fit:cover; }
  .cell span.yr { position:absolute; left:8px; top:8px; background:rgba(0,0,0,.65);
                  padding:2px 7px; border-radius:4px; font-size:12px; letter-spacing:.04em; }
  /* the 10 m square, and the centre dot that is what actually gets judged */
  .cell::after { content:""; position:absolute; left:50%%; top:50%%; width:20%%; height:20%%;
                 transform:translate(-50%%,-50%%); border:2px solid #fff;
                 box-shadow:0 0 0 1px rgba(0,0,0,.7); pointer-events:none; }
  .dot { display:none; }   /* no centre mark: the question is the whole square */
  .meta { padding:9px 12px; font-size:13px; display:flex; justify-content:space-between; gap:12px; }
  .id { color:var(--dim); font-variant-numeric:tabular-nums; }
  .answer { display:none; }
  body.revealed .answer { display:block; }
  .agree { color:var(--hit); } .disagree { color:var(--miss); }
  @media (max-width:760px) { .pair { grid-template-columns:1fr; } }
</style></head>
<body>
<header>
  <h1>M3 review — the “%(stratum)s” stratum, %(n)d points</h1>
  <p>Both dates, same ground, same framing the labelling tool used. The white square
  is 30 m, and the question it was judged by is whether a building appears anywhere
  inside it.</p>
  <p><strong>Shown in shuffled order with the answers hidden</strong>, so that a
  second look is not steered by what you or the map said the first time. Reveal only
  after you have formed your own view of a card.</p>
  <p><strong>This sheet is for looking, not for correcting.</strong> Changing answers
  on a set that was filtered to disagreements finds mistakes in one direction only —
  the ones that happen to favour the map — and tilts the reference data rather than
  cleaning it. To actually revise answers, use the blind recheck
  (<code>scripts/m3_recheck.py</code>), which contains the whole class.</p>
  <button onclick="document.body.classList.toggle('revealed')">Show / hide the answers</button>
  <button onclick="window.scrollTo(0,0)">Back to top</button>
</header>
<div class="grid">%(cards)s</div>
</body></html>
"""

CARD = """
  <div class="card">
    <div class="pair">
      <div class="cell"><img loading="lazy" src="%(u2015)s" alt=""><span class="yr">2015</span><i class="dot"></i></div>
      <div class="cell"><img loading="lazy" src="%(u2024)s" alt=""><span class="yr">recent</span><i class="dot"></i></div>
    </div>
    <div class="meta">
      <span class="id">%(pid)s &middot; %(lat).5f, %(lon).5f</span>
      <span class="answer %(cls)s">you said %(said)s &nbsp;|&nbsp; map said %(claim)s</span>
    </div>
  </div>"""

CHIP_M, CHIP_PX = 150, 640
CELL_FRAC = 30 / CHIP_M   # the 30 m square as a share of the chip
WMS_HISTORIC = "https://www.ign.es/wms/pnoa-historico"
WMS_CURRENT = "https://www.ign.es/wms-inspire/pnoa-ma"


def chip_url(lon: float, lat: float, recent: bool) -> str:
    import math
    half = CHIP_M / 2
    dlat = half / 110_540
    dlon = half / (111_320 * math.cos(math.radians(lat)))
    # WMS 1.3.0 with EPSG:4326 takes the bbox as lat,lon — the other way round
    # silently returns imagery of somewhere else entirely.
    bbox = f"{lat - dlat},{lon - dlon},{lat + dlat},{lon + dlon}"
    url, layer = (WMS_CURRENT, "OI.OrthoimageCoverage") if recent else (WMS_HISTORIC, "PNOA2015")
    return (f"{url}?service=WMS&amp;version=1.3.0&amp;request=GetMap&amp;layers={layer}"
            f"&amp;styles=&amp;crs=EPSG:4326&amp;bbox={bbox}&amp;width={CHIP_PX}"
            f"&amp;height={CHIP_PX}&amp;format=image/jpeg")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--sample", default="m3_30m")
    ap.add_argument("--stratum", default="undated")
    ap.add_argument("--only", choices=["all", "disputed"], default="all",
                    help="'disputed' shows only the points that disagreed — for "
                         "LOOKING at, never for correcting (see the header)")
    ap.add_argument("--out", type=Path, default=Path("viewer/m3-review.html"))
    ap.add_argument("--seed", type=int, default=7, help="shuffle seed, so the sheet is reproducible")
    args = ap.parse_args()

    rows = {r["id"]: r for r in json.loads(args.labels.read_text())["labels"]}
    claims = json.loads((PROCESSED / args.sample / "map_claims.json").read_text())["claims"]
    # map_claims.json deliberately holds no coordinates — it is the answer key, and
    # keeping the two apart is what let the labelling tool stay blind. The points
    # file carries the geometry.
    coords = {p["id"]: p for p in json.loads((PROCESSED / args.sample / "points.json").read_text())["points"]}

    def disagrees(pid: str, stratum: str) -> bool:
        r = rows[pid]
        a, b = r.get("label_2015"), r.get("label_2024")
        if not a or not b or "unsure" in (a, b):
            return False
        seen = "built_before_2015" if a == "built" else (
            "new_2015_2024" if b == "built" else "not_built")
        # "undated" can never be returned by a photograph; the map's claim there is
        # only that SOMETHING is built, so the disagreement is "no building at all".
        return seen == "not_built" if stratum == "undated" else seen != stratum

    pts = [dict(c, **coords[c["id"]]) for c in claims
           if c["stratum"] == args.stratum and c["id"] in rows and c["id"] in coords]
    if args.only == "disputed":
        pts = [c for c in pts if disagrees(c["id"], c["stratum"])]
    random.Random(args.seed).shuffle(pts)

    cards = []
    for c in pts:
        r = rows[c["id"]]
        said = f"{r.get('label_2015') or '—'} / {r.get('label_2024') or '—'}"
        agrees = not (args.stratum == "undated" and r.get("label_2015") == "not"
                      and r.get("label_2024") == "not")
        cards.append(CARD % {
            "u2015": chip_url(c["lon"], c["lat"], False),
            "u2024": chip_url(c["lon"], c["lat"], True),
            "pid": c["id"], "lat": c["lat"], "lon": c["lon"],
            "said": said, "claim": args.stratum.replace("_", " "),
            "cls": "agree" if agrees else "disagree",
        })

    args.out.write_text(TEMPLATE % {"stratum": args.stratum.replace("_", " "),
                                    "n": len(pts), "cards": "".join(cards)})
    print(f"{args.out}  —  {len(pts)} points, shuffled, answers hidden until revealed")


if __name__ == "__main__":
    main()
