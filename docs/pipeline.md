# M2 — the processing pipeline, in plain language

<!--[[[cog cog.outl(f.contract()) ]]]-->
**About the numbers in this document.** Figures fall into two kinds.

*Live figures* are generated from the current build — the same `data/processed/statistics/layers.json` that produced the 7 published layers — by `scripts/sync_docs.py`. They cannot be stale: `scripts/build.py` regenerates them, `pytest` checks them, and `scripts/publish.py` refuses to assemble the site while any disagrees.

*Historical measurements* are recorded as they were when they were taken, and are deliberately NOT updated. They are the evidence for a decision — the number that disqualified a dataset, or justified a threshold — and rewriting them to match a later build would destroy the reasoning they exist to support. Where one is reported, its analysis script is named, so it can be re-run and compared rather than trusted.
<!--[[[end]]]-->

**What this milestone produced:** seven map layers covering the eight Canary
Islands, written to disk as files a web browser can read directly, each one
checked by automatic tests and described by a machine-readable catalogue.

M0 measured which datasets could be trusted. M1 chose between them. M2 turns those
choices into actual files. Nothing here runs in the cloud: everything is built on a
laptop into `data/processed/`, and that folder is exactly what a web host would
later serve, so the deployment step has nothing left to decide.

---

## 1. The idea that makes all of this work: one shared grid
<!-- figures: sensisat/grid.py; sensisat/config.py @ 2026-09-19 -->

Seven layers come from five producers who each use a different coordinate system —
a different way of flattening the round Earth onto a flat grid of pixels. WSF uses
plain longitude and latitude. Copernicus uses a metre-based European projection.
The Spanish cadastre uses a UTM zone.

If we published each layer on its own grid, two problems follow. The viewer could
not stack them, because their pixels would not line up. And every comparison
between them — "is this pixel built in both?" — would need the computer to
re-project one onto the other on the spot. Re-projecting is not free: when values
are *categories* rather than quantities, it can invent values that were never
measured. Averaging the years 1994 and 2006 gives 2000, a date on which nothing
happened, in a layer whose whole purpose is to say when things happened.

So everything is put on **one grid, once, at build time**. Two layers of the same
island then have identical pixels, and `A and B` is a valid question about the same
piece of ground.

**Which grid?** WSF Tracker's own, unchanged. It is in longitude/latitude, which
four of our seven sources already use; it is the native grid of the layer carrying
2016 to today, which we least want to disturb; and web maps want geographic
coordinates anyway. The cost is that the Copernicus layers get re-projected once,
here, deliberately, and the fact is recorded in their catalogue entry.

> **A trap worth naming.** These pixels are a fixed number of *degrees*, not
> metres. A "10 m" pixel is 9.98 m tall but only 8.81 m wide at the Canaries'
> latitude — about 88 m², not 100 m². Counting pixels and multiplying by 100 would
> overstate every area by roughly 12 %. All areas here are integrated row by row
> with the true latitude, never counted.

## 2. The seven layers
<!-- figures: sensisat/layers.py; docs/figures/data/m0_seam_factors.csv; docs/figures/data/m0_undated_vs_crops.csv @ 2026-09-19 -->

| layer | what it shows | resolution | source |
|---|---|---|---|
| `buildings-dated` | every registered building and the year it was built, 1900–2020 | 10 m | Spanish cadastre |
| `settlement-era-a` | settlement extent including roads, dated 1985–2015 | 10 m | WSF Evolution + WSF Tracker |
| `settlement-era-b` | settlement extent twice a year, 2016 → 2026 | 10 m | WSF Tracker |
| `covered-agriculture` | greenhouse parcels | 10 m | Mapa de Cultivos |
| `density-current` | % of each pixel sealed by any hard surface, 2024 | 10 m | Copernicus Imperviousness |
| `density-trend` | m² of built surface per cell, ten epochs 1975–2020 | ~92 m | GHSL |
| `loss-events` | built-up gained **and lost**, 2018–21 and 2021–24 | 20 m | Copernicus change layers |

### Why two settlement layers instead of one timeline

The obvious thing to build is a single raster running 1985 to today. We
deliberately did not, and this is the most important design decision in M2.

At 2016 the source changes: instrument, resolution and definition all at once.
Crossing that join the measured extent **drops by 26–52 %** — not because anything
was demolished, but because the map started being made a different way. Splicing
the eras into one raster would bake that artefact into the data, and no reader
could then tell it apart from a real event.

So the eras stay separate, the viewer announces the transition, and the measured
size of the discontinuity ships alongside the data in `statistics/seam.json`. This
follows the practice of published land-cover products, which describe a
discontinuity rather than blending across it.

