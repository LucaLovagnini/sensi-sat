# Milestone 0 — dataset evaluation for the Canary Islands

What this is: a measured, reproducible answer to "which open datasets can SensiSat
trust, and where do they fail?" Nothing here is taken on faith from a dataset's
documentation; every number was computed locally from the downloaded files.

Run date: 2026-09-19. Reproduce with `python scripts/fetch_m0.py` then the
`scripts/analysis_*.py` files (list at the end). Downloads are recorded with size and
SHA-256 in `data/raw/manifest.json`; the rasters actually used total ~200 MiB. Two
inputs are not auto-fetched: the Copernicus Built-Up Change package (needs a free
CLMS account; place under `data/raw/hrl/110241/`) and the HISDAC-ES municipal tables.

Evidence tags: **measured** = computed here · **verified** = read in a primary
source · **estimate** = our arithmetic, shown.

---

## Headline findings

1. **Dynamic World is disqualified.** It reports 307.8 km² built on Gran Canaria
   alone. The whole archipelago measures 376.9 km² (WSF Evolution, 30 m),
   230.4 km² (WSF 2019, 10 m) or 152.9 km² (GHSL built surface). One island in
   Dynamic World exceeds all eight islands in every independent product.
2. **Lava is not the problem we feared.** Timanfaya National Park — 51 km² of bare
   lava — comes back clean in every product (≤ 0.08 %). The documented
   bare-rock/built confusion does not materialise here. No lava mask is needed.
3. **WSF 2015 and WSF 2019 are not a time series.** They imply 9.7 %/yr growth,
   against WSF Evolution's own 0.49 %/yr. The difference is method, not building.
4. **The WSF family and GHSL cannot measure demolition — Copernicus can, and the
   answer is "almost none".** WSF 2019 is a strict superset of WSF 2015 (loss
   0.02 km²), and Tracker encodes the *earliest* epoch a pixel was seen built. But
   Copernicus Impervious Built-Up Change 2018–2021 (downloaded 2026-09-19) records
   gain and loss separately: **0.259 km² lost against 1.95 km² gained** across the
   archipelago — **0.052 %/yr**. A growth-only encoding therefore misplaces ~2 % of
   built pixels over 40 years. Decision 5 stands; the two-image "real view" is not
   needed (section 5).

5. **WSF Tracker passes its tests and is a GO** — 1.11 %/yr growth archipelago-wide,
   a smooth epoch histogram, a clean Timanfaya, and only 0.5 % of the Tajogaite
   lava field newly flagged as built (most likely the rebuilt LP-2 road, not
   fresh-lava confusion). But its 2016 baseline is 1.66× WSF 2015 from eighteen
   months earlier, which makes the 2015/2016 seam a calibration problem, not a
   join (section 6).
6. **Extent and surface disagree in *opposite directions* depending on density** —
   the cleanest empirical demonstration of the distinction so far (section 3).
7. **The 1985 baseline is half-confirmed and WSF Evolution misses the other half of
   the island.** Against the cadastre (98.5 % of Canary buildings carry a construction
   year), about half of WSF's "built by 1985" pixels sit on cells with a pre-1985
   building, a quarter to a third on cells with **no building at all**. And WSF has no
   built pixel in ~50 % of the cells that held a pre-1985 building — 89 % on La Gomera.
   WSF maps *settlement*, not *buildings*; dispersed rural stock is largely invisible
   to it (section 6c). The cadastre-derived HISDAC-ES becomes a serious candidate for
   the pre-2016 "when" layer in Spain.

---

## 1. How much is built? (analysis 1)

Per island, with the same island polygon applied to every product.

| island | area km² | WSF Evo 2015 (30 m) | % | WSF 2015 (10 m) | % | WSF 2019 (10 m) | % | GHSL surface 2020 | % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| El Hierro | 268 | 2.4 | 0.9 | 1.4 | 0.5 | 2.5 | 0.9 | 1.6 | 0.6 |
| La Palma | 708 | 18.2 | 2.6 | 7.4 | 1.0 | 11.7 | 1.6 | 9.3 | 1.3 |
| La Gomera | 369 | 1.8 | 0.5 | 2.0 | 0.5 | 2.9 | 0.8 | 2.3 | 0.6 |
| Tenerife | 2039 | 128.6 | 6.3 | 60.9 | 3.0 | 79.4 | 3.9 | 58.3 | 2.9 |
| Gran Canaria | 1566 | 125.5 | 8.0 | 53.3 | 3.4 | 83.2 | 5.3 | 49.0 | 3.1 |
| Fuerteventura | 1663 | 42.1 | 2.5 | 18.0 | 1.1 | 23.3 | 1.4 | 14.8 | 0.9 |
| Lanzarote | 809 | 57.9 | 7.2 | 22.6 | 2.8 | 27.1 | 3.4 | 17.5 | 2.2 |
| La Graciosa | 27 | 0.4 | 1.3 | 0.1 | 0.5 | 0.2 | 0.7 | 0.1 | 0.3 |
| **archipelago** | **7476** | **376.9** | **5.0** | **165.8** | **2.2** | **230.4** | **3.1** | **152.9** | **2.0** |

