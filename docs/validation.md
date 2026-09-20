# M3 — Accuracy assessment of the building layer

**Status: complete, 2026-09-20.** Two runs were made. The **30 m run is the
result**; the 10 m run that preceded it is kept in §9 because its failure is the
most transferable thing M3 produced.

| | 10 m run (superseded) | **30 m run (the result)** |
|---|---|---|
| assessment unit | one 10 m pixel, judged at its centre | **a 30 m square, judged anywhere inside** |
| drawn / usable | 500 / 448 | **911 / 838** |
| unsure | 10.4 % | **8.0 %** |
| effort | ≈ 2 h | ≈ 3.5 h |

Interpreter: Luca, blind to the map. Reference: IGN PNOA aerial photography
(12–25 cm per pixel) at two dates. Estimator: Olofsson et al. 2014.
Reproduce: `scripts/m3_sample.py`, `scripts/m3_score.py`, `scripts/m3_diagnose.py`.

---

## In plain words, before any numbers

**What we did.** A computer picked 911 spots at random across the Canary Islands.
For each one, Luca looked at two aerial photographs — one from 2015, one from now —
and answered a single question: *is there a building here?* He could not see what
our map said. Afterwards we compared his answers with the map's claims.

**What we learned.** The map makes four different claims, and it is not equally
good at all four.

1. **"There's a building here, from before 2015."** Almost always true — 98 times
   in 100. Trust this.
2. **"There's nothing built here."** Almost always true — 98 times in 100. Trust
   this too.
3. **"A building appeared here between 2015 and 2024."** True only about 6 times
   in 10. A third of these places already had a building in 2015. **This is the
   weakest thing on the map.**
4. **"There's a building here but we don't know its age."** True about 7 times in
   10. The other three in ten have nothing on them.

**Why claim 3 goes wrong.** Our dates come from the Spanish building register, and
we assumed the year in it means *the year the building went up*. It doesn't always.
It means *the year someone filed paperwork*. If an owner adds a floor in 2019, or
finally registers a house that was never on the books, the register says 2019 — but
the house may be from 1975. So the map shows old buildings as new ones.

**One more thing we found.** Where the map says "nothing here", it is wrong about
2 % of the time. That sounds tiny, but empty land is 95 % of the archipelago, so it
adds up. Correcting for it, roughly **463 km²** of the islands has a building
standing on it, against the **324 km²** our map shows. The missing ones are mostly
isolated buildings in the countryside that the register simply does not hold — we
checked eleven of them and ten are absent from the register entirely.

**How much to trust all this.** Every number above has a margin of error, given in
§3. The important one: "6 times in 10" could really be anywhere from 5.4 to 7.4.
It is definitely the weakest claim on the map, and we cannot pin it more tightly
than that without more work.

**One limit worth stating twice.** All of this is about **30-metre squares**, not
individual buildings. We can say the map is right about where buildings are to
within 30 metres. We cannot say it is right to within 10 metres — §9 explains why
nobody could, using aerial photographs.

---

## 0. What was measured, and what was not

This covers **`buildings-dated`** — the cadastral building layer, the primary
pre-2016 timeline (decision M1.1) and the layer the viewer's time slider is drawn
from. It says nothing about the satellite settlement layers, the density layers or
the loss layer. It is archipelago-wide; no island has enough points for its own
number.

"Built" means **a roofed structure**. The cadastre rasterises `building.gml` and
nothing else — no roads, and its open-air structures are in a file we do not read.
Scoring a road or a paved yard as built would measure the *definition* rather than
the accuracy.

**The unit is a 30 m square, so every number below is about 30 m squares.** The
question put to the interpreter was *"is there a building anywhere inside this
square?"* and the map's claim was read the same way. This is a real limitation: the
assessment says the map is right about **where buildings are to within 30 m**, not
to within 10 m. §9 explains why a finer unit is not measurable with aerial
photography.

---

## 1. The design

The four strata are the four claims the map makes about a 30 m cell, taking the
oldest claim inside it — which mirrors the paint order the layer was built with:

