"""Build the published layers, check them, and catalogue them. M2's entry point.

    python scripts/build.py --layer buildings-dated --island "Gran Canaria"
    python scripts/build.py --all
    python scripts/build.py --all --skip-existing        # resume an interrupted run

Everything lands in data/processed/ and is verified locally. There is no cloud and
no server in M2: the output is exactly the set of files M4 would upload, so the
deployment step later has nothing left to decide.

What one build does, per layer per island:
  1. builds the array from the adapters (sensisat/layers.py)
  2. writes it as a sparse Cloud-Optimized GeoTIFF
  3. runs the Level-1 QA gates and prints their measured values
  4. computes per-zone statistics through the same stats.zonal() a web API
     would call (decision 7 — there must never be a second implementation)
  5. writes a STAC item, so the caveats travel with the data
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from sensisat import catalog, derive, layers, qa  # noqa: E402
from sensisat.config import ISLAND_BBOX, PROCESSED  # noqa: E402
from sensisat.raster import area_km2, weighted_km2, write_cog  # noqa: E402
from sensisat.stats import zonal  # noqa: E402

STATS_DIR = PROCESSED / "statistics"
SEAM_PATH = STATS_DIR / "seam.json"

# How each encoding is turned into an area, so statistics mean one thing per layer.
ZONAL_KIND = {
    "year first built": ("binary", 1.0),
    "epoch first built": ("binary", 1.0),
    "binary": ("binary", 1.0),
    "percent": ("fraction", 0.01),
    "amount": ("amount", 1.0),
}


def headline_km2(spec, built) -> float:
    """The one number the totals gate polices, in the layer's own measure."""
    data = built.data if built.data.ndim == 2 else built.data[0]
    if spec.encoding == "percent":
        return weighted_km2(data / 100.0, built.transform)
    if spec.encoding == "amount":
        last = built.data[-1]          # the most recent epoch of the trend stack
        return float(last.sum()) / 1e6
    return area_km2(data > 0, built.transform)


def build_one(layer: str, island: str, *, skip_existing: bool = False) -> dict | None:
    spec = layers.LAYERS[layer]
    out_path = PROCESSED / layer / f"{catalog._slug(island)}.tif"
    t0 = time.time()

    if skip_existing and out_path.exists():
        print(f"  {layer:20s} {island:14s} exists, skipped")
        return None

    built = layers.build(layer, island)
    write_cog(
        out_path, built.data, built.transform, built.crs,
        nodata=built.nodata, band_descriptions=built.band_descriptions,
        resampling=built.resampling,
        tags={"sensisat_layer": layer, "sensisat_island": island,
              "sensisat_measure": spec.measure, "sensisat_encoding": spec.encoding},
    )
    companion_paths = {}
    for companion in built.companions:
        companion_path = out_path.with_name(f"{out_path.stem}.{companion.key}.tif")
        write_cog(companion_path, companion.data, built.transform, built.crs,
                  nodata=built.nodata, band_descriptions=companion.band_descriptions,
                  resampling=companion.resampling,
                  tags={"sensisat_layer": layer, "sensisat_island": island,
                        "sensisat_asset": companion.key})
        companion_paths[companion.key] = companion_path

    size_mib = out_path.stat().st_size / 1048576
    total = headline_km2(spec, built)
    print(f"  {layer:20s} {island:14s} {size_mib:6.2f} MiB  {total:8.2f} km2  {time.time()-t0:5.1f}s")

    gates = run_gates(spec, island, built, out_path, total)
    stats = per_zone(spec, island, built)
    return {"layer": layer, "island": island, "path": out_path, "built": built,
            "companions": companion_paths,
            "gates": gates, "statistics": stats, "MiB": round(size_mib, 3),
            "headline_km2": round(total, 3)}


def run_gates(spec, island, built, path, total) -> list[qa.Gate]:
    gates = [qa.totals_in_band(spec.name, island, total), qa.cog_valid(path, spec.name, island)]
    data = built.data if built.data.ndim == 2 else built.data[0]

    if spec.measure == "extent" and spec.commission_risk:
        gates.append(qa.negative_control(spec.name, island, data > 0, built.transform))
    if spec.encoding == "year first built":
        gates.append(qa.growth_only(spec.name, island, data))
    if spec.name == "loss-events":
        for _, label in layers.LOSS_PERIODS:
            change = built.properties["change_km2"][label]
            years = int(label[5:]) - int(label[:4])
            gates.append(qa.loss_rate(f"{spec.name} {label}", island,
                                      change["loss_of_cover_km2"],
                                      max(total, 1e-9), years))
    if spec.name == "settlement-era-b":
        gates.append(independent_agreement(spec, island, built))
    return gates