**Plausibility.** Official statistics put artificial land near 6 % of the
archipelago, and artificial surfaces are a *superset* of built-up (they include
quarries, dumps and sports grounds). Every product above lands below that ceiling,
in the right order: extent at 30 m (5.0 %) > extent at 10 m (3.1 %) > surface
(2.0 %). All three are plausible. **measured**

**Dynamic World is not.** Its 307.8 km² for Gran Canaria is 19.7 % of that island
— higher than the whole archipelago's artificial-land share, and 2.5× the best
30 m extent estimate for the same island, 6× the surface estimate. Its "Built"
class includes urban open space and confuses bare ground, crops and greenhouses
**verified**; the arithmetic here **measured** confirms the scale of the error.
**Verdict: do not use, not even as an experimental layer, without correction.**

## 2. Lava: one control passes, one test is not yet testable (analysis 2)

| polygon | role | product | built | share | verdict |
|---|---|---|---:|---:|---|
| Timanfaya NP (50.7 km² after removing the LZ-67 road and visitor facilities) | negative control | WSF Evolution 2015 | 0.000 km² | 0.00 % | **PASS** |
| | | WSF 2015 | 0.000 km² | 0.00 % | **PASS** |
| | | WSF 2019 | 0.043 km² | 0.08 % | **PASS** |
| | | GHSL 2015 / 2020 | 0.004 km² | 0.01 % | **PASS** |
| Tajogaite 2021 lava (10.4 km²) | loss test case | WSF Evolution 2015 | 2.652 km² | 25.6 % | baseline |
| | | WSF 2015 | 0.556 km² | 5.4 % | baseline |
| | | WSF 2019 | 0.823 km² | 7.9 % | baseline |
| | | GHSL 2015 / 2020 | 0.587 / 0.595 km² | 5.7 % | baseline |

**Timanfaya passes cleanly.** 300-year-old bare lava is not mistaken for
settlement by WSF or GHSL. This removes a risk the plan flagged for Lanzarote and
Fuerteventura, and means no lava mask is required. **measured**

**Tajogaite is a loss test, not a control** — and a correction to our own test
design. That lava buried Todoque and part of La Laguna in Sep–Dec 2021, so
built-up land inside the polygon is *correct* for every dataset evaluated here,
all of which predate the eruption. It measures what was destroyed. The polygon
only becomes a test once a product covers 2022+, when those pixels must switch to
not-built. **That is the single sharpest test available for WSF Tracker.**

**An accidental cross-validation.** GHSL puts 0.587 km² of built *surface* inside
the lava field; Catastro recorded 1,676 buildings destroyed **verified**. That
implies ~350 m² per building — plausible for detached housing plus agricultural
structures in a rural municipality. Two completely independent methods, one
satellite and one cadastral, agree to within the precision either can claim.
**estimate** (the per-building figure, not the two source numbers).

**Resolution inflation is worst where settlement is sparse.** In the Tajogaite
polygon, WSF Evolution at 30 m reports 4.8× the extent that WSF 2015 reports at
10 m, against ~2.3× archipelago-wide. Scattered rural buildings each switch on a
whole coarse pixel. **measured**

## 3. Extent vs surface: the direction of the gap depends on density (analysis 1)

Growth 1990 → 2015, same island polygon, extent (WSF Evolution) vs surface (GHSL):

| island | WSF extent | GHSL surface | which is larger |
|---|---:|---:|---|
| Tenerife | +10 % | +13 % | surface |
| Gran Canaria | +11 % | +57 % | **surface, by far** |
| La Palma | +17 % | +15 % | ~equal |
| La Gomera | +18 % | +15 % | ~equal |
| El Hierro | +26 % | +13 % | extent |
| Lanzarote | +183 % | +192 % | ~equal |
| Fuerteventura | +400 % | +162 % | **extent, by far** |
| La Graciosa | +620 % | +285 % | extent |

This is the extent/surface distinction (docs/concepts.md §3) showing both of its
faces:

- **Dense, already-urbanised islands** (Gran Canaria): extent saturates — the
  pixels were already switched on in 1990, so infill adds surface but no extent.
  Surface growth is 5× extent growth.
- **Sparse, rapidly developing islands** (Fuerteventura, La Graciosa): the
  opposite. Each new scattered building switches on a whole 30 m pixel while
  adding little actual cover, so extent grows 2.5× faster than surface.

Neither product is wrong. **Reporting only one of them would misrepresent
whichever half of the archipelago it suits less**, which settles the plan's
decision to publish both.

## 4. The 1985 baseline (analysis 1)

WSF Evolution's first year is a baseline: everything built before satellite record
began. The plan flagged a risk that early Landsat over-detects bare dry soil,
inflating it.

