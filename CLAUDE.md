# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

## Project Overview
<!-- figures: sensisat/config.py; external:design target set by Luca (plan §4 decision 4) @ 2026-09-18 -->

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
<!-- figures: docs/validation.md; docs/data-evaluation.md @ 2026-09-21 -->

M0 (data evaluation), M1 (source decisions), M2 (processing pipeline), M3
(accuracy assessment), M4 (viewer) and M4b (the public "about the data" page) are
complete. The site is live but **unannounced** at
`https://sensisat.org`. **M4c** — figure provenance, every published
number accounted for — was **implemented 2026-09-21** (`docs/design/figure-provenance.md`;
acceptance `python scripts/verify_m4c.py`). **The repository went public on
2026-09-21** after the checklist at the end of this file was walked. **M5** — the
per-zone statistics panel, attribution and releases — remains.

M3's result, in `docs/validation.md`, measured on **30 m squares** (see point 16).
User's accuracy: **98 %** for "holds a pre-2015 building", **98 %** for "holds no
building", **64–74 %** for "holds a building that appeared 2015–2024", **67–72 %**
for the undated class. The last two are *ranges* because the sample was judged
twice and the between-pass spread matched the statistical margin (§7). Error-adjusted
area **462.65 ± 82.74 km²** of cells holding a building against 324.41 km² mapped —
an extent measure, never to be set against the 100 km² of footprint.

**The layer's years mean "built OR comprehensively rebuilt"**, by the Catastro's own
definition — a *reforma integral* resets the year. This is the measured cause of the
24–33 % of "new construction" that was already standing in 2015, and it is a
definition we misread, not a data fault (`data-evaluation.md` §11).

The plan lives at `~/.claude/plans/ok-i-think-that-purrfect-horizon.md`; §9b is the
state snapshot to read first, §4 holds all 19 decisions.

### Google Earth Engine is no longer used

The original prototype used GEE with Google Dynamic World. **Dynamic World was
disqualified in M0**: it reported 308 km² built on Gran Canaria alone, more than
double CORINE's artificial total for that island, and more than the whole
archipelago in every other product. The notebooks under `geeLocalTesting/` are kept
as history. Nothing in `sensisat/` touches GEE, and no new work should add it.

## Layout
<!-- figures: scripts/build.py; scripts/fetch_m0.py; docs/pipeline.md @ 2026-09-21 -->

| | |
|---|---|
| `sensisat/` | the package — adapters, grid, encoding, derivation, QA, catalogue |
| `scripts/analysis_01..20` | the evidence; every number in the docs is reproducible from these |
| `scripts/build.py` | M2: produce, check and catalogue the seven layers |
| `scripts/verify_m2.py` | M2's acceptance criteria as an executable check |
| `scripts/m3_*.py` | M3: `sample` (draw), `label` via viewer, `score` (Olofsson), `diagnose`, `recheck`, `review` |
| `scripts/sync_docs.py` | rewrite (or `--check`) every live figure in the documents |
| `scripts/plan_review.py` | list the plan's forward-looking sentences and the build figures typed into it — the plan is outside the repo, so nothing else checks it |
| `sensisat/facts.py` | the published figures as functions — the single source for prose |
| `sensisat/provenance.py` | where every hand-written figure on the public page came from |
| `viewer/` | M4: the map. `python viewer/serve.py` then open `/viewer/`. **The page loads `app.bundle.js`** — after editing `app.js`, run `cd viewer && npm run build` |
| `tests/` | the pytest suite over small fixture rasters — `pytest` counts them |
| `sensisat/figures.py`, `tests/test_documented_numbers.py` | the figure gate: what a figure is, and the tests that every one is accounted for |
| `scripts/review_figures.py`, `.claude/skills/verify-figures/` | the three judgements the gate cannot make, and their attestation `docs/figures-review.json` |
| `.githooks/pre-push` | refuses to push while the review is stale; enable per clone with `git config core.hooksPath .githooks` |
| `data/` | gitignored: `raw/` downloads (~13 GiB), `processed/` published layers |

### The documentation, and which question each file answers

Nothing under `docs/` is loaded automatically — **this file is the only router**, so
a question not indexed here is a question a fresh session will not know to look up.