def independent_agreement(spec, island, built) -> qa.Gate:
    """Compare our 2021 footprint with Copernicus's, an unrelated producer."""
    from sensisat.datasets import copernicus as cop
    from sensisat.datasets import wsf_tracker as wt

    try:
        theirs, _, _ = cop.on_grid("ibu_2021", island,
                                   transform=built.transform, shape=built.data.shape[-2:])
    except FileNotFoundError as exc:
        return qa.Gate("agreement", spec.name, island, True, None, "Copernicus not present",
                       f"skipped ({exc.__class__.__name__})")
    by_2021 = wt.epochs_up_to(2021.5)
    ours = (built.data > 0) & (built.data <= by_2021)
    return qa.agreement(spec.name, island, ours, theirs == 1)


def per_zone(spec, island, built) -> pd.DataFrame | None:
    """Per-zone areas through the same function a future API endpoint will call."""
    from sensisat import zones

    kind_scale = ZONAL_KIND.get(spec.encoding)
    if kind_scale is None:
        return None
    kind, scale = kind_scale
    isl = zones.islands()
    zone_gdf = isl[isl["name"] == island]
    data = built.data if built.data.ndim == 2 else built.data[0]
    if kind == "binary":
        data = (data > 0).astype("uint8")
    return zonal(data, built.transform, built.crs, zone_gdf,
                 kind=kind, scale=scale, label=spec.name.replace("-", "_"))


def write_statistics(records: list[dict]) -> dict:
    """Merge this run's statistics into what is already published.

    Merge, not replace. A partial build (`--layer X`) knows nothing about the other
    six layers, and overwriting the file with only its own records would delete
    them — which is exactly what happened to the STAC catalogue before this was
    fixed, silently leaving a catalogue advertising one layer out of seven.
    """
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    path = STATS_DIR / "layers.json"
    payload: dict[str, dict] = json.loads(path.read_text()) if path.exists() else {}
    for r in records:
        entry = payload.setdefault(r["layer"], {})
        entry[r["island"]] = {
            "headline_km2": r["headline_km2"],
            "file_MiB": r["MiB"],
            "properties": catalog._jsonable(r["built"].properties),
            "zones": json.loads(r["statistics"].to_json(orient="records")) if r["statistics"] is not None else None,
        }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"\nwrote {path}")
    return payload


def write_seam(islands: list[str]) -> None:
    """The measured 2015/2016 discontinuity, published beside the data (decision 13)."""
    STATS_DIR.mkdir(parents=True, exist_ok=True)
    records = []
    for island in islands:
        try:
            records.append(derive.seam_record(island))
        except Exception as exc:
            print(f"  ! seam {island}: {type(exc).__name__}: {exc}")
    SEAM_PATH.write_text(json.dumps(records, indent=2))
    df = pd.DataFrame(records)
    print("\nSeam at 2015/2016 — the join is declared, never blended:")
    print(df.to_string(index=False))
    print(f"wrote {SEAM_PATH}")


def write_catalog(stats: dict) -> Path:
    """Rebuild the catalogue from everything on disk, not just this run's records.

    The catalogue describes the published folder, so it is assembled from the files
    that are actually there. Building it from one run's records instead means a
    partial build publishes a catalogue that denies the existence of every layer it
    did not touch.
    """
    by_layer: dict[str, list] = {}
    for name, spec in layers.LAYERS.items():
        for island in sorted(ISLAND_BBOX):
            path = PROCESSED / name / f"{catalog._slug(island)}.tif"
            if not path.exists():
                continue
            entry = stats.get(name, {}).get(island, {})
            companions = {p.name.split(".")[-2]: p
                          for p in path.parent.glob(f"{path.stem}.*.tif")}
            by_layer.setdefault(name, []).append(
                catalog.item_for(spec, island, entry.get("properties", {}), path,
                                 base_dir=PROCESSED, companions=companions))

    collections = [catalog.collection_for(layers.LAYERS[name], items)
                   for name, items in by_layer.items()]
    path = catalog.save(catalog.build_catalog(collections), PROCESSED)
    print(f"\nwrote {path}")
    print(catalog.summary(PROCESSED))
    return path