> **Do not add the two eras together.** They overlap on purpose. Era-b's first
> epoch is not the settlement built during 2016 — it is everything standing by July
> 2016, which is the same ground era-a describes, dated differently. Era-a answers
> "when did this appear, before 2016"; era-b answers "what has appeared since".
> Summed, they count the 2016 baseline twice.

### Why greenhouses are removed from three layers and given one of their own

Radar sees a plastic greenhouse roof much the way it sees a building roof. WSF
Tracker classifies **72 %** of Gran Canaria's greenhouse parcels as built-up;
Copernicus's Imperviousness reports **43.7 % mean sealing** inside them. Leaving
that in would put roughly 17 km² of tomatoes into one island's urban total.

But simply deleting it would throw away real ground cover, and for a conservation
reader the soil under a greenhouse is no less covered than the soil under a car
park. So covered agriculture is **subtracted from the urban layers and published as
its own layer**. Because it ships beside the others on the same grid, anyone who
disagrees with the call can add it back exactly.

## 3. How "we don't know" survives to the map
<!-- figures: scripts/analysis_03_seam_factors.py; sensisat/encoding.py; docs/figures/data/m0_seam_factors.csv @ 2026-09-19 -->

Three of the layers carry a **provenance band**: a second band saying, per pixel,
where that pixel's year came from.

This exists because of a real gap. Draping WSF Evolution's 30 m years onto the 10 m
footprint only dates about **57 %** of it. The rest — 115 km² across the
archipelago — is real settlement that existed by 2016 with no year attached.

There are three things one could do with it: guess a year from the nearest dated
pixel, assign it the first epoch, or admit it. The first two manufacture 115 km² of
history that was never observed. So the encoding has a **third state**:

```
0          not built
1..200     the year it was first built  (1 = 1900, 121 = 2020)
255        built, but the year is unknown
```

A time slider never switches the undated class on; the map draws it in its own
colour. The same code covers the cadastre's 1.3 % of buildings whose date field is
malformed — and those are malformed in an instructive way: `--01-01` with no year,
or `88-01-01`, which could be 1888 or 1988. A two-digit year is genuinely
ambiguous, so it stays undated rather than being resolved to whichever century
looks likelier.

## 4. The checks that run on every build
<!-- figures: sensisat/qa.py @ 2026-09-19 -->

These are cheap, automatic, and run in seconds. They are **not** an accuracy
assessment — that is M3, needs a human reading aerial photographs, and produces a
number with a confidence interval. These catch the failures that are knowable
*without* ground truth:

| gate | what it catches |
|---|---|
| **totals in band** | a layer whose total has moved by a factor — the failure that disqualified Dynamic World, which reported more built-up on Gran Canaria alone than every independent product found in the whole archipelago |
| **negative control** | settlement appearing inside Timanfaya, a lava desert with no buildings |
| **growth-only** | a year encoding that has been broken by merging sources in the wrong order |
| **loss rate** | loss faster than anything physical could produce — which is how a method change disguises itself |
| **agreement** | our footprint disagreeing with an unrelated producer's beyond what different definitions explain |
| **grid alignment** | two layers of one island silently half a pixel apart |
| **valid COG / valid STAC** | a file a browser or another person's tools cannot read |

Each gate reports its **measured value**, not just pass or fail, so a pass leaves a
number worth reading and a failure says how far off it is.

> **Why the totals gate compares against CORINE rather than another satellite
> product.** CORINE is an official map made by a different method. Agreeing with it
> is weak evidence of being right — but being far outside its range is strong
> evidence of a bug. The bands are M0's measured ratios, widened, so a
> *definitional* difference passes and a *broken build* does not.

> **Why agreement uses IoU and not plain agreement.** About 95 % of pixels are
> "neither built". Any two maps of the Canaries agree on those, so plain agreement
> would score almost anything above 0.9. IoU only looks at the union of what the
> two maps call built.

## 5. One implementation of the statistics, not two

Decision 7 says per-zone numbers are precomputed now and may be served by a web API
later. The classic failure there is that the batch job and the web endpoint drift
apart, and the website starts quoting numbers the published tables do not contain.

So `stats.zonal()` is one function with no assumptions about where its data came
from. The build calls it. A test stands up a throwaway web route that calls it too,
and asserts the two return **byte-identical JSON**. If someone later writes a second
implementation, that test fails.

## 6. Running it
<!-- figures: sensisat/datasets/cadastre.py @ 2026-09-19 -->

```bash
python scripts/build.py --all                              # everything
python scripts/build.py --layer buildings-dated --island "Gran Canaria"
python scripts/build.py --all --skip-existing               # resume
pytest                                                      # the unit tests
```

