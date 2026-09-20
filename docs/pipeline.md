# M2 — the processing pipeline, in plain language

**What this milestone produced:** seven map layers covering the eight Canary
Islands, written to disk as files a web browser can read directly, each one
checked by automatic tests and described by a machine-readable catalogue.

M0 measured which datasets could be trusted. M1 chose between them. M2 turns those
choices into actual files. Nothing here runs in the cloud: everything is built on a
laptop into `data/processed/`, and that folder is exactly what a web host would
later serve, so the deployment step has nothing left to decide.

---

## 1. The idea that makes all of this work: one shared grid

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

Built with `python scripts/build.py --all`: **56 files, seven layers across eight
islands, 168/168 measured QA gates passing** (49 further checks did not apply),
every COG passing `rio cogeo validate --strict` and every catalogue object passing
STAC validation.

The gates break down like this, and the skips are worth reading rather than
glossing — a check that did not run is not a check that passed:

| gate | measured | did not apply | catches |
|---|---|---|---|
| `totals` | 35 | 21 | a layer whose size has moved by a factor |
| `cog-valid` | 56 | — | a file a browser cannot read by byte-range |
| `grid-alignment` | 32 | — | two layers of one island half a pixel apart |
| `loss-rate` | 16 | — | a method change disguised as demolition |
| `growth-only` | 16 | — | a year encoding broken by a bad merge |
| `agreement` | 8 | — | disagreeing with an unrelated producer |
| `negative-control` | 4 | 28 | settlement hallucinated onto bare lava |
| `stac-valid` | 1 | — | a catalogue other tools cannot read |

Almost all the skips are the lava control: Timanfaya is on Lanzarote, so 28 of its
32 instances can say nothing about the other seven islands. The other 21 are
`totals` on layers with no meaningful CORINE band — greenhouses are not
"artificial surfaces" and a change layer is not a stock of anything — plus La
Graciosa, whose CORINE total of 0.27 km² is too small to police.

Measured values, not just verdicts: Timanfaya **0.047 %** of a 50.8 km² control
against a 0.1 % limit; loss **0.002–0.083 %/yr** outside the whitelisted Tajogaite
polygon against a 0.2 % limit; agreement with Copernicus **IoU 0.34–0.53** against
a 0.30 floor.

### Totals, and how they check out against M0

M0 measured these quantities independently, months of analysis before any of this
code existed. The pipeline reproducing them is the real test that it is doing what
it claims.

| layer | archipelago | independent M0 figure |
|---|---|---|
| `buildings-dated` | **101.98 km²** (by 2020) | 100.3 km² — agrees to **1.017×** |
| `density-trend` | **152.87 km²** (2020) | 152.9 km² — agrees to three digits |
| `density-current` | 317.9 km² masked / 338.8 incl. greenhouses | 341.5 km² sealed |
| `settlement-era-a` | 239.1 km² (2016 baseline, masked) | per-island extents reproduce M0 **exactly** |
| `settlement-era-b` | 262.5 km² (masked) | 305.2 km² unmasked — the 42.7 km² gap is the greenhouses |
| `covered-agriculture` | 63.3 km² | 27.1 km² on Gran Canaria alone |
| `loss-events` | 167.2 km² of change-layer built-up | — |

The cadastre's 1.7 % excess over M0 is not an error in either: M0 used HISDAC-ES,
which sums exact polygon areas, while this rasterises polygons onto 10 m pixels.
A small building narrower than a pixel still lights the whole pixel. The two
measure slightly different things and agreeing to 1.7 % is what should happen.

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

M2's plan asked for the published output to stay in **single-digit MiB**. It is
**54.1 MiB**. That target was set before the sealing layer had been measured, and
it is worth being precise about where the bytes went rather than quietly widening
the goal:

| | MiB |
|---|---|
| six layers (buildings, both settlement eras, greenhouses, trend, loss) | **17.1** |
| `density-current` — the sealing map itself | 11.5 |
| `density-current` — the per-pixel confidence companion | 25.2 |
| **total** | **54.1** |

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