def published_mib(records: list[dict]) -> float:
    """Total size of everything written — the number that decides if this can be
    hosted as static files rather than served."""
    return sum(f.stat().st_size for f in PROCESSED.rglob("*") if f.is_file()) / 1048576


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layer", action="append", choices=sorted(layers.LAYERS), help="repeatable")
    ap.add_argument("--island", action="append", choices=sorted(ISLAND_BBOX), help="repeatable")
    ap.add_argument("--all", action="store_true", help="every layer on every island")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--no-seam", action="store_true")
    args = ap.parse_args()

    if not (args.all or args.layer):
        ap.error("give --layer/--island or --all")
    chosen_layers = sorted(layers.LAYERS) if args.all else args.layer
    chosen_islands = args.island or sorted(ISLAND_BBOX)

    print(f"Building {len(chosen_layers)} layer(s) x {len(chosen_islands)} island(s) -> {PROCESSED}\n")
    records, all_gates = [], []
    for layer in chosen_layers:
        for island in chosen_islands:
            try:
                record = build_one(layer, island, skip_existing=args.skip_existing)
            except Exception as exc:
                print(f"  {layer:20s} {island:14s} FAILED {type(exc).__name__}: {exc}")
                continue
            if record:
                records.append(record)
                all_gates.extend(record["gates"])

    if not records:
        print("nothing built")
        return 1

    # Outputs first, then the gates — two of them (the COG check aside) can only be
    # run against what was actually written, and a gate that runs before the file
    # exists is a gate that never fails.
    stats = write_statistics(records)
    catalog_path = write_catalog(stats)

    grids: dict[str, dict] = {}
    for r in records:
        if layers.LAYERS[r["layer"]].resolution_m == 10:
            grids.setdefault(r["island"], {})[r["layer"]] = (r["built"].transform, r["built"].data.shape[-2:])
    for island, g in grids.items():
        all_gates.extend(qa.grid_alignment(island, g))
    all_gates.append(qa.stac_valid(catalog_path))
    all_gates.append(qa.assets_resolve(catalog_path))

    print("\nQA gates (plan section 7, level 1):")
    passed, measured, skipped = qa.summarise(all_gates)
    print(f"\n  {passed}/{measured} gates passed; {skipped} did not apply "
          f"({len(all_gates)} checks attempted)")
    if passed < measured:
        print("  failures:")
        for g in all_gates:
            if not g.passed and not g.skipped:
                print(f"   {g}")

    if not args.no_seam:
        write_seam([i for i in chosen_islands if i in ISLAND_BBOX])

    by_gate: dict[str, list[int]] = {}
    for g in all_gates:
        row = by_gate.setdefault(g.gate, [0, 0])
        row[1 if g.skipped else 0] += 1
    print("\n  by gate:  " + " | ".join(
        f"{name} {m}" + (f" (+{s} n/a)" if s else "") for name, (m, s) in sorted(by_gate.items())))

    # The viewer does not read the STAC items. It reads data/processed/index.json,
    # a flattened runtime index written by scripts/publish.py so a cold page load
    # costs one request instead of a 64-file STAC walk. That index is a COPY of the
    # statistics, so a rebuild leaves it stale — and stale is worse than absent
    # here, because every gate still passes, every STAC item is correct, and the
    # only symptom is a viewer quietly showing yesterday's numbers. Deleting it is
    # self-healing: loadCatalog() falls back to the STAC walk, which is slower and
    # right, until publish.py regenerates the index.
    # A rebuild is what makes the documents stale, so it is what fixes them. The
    # change then arrives as a reviewable git diff rather than as silent drift.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sync_docs import run as sync_documents
        sync_documents(check=False)
    except Exception as exc:                      # never fail a build over prose
        print(f"  (could not sync documents: {exc})")

    index = PROCESSED / "index.json"
    if index.exists():
        index.unlink()
        print("  removed index.json (now stale) — run scripts/publish.py to rebuild it")

    print(f"\nPublished {published_mib(records):.1f} MiB to {PROCESSED}")
    return 0 if passed == measured else 2

if __name__ == "__main__":
    raise SystemExit(main())