The first run of anything cadastral downloads 88 municipality archives from the
Spanish Catastro. That is the one slow step, it is cached, and only the building
files are unpacked — the building-part files are three times the size and nothing
uses them.

---

## 7. What M2 actually produced
<!-- figures: scripts/verify_m2.py; scripts/build.py; sensisat/mosaic.py; data/processed/statistics/layers.json; measured:archipelago mosaic sizes and the share of the archipelago bounding box the island boxes cover, 2026-09-24 @ 2026-09-24 -->

Built with `python scripts/build.py --all`: **56 files, seven layers across eight
islands, 185/185 measured QA gates passing** (24 further checks did not apply),
every COG passing `rio cogeo validate --strict` and every catalogue object passing
STAC validation.

The gates break down like this, and the skips are worth reading rather than
glossing — a check that did not run is not a check that passed:

| gate | measured | did not apply | catches |
|---|---|---|---|
| `cog-valid` | 56 | — | a file a browser cannot read by byte-range |
| `totals` | 35 | 21 | a layer whose size has moved by a factor |
| `grid-alignment` | 32 | — | two layers of one island half a pixel apart |
| `negative-control` | 21 | 3 | settlement hallucinated onto protected ground |
| `loss-rate` | 16 | — | a method change disguised as demolition |
| `growth-only` | 16 | — | a year encoding broken by a bad merge |
| `agreement` | 8 | — | disagreeing with an unrelated producer |
| `stac-valid` | 1 | — | a catalogue other tools cannot read |

The 21 `totals` skips are layers with no meaningful CORINE band — greenhouses are
not "artificial surfaces" and a change layer is not a stock of anything — plus La
Graciosa, whose CORINE total of 0.27 km² is about one CORINE mapping unit and too
small to police. The 3 remaining skips are La Graciosa's missing control.

Measured values, not just verdicts: loss **0.002–0.083 %/yr** outside the
whitelisted Tajogaite polygon against a 0.2 % limit; agreement with Copernicus
**IoU 0.34–0.53** against a 0.30 floor.

### The negative controls

This is the only gate that can catch a product *inventing* settlement, and it used
to run on one island. Timanfaya alone meant Tenerife and Gran Canaria — which hold
most of the built-up area — had no commission check at all. Seven islands now have
one, **591 km² of protected ground against the previous 51**:

| island | control | clean km² | worst settlement reading |
|---|---|---|---|
| Tenerife | 11 areas (tier 1) | 247.3 | 0.023 % |
| Gran Canaria | 8 areas (tier 1) | 99.8 | 0.008 % |
| Fuerteventura | 7 areas (tier 1+2) | 81.0 | 0.024 % |
| La Palma | 3 areas (tier 1) | 63.3 | 0.004 % |
| Lanzarote | Timanfaya NP (tier 1) | 50.7 | 0.047 % |
| La Gomera | 3 areas (tier 1) | 39.5 | 0.005 % |
| El Hierro | 3 areas (tier 1) | 10.2 | 0.000 % |

The polygons come from the **Red Canaria de Espacios Naturales Protegidos**, the
official register — 147 areas, each carrying its legal protection category. That
replaced looking parks up by name in OpenStreetMap, which was fragile twice over:
a stale query once made the whole gate skip silently, and OSM has no polygon at
all for several of these areas.

**The protection category decides everything, and the categories are not
interchangeable:**

- **Tier 1** — *Parque Nacional*, *Reserva Natural Integral*, *Reserva Natural
  Especial*. Settlement is forbidden outright. Any built-up pixel is an error.
- **Tier 2** — *Monumento Natural*, *Sitio de Interés Científico*. These protect a
  specific feature: a volcanic cone, a cliff, a dune field. Usually unbuilt, but
  small and often close to towns, so they are used only where an island has no
  tier 1 area — which is Fuerteventura alone. Measured: adding them everywhere
  raised Tenerife's reading from 0.023 % to 0.085 %.
- **Tier 3** — *Parque Natural*, *Paisaje Protegido*, *Parque Rural*. These
  **explicitly include inhabited land**. A product finding buildings inside one is
  *right*, so they can never be controls however scenic.

**A protected area means nothing until it is cleaned.** Every one of these
contains real structures: Teide has the Parador hotel, mountain refuges and the
cable-car stations — 127 buildings in OpenStreetMap. Those are real, so the
control is the polygon *minus* a 30 m buffer around every known road and building.
Without that subtraction the control would generate false alarms instead of
catching them.

