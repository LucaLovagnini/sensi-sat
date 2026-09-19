# Design — joining two urban time series at the 2015/2016 seam

Status: proposal, 2026-09-19. Grounded in published methods; the parts that are our own
choices are marked as such. Plain-language definitions are in `docs/concepts.md`.

## 1. The problem in one paragraph

SensiSat's timeline is carried by two datasets that meet at one point in time. Before
2015: **WSF Evolution** (DLR), 30 m pixels, Landsat, one value per pixel = year first
seen built. After July 2016: **WSF Tracker** (DLR + MindEarth), 10 m pixels,
Sentinel-1/2, one value per pixel = half-year first seen built. At the join they
disagree about how much is built — 376.9 km² vs 276.1 km² for the archipelago — and,
more importantly, about *which land* is built. Glued naively, the map would show a
27 % collapse in urban area between 2015 and 2016 that never happened. This document
decides how the join is made.

## 2. What we measured (Milestone 0, `docs/data-evaluation.md`)

- The 27 % gap is two opposite effects: pixel size (30 m → 10 m shrinks extent ÷ 2.27)
  and definition (Tracker counts more: × 1.66). They partly cancel archipelago-wide
  and will not cancel the same way per island (definitional ratio 1.12× to 2.02×).
- **43 % of Tracker's 2016 footprint (115 km²) lies on land WSF Evolution never
  flagged in any year** — 57 % on Gran Canaria, 48 % on Tenerife, 68 % on La Palma.
  Only 57 % of Tracker's baseline can inherit a year from Evolution at all.
- Both products are growth-only by construction; neither can express loss.
- GHSL (surface, 1975–2020) spans the seam with a single method. Copernicus HRL
  (2006–2024, once downloaded) does too, and publishes an explicit "technical vs
  real change" flag between its own releases.

## 3. What the literature and the producers actually do

Six practices, each with a source we read:

**P1 — Do not derive change by subtracting independently produced maps.** The CEOS
Land Product Validation protocol (v1.1, 2025) states that deriving change from
comparison of maps "is not recommended, as overlapping errors in the annual maps may
exceed real land cover change in magnitude", and that "when comparing or harmonizing
land cover maps … it is important to harmonize the legends", because "differences in
employed land cover class definitions can lead to substantial differences between the
maps". Serra, Pons & Saurí (2003) built a protocol for exactly our case — comparing
classified maps from *different sensors* (MSS 1970s vs TM 1990s) — and require
accounting for "classification accuracies, landscape fragmentation, planimetric
accuracies, pixel sizes and grid origins" before any comparison is trusted.
*Consequence:* change statistics are computed only **within** one internally
consistent series, never across the seam by pixel subtraction.

**P2 — Multi-decade urban series are built from one recent, trusted footprint,
working backwards, with a monotonic rule.** WSF Evolution: "all pixels categorized as
non-settlement in the WSF2015 … are excluded a priori", years assigned backwards,
"at least 7 clear … observations". GHSL R2023A: the process "can only decrease the
amount of built-up surface going from recent to past epochs". GAIA (Gong et al. 2020):
"temporally consistent (i.e. from non-urban to urban monotonically)". GISD30 (Zhang
et al. 2022): "the irreversibility assumption to remove illogical transitions", plus a
3×3×3 spatiotemporal consistency filter. *Consequence:* the industry does not "join"
two maps; it anchors to one footprint and assigns dates within it.

**P3 — Sensor transitions are handled by calibrating over an overlap, at the input
level where possible.** Landsat 7→8 (Roy et al. 2016, ~29 million paired
observations), the Harmonized Landsat–Sentinel product (Claverie et al. 2018), and
GISD30's linear normalisation of every Landsat generation to a 2020 reference. We
consume finished products and cannot re-run the classifier, so the transferable idea
is: **measure the offset over an overlap and carry it as metadata**, not to invent
pixels.

**P4 — Compare areas only at a common support.** Pixel size alone changes measured
extent by > 2× here; intercomparison work (Tsendbazar et al.; the CEOS protocol's
treatment of continuous "built-up surface" fields) aggregates to a common grid before
comparing. *Consequence:* cross-product statistics use the 100 m **fraction grid**.

**P5 — Validate change with strata per epoch and reference data at both dates.** CEOS
LPV: "for multi-year land cover maps, individual mapped years or epochs can be used as
map strata", with error-adjusted area and 95 % confidence intervals. GISD30 validated
with strata "impervious surfaces before 1985, and expanded impervious surfaces during
1985–1990, 1990–1995 …".

**P6 — When a producer's own method changes between releases, publish the break, do
not hide it.** Copernicus HRL ships "Change Support layers … providing the classes of
decreased and increased built-up due to **technical change (as opposed to real
change)**" for 2018–2021. That is a producer facing our exact problem and choosing
transparency over a smoothed series.

## 4. Options considered

| | mechanism | backed by | verdict |
|---|---|---|---|
| A | **Two eras, explicit seam.** Slider works within each era; crossing 2015/16 is a visible method-change event. No cross-seam pixel differences. | P1, P6 | **Adopt** as the baseline behaviour |
| B | **Drape years onto Tracker's 10 m footprint.** Each Tracker pixel with epoch 1 inherits the year of the WSF Evolution pixel it sits in. | P2 (DLR's own recipe) | **Adopt, partially**: works for the 57 % that has a year; the other 43 % becomes an explicit class, not a guess |
| C | **Fraction grid + per-island offset as metadata** for statistics; GHSL/HRL as the single-method bridge for long-run trends. | P3, P4 | **Adopt** for all numbers that cross the seam |
| D | **Scale Evolution to Tracker's level** (multiply by a per-island factor so the curve is continuous). | chain-linking in economics; weak for maps | **Reject** for pixels — it manufactures history. Acceptable only in an aggregate chart, disclosed |
| E | **Spatial infill of unknown years** (give an orphan pixel the year of the nearest dated pixel). | none found for urban products | **Reject for v1**; revisit only after M3 tells us what the orphans are |