| stratum | the map's claim about the cell | km² | share |
|---|---|---:|---:|
| `not_built` | no building anywhere in it | 7,115.20 | 95.53 % |
| `built_before_2015` | holds a building that stood by 2015 | 324.41 | 4.36 % |
| `new_2015_2024` | holds a building that appeared 2015–2024, **and nothing before** | 5.90 | 0.08 % |
| `undated` | holds a building, year unknown | 2.89 | 0.04 % |

Note `built_before_2015` reads 324 km² here against 100 km² in the 10 m run. These
are **not the same quantity**: 324 km² is the area of 30 m cells *containing* a
building, 100 km² is building footprint. Extent is not surface — the distinction
that runs through this whole project. Do not quote one against the other.

**Allocation.** 100 usable in each rare class, **500 in `not_built`**. The rare
classes are bounded by their own point count and gain almost nothing beyond 100.
The error-adjusted *area* is decided entirely by `not_built`, which is 95.5 % of
the land: at 557 points each one carries **12.8 km²**. Raising only that stratum is
what made the area figure publishable for the first time.

---

## 2. The confusion matrix

Rows are what the map says, columns what the photographs show.

| map says | n | photos: built ≤2015 | photos: new 2015–24 | photos: no building |
|---|---:|---:|---:|---:|
| `built_before_2015` | 104 | **102** | 0 | 2 |
| `new_2015_2024` | 92 | 30 | **59** | 3 |
| `not_built` | 557 | 11 | 0 | **546** |
| `undated` | 85 | 60 | 1 | 24 |

`undated` has no diagonal cell: "built, year unknown" is a statement about our
knowledge, not something a photograph can return. It is read separately in §6.

---

## 3. The result

**Overall accuracy: 98.0 %.** Reported because it is conventional, and close to
meaningless: it is dominated by the 95.5 % of land that is empty and correctly
called empty. Never quote it alone.

| class | user's accuracy | producer's accuracy | mapped km² | error-adjusted km² |
|---|---|---|---:|---:|
| `built_before_2015` | **98.1 % ± 2.7** | 68.8 % ± 12.2 | 324.41 | **462.65 ± 82.74** |
| `new_2015_2024` | **64.1 % ± 9.9** | 99.1 % ± 1.7 | 5.90 | **3.82 ± 0.59** |
| `not_built` | **98.0 % ± 1.2** | 99.9 % ± 0.1 | 7,115.19 | 6,981.93 ± 82.74 |

- **User's accuracy** answers *"of what we call X, how much truly is X?"* — the
  question a reader of the map asks. It comes from that class's own points alone,
  so it is a plain binomial (Olofsson eq. 6).
- **Producer's accuracy** answers *"of what truly is X, how much did we find?"*. It
  mixes every stratum, so it carries the big stratum's rare errors at full area
  weight (eq. 7).

### The error-adjusted area is publishable this time

**462.65 ± 82.74 km²** of 30 m cells hold a building, against **324.41 km²** the
map marks. The interval is 380–545 and does **not** contain the mapped value, so
the omission is real rather than noise.

It also lands where it should on the ladder of definitions: above WSF Evolution's
settlement extent (376.9 km², which misses dispersed rural buildings) and below
CORINE's artificial surface (469.5 km², which includes quarries and sports
grounds). A number that had come out at 200 or at 900 would have been a red flag.

The 10 m run could not produce this: its interval was ±201 km² on 3 points. The
difference is 557 points in `not_built` instead of 123.

---

## 4. Finding: the register misses isolated rural buildings

Producer's accuracy of 68.8 % means roughly **three in ten 30 m cells that hold a
building are not in the map at all**. Eleven sampled points drive it, and they were
checked against the raw INSPIRE feed rather than our raster:

- **10 of the 11 have no cadastral building within 60 m** in the register itself.
  This is not our rasterisation losing small buildings; the Catastro does not hold
  them.
- **7 of the 11 are more than 200 m from anything the map calls built** — open
  country, not the edge of a town.