| island | 1985 km² | 2015 km² | baseline share | growth |
|---|---:|---:|---:|---:|
| La Graciosa | 0.05 | 0.36 | 14 % | ×7.2 |
| Fuerteventura | 7.59 | 42.07 | 18 % | ×5.5 |
| Lanzarote | 18.50 | 57.92 | 32 % | ×3.1 |
| El Hierro | 1.88 | 2.37 | 79 % | ×1.3 |
| La Gomera | 1.48 | 1.76 | 84 % | ×1.2 |
| La Palma | 15.56 | 18.21 | 85 % | ×1.2 |
| Gran Canaria | 109.66 | 125.52 | 87 % | ×1.1 |
| Tenerife | 115.62 | 128.64 | 90 % | ×1.1 |
| **archipelago** | **270.4** | **376.9** | **72 %** | **×1.4** |

**This is more credible than a uniform saturation would be.** The split is not
random: the islands with a low baseline and explosive growth (Fuerteventura ×5.5,
Lanzarote ×3.1) are exactly the two whose tourism development came late, while the
saturated ones (Tenerife, Gran Canaria) had their build-out in the 1960s–70s,
before the record starts. WSF Evolution is reproducing known history, not noise.
**measured**, interpretation ours.

It remains true that for Gran Canaria and Tenerife the product has little to say:
~88 % of what it will ever show is present in frame one. For those islands the
1975–1990 GHSL epochs and cadastral data carry the story, not WSF.

**Still to test:** what share of WSF's "built by 1985" pixels contain a building
the cadastre dates ≤ 1985. That needs HISDAC-ES (not yet fetched).

## 5. Loss and demolition: still unanswered (analysis 7)

The plan needs the real rate at which built-up land stops being built-up, because
that is the cost of a growth-only time encoding.

Measured between WSF 2015 and WSF 2019 (both 10 m, same producer, 4 years apart):

| | archipelago |
|---|---:|
| built 2015 | 165.78 km² |
| built 2019 | 230.42 km² |
| apparent loss | **0.02 km² (0.01 %)** |
| gained | 64.66 km² |

**Loss is exactly zero.** WSF 2019 is effectively a strict superset of WSF 2015.
Combined with the documented growth-only construction of WSF Evolution and GHSL
**verified**, no dataset currently in hand can express demolition at all.

**And the gain is not real either.** +64.66 km² in four years is 9.7 %/yr, against
WSF Evolution's own 2011–2015 rate of 0.49 %/yr — a factor of 20. Per island the
implied rates are absurd: El Hierro +20 %/yr, Gran Canaria +14 %/yr. WSF 2015 and
WSF 2019 were built from different sensors, and the difference is method change.
**measured**

Two consequences for the plan:

- **The 2015/2016 seam is more dangerous than assumed.** If two products from the
  same producer four years apart differ by 39 %, splicing WSF Evolution (ends
  2015) onto WSF Tracker (starts 2016-07) will produce a step change that looks
  like a building boom. Calibration across the seam is mandatory, not optional.
- ~~The loss question needs a source we do not have.~~ **Answered** (analysis 13,
  Copernicus Impervious Built-Up Change 2018–2021, 20 m, EPSG:3035, ten 100 km tiles
  covering all islands; class codes read from the shipped SLD style):

  | island | built 2018 | built 2021 | new | **lost** | loss %/yr |
  |---|---:|---:|---:|---:|---:|
  | Tenerife | 59.94 | 60.38 | 0.572 | **0.130** | 0.072 |
  | Gran Canaria | 55.56 | 56.00 | 0.536 | **0.098** | 0.059 |
  | Lanzarote | 24.77 | 25.10 | 0.349 | 0.020 | 0.027 |
  | Fuerteventura | 13.31 | 13.68 | 0.374 | 0.011 | 0.027 |
  | La Palma | 7.62 | 7.63 | 0.006 | 0.000 | 0.000 |
  | La Gomera | 2.07 | 2.13 | 0.061 | 0.000 | 0.006 |
  | El Hierro | 1.51 | 1.56 | 0.052 | 0.000 | 0.000 |
  | **archipelago** | **164.97** | **166.67** | **1.950** | **0.259** | **0.052** |

  (km², 20 m pixels = exactly 400 m² in the LAEA grid, no latitude correction.)
  **Real loss is 0.052 %/yr** — a growth-only encoding misplaces ~2.1 % of built pixels
  over 40 years. Gain is 0.394 %/yr, about a third of Tracker's 1.11 %/yr; Copernicus
  counts buildings within sealed areas, Tracker counts more (including greenhouses,
  section 6b). Two caveats: the "technical vs real change" support layer was not in the
  download, so 0.259 km² is an upper bound on real loss; and La Palma shows **zero**
  loss, so the 2021 reference imagery predates the Sep–Dec 2021 eruption — the 2024
  layer is the one that will show Todoque disappear.

## 6. WSF Tracker: plausible, but the seam is worse than we thought (analysis 10)

Read directly from the GeoZarr on source.coop over anonymous HTTP range requests —
no bulk download of the 1.54M × 4.01M global grid, only the windows we ask for.

**Its internal growth rate is credible.** This is the single most important test it
passes, and the one WSF 2015 → 2019 failed badly:

