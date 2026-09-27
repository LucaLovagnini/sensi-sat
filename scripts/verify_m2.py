"""Check M2 against its acceptance criteria, as written in the plan.

Separate from `build.py` on purpose. The build's QA gates ask "is this output
sane?" — they run every time and know nothing about milestones. This asks the
narrower question "did M2 deliver what M2 promised?", by comparing the published
layers against the numbers M0 measured independently.

    python scripts/verify_m2.py
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402
import rasterio  # noqa: E402

from sensisat import encoding as enc  # noqa: E402
from sensisat.config import FIGURES, ISLAND_BBOX, PROCESSED  # noqa: E402
from sensisat.layers import LAYERS  # noqa: E402
from sensisat.raster import area_km2  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, passed: bool, detail: str) -> None:
    CHECKS.append((name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name:38s} {detail}")


def main() -> int:
    print("M2 acceptance — measured against M0's independent figures\n")

    # 1. Seven layers, eight islands.
    missing = [f"{layer}/{island}" for layer in LAYERS for island in ISLAND_BBOX
               if not (PROCESSED / layer / f"{island.lower().replace(' ', '-')}.tif").exists()]
    check("seven layers x eight islands", not missing,
          f"{len(LAYERS) * len(ISLAND_BBOX) - len(missing)}/{len(LAYERS) * len(ISLAND_BBOX)} files"
          + (f"; missing {missing[:3]}" if missing else ""))

    # 2. The cadastre layer reproduces analysis 8 (~100.3 km2 by 2020).
    total_2020 = 0.0
    for island in ISLAND_BBOX:
        path = PROCESSED / "buildings-dated" / f"{island.lower().replace(' ', '-')}.tif"
        with rasterio.open(path) as src:
            years = src.read(1)
            total_2020 += area_km2(enc.built_by(years, 2020), src.transform)
    ratio = total_2020 / 100.3
    check("cadastre footprint by 2020 ~ 100.3 km2", 0.95 <= ratio <= 1.08,
          f"{total_2020:.2f} km2 = {ratio:.3f}x M0 "
          f"(10 m rasterisation vs HISDAC-ES exact polygon area)")

    # 3. The greenhouse mask reproduces analysis 3's definition factor.
    seam = pd.DataFrame(json.loads((PROCESSED / "statistics" / "seam.json").read_text()))
    gc = seam[seam["island"] == "Gran Canaria"].iloc[0]
    check("Gran Canaria definition factor 1.41 (masked)",
          gc["definition_factor_masked"] == 1.41 and gc["definition_factor_raw"] == 1.73,
          f"raw {gc['definition_factor_raw']} -> masked {gc['definition_factor_masked']}")

    # 4. The seam record reproduces m0_seam_factors.csv for the five islands it covered.
    m0 = pd.read_csv(FIGURES / "data" / "m0_seam_factors.csv").set_index("island")
    cols = ["evo30", "wsf15", "trk_e1", "trk_e1_nogh"]
    diffs = []
    for island in m0.index:
        ours = seam[seam["island"] == island].iloc[0]
        for col in cols:
            if abs(ours[col] - m0.loc[island, col]) > 0.01:
                diffs.append(f"{island}.{col}")
    check("seam record reproduces M0 for 5 islands", not diffs,
          f"{len(m0)} islands x {len(cols)} extents exact" + (f"; differs {diffs}" if diffs else ""))

    # 5. GHSL trend reproduces M0's 152.9 km2 for 2020.
    stats = json.loads((PROCESSED / "statistics" / "layers.json").read_text())
    trend = sum(v["headline_km2"] for v in stats["density-trend"].values())
    check("GHSL built surface 2020 ~ 152.9 km2", abs(trend - 152.9) < 1.0, f"{trend:.2f} km2")

    # 6. Size. Reported, not asserted — see the note below.
    total_mib = sum(f.stat().st_size for f in PROCESSED.rglob("*") if f.is_file()) / 1048576
    viewer_mib = sum(f.stat().st_size for f in PROCESSED.rglob("*.tif")
                     if ".confidence." not in f.name) / 1048576
    print(f"\n  published {total_mib:.1f} MiB total; {viewer_mib:.1f} MiB excluding the "
          f"confidence companions")

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    print(f"\n  {passed}/{len(CHECKS)} acceptance checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