- All 11 show a building in **both** photographs, so they are old structures, not
  recent construction the register has yet to catch up with.
- They cluster in the sparse rural islands: 4 on Fuerteventura, 3 on Tenerife, 3 on
  Gran Canaria, 1 each on La Palma and La Gomera.

**The honest caveat.** The interpreter was asked for *roofed structures*, and the
Catastro registers *buildings for tax purposes*. An animal pen, a water-tank
housing, a tool shed or a ruin can satisfy the first and never appear in the
second. Part of this 30 % is a definitional gap rather than an error, and this
sample cannot say how much. What it does establish is that the cadastral layer is a
**floor** on rural building presence, which is what the dataset roster already said
qualitatively.

---

## 5. Finding: a third of "new construction" was already standing

Of the cells the map calls new building 2015–2024:

- **64.1 % ± 9.9** truly is new construction in that window,
- **32.6 %** (30 of 92) already had a building in 2015 — a **dating** error,
- **3.3 %** (3 of 92) shows no building at either date.

**This survived the redesign, which is what makes it trustworthy.** In the 10 m run
the same finding read 29 %, and there were three ways to explain it away: the point
might sit on a roof edge; the cell might be infill beside an older building; the
interpreter might be anchoring. The 30 m design removes the first two by
construction — a `new_2015_2024` cell is one where the register holds **nothing at
all within 30 m** dated before 2015. The finding got *larger*, not smaller.

One route remains and was measured: a tall roof just outside the square leaning in.
Of the 30 disputed cells, **8 have a pre-2015 building within 20 m** (against 1 of
59 in the agreeing control). Even charging all eight to roof lean leaves **22 of 92
= 24 %** with no available explanation but a wrong date. So the range is
**24–33 %**.

**The cause is re-registration, not misdetection.** The Catastro records the year of
a *declaration*, and a renovation, extension or the regularisation of a previously
unregistered building creates or resets it. The roster already listed this
qualitatively ("renovation can reset the date"); M3 puts a number on it.

**This is the failure mode no automated gate could have found.** Every gate in M0
and M2 compares our totals against other products' totals, and a building given the
wrong year is still a building in all of them.

**Consequence for the viewer.** The time slider's most eye-catching content —
recent growth — is its least reliable layer, and the "about the data" page says so.

---

## 6. Finding: the undated class is about a quarter empty

`undated` is pixels the map knows are built but cannot date — 43 % of the 2016
footprint. Decision 15 created a dedicated stratum because M0 could not explain it.

Of 85 usable points: **60 hold a building (70.6 %)**, **24 show nothing at either
date (28.2 %)**, 1 is new construction.

The 10 m run put the empty share at 42.5 %; at 30 m it is 28.2 %. Both are large.
The difference is the boundary problem — at 10 m an undated pixel beside a building
often read as empty.

**An independent product agreed, in the 10 m run where it was tested.** Copernicus
Imperviousness — different sensors, different method, never shown to the
interpreter — read a median **91 %** sealed where the photographs found a building
and **3 %** where they did not.

**M0's greenhouse hypothesis is refuted.** Radar reads plastic as structure, so
greenhouses were the leading candidate. **Zero of 107 undated points in the 10 m
run fell inside a mapped greenhouse parcel**, on either side of the split. What the
class is remains unexplained; it is now at least measured.

---

## 7. What the classes cost to judge

| stratum | unsure rate |
|---|---:|
| `undated` | 25.4 % |
| `new_2015_2024` | 19.3 % |
| `built_before_2015` | 8.8 % |
| `not_built` | 2.1 % |

Worth recording because it went the wrong way: on the rare classes the 30 m
question is **harder** to answer than the 10 m one (undated 10 % → 25 %). A larger
square contains more things, and more of them are debatable — a ruin, a wall, a
half-demolished shed. The overall rate still fell, from 10.4 % to 8.0 %, only
because `not_built` now dominates the count.

A class the interpreter cannot judge is itself a finding: the two classes that are
hardest to see are the two the map is least reliable about.

---

## 8. Effort