**La Graciosa has no control, and that is a deliberate refusal.** Its only
protected area is the Chinijo *Parque Natural*, which covers nearly the whole
island including the village of Caleta de Sebo. Cleaning it would mean trusting
OpenStreetMap to know where the village is — and OSM holds **299 of the island's
539 cadastral buildings, 55 %**. A control leaving 240 real buildings unsubtracted
would report correct detections as errors, which is worse than no control at all.
The gate reports a SKIP naming the reason.

**One layer is deliberately exempt.** `covered-agriculture` is a rasterised
official crop survey, not a classifier output, so there is no false positive for a
control to catch — and farming is permitted inside most protected areas, so
greenhouses found there are real. Testing it against a no-settlement control
measured 0.333 % on La Palma and read as a failure when it was the gate being
misapplied.

### Totals, and how they check out against M0

M0 measured these quantities independently, months of analysis before any of this
code existed. The pipeline reproducing them is the real test that it is doing what
it claims.

<!--[[[cog
# Left column: this build. Right column: M0's own measurement of the same quantity,
# typed here from docs/figures/data/m0_totals.csv, m0_imd_2024.csv and
# m0_undated_vs_crops.csv — historical by design, so a rebuild moves only the left.
bd = area_by("buildings-dated", 2020)
dc, dc_all = area("density-current"), f.prop_sum("density-current", "sealed_km2_including_greenhouses")
eb, eb_all = area("settlement-era-b"), area("settlement-era-b") + f.prop_sum("settlement-era-b", "greenhouse_removed_km2")
rows = [
    ("buildings-dated", f"**{km2(bd)} km²** (by 2020)", f"100.3 km² — agrees to **{bd / 100.3:.3f}×**"),
    ("density-trend", f"**{km2(area('density-trend'))} km²** (2020)",
     f"152.9 km² — differs by {abs(area('density-trend') - 152.9):.2f} km²"),
    ("density-current", f"{km2(dc, 1)} km² masked / {km2(dc_all, 1)} incl. greenhouses", "341.5 km² sealed"),
    ("settlement-era-a", f"{km2(area('settlement-era-a'), 1)} km² (2016 baseline, masked)",
     "per-island extents reproduce M0 **exactly**"),
    ("settlement-era-b", f"{km2(eb, 1)} km² (masked)",
     f"{km2(eb_all, 1)} km² unmasked — the {km2(eb_all - eb, 1)} km² gap is the greenhouses"),
    ("covered-agriculture", f"{km2(area('covered-agriculture'), 1)} km²",
     f"{km2(area('covered-agriculture', 'Gran Canaria'), 1)} km² on Gran Canaria alone"),
    ("loss-events", f"{km2(area('loss-events'), 1)} km² of change-layer built-up", "—"),
]
cog.outl("| layer | archipelago | independent M0 figure |")
cog.outl("|---|---|---|")
for name, ours, m0 in rows:
    cog.outl(f"| `{name}` | {ours} | {m0} |")
]]]-->
| layer | archipelago | independent M0 figure |
|---|---|---|
| `buildings-dated` | **101.98 km²** (by 2020) | 100.3 km² — agrees to **1.017×** |
| `density-trend` | **152.87 km²** (2020) | 152.9 km² — differs by 0.03 km² |
| `density-current` | 317.9 km² masked / 338.8 incl. greenhouses | 341.5 km² sealed |
| `settlement-era-a` | 239.1 km² (2016 baseline, masked) | per-island extents reproduce M0 **exactly** |
| `settlement-era-b` | 262.5 km² (masked) | 305.2 km² unmasked — the 42.8 km² gap is the greenhouses |
| `covered-agriculture` | 63.3 km² | 27.1 km² on Gran Canaria alone |
| `loss-events` | 167.2 km² of change-layer built-up | — |
<!--[[[end]]]-->

<!--[[[cog
excess = f"{100 * (area_by('buildings-dated', 2020) / 100.3 - 1):.1f} %"
cog.outl(f"The cadastre's {excess} excess over M0 is not an error in either: M0 used HISDAC-ES, "
         "which sums exact polygon areas, while this rasterises polygons onto 10 m pixels. "
         "A small building narrower than a pixel still lights the whole pixel. The two measure "
         f"slightly different things and agreeing to {excess} is what should happen.")
]]]-->
The cadastre's 1.7 % excess over M0 is not an error in either: M0 used HISDAC-ES, which sums exact polygon areas, while this rasterises polygons onto 10 m pixels. A small building narrower than a pixel still lights the whole pixel. The two measure slightly different things and agreeing to 1.7 % is what should happen.
<!--[[[end]]]-->

