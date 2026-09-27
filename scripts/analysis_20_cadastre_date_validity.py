"""How trustworthy is the Catastro's `dateOfConstruction/beginning`?

THE ANSWER, established 2026-09-20 and confirmed against primary sources: the field
does not mean what this project assumed. It is not the year the building went up.
The Direccion General del Catastro defines it, verbatim in its own methodology:

    "Fecha de construccion. Fecha de finalizacion de la construccion que consta en
     la base de datos catastral. En el supuesto de rehabilitacion integral de una
     construccion, la fecha de finalizacion de dicha rehabilitacion tiene la
     consideracion de fecha de construccion."

    -- "the completion date of that rehabilitation IS CONSIDERED TO BE the date of
       construction"

The map the Catastro itself publishes from this field is titled "Fecha de
construccion O REFORMA INTEGRAL". A "reforma integral" is defined quantitatively:
works meeting the planning definition of rehabilitation, or costing more than 75 %
of what the same building would cost new.

So M3's finding -- a quarter to a third of buildings we date 2016-2024 were already
standing in 2015 -- is not a data-quality defect. It is the documented semantics of
the field, and we misread them. A 1970 house comprehensively rebuilt in 2019 is a
2019 building to the Catastro, and correctly so for its purpose, which is taxation.

Sources:
  catastro.hacienda.gob.es/ayuda/METODOLOGIA_MAPAS TEMATICOS_DEF.pdf
  catastro.hacienda.gob.es/webinspire/documentos/Conjuntos de datos_en.pdf

What follows measures how far the problem reaches.

M3 found that a quarter to a third of the buildings our map dates 2016-2024 were
already standing in 2015. The suspected cause is that the register records the year
of a *declaration* -- a renovation, an extension, or the legalisation of an
unregistered building -- rather than the year the structure went up. That was an
inference from photographs. This asks the register itself.

Four tests, all internal to the feed, none using imagery:

1. **beginLifespanVersion vs dateOfConstruction.** INSPIRE defines
   `beginLifespanVersion` as the moment this version of the record entered the
   database. A record version cannot predate the building it describes. So a
   building "constructed" in 2019 whose record version began in 2005 is not a 2019
   building -- it is an older record whose construction year was rewritten. This is
   the direct test of the re-registration hypothesis.

2. **Is `dateOfConstruction/end` ever different from `beginning`?** INSPIRE allows
   a construction *period*. If Spain always collapses it to a single instant, the
   field carries no uncertainty information and there is nothing more to extract.

3. **Placeholder years.** A real building stock has no reason to cluster on round
   years. Clustering means the year is an administrative default, not an
   observation.

4. **Does the year's quality depend on what the building is?** An agricultural shed
   and an apartment block reach the register by different routes.

Run: python scripts/analysis_20_cadastre_date_validity.py [--all]
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat.config import RAW  # noqa: E402

FEAT = re.compile(r"<bu-ext2d:Building\b(.*?)</bu-ext2d:Building>", re.S)
LIFE = re.compile(r"<bu-core2d:beginLifespanVersion>(\d{4})")
CONS = re.compile(r"<bu-core2d:dateOfConstruction>.*?<bu-core2d:beginning>(\d{4}-\d{2}-\d{2})"
                  r".*?<bu-core2d:end>(\d{4}-\d{2}-\d{2})", re.S)
COND = re.compile(r"<bu-core2d:conditionOfConstruction>([^<]+)")
USE = re.compile(r"<bu-ext2d:currentUse>([^<]+)")
AREA = re.compile(r'<bu-ext2d:value uom="m2">(\d+)')


def scan(paths: list[Path]):
    rows = []
    for z in paths:
        try:
            with zipfile.ZipFile(z) as zf:
                n = next((x for x in zf.namelist() if x.endswith("building.gml")), None)
                if not n:
                    continue
                txt = zf.read(n).decode("utf-8", "replace")
        except Exception:
            continue
        for body in FEAT.findall(txt):
            c = CONS.search(body)
            life = LIFE.search(body)
            rows.append({
                "year": int(c.group(1)[:4]) if c else None,
                "begin": c.group(1) if c else None,
                "end": c.group(2) if c else None,
                "life": int(life.group(1)) if life else None,
                "cond": (COND.search(body) or [None, None])[1] if COND.search(body) else None,
                "use": (USE.search(body).group(1) if USE.search(body) else None),
                "area": int(AREA.search(body).group(1)) if AREA.search(body) else None,
                "muni": z.stem.split(".")[-1],
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true", help="all 88 feeds (slow)")
    ap.add_argument("--n", type=int, default=20, help="how many feeds to sample")
    args = ap.parse_args()

    feeds = sorted((RAW / "catastro").glob("*.zip"))
    if not args.all:
        step = max(1, len(feeds) // args.n)
        feeds = feeds[::step][:args.n]
    print(f"Reading {len(feeds)} municipality feeds…\n")
    rows = scan(feeds)
    dated = [r for r in rows if r["year"]]
    print(f"{len(rows):,} buildings, {len(dated):,} with a construction year "
          f"({100*len(dated)/len(rows):.2f} %)\n")

    # -- 2. is the construction date ever a period? --------------------------
    span = sum(1 for r in dated if r["begin"] != r["end"])
    nonjan = sum(1 for r in dated if not r["begin"].endswith("-01-01"))
    print("TEST 2 — what is the `end` field?")
    print(f"   beginning != end          : {span:,} of {len(dated):,} ({100*span/len(dated):.2f} %)")
    print(f"   date is not 1 January     : {nonjan:,} ({100*nonjan/len(dated):.2f} %)")
    later = sum(1 for r in dated if r["begin"] != r["end"] and r["end"] > r["begin"])
    gaps = sorted(int(r["end"][:4]) - int(r["begin"][:4])
                  for r in dated if r["begin"] != r["end"])
    if gaps:
        print(f"   end is LATER than beginning in {later:,} of {span:,} such rows "
              f"({100*later/span:.1f} %)")
        print(f"   gap in years: median {gaps[len(gaps)//2]}, "
              f"90th pct {gaps[int(.9*len(gaps))]}, max {gaps[-1]}")
    print("   -> `end` is NOT the end of a construction period: nothing takes")
    print(f"      {gaps[-1] if gaps else 0} years to build. Per the Catastro's own")
    print("      specification, a Building holds several CONSTRUCTION UNITS, and")
    print("      `beginning` is the oldest unit's date while `end` is the newest.")
    print("      Taking `beginning`, as this project does, is therefore correct:")
    print("      it is the oldest date the register still holds.\n")

    # -- 1. the record version vs the construction year ----------------------
    both = [r for r in dated if r["life"]]
    impossible = [r for r in both if r["year"] > r["life"]]
    print("TEST 1 — can the record predate the building it describes?")
    print(f"   buildings with both fields: {len(both):,}")
    print(f"   construction year LATER than the record version: {len(impossible):,} "
          f"({100*len(impossible)/len(both):.2f} %)")
    print("   A record version cannot predate its building, so each of these is a")
    print("   construction year written onto an older record.\n")
    recent = [r for r in both if r["year"] >= 2016]
    if recent:
        bad = sum(1 for r in recent if r["year"] > r["life"])
        print(f"   Restricted to buildings dated 2016 or later — the class M3 tested:")
        print(f"      {bad:,} of {len(recent):,} ({100*bad/len(recent):.1f} %) sit on a record")
        print(f"      version that already existed before the stated construction year.")
        gaps = sorted(r["life"] - r["year"] for r in recent if r["year"] > r["life"])
        if gaps:
            print(f"      median age of the record beyond the claimed build: "
                  f"{-gaps[len(gaps)//2]} years\n")

    # -- 3. placeholder years ------------------------------------------------
    print("TEST 3 — placeholder years")
    c = Counter(r["year"] for r in dated)
    top = c.most_common(8)
    tot = sum(c.values())
    print(f"   the eight commonest years hold {100*sum(n for _, n in top)/tot:.1f} % of all dated buildings:")
    for y, n in top:
        neigh = (c.get(y - 1, 0) + c.get(y + 1, 0)) / 2 or 0.5
        print(f"      {y}  {n:7,}  ({100*n/tot:5.2f} %)   {n/neigh:7.1f}x its neighbours")

    # -- 4. does it depend on the kind of building? --------------------------
    print("\nTEST 4 — by what the building is")
    print(f"   {'use':26s} {'n':>8s} {'dated':>7s} {'on a round year':>16s}")
    round_years = {y for y, _ in top}
    for use, n in Counter(r["use"] for r in rows).most_common(7):
        grp = [r for r in rows if r["use"] == use]
        d = [r for r in grp if r["year"]]
        rnd = sum(1 for r in d if r["year"] in round_years)
        print(f"   {str(use):26s} {n:8,} {100*len(d)/n:6.1f} % "
              f"{(100*rnd/len(d) if d else 0):15.1f} %")

    print("\n   condition:", dict(Counter(r["cond"] for r in rows).most_common(5)))


if __name__ == "__main__":
    main()