| island | built 2026 | baseline (2016-07) | baseline share | added | growth |
|---|---:|---:|---:|---:|---:|
| Tenerife | 122.61 | 110.85 | 90.4 % | 11.76 | 1.12 %/yr |
| Gran Canaria | 101.91 | 92.33 | 90.6 % | 9.58 | 1.09 %/yr |
| Lanzarote | 30.57 | 28.11 | 92.0 % | 2.46 | 0.92 %/yr |
| Fuerteventura | 27.02 | 23.72 | 87.8 % | 3.31 | 1.47 %/yr |
| La Palma | 16.25 | 14.91 | 91.8 % | 1.34 | 0.95 %/yr |
| La Gomera | 3.69 | 3.27 | 88.5 % | 0.43 | 1.37 %/yr |
| El Hierro | 3.02 | 2.75 | 91.2 % | 0.26 | 1.01 %/yr |
| La Graciosa | 0.17 | 0.16 | 95.6 % | 0.01 | 0.48 %/yr |
| **archipelago** | **305.23** | **276.10** | **90.5 %** | **29.14** | **1.11 %/yr** |

0.5–1.5 %/yr is what real urban growth looks like. The epoch histogram is smooth —
1.0 to 3.6 km² per half-year with no spikes — which is what genuine construction
looks like and what a method change does not. **measured**

**Timanfaya: PASS.** 0.029 km² in 50.7 km² of lava = 0.06 %.

**Tajogaite: the sharpest result in M0.** Tracker reports 0.839 km² of built-up
inside the 2021 lava field, split by when it was *first* detected:

- 0.776 km² first seen **before** 2021-07 — the buildings the lava buried. Correct.
- 0.062 km² first seen **after** 2021-07 — built-up appearing *on* the lava.

That 6.2 hectares is most likely the LP-2 road rebuilt across the flow, which is
real construction. It is only 0.5 % of the lava field, far too little for
systematic fresh-lava-reads-as-built confusion. **This is the strongest available
evidence that Tracker is not fooled by fresh basalt** — the risk the plan worried
about most. A visual check against 2023+ imagery would settle it; not done here.

**But Tracker confirms the seam is a real hazard.** There are now *three*
incompatible 10 m footprints from DLR for essentially the same moment:

| product | date | archipelago built-up |
|---|---|---:|
| WSF 2015 | 2015 | 165.8 km² |
| **WSF Tracker epoch 1** | **2016-07** | **276.1 km²** |
| WSF 2019 | 2019 | 230.4 km² |

Tracker's 2016 baseline is **1.66× WSF 2015** eighteen months earlier, and larger
than WSF 2019 from three years *later*. Per island the ratio to WSF 2015 ranges
1.12× (La Graciosa) to 2.02× (La Palma). These are definitional differences, not
construction. **measured**

Consequence for the plan: WSF Evolution (ends 2015, 30 m) and WSF Tracker (starts
2016-07, 10 m) **cannot simply be spliced**. The 30 m → 10 m change would shrink
the footprint while the definitional change would inflate it, by different amounts
per island. The two effects partially cancel archipelago-wide (376.9 → 276.1) and
would be read as a 27 % collapse in urban area at the seam. Calibration is
mandatory.

**And Tracker cannot show loss either.** Its values encode the *earliest* epoch a
pixel was seen built, and its overviews aggregate by minimum — growth-only by
construction, like everything else in the family **verified from the array's own
metadata**. The La Palma burial is invisible to it.

**The seam per island, with the greenhouse mask applied (analysis 3).** Resolution
factor = WSF Evolution 2015 (30 m) ÷ WSF 2015 (10 m), same producer and year.
Definition factor = Tracker epoch 1 (2016-07) ÷ WSF 2015, both 10 m, before and after
removing greenhouse parcels from Tracker. Agreement = WSF Evolution 2015 vs masked
Tracker 2016 on a common 100 m grid: Jaccard of cells ≥ 10 % built, and correlation
of cell fractions.

| island | Evo 2015 (30 m) | WSF 2015 (10 m) | Tracker 2016 → masked | resolution × | definition × raw → masked | Evo→Tracker net × | Jaccard | r |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Gran Canaria | 125.5 | 53.3 | 92.3 → 75.4 | 2.35 | 1.73 → **1.41** | 0.60 | 0.53 | 0.77 |
| Tenerife | 128.6 | 60.9 | 110.9 → 95.0 | 2.11 | 1.82 → **1.56** | 0.74 | 0.53 | 0.78 |
| La Palma | 18.2 | 7.4 | 14.9 → 11.4 | 2.47 | 2.02 → **1.55** | 0.63 | 0.37 | 0.63 |
| Fuerteventura | 42.1 | 18.0 | 23.7 → 23.3 | 2.33 | 1.31 → 1.29 | 0.55 | 0.49 | 0.79 |
| Lanzarote | 57.9 | 22.6 | 28.1 → 28.1 | 2.56 | 1.24 → 1.24 | 0.48 | 0.61 | 0.85 |