The seam factors reproduce `m0_seam_factors.csv` **exactly** — five islands × four
extents, to the last published decimal — and now extend to all eight.

### Two things worth knowing that came out of the build

**El Hierro can barely be dated by satellite.** Only **24.5 %** of its 2016
footprint inherits a year from WSF Evolution, against 66–68 % on Gran Canaria and
Fuerteventura. La Gomera is the only island where the 30 m product measures *less*
settlement than the 10 m one (a resolution factor of 0.88 where every other island
is 2.1–2.6). Both are the same known weakness: WSF Evolution maps settlement
clusters, and the small western islands are dispersed hamlets, not clusters. For
these islands the cadastre is not merely preferable — it is close to the only
usable source, which is what decision M1.1 chose.

**Cadastral dating is better than assumed.** Measured directly across all 88
municipalities: **474,292 buildings, 98.92 % carrying a construction year.** The
1.08 % that do not are undated for an honest reason — `--01-01` with no year at
all, or `88-01-01`, which could be 1888 or 1988. A two-digit year is ambiguous, so
those stay in the undated class rather than being resolved by guesswork.

### Size — the one criterion not met as written

M2's plan asked for the published output to stay in **single-digit MiB**. The total is

<!--[[[cog cog.out("**" + km2(f.size_published(), 1) + " MiB**") ]]]-->
**67.9 MiB**
<!--[[[end]]]-->

That target was set before the sealing layer had been measured, and it is worth
being precise about where the bytes went rather than quietly widening the goal:

<!--[[[cog
cog.outl("| | MiB |")
cog.outl("|---|---|")
cog.outl(f"| six layers (buildings, both settlement eras, greenhouses, trend, loss) "
         f"| **{km2(f.size_six_layers(), 1)}** |")
cog.outl(f"| `density-current` — the sealing map itself | {km2(f.size_mib('density-current'), 1)} |")
cog.outl(f"| `density-current` — the per-pixel confidence companion | {km2(f.size_confidence(), 1)} |")
cog.outl(f"| **total published** | **{km2(f.size_published(), 1)}** |")
]]]-->
| | MiB |
|---|---|
| six layers (buildings, both settlement eras, greenhouses, trend, loss) | **28.8** |
| `density-current` — the sealing map itself | 12.7 |
| `density-current` — the per-pixel confidence companion | 25.5 |
| **total published** | **67.9** |
<!--[[[end]]]-->

**It was 54.1 MiB when M2 closed and 60.2 MiB when the figure gate shipped.** Two
separate changes moved it, and both cost bytes on purpose.

M4 changed how COGs are written: overviews moved from `nearest` to `mode`, because
nearest made scattered 10 m buildings vanish when zoomed out, and `SPARSE_OK` was
removed, because geotiff.js cannot read zero-length tile offsets so no browser could
open the files at all. The six layers account for that **+5.0**.

The rest arrived on 2026-09-24, when each layer became **one archipelago-wide COG
instead of eight per-island ones**, so that the map can show the Canary Islands as
an archipelago rather than one island at a time. The island bounding boxes cover
21.1 % of the archipelago's box, so four fifths (78.9 %) of the new grid is ocean;
DEFLATE squashes ocean to almost nothing but does not erase it, and the measured
cost is a fifth more bytes on disk (22 %: the layer files go from 33.9 to 41.5 MiB). The per-island files are
still built — they are what the statistics and the QA gates are computed on — but
they are no longer published, or the same pixels would ship twice.

Correctness and reach bought with bytes, in a project whose per-visitor download is
what actually matters — and that is unchanged, because a COG is read by range
request whatever its extent.

The confidence grid is the single largest object in the project, larger than every
map layer combined. It is 52 distinct values scattered across tens of millions of
pixels, which is close to incompressible. Originally it was a second band of the
sealing layer, which tripled that layer's download for every visitor to carry
something almost none of them would open. It is now a **separate STAC asset**:
present, documented, fetched only when asked for. Tenerife's sealing layer went
from 13.7 MB to 4.3 MB as a result.

**The number that actually decides the architecture** is not the total but what one
visitor downloads. For all five 10 m layers of one island:

- La Gomera **0.59 MiB** · Gran Canaria **6.26 MiB** · Tenerife **8.04 MiB**

That is comfortably within what a browser reads directly from static files by
range request, so the conclusion the criterion was protecting — **no tile server is
needed** — holds. M0's 3.6 MiB figure was for the WSF timeline alone: sparse,
categorical, mostly ocean. A continuous 10 m sealing percentage over an entire
archipelago is a denser object by nature. At 11.5 MiB for all eight islands it is
not bloated; it is simply information the other layers do not contain.
