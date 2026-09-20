# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project Overview

SensiSat visualises urban expansion in the Canary Islands over time from open
land-cover and cadastral datasets, for researchers, conservation NGOs and
environmental planners.

**Geographic scope:** Canary Islands, bbox `(-18.50, 27.50, -13.20, 29.60)`.
**Temporal scope:** 1900–2026, from the Spanish cadastre and satellite products.
**Design target:** ~1,000 visitors/month — every hosting option is free at that
scale, so choices are about simplicity, not cost.

## The user, and how to work with him

Luca is a **senior software engineer with no geospatial background**, and the
project exists so he can learn the domain. This is the single most important thing
about working here:

- **Define every domain term the first time it appears**, in the code, in commit
  messages and in the docs. Not "we reproject to EPSG:3035" but what a projection
  is and why this one.
- **Show the arithmetic** behind any estimate, so it can be checked.
- **Park options, don't drop them.** If an approach is rejected, record the number
  that rejected it.
- When he says he is stepping out, **keep going** — do not block on questions that
  a stated assumption can carry.

## Current state (2026-09-20)

M0 (data evaluation), M1 (source decisions) and M2 (processing pipeline) are
complete. **M3** — a manual accuracy assessment against aerial photography — is
next, and its first need is PNOA orthophotos, not yet fetched.

The plan lives at `~/.claude/plans/ok-i-think-that-purrfect-horizon.md`; §9b is the
state snapshot to read first, §4 holds all 19 decisions.

### Google Earth Engine is no longer used

The original prototype used GEE with Google Dynamic World. **Dynamic World was
disqualified in M0**: it reported 308 km² built on Gran Canaria alone, more than
double CORINE's artificial total for that island, and more than the whole
archipelago in every other product. The notebooks under `geeLocalTesting/` are kept
as history. Nothing in `sensisat/` touches GEE, and no new work should add it.

## Layout

| | |
|---|---|
| `sensisat/` | the package — adapters, grid, encoding, derivation, QA, catalogue |
| `scripts/analysis_01..18` | the M0 evidence; every number in the docs is reproducible from these |
| `scripts/build.py` | M2: produce, check and catalogue the seven layers |
| `scripts/verify_m2.py` | M2's acceptance criteria as an executable check |
| `viewer/` | M4: the map. `python viewer/serve.py` then open `/viewer/` |
| `tests/` | 56 pytest tests over small fixture rasters |
| `docs/` | `concepts.md`, `data-evaluation.md`, `design/seam-harmonization.md`, `pipeline.md`, `viewer.md` |
| `data/` | gitignored: `raw/` downloads (~13 GiB), `processed/` published layers |

```bash
pip install -e ".[zarr,dev]"
python scripts/build.py --all       # 7 layers x 8 islands -> data/processed/
python scripts/verify_m2.py
pytest && ruff check .          # M0 analysis scripts have relaxed layout rules
```

## Things that are easy to get wrong here

These each cost real time to find. Read before touching the data code.

1. **Never subtract two maps made at different times by different methods.** Found
   three times in M0. WSF 2015 vs 2019 implies 9.7 %/yr growth; Copernicus's own
   status layers read 215 → 185 → 259 km². Only purpose-built *change* layers
   measure change. `datasets/copernicus.py` carries this warning in its docstring.
2. **Pixels are degrees, not metres.** A "10 m" pixel is ~88 m² at 28°N, not 100.
   Counting pixels and multiplying overstates area by ~12 %. Use
   `raster.area_km2`, which integrates row by row.
3. **Extent and surface are different quantities.** Extent = pixels *containing*
   settlement (saturates); surface = m² of built cover (keeps growing). Their gap
   reverses with density: Gran Canaria +11 % extent vs +57 % surface 1990→2015;
   Fuerteventura +400 % vs +162 %. Never compare one against the other.
4. **Every product means something different by "built".** Archipelago totals:
   CORINE 469.5, WSF Evolution 376.9, Copernicus sealed 341.5, Copernicus built-up
   259.3, GHSL 152.9, cadastre 100.3 km². None is wrong. State the definition.
5. **Never resample a category.** Years, epochs and class codes move with
   nearest-neighbour only; averaging 1994 and 2006 gives a date nothing happened.
6. **A COG is defined by its byte layout**, not by having overviews. Write through
   `raster.write_cog`, which uses GDAL's COG driver; appending overviews to a
   GeoTIFF fails `rio cogeo validate --strict`.
7. **The 2015/2016 seam is declared, never blended.** Crossing it the measured
   extent drops 26–52 % because the method changed. See
   `docs/design/seam-harmonization.md`.
8. **Greenhouses read as buildings to radar.** WSF Tracker flags 72 % of Gran
   Canaria's greenhouse parcels as built-up. They are masked out of the urban
   layers and published as `covered-agriculture` (decision M1.2).
9. **`stats.zonal()` must stay the only implementation** of per-zone statistics
   (decision 7). `tests/test_api_parity.py` enforces it.
10. **A protected area is not automatically a negative control.** The legal
    category decides it: *Parque Nacional* / *Reserva Natural Integral* /
    *Reserva Natural Especial* forbid settlement, but *Parque Natural*,
    *Paisaje Protegido* and *Parque Rural* explicitly include inhabited land — a
    product finding buildings inside one is **right**. And no control works until
    known roads and buildings are buffered and subtracted: Teide contains 127
    OSM-mapped buildings.
11. **A skipped check is not a passed check.** `qa.summarise()` reports measured,
    skipped and failed separately, because a build once claimed "217/217 passed"
    when 49 of those had never run.
12. **Do not write sparse COGs.** `SPARSE_OK` saves ~5 % (DEFLATE already squashes
    ocean) and makes the file unreadable by geotiff.js, so no browser can open it.
13. **Overviews use `mode`, not `nearest`.** Nearest makes sparse buildings vanish
    when zoomed out; mode keeps them and never invents a value. `average` would
    also keep them but would invent years, so it is only for the continuous layers.
14. **A valid STAC catalogue is not a usable one.** Schemas never check that an
    href resolves. The `assets-resolve` gate does.
15. **A partial build must not erase the rest of the catalogue.** It is assembled
    from what is on disk, not from one run's records.

## Git

The remote is **Luca's personal GitHub**, and work credentials must never be used:

```
origin  github-personal:LucaLovagnini/sensi-sat.git
```

`github-personal` is an SSH host alias in `~/.ssh/config` using
`~/.ssh/id_ed25519_personal`. The repo-local git identity is `lucalova91@gmail.com`.