| file | answers | published? |
|---|---|---|
| `docs/concepts.md` | what a raster, projection, COG, extent-vs-surface *is* | internal |
| `docs/data-evaluation.md` | M0: which datasets to trust and why; §10 the bucketed pre-1980 years; **§11 what the cadastre's year actually means**; §12 GHSL vs the cadastre on timing | internal |
| `docs/design/seam-harmonization.md` | why 2015/2016 is declared and never blended | internal |
| `docs/pipeline.md` | M2: the seven layers, the grid, the QA gates, the results | internal |
| `docs/validation.md` | M3: the accuracy numbers, how they were measured, and §9 why the first attempt was discarded | internal |
| `docs/viewer.md` | M4: how the map works, why OpenLayers, the WebGL constraints | internal |
| `docs/design/scaling.md` | hosting cost, guardrails G1–G7, the R2 migration and the pre-flight that de-risked it | internal |
| `docs/design/figure-provenance.md` | M4c: how every published number is generated, declared or excepted; the limits; what building it found | internal |
| `viewer/about-the-data.html` | **the public page** — every figure with its conditions, for a cold reader | **PUBLISHED** |

**The repo is public since 2026-09-21** (github.com/LucaLovagnini/sensi-sat; the
going-public checklist below was walked in full, `verify_m4b.py` 18/18). `docs/`
is therefore readable by anyone, though written for us; the page remains the only
thing written *for* a cold reader, and it links to the repository from "How to
cite". Being public changes one habit — see `CONTRIBUTING.md`: the documents
execute code, so never run the gate on a branch you have not read.

**Keeping this honest.** When something load-bearing is learned, the one-line
version belongs here and the working detail belongs in `docs/`. A fact that exists
only in `docs/` will be missed; a fact that exists only here loses its evidence.

```bash
pip install -e ".[zarr,dev]"
python scripts/build.py --all       # 7 layers x 8 islands -> data/processed/
python scripts/verify_m2.py
pytest && ruff check .          # M0 analysis scripts have relaxed layout rules
```

## Things that are easy to get wrong here
<!-- figures: docs/data-evaluation.md; docs/validation.md; docs/pipeline.md; docs/design/seam-harmonization.md; docs/viewer.md @ 2026-09-21 -->

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
16. **An accuracy assessment's unit must be bigger than the geolocation error it
    is measuring across.** M3's first run judged single 10 m pixels and had to be
    thrown away: the median Canary building is 121 m² against a 100 m² pixel and
    81 % are ≤ 2 pixels, so a built pixel has no interior and 78–87 % of drawn
    points landed on a class boundary — against a photograph showing a **roof**
    while the map stores a **ground footprint**, which orthorectification does not
    reconcile because it corrects terrain and not building height. The redraw uses
    30 m squares and asks "is there a building anywhere inside", which is a question
    a photograph can answer. Do not compare the two runs' km²: 30 m cells
    *containing* a building is extent (324 km²), building footprint is surface
    (100 km²).
17. **Per-class accuracy and error-adjusted area need opposite allocations.** User's
    accuracy for a class uses only that class's own points, so ~100 is plenty and
    more buys almost nothing. Error-adjusted area is decided entirely by the
    95 %-of-land `not_built` stratum, where each point carries 12.8 km². Raising
    only that stratum from 123 to 557 points moved the area interval from ±201 km²
    (unpublishable) to ±83 km² (publishable).
18. **A mis-dated building is invisible to every automated gate.** They all compare
    our totals against other products' totals, where a building given the wrong
    year is still a building. M3 found 29 % of the `new 2015–2024` class was
    already standing in 2015, and the 30 m redraw raised it to 33 % — the Catastro
    records the year of a *declaration*, so a renovation or a regularisation resets
    it. Only human interpretation finds this class of error.
19. **GHSL cannot date recent growth.** Its 1975, 1990 and 2000 epochs are
    observed Landsat and agree with the cadastre to within a 0.58–1.26 increment
    ratio — the only corroboration the unphotographed pre-2005 decades have. But
    after 2010 the two diverge 5× then 8×, because GHSL interpolates between sparse
    observations and smooths Spain's 2008 construction crash out of existence: it
    puts its **largest increment of the whole series in 2015–2020**, when the
    cadastre records 11 % of the pre-crash rate. Use it for the long trend and for
    density, never for timing after ~2005 (`data-evaluation.md` §12).
20. **The viewer reads `data/processed/index.json`, not the STAC items.** It is a
    flattened runtime index (one request instead of a 64-file STAC walk) written by
    **`publish.py`, not `build.py`** — so a rebuild leaves it stale while every gate
    passes and every STAC item on disk is correct, and the only symptom is the
    viewer quietly showing old numbers. `build.py` now deletes it, because
    `loadCatalog()` falls back to the STAC walk when it is missing: slower and right
    beats fast and stale. Run `python scripts/publish.py` after any rebuild.
21. **Numbers in documents are generated, not typed — but only the marked ones.**
    A figure derived from the current build goes in `sensisat/facts.py` and is
    written into the document by `cog` through `scripts/sync_docs.py`. `build.py`
    regenerates them (a rebuild is what makes them stale, so it fixes them and you
    review the diff), `pytest` checks them, and `publish.py` refuses to assemble
    `dist/` while any disagrees. **Never hand-type a live figure** — mark it, or it
    will go stale in silence, which has already happened twice.
