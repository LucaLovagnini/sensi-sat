# M3 — Accuracy assessment of the building layer

**Status: complete, 2026-09-20.** 500 points drawn, 500 judged, 448 usable.
Interpreter: Luca, blind to the map. Reference: IGN PNOA aerial photography
(12–25 cm per pixel) at two dates. Estimator: Olofsson et al. 2014.
Reproduce with `scripts/m3_score.py` and `scripts/m3_diagnose.py`.

---

## 0. What was measured, and what was not

This assessment covers **`buildings-dated`** — the cadastral building layer, which
is the primary pre-2016 timeline (decision M1.1) and the layer the viewer's time
slider is drawn from. It says nothing about `settlement-era-a/b`,
`covered-agriculture`, `density-current`, `density-trend` or `loss-events`.

"Built" throughout means **a roofed structure**, not "any artificial surface". The
cadastre rasterises `building.gml` and nothing else: it holds no roads, and its
open-air structures are in a file we do not read. Scoring a road or a paved yard as
built would measure the *definition* rather than the accuracy — it would report an
omission against a map that never claimed the feature.

Partial cover was judged **at the centre of the square**, because that is the rule
the map was drawn by: `rasterize(..., all_touched=False)` marks a pixel built when
a footprint covers its centre point, not when it merely overlaps the pixel.

---

## 1. The design

The four strata are the four claims the map makes about a place. Their areas
across all eight islands:

| stratum | the map's claim | km² | share of land |
|---|---|---:|---:|
| `not_built` | nothing is built here | 7,344.65 | 98.60 % |
| `built_before_2015` | a building stood here by 2015 | 100.72 | 1.35 % |
| `new_2015_2024` | a building appeared 2015–2024 | 2.23 | 0.03 % |
| `undated` | something is built, year unknown | 1.21 | 0.02 % |

**Why the sample is stratified.** A simple random sample of 500 points would put
*one third of one point* on new construction. Drawing separately per class and
re-weighting afterwards by area is what makes the rare classes measurable at all.

**Why 100 per class.** Olofsson eq. 13 asks for only **101 points in total** to put
±2 % on *overall* accuracy — because 98.6 % of the land is empty and easy, so
overall accuracy is nearly free and is the least interesting number here. What
costs points is **per-class** accuracy, whose precision depends on the count in
that class and not at all on its area. Hence 100 usable per class, inflated for
points the photographs cannot settle → **500 drawn**.

**The inflation was set at 20 % and the measured unsure rate was 10.4 %**, so 448
points were usable against a design target of 400.

**The interpreter was blind.** Point ids are opaque (`p00267`), the four strata are
interleaved in the labelling order, and no map layer is shown in the tool. An
earlier draft leaked the stratum into the id (`undated-5102-3187`) and was fixed
before any labelling began.

---

## 2. The confusion matrix

Rows are what the map says, columns what the photographs show.

| map says | n | photos: built ≤2015 | photos: new 2015–24 | photos: not built |
|---|---:|---:|---:|---:|
| `built_before_2015` | 113 | **107** | 1 | 5 |
| `new_2015_2024` | 106 | 31 | **62** | 13 |
| `not_built` | 123 | 3 | 0 | **120** |
| `undated` | 106 | 61 | 0 | 45 |

`undated` has no diagonal cell: "built, year unknown" is a statement about our
knowledge, not a class the photographs can return. It is read separately in §5.

---

## 3. The headline numbers

**Overall accuracy (area-weighted): 97.5 %.** This number is nearly meaningless
and is reported only because it is conventional: it is dominated by the 98.6 % of
the archipelago that is empty and correctly called empty. Do not quote it alone.

The numbers that matter are per class. **User's accuracy** answers *"of the area we
call X, how much truly is X?"* — the question a reader of the map asks.

| class | user's accuracy | producer's accuracy |
|---|---|---|
| `built_before_2015` | **94.7 % ± 4.2** | 34.6 % ± 25.2 |
| `new_2015_2024` | **58.5 % ± 9.4** | 59.4 % ± 47.4 |
| `not_built` | **97.6 % ± 2.7** | 99.9 % ± 0.1 |

**User's accuracy is solid; producer's accuracy is not.** The two are estimated
differently and it is worth knowing why:

- **User's accuracy** for a class comes from that class's own points alone. The
  stratum weight cancels, so it is a plain binomial over ~110 points (Olofsson
  eq. 6). It does not depend on the vast `not_built` stratum in any way.
- **Producer's accuracy** asks *"of the land that truly is X, how much did we
  find?"* — which requires knowing how much X is hiding in the other strata. It
  therefore inherits the big stratum's rare errors at full area weight (eq. 7).

### The error-adjusted areas are NOT publishable