**About 2 hours for the 10 m run (500 points) and about 3.5 for the 30 m run
(911).** Reported by the interpreter; the tool now stamps each judgement, so the
next run measures it directly.

**Every estimate this project made was far too high.** The original plan said 650
points and ≈ 4 person-days; the redesign said 500 points and ≈ 12.5 hours; the
truth was ≈ 2 hours — the final estimate was still **6× too pessimistic**. The
cause: 1–2 minutes per point is right for a *hard* point, but two-thirds of the
sample is open countryside dismissed in a second, and the tool auto-advances.

Recorded because it changed a decision. The 500-point `not_built` stratum that made
§3 publishable had been dismissed as "≈ 50 hours" on the old estimate. It cost
about 90 minutes.

---

## 9. Why the first run was rebuilt — the transferable lesson

The 10 m run measured the wrong thing, and the reason generalises to any raster
accuracy assessment.

**The median Canary cadastral building is 121 m². The pixel is 100 m².** 81 % of
buildings are two pixels or smaller, so a built pixel has essentially **no
interior** — it is all edge. Measured on the drawn sample:

| stratum | points sitting directly on a class boundary |
|---|---:|
| `built_before_2015` | 87 % |
| `new_2015_2024` | 78 % |
| `undated` | 64 % |
| `not_built` | 1.6 % (median 410 m from one) |

So for three of four strata the exercise was not testing *presence*. It was testing
**sub-pixel boundary placement** — against a photograph showing a **roof** while the
map stores a **ground footprint**. Orthorectification corrects terrain, not building
height, so a tall roof sits several metres from its own footprint. At that scale the
two sources are not describing the same object and no interpreter can reconcile them.

**The rule: the assessment unit must be larger than the combined geolocation error
of the map and the reference.** With ~5 m roof displacement and 1.2-pixel buildings,
10 m is below that floor; 30 m is above it.

The 10 m run was also scored with a one-pixel tolerance (`--tolerance-px 1`, a point
counts as agreeing if the map holds the reference class within one pixel) to bound
the damage. That gave user's accuracy of 94.7–97.3 % for built-before-2015 and
**58.5–76.4 % for new construction**. The 30 m run's 64.1 % falls inside that band,
which is a small but real check that the two designs are measuring the same world.

**Three checks that failed, kept because a rejected instrument is evidence:**

1. *WSF Evolution, 30 m, unmatched.* Said 33 % of new-class pixels already had
   settlement in 2015 — uninterpretable, because a new infill building sits inside
   an existing cluster regardless.
2. *WSF 2015, 10 m, density-matched* (`scripts/m3_dating_independent.py`). Returned
   a **160 % mixture share, which is impossible**. Conditioning on the density of
   pre-2015 buildings makes the groups non-comparable: an old pixel in a sparse band
   is an isolated rural building, exactly what WSF detects worst.
3. *Cadastral neighbours, 84 % vs 34 %.* Suggestive, but it cannot separate "the
   interpreter read a real old building" from "the interpreter misread a
   neighbouring old building in a dense block" — both produce the same number.

None of these was needed in the end. **The 30 m redesign answered by construction
what the indirect tests could not answer at all**, which is the general lesson:
fix the measurement rather than modelling your way around it.

---

## 10. What this does and does not license

**You may say:** of the 30 m cells SensiSat marks as holding a building from before
2015, 98.1 % ± 2.7 do; of those marked new construction 2015–2024, 64.1 % ± 9.9 do;
of those marked empty, 98.0 % ± 1.2 are. Correcting for both kinds of error, about
**462.65 ± 82.74 km²** of the archipelago's land sits in a 30 m cell holding a
building, against 324.41 km² the map marks.

**You may not say:** how much *built surface* the Canary Islands contain. Cells
containing a building is an extent measure and saturates; it is not square metres of
roof. The cadastral footprint total (100.3 km²) is the surface measure, and it was
not validated by this exercise.

**Scope:** the cadastral building layer, archipelago-wide, at 30 m. Not the
satellite settlement layers, not density, not loss, and not per-island.