22. **No figure may reach a reader unaccounted for.** Every run of digits on the
    page, in `app.js` strings and in `README.md` must be generated, in
    `sensisat/provenance.HISTORICAL`, or excepted by a positional rule; every
    section of `docs/` and this file that states a figure carries
    `<!-- figures: <source>; … @ <date> -->` under its heading; every headline
    value `facts.py` computes is searched for typed by hand (the collision check).
    `sensisat/figures.py` is the one definition; `pytest`, `build.py` (exit 4) and
    `publish.py` (exit 3) run the same tests. Adding a number forces a choice —
    **generate it, or declare where it came from** — and the failure names the
    token and the file. The first fail-closed run surfaced 45 figures the old
    regex had silently exempted, and four viewer figures wrong on the live site.
23. **A quantity word must carry its digits.** Write "three in ten (31 %)", not
    "three in ten"; "a third (33.8 %)", not "a third". The figure gates are
    digit-based, so a number written as a word escapes them — which would make
    dodging the gate easier than satisfying it. This is the one way the whole
    arrangement could leave the project worse off than before, so it is a writing
    rule, not a preference, and a lint enforces it (`docs/design/figure-provenance.md` §4).
24. **Historical measurements must NOT be updated, and must be distinguishable.**
    Most of the ~1,300 numbers in `docs/` record why a decision was taken — the
    figure that disqualified Dynamic World, the recall that rejected GAIA. Rewriting
    them to match a later build destroys the reasoning they exist to support. But a
    reader cannot tell a frozen measurement from a stale one, so every document
    carries a generated block (`facts.contract()`) stating which is which, and a
    historical figure names the analysis script that produced it — per token in the
    registry, per section in the declaration. **The gate cannot judge** whether a
    generated figure comes from the right fact, whether a registry entry is really
    a live claim, or whether a declared source fits: that is `/verify-figures`,
    attested in `docs/figures-review.json`, which `publish.py` and the pre-push
    hook require to be current.
25. **`rasterio.windows.from_bounds` returns a fractional window** whose transform
    is offset from the array `read()` actually returns. Distances computed that way
    carry a ~2.6 m floor, which silently hides exactly the sub-pixel cases that
    matter. Take the window in integer pixels around `src.index(lon, lat)`; a point
    on a built pixel must then measure 0.0 m from one.

## Before the site goes public
<!-- figures: scripts/build.py; scripts/publish.py @ 2026-09-21 -->

It must carry an **"about the data" page** (plan M4b) explaining every number's
conditions for a reader who is not us — the ladder of definitions, extent vs
surface, the 2015/2016 seam, the undated class, the cadastre's pre-1980 buckets,
growth-only encoding, greenhouses, and per-island quality. The audience quotes
these figures; publishing them without their conditions is the failure M0 spent
three findings learning to avoid.

**Checklist — nothing runs when the repository is made public, so this is the
gate (M4c).** Walk it in order; each line is a command or a look.

1. `python scripts/build.py --all` exits 0 — layers, QA gates and the figure gate.
2. `python -m pytest -q && ruff check .` clean.
3. `python scripts/verify_m4c.py` passes every criterion it can run.
4. **Luca runs `/verify-figures` himself** — the review on file was made by the
   implementing session; the three judgements need his eyes once — and attests.
5. `python scripts/publish.py` assembles `dist/` (it refuses while anything above
   is stale); open the viewer and the page from `dist/` in a browser.
6. `git config core.hooksPath .githooks` is set in the clone that will push.
7. `python scripts/verify_m4b.py` — every promised topic present, every external
   link resolving, the accuracy section carrying real figures. **Its repository-link
   check fails until step 9**; everything else must pass here.
8. The repository README says what the numbers are conditional on, and links to
   the page rather than restating figures.
9. Only then the GitHub settings click — then `python scripts/verify_m4b.py` once
   more, which is the only check that can see the result of the click.
10. **Decided 2026-09-21:** code MIT (`LICENSE`), published layers / statistics /
    docs / page **CC BY 4.0** (`LICENSE-DATA.md`, with every source's terms read at
    source and the attribution block). Every input is attribution-only, so CC0 was
    unavailable and share-alike unnecessary. The STAC collections say `CC-BY-4.0`
    (`python scripts/build.py --catalog-only` rewrites the catalogue from disk).

## Git

The remote is **Luca's personal GitHub**, and work credentials must never be used:

```
origin  github-personal:LucaLovagnini/sensi-sat.git
```

`github-personal` is an SSH host alias in `~/.ssh/config` using
`~/.ssh/id_ed25519_personal`. The repo-local git identity is `lucalova91@gmail.com`.
