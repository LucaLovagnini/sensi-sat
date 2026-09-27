"""Download every dataset Milestone 0 evaluates, for the whole archipelago.

Safe to re-run: everything is cached and verified against data/raw/manifest.json.
Datasets that need an account (Copernicus HRL, CNIG CORINE) are reported as
blocked rather than attempted, so the rest of M0 can proceed without them.

    python scripts/fetch_m0.py
"""

from __future__ import annotations

import sys
import traceback

from sensisat.config import CANARIES_BBOX
from sensisat.datasets import ghsl, wsf
from sensisat.download import manifest_table

BLOCKED = {
    "HRL Imperviousness (2018/2021/2024 + Built-up Change 2018-2021)":
        "Copernicus CLMS requires a free account; needed for the real loss-rate analysis (M0-7)",
    "CORINE 2018 (provinces 35, 38)":
        "CNIG/CLMS download requires a free account; used only as a coarse sanity band",
    "HISDAC-ES (cadastral construction years)":
        "Zenodo record is open but large; fetched separately once the raster analyses are done",
}


def main() -> int:
    failures = []

    print("=" * 78)
    print("WSF (DLR) — extent products")
    print("=" * 78)
    for product in ("wsf_evolution", "wsf2015", "wsf2019"):
        print(f"\n{product}:")
        try:
            paths = wsf.fetch_tiles(product, CANARIES_BBOX)
            total = sum(p.stat().st_size for p in paths) / 1048576
            print(f"  -> {len(paths)} tiles, {total:.1f} MiB")
        except Exception as exc:
            failures.append((product, exc))
            traceback.print_exc()

    print()
    print("=" * 78)
    print("GHSL GHS-BUILT-S R2023A — surface product")
    print("=" * 78)
    for epoch in ghsl.EPOCHS:
        try:
            paths = ghsl.fetch_tiles(epoch, CANARIES_BBOX, quiet=True)
            total = sum(p.stat().st_size for p in paths) / 1048576
            print(f"  E{epoch} [{ghsl.is_observed(epoch):>13}]  {len(paths)} tile(s), {total:.1f} MiB")
        except Exception as exc:
            failures.append((f"ghsl {epoch}", exc))
            print(f"  E{epoch} FAILED: {type(exc).__name__}: {exc}")

    print()
    print("=" * 78)
    print("Needs an account — not attempted")
    print("=" * 78)
    for name, why in BLOCKED.items():
        print(f"  - {name}\n      {why}")

    df = manifest_table()
    print()
    print("=" * 78)
    print(f"cache: {len(df)} files, {df['MiB'].sum():.1f} MiB total")
    print("=" * 78)

    if failures:
        print("\nFAILURES:")
        for what, exc in failures:
            print(f"  {what}: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