The greenhouse mask takes a third off the definitional jump where greenhouses are
common (Gran Canaria, Tenerife, La Palma) and nothing where they are not. A residual
×1.24–1.56 remains — the dispersed buildings and infrastructure Landsat never saw
(section 6c). Spliced naively, the footprint would **drop by 26–52 % at the join,
differently on every island**; the calibration is per island, as the design requires.
Spatial agreement between the two eras on a common grid is moderate (r 0.63–0.85),
worst on La Palma, best on Lanzarote. **measured**

A correction to the plan's wording: averaging a binary mask to 100 m *fractions*
preserves total area, so the fraction grid does **not** remove coarse-pixel
inflation — it only provides a common support for cell-by-cell comparison. Only
surface products (GHSL, HRL, cadastre) are free of the pixel-size effect.

## 6b. The greenhouse question, answered sideways (analysis 11)

43 % of Tracker's 2016 footprint has no WSF Evolution year. Roads do not explain it:
28.7 % of those pixels lie within 15 m of an OpenStreetMap road, against 47.0 % of the
dated pixels (60,603 highway ways, Gran Canaria) **measured**. A map does: the two
largest undated clusters (129 ha by Vecindario, 63 ha by Gáldar) are greenhouses and
plastic- or mesh-covered plantations, drawn precisely along the plot boundaries, with
the dated pixels on the adjacent towns. Sentinel-1 radar sees metal and plastic
frames as structure; Landsat spectral indices did not.

Two consequences. WSF Tracker's "built-up" is over-inclusive against our definition
(decision 2) and needs covered agriculture masked out before its totals are comparable
with anything else — the plan's "plan B" greenhouse mask returns, but for Tracker
specifically, not for WSF Evolution or GHSL. And a substantial part of the 1.66×
definitional jump at the 2015/2016 seam is agriculture, not urban growth.

**Quantified against the Gobierno de Canarias Mapa de Cultivos** (1:2 000, surveyed
2023–24; Global-PCG-10 turned out to have no cells over the Canaries): on Gran Canaria
**36.5 % of the undated class lies on greenhouse parcels, against 4.6 % of the dated
class**; 42.4 % on any agricultural parcel; **57.6 % (≈ 23 km²) outside every parcel
and mostly away from roads — unexplained**, and the target of the M3 stratum
(analysis 12). The greenhouse mask alone removes ≈ 17 km² (18 %) from Tracker's
Gran Canaria 2016 baseline.

Timanfaya remains clean; the *lava* mask is still unnecessary. The two masks answer
different failure modes.

## 6c. The cadastre as an independent witness (analysis 8)

Spain's cadastre records a construction year for every building; HISDAC-ES (Uhl et
al. 2023, CC BY 4.0) grids it at 100 m: earliest construction year per cell, and
building footprint area per 5-year epoch 1900–2020. It shares no data and no failure
mode with any satellite product. In the Canaries it is unusually complete: **only
1.5 % of 470,942 buildings lack a construction year** (worst municipality 10 %), and
cells whose only buildings are undated account for 0.1–0.4 % of the area below —
so "no dated building" can be read as "no building". **measured**

**Is WSF Evolution's 1985 baseline real?** For its "built by 1985" pixels, what the
cadastre has in the same 100 m cell:

| island | WSF 1985 km² | building dated ≤ 1985 | earliest building after 1985 | **no building at all** |
|---|---:|---:|---:|---:|
| Tenerife | 115.6 | 53.0 % | 21.9 % | **25.0 %** |
| Gran Canaria | 109.7 | 51.4 % | 17.7 % | **30.5 %** |
| Lanzarote | 18.5 | 51.7 % | 24.8 % | 23.2 % |
| La Palma | 15.6 | 61.4 % | 16.4 % | 22.1 % |
| Fuerteventura | 7.6 | 42.0 % | 29.1 % | 28.7 % |

About half is confirmed. A quarter to a third sits in cells with **no building** —
roads, ports, airports and quarries (the cadastre excludes them, and they *are*
built-up under our definition), greenhouses, or bare-soil commission. A fifth sits
where the earliest surviving building post-dates 1985 — WSF early, or the whole cell
rebuilt. Because a 100 m cell is generous (any building within it counts), the
confirmed share is an upper bound and the no-building share a lower bound.

**And the other direction: what WSF Evolution never saw.** Of the cadastre's cells
with a building dated ≤ 1985:

| island | cells | WSF has a ≤ 1985 pixel | WSF dates it later | **WSF never flags the cell** |
|---|---:|---:|---:|---:|
| Lanzarote | 4,517 | 56.4 % | 20.4 % | 23.2 % |
| Tenerife | 23,494 | 52.6 % | 1.6 % | **45.7 %** |
| Gran Canaria | 19,785 | 47.0 % | 1.6 % | **51.4 %** |
| Fuerteventura | 3,362 | 19.0 % | 38.3 % | 42.7 % |
| La Palma | 7,665 | 29.8 % | 1.1 % | **69.1 %** |
| El Hierro | 1,028 | 27.5 % | 1.8 % | **70.6 %** |
| La Gomera | 2,173 | 10.4 % | 0.8 % | **88.9 %** |