## 5. The mechanism (recommended)

**5.1 Two eras as first-class objects.** The catalog declares `era-a` (WSF Evolution,
1985–2015, 30 m) and `era-b` (WSF Tracker, 2016-07–2026-01, 10 m). Every statistic and
every change map carries an `era` field. There is no function anywhere that subtracts
an era-b mask from an era-a mask (P1).

**5.2 The seam is a published object, not a join.** For each island the catalog stores
a `seam` record: WSF Evolution 2015 extent, WSF 2015 extent, Tracker epoch-1 extent,
GHSL surface 2015 and 2020, the resolution factor and the definitional factor, and the
overlap share measured in section 2 (P3, P6). The viewer reads it to render the
transition honestly — a marked discontinuity with the two figures side by side, the
way Copernicus flags technical change — rather than a smooth line.

**5.3 One 10 m "history" layer, with three provenance classes.** For the slider's fine
view of the past we publish Tracker's footprint with, per pixel:

| class | meaning | share (5 islands) |
|---|---|---:|
| `dated` | year from the WSF Evolution pixel it falls in (1985–2015) | 57 % |
| `pre-2016, undated` | Tracker says built by 2016-07; Evolution never flagged it | 43 % |
| `epoch` | Tracker epochs 2–20 (2017-01 … 2026-01) | growth since 2016 |

plus a provenance band so the UI can badge each pixel's source. The undated class is
drawn in its own colour and appears only when the slider reaches 2016. This is P2
applied honestly: the recipe DLR used, minus the part where we would have to invent
data. *(Our design choice; the class shares are measured.)*

**5.4 Numbers that must cross the seam use a bridge, not a splice.** Long-run growth
1985→2026 is reported from products that span the seam with one method: GHSL built
surface (1975–2020, per P2 it is internally consistent) and, once downloaded,
Copernicus Imperviousness Density (2006–2024). WSF gives the fine geography within an
era; the bridge gives the trend across it (P3, P4). Where a WSF-only figure across the
seam is unavoidable it is computed on the 100 m fraction grid and shown with the
per-island offset and its uncertainty (P4).

**5.5 Validation stratified by era and by the undated class.** Strata: built before
1985 · dated 1985–2015 · undated pre-2016 · each Tracker epoch group · never built.
Reference at two dates from PNOA orthophotos; error-adjusted areas with 95 % CI (P5).
The `undated` stratum answers the open question "what are these 115 km²?" — the
hypothesis, from Tracker's input list (OpenStreetMap/Facebook roads, Microsoft/Google
building footprints), is roads and dispersed structures that Landsat spectral indices
never picked up.

**5.6 Make the pre-2016 era replaceable.** DLR's 2025 roadmap lists "WSF evolution
1985 – present" as a next step. If that ships, the seam disappears at source. The
adapter pattern keeps era-a a plug-in so swapping it is one module, not a rewrite.

## 6. What stays open for Luca

1. Viewer behaviour at the seam — explicit two-era transition (5.2) vs a single
   blended slider that hides it.
2. Whether the `pre-2016, undated` class is shown by default, shown on request, or
   held back until M3 says what it is.
3. Whether to spend a manual-sampling stratum on the undated class in M3 (≈ 100 points,
   ~2 hours), which is the only way to learn what those 115 km² are.

## Sources read for this design

WSF Evolution method and license — https://geoservice.dlr.de/web/datasets/wsf_evo ·
WSF Tracker inputs, training ("WSF2019 reference ~300K settlements samples"), validation
and roadmap — Marconcini, Metz-Marconcini, Gorelick, ESA LPS 2025,
https://lps25.esa.int/lps25-presentations/presentations/956/_956.pdf · WSF Tracker
encoding — array metadata at https://source.coop/mindearth/wsf · CEOS WGCV LPV *Land
Cover and Change Map Accuracy Assessment and Area Estimation Good Practices Protocol*
v1.1 (Tyukavina, Stehman, Foody et al., 2025),
https://ceos.org/document_management/Working_Groups/WGCV/CEOS_WGCV_LPV_Land_Cover_protocol_Nov2025_V1.1.pdf ·
Serra, Pons & Saurí (2003) *Post-classification change detection with data from
different sensors: some accuracy considerations*, Int. J. Remote Sensing 24(16),
https://www.tandfonline.com/doi/abs/10.1080/714110283 · Zhang et al. (2022) GISD30,
ESSD 14, https://essd.copernicus.org/articles/14/1831/2022/ · Gong et al. (2020) GAIA,
Remote Sensing of Environment 236, https://ui.adsabs.harvard.edu/abs/2020RSEnv.23611510G/abstract ·
GHSL Data Package 2023 (JRC) — quoted in `docs/concepts.md` §6 · Roy et al. (2016) and
Claverie et al. (2018) via https://www.sciencedirect.com/science/article/pii/S0034425718304139 ·
Copernicus HRL Imperviousness change and support layers — CLMS catalogue listing,
https://land.copernicus.eu/en/products/high-resolution-layer-imperviousness.
