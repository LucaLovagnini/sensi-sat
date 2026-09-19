# Milestone 0 — dataset evaluation for the Canary Islands

What this is: a measured, reproducible answer to "which open datasets can SensiSat
trust, and where do they fail?" Nothing here is taken on faith from a dataset's
documentation; every number was computed locally from the downloaded files.

Run date: 2026-09-19. Reproduce with `python scripts/fetch_m0.py` then the
`scripts/analysis_*.py` files. Downloads are recorded with size and SHA-256 in
`data/raw/manifest.json` (90 MiB total, 48 files).

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
4. **No product available without a login can measure demolition.** WSF 2019 is a
   strict superset of WSF 2015: measured loss is 0.02 km² across the entire
   archipelago, i.e. zero. The loss question is still open.
5. **Extent and surface disagree in *opposite directions* depending on density** —
   the cleanest empirical demonstration of the distinction so far (section 3).
6. **The 1985 baseline problem is real but island-specific**, and much smaller than
   feared: 72 % archipelago-wide, but ranging from 14 % to 90 % by island in a
   pattern that matches known development history (section 4).

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
- **The loss question needs a source we do not have.** Candidates, in order of
  preference: Copernicus HRL Built-up Change 2018–2021 (official gain *and* loss
  layer — **needs a free CLMS account**), Esri/Impact Observatory annual LULC via
  Microsoft Planetary Computer (2017–2023, no login), or WSF Tracker's own
  biannual series tested against the Tajogaite lava.

## 6. What each dataset is good for

| dataset | verdict | use it for | do not use it for |
|---|---|---|---|
| **WSF Evolution** (30 m, 1985–2015) | **GO** | the 1985–2015 extent timeline; the only annual series we have | anything on Gran Canaria/Tenerife before 1985; loss; comparison with 10 m products |
| **GHSL built surface** (~92 m, 1975–2020) | **GO** | surface/density; 1975–1985 context; the only pre-1985 source in hand | extent; sub-100 m detail; loss (non-decreasing by construction) |
| **WSF 2019** (10 m) | **GO, as a snapshot** | one accurate modern extent figure; validating a 10 m footprint | any time series with WSF 2015 |
| **WSF 2015** (10 m) | **GO, as a snapshot** | the 10 m footprint at the seam year | time series with WSF 2019 |
| **Dynamic World** (10 m) | **NO-GO** | — | anything; 2.5–6× over-count here |
| **WSF Tracker** (10 m, 2016–2026) | **UNTESTED** | — | — (next priority; the Tajogaite test is ready for it) |
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
```

Tables are written to `docs/figures/data/m0_*.csv`.

Sources: WSF Evolution / 2015 / 2019 © DLR (CC-BY-4.0, CC0-1.0) via
download.geoservice.dlr.de · GHS-BUILT-S R2023A © European Union, JRC (CC BY 4.0)
via jeodpp.jrc.ec.europa.eu · island and control boundaries © OpenStreetMap
contributors (ODbL) via Nominatim and Overpass · Dynamic World figures from the
project's own earlier notebook.