**WSF Evolution has no built pixel at all in roughly half of the 100 m cells that
held a pre-1985 building — 89 % on La Gomera.** This is the fair reading: WSF maps
*settlement* — clusters dense enough to register at 30 m — not *buildings*. A lone
farmhouse in a ravine is a building to the cadastre and nothing to WSF. It is not a
classification error so much as a definition, but it means WSF Evolution
under-represents dispersed rural building stock badly, worst on the steep western
islands. It explains two earlier puzzles at once: La Gomera's "127 % full" (GHSL
surface exceeding WSF extent — WSF simply misses most of the island's buildings),
and the Tracker undated class, **51–65 % of which sits in cells that do contain
cadastral buildings** — dispersed houses that 10 m radar sees and 30 m Landsat
indices did not.

**Does WSF's year match the cadastre's?** For pixels WSF dates 1986–2015, the
cadastre's earliest building in the cell agrees within ±5 years in only 9–16 % of
cases; it is *earlier* in 32–53 %. WSF's year is the year a pixel became detectably
settled, which comes after the first building. The honest label is **"settlement
detected by year X"**, not "built in X".

**A third surface series across the seam.** Cadastral building footprint per island
(surviving buildings, by construction year), km²:

| | 1975 | 1985 | 1990 | 2000 | 2010 | 2015 | 2020 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Tenerife | 14.5 | 20.4 | 23.8 | 31.3 | 40.1 | 40.7 | 41.1 |
| Gran Canaria | 12.8 | 18.5 | 21.3 | 27.2 | 33.3 | 33.8 | 34.1 |
| Lanzarote | 2.3 | 4.0 | 5.7 | 7.7 | 9.9 | 10.0 | 10.1 |
| Fuerteventura | 1.1 | 1.9 | 2.7 | 4.4 | 7.2 | 7.4 | 7.5 |
| **archipelago** | **34.1** | **49.2** | **58.5** | **77.6** | **96.1** | **99.5** | **100.3** |

Growth 1990→2015: **cadastre +70 %**, GHSL surface +42 %, WSF Evolution extent
+36 %. The cadastre's is an upper bound — demolished buildings vanish and a rebuild
takes the rebuild's date — and the near-flat 2015→2020 (+0.8 %) is registration lag
as much as a slowdown. Three products, three definitions, growth rates from +36 % to
+70 % for the same islands and years.

**What is the no-building third made of?** (analysis 14, Gran Canaria). Of the
33.45 km² of WSF's 1985 baseline that sits in cells with no cadastral building:

| explanation | share | cumulative |
|---|---:|---:|
| within 15 m of an OpenStreetMap road | 43.3 % | 43.3 % |
| airport, port, industrial, quarry, marina, golf (OSM) | +7.8 % | 51.1 % |
| greenhouse parcels (crop map) | +3.5 % | 54.6 % |
| other agricultural parcels | +7.4 % | 62.0 % |
| **unexplained — candidate bare-soil commission** | **38.0 % = 12.7 km²** | |

Roads and infrastructure — built-up under our definition, invisible to the cadastre
— account for half. The unexplained 12.7 km² is **11.6 % of the whole 1985
baseline** on Gran Canaria and becomes its own stratum in the M3 sample. **measured**

**Is GHSL any better at seeing buildings?** Same cell test, GHSL 1990 against cells
with a building dated ≤ 1990, with a minimum surface per 100 m cell so that
interpolation smear does not count:

| island | GHSL ≥ 1 m² | GHSL ≥ 100 m² | GHSL ≥ 500 m² | WSF Evo (any pixel ≤ 1990) | GHSL surface on cells with a building |
|---|---:|---:|---:|---:|---:|
| Tenerife | 99 % | 91 % | 55 % | 53 % | 65 % |
| Gran Canaria | 97 % | 81 % | 39 % | 47 % | 62 % |
| Lanzarote | 99 % | 81 % | 27 % | 59 % | 62 % |
| Fuerteventura | 97 % | 73 % | 21 % | 21 % | 51 % |
| La Palma | 96 % | 82 % | 41 % | 29 % | 70 % |
| La Gomera | 94 % | 75 % | 33 % | 11 % | 66 % |

GHSL *does* register dispersed buildings that WSF misses — at ≥ 100 m² per cell its
recall is 73–91 % against WSF's 11–59 % — but it pays for it in precision: 30–49 % of
its 1990 built surface lies on cells with no cadastral building, and its surface
exceeds the cadastral footprint by 1.3–2.5× on most islands. GHSL sees more and
smears it; WSF sees less and sharper. Neither is a *buildings* map. **measured**

**Can the raw cadastre be turned into a 10 m dated layer? Yes — demonstrated.**
The INSPIRE Buildings feed for Santa Lucía de Tirajana (Vecindario; one zip of
6.4 MiB from the province-35 ATOM feed) holds 12,481 building polygons in EPSG:32628,
**98.7 % with a construction date**, readable with GeoPandas and rasterised by year
onto Tracker's 10 m grid in seconds; the resulting year-first-built COG for the
municipality is 58 KiB. On that grid:

| | km² |
|---|---:|
| cadastral building footprints, any year | 2.32 |
| footprints built by 1985 / by 2016 | 1.07 / 2.29 |
| WSF Tracker built-up by 2016-07 | 18.61 |
| WSF Evolution, any year | 22.35 |

Footprints are ~12 % of the *extent* products — yards, streets and plots make up the
rest, as they should. Recall is high where settlement is dense: Tracker covers
**88.6 %** of the 2016 footprints and WSF Evolution **85.0 %** of the pre-1985 ones in
this town, against ~50 % for WSF island-wide — the dispersed-building gap is a rural
phenomenon. And only **3.0 %** of Tracker's undated pixels here fall on a building
footprint: in Vecindario the undated class is the greenhouse belt, as the map showed.
Scaling to all 88 Canary municipalities is ~500 MiB of downloads and minutes of
processing. **measured**

**Verdict.** The cadastre is the strongest reference we have for *buildings* in the
Canaries, and a serious candidate for the pre-2016 "when" layer in Spain — 98.5 %
dated, 1900→2020, 100 m. WSF Evolution remains the right product for *settlement
extent* and the only global option; the two answer different questions and the map
must say which one it is showing.

## 6c′. The other global candidates, through the same test (analysis 15)

Every remaining global "year first built" product was put through one harness
(`sensisat/evaluate.py`): extent by year on Gran Canaria, and the cadastre cell test
at 1990 — recall = share of 100 m cells with a building dated ≤ 1990 that the product
flags by 1990; precision = share of the cells it flags that contain any building.

| product | source | GC extent 1990 → 2015 | growth | recall | precision | verdict |
|---|---|---:|---:|---:|---:|---|
| **WSF Evolution** (30 m, 1985–2015) | DLR | 112.7 → 125.5 | +11 % | **47.0 %** | **59.8 %** | reference |
| GAIA (30 m, 1985–2018) | Tsinghua, via GEE (host migrated) | 67.0 → 70.0 | +4 %; **flat for 25 years** | 27.7 % | 54.0 % | **NO-GO** |
| GISA v1 (30 m, 1972–2019) | Zenodo | 36.3 → 102.3 | +181 %, era-shaped jumps; **no data at all on Tenerife** | 13.6 % | 47.1 % | **NO-GO** |
| GISA-new (30 m, 1985–2021) | Zenodo | 69.0 → 136.6 | +98 %, jumps at 2005/2015; 157 km² in 2020 | 41.0 % | 55.8 % | **NO-GO** |
| GISD30 (30 m, 1985–2020) | Zenodo (RAR) | 37.8 → 51.4 | +36 %, smooth | 25.6 % | 64.7 % | **NO-GO** as a replacement; usable as a cross-check |
| GHSL built surface (~92 m, 1975–2030) | JRC | surface, not extent | +58 % | 80.6 % (≥ 100 m²/cell) | ~62 % of surface on building cells | keep, as *surface* (§6c) |
| Esri / IO annual LULC "Built area" (10 m, 2017–2023) | Planetary Computer, no login | 284.9 (2017) → 288.0 (2023); **2019 spikes to 313.8** | year-to-year "loss" 2.6–11.8 %/yr — flicker | 82.6 % (2017) | 54.5 % | **NO-GO**: Dynamic-World-scale inflation and unusable as a state series |

Tenerife confirms the pattern: GAIA 14.8 km² flat, recall 9 %; GISD30 recall 15 %;
GISA v1 returns zero pixels for the whole island. **No global product beats WSF
Evolution on both recall and precision.** The two that see dispersed buildings — GHSL
and Esri — pay for it with smeared or inflated area; the 30 m Landsat products share
WSF's detectability limit and add method artefacts of their own. **measured**

The candidate list for the pre-2016 era is therefore closed: **WSF Evolution for
settlement extent (global), the cadastre for buildings (Spain), GHSL for surface.**

## 6d. How big is it, really? (analysis 9)

Every dataset's Canary window, re-encoded the way we would publish it (GeoTIFF,
DEFLATE, sparse blocks, overviews):

| layer | size |
|---|---:|
| WSF Evolution 1985–2015, year first built, 30 m, **all 31 years in one file** | **0.48 MiB** |
| WSF Tracker 2016–2026, epoch first built, 10 m, **all 20 epochs**, 8 island windows | **3.13 MiB** |
| WSF 2015 binary, 10 m | 1.96 MiB |
| WSF 2019 binary, 10 m | 2.46 MiB |
| GHSL built surface 2020, 3 arcsec, m² per cell | 0.83 MiB |
| **all of the above** | **8.9 MiB** |

The complete 1985–2026 timeline for the whole archipelago at native resolution is
**3.6 MiB**. The raw download cache is 893 MiB, but 311 MiB of that is the useless
Global-PCG-10 and 358 MiB the HISDAC-ES municipal tables; the rasters we actually
use total ~200 MiB. The plan's hosting argument — that no server is needed to
display this — is confirmed by measurement. **measured**

