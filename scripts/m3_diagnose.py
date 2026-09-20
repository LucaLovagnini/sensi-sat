"""M3, after scoring: why the map and the photographs disagreed.

`m3_score.py` produces the accuracy figures. It cannot say what caused a
disagreement, and the cause decides whether a number is publishable. Three
questions, each answered from data the interpreter never saw:

1. **How far is a disagreeing point from the nearest thing the map calls built?**
   A disagreement on a pixel touching a footprint is the interpreter and the map
   splitting a 10 m square; a disagreement 50 m from anything is a real miss.
   They carry the same weight in the estimator and mean opposite things.

2. **Does an independent product agree with the interpreter?** Copernicus
   Imperviousness measures *sealed* ground at 10 m from different sensors by a
   different method. It is not a truth, but where it agrees with the photographs
   against our map, two independent sources have lined up.

3. **Is a failure bunched in the most recent years?** If so the reference imagery
   predates the building and the map is right — an artefact of the reference, not
   an error. Spread evenly, it is a real failure mode.

Run: python scripts/m3_diagnose.py --labels ~/Downloads/m3-labels.json
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sensisat.config import PROCESSED  # noqa: E402

_OPEN: dict[str, rasterio.DatasetReader] = {}


def _src(layer: str, island: str) -> rasterio.DatasetReader | None:
    slug = island.lower().replace(" ", "-")
    key = f"{layer}/{slug}"
    if key not in _OPEN:
        path = PROCESSED / layer / f"{slug}.tif"
        _OPEN[key] = rasterio.open(path) if path.exists() else None
    return _OPEN[key]


def reference_class(a: str | None, b: str | None) -> str | None:
    if not a or not b or "unsure" in (a, b):
        return None
    return "built_before_2015" if a == "built" else (
        "new_2015_2024" if b == "built" else "not_built")


def nearest_built_m(lon: float, lat: float, island: str, half: int = 20) -> float | None:
    """Metres from this pixel to the nearest pixel `buildings-dated` calls built.

    The window is taken in integer pixels around the point's own row/col. Using
    `from_bounds` instead returns a fractional window whose transform is offset
    from the array actually read, which puts a spurious ~2.6 m floor under every
    distance — including points that ARE built, where the answer must be 0.
    """
    src = _src("buildings-dated", island)
    if src is None:
        return None
    r, c = src.index(lon, lat)
    a = src.read(1, window=Window(c - half, r - half, 2 * half + 1, 2 * half + 1),
                 boundless=True, fill_value=0)
    ys, xs = np.nonzero(a > 0)
    if not len(ys):
        return None
    dx = (xs - half) * src.transform.a * 111320 * np.cos(np.radians(lat))
    dy = (ys - half) * src.transform.e * 110540
    return float(np.hypot(dx, dy).min())


def value_at(layer: str, lon: float, lat: float, island: str) -> int | None:
    src = _src(layer, island)
    if src is None:
        return None
    return int(next(src.sample([(lon, lat)]))[0])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True, type=Path)
    ap.add_argument("--sample", type=Path, default=PROCESSED / "m3" / "map_claims.json")
    args = ap.parse_args()

    rows = json.loads(args.labels.read_text())["labels"]
    claims = json.loads(args.sample.read_text())["claims"]
    stratum = {c["id"]: c["stratum"] for c in claims}
    island = {c["id"]: c.get("island") for c in claims}

    judged = [r for r in rows
              if reference_class(r.get("label_2015"), r.get("label_2024"))
              and island.get(r["id"])]

    # -- 1. distance to the nearest built pixel -------------------------------
    print("1. DISTANCE from the sampled pixel to the nearest pixel the map calls built")
    print("   0.0 m means the point itself is built, so every agreement inside a")
    print("   built stratum must read 0.0 — that is the check on the sampling.\n")
    groups: dict[str, list[tuple[str, float | None]]] = {}
    for r in judged:
        key = f"{stratum[r['id']]} -> {reference_class(r['label_2015'], r['label_2024'])}"
        groups.setdefault(key, []).append(
            (r["id"], nearest_built_m(r["lon"], r["lat"], island[r["id"]])))
    for key in sorted(groups):
        v = groups[key]
        ds = [d if d is not None else 200.0 for _, d in v]
        said, saw = key.split(" -> ")
        mark = "" if said == saw else "   <-- DISAGREES"
        print(f"   {key:46s} n={len(v):3d}  median {np.median(ds):5.1f} m{mark}")
        if said != saw and len(v) <= 6:
            for pid, d in sorted(v, key=lambda x: (x[1] is None, x[1])):
                shown = "nothing within 200 m" if d is None else f"{d:5.1f} m"
                print(f"        {pid}  {shown}")

    # -- 2. does an independent product agree with the interpreter? -----------
    print("\n2. INDEPENDENT CHECK on the undated class (Copernicus sealing %, and the")
    print("   greenhouse parcels M0 proposed as the explanation)\n")
    for name, pick in (
        ("photos show a building", lambda r: r["label_2015"] == "built"),
        ("photos show NOTHING built",
         lambda r: r["label_2015"] == "not" and r["label_2024"] == "not"),
    ):
        grp = [r for r in judged if stratum[r["id"]] == "undated" and pick(r)]
        seal = [v for r in grp
                if (v := value_at("density-current", r["lon"], r["lat"], island[r["id"]])) is not None]
        gh = [v for r in grp
              if (v := value_at("covered-agriculture", r["lon"], r["lat"], island[r["id"]])) is not None]
        med = sorted(seal)[len(seal) // 2] if seal else "—"
        print(f"   undated, {name} (n={len(grp)}):")
        print(f"      median Copernicus sealing      : {med} %")
        print(f"      inside a mapped greenhouse     : {sum(1 for v in gh if v)} / {len(gh)}")
        print(f"      islands                        : {dict(Counter(island[r['id']] for r in grp))}\n")

    # -- 3. are the new-construction failures bunched in recent years? --------
    print("3. YEAR the map claims, for each outcome of the new-construction class.")
    print("   Bunching at 2023-24 would mean the reference imagery predates the")
    print("   building; spread evenly, the failure is real.\n")
    for name, pick in (
        ("photos AGREE",
         lambda r: r["label_2015"] == "not" and r["label_2024"] == "built"),
        ("photos show it ALREADY BUILT in 2015", lambda r: r["label_2015"] == "built"),
        ("photos show NOTHING at either date",
         lambda r: r["label_2015"] == "not" and r["label_2024"] == "not"),
    ):
        yrs = [y for r in judged if stratum[r["id"]] == "new_2015_2024" and pick(r)
               if (v := value_at("buildings-dated", r["lon"], r["lat"], island[r["id"]]))
               not in (None, 0, 255) and (y := v + 1899)]
        print(f"   map says new, {name} (n={len(yrs)}):")
        print(f"      {dict(sorted(Counter(yrs).items()))}\n")


if __name__ == "__main__":
    main()