| class | mapped km² | error-adjusted km² | 95 % CI |
|---|---:|---:|---:|
| `built_before_2015` | 100.72 | 275.86 | ±201.09 |
| `new_2015_2024` | 2.23 | 2.19 | ±1.76 |
| `not_built` | 7,344.65 | 7,170.75 | ±201.08 |

The interval on the first row spans 75 to 477 km². The point estimate rests on
**three points** in the `not_built` stratum — each one carries 7,344.65 ÷ 123 =
**59.7 km²** of the estimate. Three points cannot locate a 2 % omission rate across
7,345 km².

Getting that interval down to ±50 km² needs about **2,000 points in the `not_built`
stratum alone**, which is roughly 50 hours of labelling for the least interesting
number in the report. The design chose per-class accuracy instead, deliberately.
**So: publish user's accuracy, do not publish error-adjusted area.**

### What the three points actually are

`scripts/m3_diagnose.py` measures how far each disagreement sits from the nearest
pixel the map calls built. Inside the built strata every point reads 0.0 m, which
is the check that the sampling is sound. The three `not_built` disagreements do
not:

| point | nearest built pixel | nearest cadastral footprint | reading |
|---|---:|---:|---|
| `p00478` | 8.8 m | **1.3 m** (a 1950 building) | the crosshair is a metre outside a registered footprint |
| `p00466` | 13.2 m | **0.8 m** (a 3,012 m² building, 2008) | same |
| `p00431` | 53.2 m | none within 30 m | **a genuine absence** |

Two of the three are sub-pixel boundary calls. The map is right by its own rule —
the footprint does not cover that pixel's centre — but no interpreter can resolve
one metre on an aerial photograph when roof lean alone displaces a tall building by
several metres. The third is a real building the register does not hold.

**These points are not discarded.** Re-labelling points because the resulting
number looks better is how an honest estimate becomes a chosen one. They are
reported as they were judged, and the conclusion is that the *area* estimate is too
fragile to publish — not that the labels were wrong.

---

## 4. Finding: the new-construction class is 58.5 % reliable

Of the area the map calls new building 2015–2024:

- **58.5 % ± 9.4** truly is new construction in that window,
- **29.2 %** (31 of 106) already had a building in 2015 — a **dating** error,
- **12.3 %** (13 of 106) has no building at either date.

The dating errors are the important half, and they are the failure mode **nothing
in M0 or M2 could have detected**: every automated gate compares our totals against
other products' totals, and a building given the wrong year is still a building in
every one of those totals.