## 7. What each dataset is good for

| dataset | verdict | use it for | do not use it for |
|---|---|---|---|
| **WSF Evolution** (30 m, 1985–2015) | **GO, as "settlement detected by year"** | the 1985–2015 *settlement* extent timeline; the only annual global series | dispersed rural buildings (misses ~half the cells with a pre-1985 building, 89 % on La Gomera); "built in year X" semantics (its year trails the cadastre's); loss; comparison with 10 m products |
| **HISDAC-ES / cadastre** (100 m, 1900–2020; raw INSPIRE footprints at 10 m) | **GO** | building-level truth for the Canaries (98.5 % dated); the pre-2016 "when" layer candidate for Spain (10 m rasterisation demonstrated, §6c); a third surface series across the seam | roads and infrastructure (not in the cadastre); demolished buildings (vanish); anywhere outside Spain |
| GAIA, GISA v1, GISA-new, GISD30 (30 m Landsat, global) | **NO-GO** | GISD30 only as a cross-check | replacing WSF Evolution — none beats it on recall and precision; GAIA is flat for 25 years, GISA v1 has no Tenerife, GISA-new jumps with sensor eras (§6c′) |
| Esri / Impact Observatory annual LULC (10 m, 2017–2023) | **NO-GO** | — | anything: 285–314 km² on Gran Canaria (Dynamic-World scale), 3–12 %/yr flicker between years (§6c′) |
| **GHSL built surface** (~92 m, 1975–2020) | **GO** | surface/density; 1975–1985 context; the only pre-1985 source in hand | extent; sub-100 m detail; loss (non-decreasing by construction) |
| **WSF 2019** (10 m) | **GO, as a snapshot** | one accurate modern extent figure; validating a 10 m footprint | any time series with WSF 2015 |
| **WSF 2015** (10 m) | **GO, as a snapshot** | the 10 m footprint at the seam year | time series with WSF 2019 |
| **Dynamic World** (10 m) | **NO-GO** | — | anything; 2.5–6× over-count here |
| **WSF Tracker** (10 m, 2016–2026) | **GO, with a greenhouse mask** | the 2016–2026 spine; 1.11 %/yr growth is credible; passes Timanfaya; not fooled by fresh lava | splicing onto WSF Evolution without calibration; loss (growth-only); **raw totals — its "built-up" includes greenhouses and covered plantations** (analysis 11 + `docs/figures/undated_pixels_gran_canaria.png`), which our definition excludes |
| **HRL Imperviousness** | **BLOCKED** | loss rate, sealed-surface density | — (needs a free Copernicus account) |
| **HISDAC-ES** | **NOT YET FETCHED** | testing the 1985 baseline against cadastral dates | — |

## 7. Blocked — needs your account

Two datasets need a free account that must be created by a human:

- **Copernicus CLMS** (land.copernicus.eu) — HRL Imperviousness 2018/2021/2024 and
  the Built-up Change 2018–2021 layer. This is the best available answer to the
  loss question and the best independent accuracy anchor for the Canaries.
- **CNIG** (centrodedescargas.cnig.es) — CORINE 2018 for provinces 35 and 38.
  Lower priority; only a coarse sanity band.

Everything else in this document was obtained without any account.

## Reproducing

```bash
pip install -e .                                  # then the extras you need
python scripts/fetch_m0.py                        # 90 MiB, all public URLs
python scripts/analysis_01_totals.py              # per-island totals
python scripts/analysis_02_negative_controls.py   # lava control and loss test
python scripts/analysis_07_loss_rate.py           # WSF 2015 vs 2019
python scripts/analysis_10_wsf_tracker.py        # WSF Tracker, read from source.coop
python scripts/analysis_11_undated_roads.py      # undated class vs OSM roads
python scripts/analysis_12_undated_vs_crops.py   # undated class vs greenhouse/crop parcels
python scripts/analysis_13_hrl_change.py         # Copernicus Built-Up Change 2018-2021 (needs data/raw/hrl/110241/)
python scripts/analysis_08_cadastre.py           # WSF and Tracker vs the cadastre (HISDAC-ES)
python scripts/analysis_03_seam_factors.py       # per-island seam factors, greenhouse-masked
python scripts/analysis_09_sizes.py              # published-layer sizes
python docs/figures/src/m0_results.py            # the summary figure
python docs/figures/src/undated_pixels.py        # the undated-class map
```

Tables are written to `docs/figures/data/m0_*.csv`.

Sources: WSF Evolution / 2015 / 2019 © DLR (CC-BY-4.0, CC0-1.0) via
download.geoservice.dlr.de · GHS-BUILT-S R2023A © European Union, JRC (CC BY 4.0)
via jeodpp.jrc.ec.europa.eu · WSF Tracker © DLR / MindEarth / ESA GDA (CC BY 4.0)
via source.coop/mindearth/wsf · island and control boundaries © OpenStreetMap
contributors (ODbL) via Nominatim and Overpass · Dynamic World figures from the
project's own earlier notebook.