**The cause is almost certainly re-registration, not misdetection.** The Catastro
records the year of a *declaration* — and a renovation, extension or the
regularisation of a previously unregistered building creates or resets that year.
This was already listed as a caveat in the dataset roster ("renovation can reset
the date"); M3 puts a number on it.

### Two independent confirmations, neither of which uses the labels

The 58.5 % is computed *from* the interpretation, so on its own it cannot rule out
the interpreter simply being wrong. Two checks were run that do not depend on it.

**1. The cadastre corroborates the disputed calls, 84 % against 34 %.** A building
covers many 10 m pixels. If only part of it were re-declared in 2019, the
neighbouring pixels should still carry their original older year.

| | n | has a pre-2015 building within 30 m |
|---|---:|---:|
| points called "already built in 2015" (map said new) | 31 | **84 %** |
| points where interpreter and map agreed it was new | 62 | **34 %** |

Where the interpreter said a building already stood in 2015, the cadastre's own
neighbouring pixels usually say so too. This also rules out **anchoring** — the
known photo-interpretation bias where seeing a building in the later image makes
the reader "see" it in the earlier one — because anchoring would produce disputed
calls indistinguishable from the control group, not a 50-point gap.

**2. An independent satellite product sees the same thing, archipelago-wide.** WSF
Evolution is made by DLR from Landsat imagery, ends in 2015, and knows nothing
about the cadastre. Measured over **every** pixel in the layer, not the sample:

| the cadastre says | had WSF settlement by 2015 | pixels |
|---|---:|---:|
| new 2016–2024 | **33.1 %** | 27,288 |
| built by 2015 | 59.5 % | 1,144,697 |
| nothing built | 1.2 % | 83,282,259 |

Read the second and third rows as the scale: 59.5 % is WSF's recall ceiling — the
most it ever detects of buildings that genuinely existed — and 1.2 % is how often
undeveloped land sits inside a settlement cluster anyway.

If a fraction *f* of the "new" class was in fact already built by 2015, then
0.595·*f* + *b*·(1−*f*) = 0.331, where *b* is the background rate for genuinely new
buildings. At *b* = 1.2 % that gives *f* ≈ **55 %**; allowing generously for infill
next to existing towns at *b* = 10 % gives ≈ **47 %**, and at a very generous
*b* = 20 %, ≈ **33 %**.

**Every one of those is worse than the interpreter's 29 %.** Two independent
sources, one of them using no labels at all, both say the dating problem is real
and if anything larger than the manual sample found. The interpretation was, if
biased at all, biased *conservatively*.

**Two alternative explanations tested and rejected:**

- *The reference imagery might predate the building.* If so the failures would
  bunch in 2023–24. They do not: the 31 dating errors spread across 2016 (1),
  2017 (4), 2018 (2), 2019 (8), 2020 (4), 2021 (3), 2022 (3), 2023 (2), 2024 (4),
  and the 13 empty points across 2016–2024 with only 2 in 2024.
- *The errors might come from one broken municipal feed.* At 102 points three of
  five clustered within 2 km, which looked systematic. At full sample the errors
  are spread across islands and years, so the clustering was noise.

**Consequence for the viewer.** The time slider's most interesting content — recent
growth — is the least reliable thing on the map. The "about the data" page must say
so, and the figure to quote is user's accuracy, 58.5 % ± 9.4.

---

## 5. Finding: 42 % of the undated class has no building

The `undated` class is pixels the map knows are built but cannot date — 43 % of
the 2016 footprint. Decision 15 created a dedicated stratum for it because M0
could not explain what it was.

Of 106 usable points: **61 show a building (57.5 % ± 9.4)** and **45 show nothing
at either date (42.5 % ± 9.4)**.

**An independent product confirms both halves.** Copernicus Imperviousness measures
*sealed* ground at 10 m, from different sensors by a different method, and was
never shown to the interpreter:

| undated points where… | n | median Copernicus sealing |
|---|---:|---:|
| the photos show a building | 62 | **91 %** |
| the photos show nothing | 45 | **3 %** |

Two independent sources agree on both sides of the split. That is much stronger
evidence than either alone, and it also validates the interpretation rules.

**M0's greenhouse hypothesis is refuted.** Radar reads plastic as structure, and
greenhouses were the leading candidate. **Zero of the 45 empty points — and zero of
the 62 built points — fall inside a mapped greenhouse parcel.** Consistent with
M0's own observation that 58–91 % of the undated class sits outside any farm
parcel. What the 42 % is remains unexplained; it is now at least *measured*.

**Consequence.** The undated class is already drawn in its own colour and hidden
from the change view. It now also needs a stated reliability: roughly two in five
undated pixels have nothing on them.

---

## 6. What the empty class gets right

`not_built` has a user's accuracy of **97.6 % ± 2.7**: where the map says nothing is
built, the photographs agree 120 times in 123. Given the caveat in §3 about what
the three exceptions are, the true figure is likely better than that.

This is the class that protects the headline area figures from inflation, and it is
the one the negative-control gates have been policing all along. The manual sample
and the automated gates agree.

---

## 7. Effort

**About 2 hours**, for 500 points × 2 dates, over two sittings on 2026-09-20 —
roughly 15 seconds per point. Reported by the interpreter; the tool did not begin
stamping each judgement until after this run, so future runs will measure it
exactly rather than relying on recall.

**Every estimate this project made for the task was far too high**, and the errors
compounded: the original plan said 650 points and ≈ 4 person-days; redesigning the
sample brought it to 500 points and ≈ 12.5 hours; the truth was ≈ 2 hours. So the
final estimate was still **6× too pessimistic**.

The reason is worth recording, because it changes what is affordable later. The
estimate assumed 1–2 minutes per point, which is about right for a *hard* point.
But the strata are not evenly hard: `not_built` points are open countryside and
take a second or two, and they are a quarter of the sample. The tool also
auto-advances once both dates are answered, so an easy point costs two keystrokes
and no navigation.

**What this makes affordable.** §3 dismissed a 2,000-point `not_built` stratum as
"≈ 50 hours". At the measured rate, and given that `not_built` points are the
fastest of all, that is more like **4–6 hours** — which moves publishing an
error-adjusted area from out of the question to a normal afternoon's work. That
option should be reconsidered rather than treated as closed.

---

## 8. What this does and does not license

**You may say:** of the land SensiSat marks as built before 2015, 94.7 % ± 4.2 %
holds a building; of what it marks as new construction 2015–2024, 58.5 % ± 9.4 %
does; of what it marks as empty, 97.6 % ± 2.7 % is.

**You may not say:** how much built-up land the Canary Islands contain. That is the
error-adjusted area, and this sample cannot pin it — see §3.

**This covers the cadastral building layer only**, not the satellite settlement
layers, the density layers or the loss layer, and it applies to the archipelago as
a whole rather than to any one island: no island has enough points for its own
number.
