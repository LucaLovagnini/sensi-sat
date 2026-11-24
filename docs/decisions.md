# Decisions — the register

What this project decided, in one place, with a pointer to the evidence for each.
Written 2026-11-24, after the plan file that used to hold the numbered decisions
was lost.

**Why this file exists.** The plan lived outside the repository on purpose
(`~/.claude/plans/ok-i-think-that-purrfect-horizon.md`). It held what we
*intended*, including the options we rejected, while the repository holds what has
been verified (`scripts/plan_review.py` explains the split). But Claude Code
deletes its own session files and plans after a retention period, and nobody had
set that period. The plan was deleted at some point after the last working session
(2026-10-08), and the loss was found on 2026-11-24. The code and the documents still cite its
decisions by number ("decision 7", "decision M1.2"), so a reader following one of
those citations needs somewhere to land. A *decision* is a settled fact about the
project, not an intention, so it belongs here in the repository, where it is
reviewed and kept.

**How it was rebuilt, and how far to trust each entry.** Sources: every citation
of a decision in the code, the documents and the commit messages; the notes Claude
Code kept between sessions (outside the repository), written on 2026-09-19 while
the plan was being drafted; and Luca's own prompts from that session. Each entry
is marked:

- **confirmed** — the repository cites this decision by its number and states what
  it says, in at least one place listed under the entry.
- **number lost** — the decision is known to have been taken, but nothing that
  survives says which number it carried. Do not cite these by a number.

**This file states no figures of its own.** Each entry points to the document that
holds the measurement behind it. A copy of a number goes stale in silence
(CLAUDE.md #21), and a register that repeated the evidence would be the next
place it went stale.

Terms used below, defined once (`docs/concepts.md` has the longer versions):

- **Cadastre** (Spanish: *Catastro*): Spain's official property register. It
  records each building's footprint and the year it was built or comprehensively
  rebuilt (`docs/data-evaluation.md` §11).
- **WSF** (World Settlement Footprint, from the German Aerospace Center, DLR):
  satellite maps of where settlement is. *WSF Evolution* covers 1985–2015 from
  Landsat. *WSF Tracker* covers 2016 onward from the Sentinel radar and optical satellites.
- **GHSL** (Global Human Settlement Layer, from the EU's Joint Research Centre):
  built *surface* per cell, in epochs from 1975.
- **Copernicus HRL** (the EU's High Resolution Layers): imperviousness (how much of
  the ground is sealed) and built-up change, measured over Europe.
- **Spine**: the source that carries the main time series for a period. Other
  sources only check it.
- **Seam**: the year where one source hands over to the next. Here that is
  2015/2016, between WSF Evolution and WSF Tracker.
- **Stratum** (plural *strata*): a subgroup of an accuracy sample that is drawn
  and scored separately, so a small class gets enough points to be measured.

## 1. The plan's numbered decisions (§4)

The plan's §4 numbered its decisions. Those below can be placed with confidence.
The rest are in section 2, by content only.

### Decision 2 — "urban" means built-up surface: buildings, roads and paving (confirmed)

The project measures built-up surface, not a land-cover class and not "settlement
detected". Greenhouses are *not* urban under this definition, which later drove
decision M1.2. Copernicus Imperviousness is the product closest to this
definition. Every product means something different by "built" (CLAUDE.md #4).
Cited in `docs/data-evaluation.md`, `docs/design/seam-harmonization.md` and
`scripts/analysis_18_imperviousness_density.py`.

### Decision 4 — static hosting at near-zero cost, sized for the design target (confirmed)

No server computes anything per visitor. Files are published once and read
directly by the browser. The design target for traffic is the one CLAUDE.md states
in its project overview; at that scale every hosting option is free, so the choice
was made for simplicity. A tile server, and the serverless TiTiler/Lambda variant
of one, were **parked, not rejected**: they would add a cost per request where
there is none. The hosting this led to (Cloudflare Workers Assets for the page, R2
for the rasters, no Worker script) is in `docs/design/scaling.md` §6. Cited in
CLAUDE.md (the overview's declaration), `docs/design/scaling.md` and
`docs/design/figure-provenance.md`.

### Decision 5 — growth-only encoding: one "year first built" raster per layer (confirmed)

Each layer stores, per pixel, the first year it was built. The time slider is then
a colour threshold and fetches nothing. Demolition is not drawn. Losses go to a
separate `loss-events` collection, fed from the Copernicus change layers rather
than drawn by hand. The parked alternative was a two-image "first built / last
built" view, to be revived only if loss proved material. M0 measured loss and
found it negligible (`docs/data-evaluation.md`, the M0 summary and §5). Cited in
`docs/data-evaluation.md`, `docs/design/seam-harmonization.md` and
`scripts/analysis_07_loss_rate.py`.

### Decision 7 — per-zone statistics are precomputed by one library function (confirmed)

Statistics per zone (each island, for instance) are computed at build time by
`stats.zonal()`, and a web API may serve them later. There must never be a second
implementation, because a batch job and a web endpoint that drift apart make the
site quote numbers the published tables do not contain. Enforced by
`tests/test_api_parity.py`. The viewer's readout keeps its own arithmetic in one
place for the same reason (`viewer/count.js`). It is tested in JavaScript rather
than rewritten in Python to test it, which would itself be a second implementation
(`tests/test_viewer_count.py`). Cited in `docs/pipeline.md` §5,
`sensisat/stats.py`, `scripts/build.py`, `pyproject.toml`, CLAUDE.md #9 and the
tests.

### Decision 10 — WSF Tracker is the spine from 2016 onward (confirmed)

Tracker had been published only months before, with no accuracy figures, so M0
tested it before relying on it: an epoch histogram per island, its baseline share,
and continuity with the older products. It passed (`docs/data-evaluation.md`, the M0
summary). Cited in `scripts/analysis_10_wsf_tracker.py`.

### Decision 12 — OpenLayers as the map library (confirmed; was provisional)

The plan left this provisional pending a prototype. It was settled without one:
MapLibre cannot colour a raster by pixel value (maplibre-gl-js issue #4479), and
colouring by pixel value is how the time slider works without pre-rendered tiles.
Cited in `docs/viewer.md` §2.

### Decision 13 — the 2015/2016 seam is declared, never blended (confirmed)

The data is split into two eras: era-a ends in 2015 and era-b starts in 2016. The
viewer shows the change of method explicitly rather than sweeping smoothly across
it. Nothing is ever subtracted across the seam. The measured seam is published
beside the data, and the two settlement layers share the 2016 baseline. Follows
the CEOS land-product validation protocol. Cited in
`docs/design/seam-harmonization.md`, `sensisat/layers.py`, `scripts/build.py`,
`viewer/app.js`, `viewer/app.test.js` and `viewer/count.test.js`, and in
CLAUDE.md #7.

### Decision 14 — the history layer has an "undated" class in its own colour (confirmed)

The settlement history layer carries pixels that are built but cannot be dated as a
class of their own, in their own colour, beside the dated pixels and Tracker's
epochs. Its first label, which called these pixels built before 2016 with the year
unknown, had to be qualified once M0 found greenhouses and covered crops inside the class. Those are not urban
under decision 2. Cited in `docs/design/seam-harmonization.md` and the M0 commits.

### Decision 15 — the accuracy sample gets a stratum for the undated class (confirmed)

M0 could not explain the undated class, so M3 sampled it as its own stratum
instead of letting the large classes swamp it. The size of that stratum is set in
`scripts/m3_sample.py`, and the result is in `docs/validation.md` §6. Cited in
`docs/validation.md`, `scripts/m3_sample.py` and
`scripts/analysis_11_undated_roads.py`.

## 2. Decided in the plan, number lost

These were settled in the architecture review of 2026-09-18 and 2026-09-19 and
recorded in the plan. Each is reflected in the code and the documents, but no
surviving source gives its number. Any decision number without a heading in
section 1 is one of these, but which one is unknown.

- **No Google Earth Engine.** Dynamic World, the product the first prototype used,
  was disqualified in M0. The pipeline is built from public files read locally.
  Evidence: CLAUDE.md ("Google Earth Engine is no longer used") and
  `docs/data-evaluation.md`.
- **Geographic scope: the Canary Islands now, Spain and then the EU later.** This is
  why the pre-2016 era is a *plug-in*: another region can supply a different
  source. Evidence: `sensisat/encoding.py`, decision M1.1.
- **The roles of the sources, before M1 refined them.** GHSL for built surface and
  the long trend. WSF Evolution for settlement extent 1985–2015. WSF Tracker for
  2016 onward (decision 10). Copernicus HRL as the independent accuracy anchor and
  the source of losses. Evidence: `docs/data-evaluation.md`.
- **Validation in levels: automated checks on every build, plus one manual
  stratified sample.** The scripts cite the manual sample as the third level of plan §7. The
  sample size the plan proposed was replaced by M3's own design (CLAUDE.md #16 and
  #17). Evidence: `docs/validation.md`, `sensisat/qa.py`,
  `scripts/m3_sample.py`.
- **Data-first milestones.** M0 evaluates the data locally, with no cloud. M1
  decides the sources. M2 builds the pipeline, M3 assesses accuracy, M4 publishes
  the site and viewer, and M5 adds statistics, CI and releases. Evidence:
  CLAUDE.md "Current state" and the git history.
- **Reproducibility.** Every download is recorded with its size and checksum.
  Evidence: `sensisat/download.py`.
- **Two display modes in the viewer from day one**: "state at year" and "added
  since". Evidence: `docs/viewer.md` §4.

## 3. The M1 decisions (2026-09-19)

M1 decided the data sources, using what M0 had measured. All of them are
**confirmed**.

- **Decision M1.1 — before 2016, the cadastre is the timeline for Spain**, with WSF
  Evolution wherever no cadastre exists. The pre-2016 era is a plug-in with two
  implementations, and the catalogue declares which one each region uses. It
  covers 1900 to the seam in one method, so it has no seam of its own. Cited in
  `sensisat/datasets/cadastre.py`, `sensisat/encoding.py`, `sensisat/layers.py`,
  `docs/pipeline.md` and `docs/validation.md`.
- **Decision M1.2 — greenhouses are not urban, but they get a published layer of their
  own** (`covered-agriculture`). They are masked out of WSF Tracker, WSF 2019 and
  Imperviousness Density, because radar reads plastic and mesh frames as
  structures. Cited in CLAUDE.md #8, `sensisat/datasets/crops.py`,
  `sensisat/derive.py`, `sensisat/layers.py` and `tests/test_layers.py`.
- **Decision M1.3 — density is two layers, not a switch.** GHSL answers "how has density
  changed since 1975" (`density-trend`). Copernicus Imperviousness answers "how
  sealed is it now" (`density-current`). There is no handover date between them.
  Cited in `sensisat/layers.py`, `sensisat/datasets/copernicus.py` and
  `docs/data-evaluation.md`. *One inconsistency:* the docstring of
  `scripts/analysis_18_imperviousness_density.py` calls the density decision
  decision M1.4. It was written before the numbering settled, and every other
  citation says decision M1.3.
- **Decision M1.4 — WSF Evolution stays, as the "settlement including roads" layer**, even
  though the cadastre is primary, because **the cadastre has no roads**. This was
  verified by reading the raw INSPIRE feed. The two layers complement each other;
  neither contains the other. Cited in `sensisat/datasets/cadastre.py`.

## 4. Decided after the plan, and where each is recorded

These never had plan numbers. They are listed so that this file is the one index.

| decided | what | recorded in |
|---|---|---|
| 2026-09-20 | the accuracy unit is a square larger than the geolocation error, not a single pixel | CLAUDE.md #16, `docs/validation.md` §9 |
| 2026-09-21 | every published figure is generated, declared or excepted | `docs/design/figure-provenance.md` |
| 2026-09-21 | code under MIT; layers, statistics, docs and page under CC BY 4.0 | the last item of CLAUDE.md's going-public checklist, `LICENSE-DATA.md` |
| 2026-09-21 | the repository is public | CLAUDE.md, `CONTRIBUTING.md` |
| 2026-09-24 | rasters on R2, the page on Workers Assets, no Worker script | `docs/design/scaling.md` §6 |
| 2026-09-27 | every change reaches `main` through a pull request reviewed by CodeRabbit | CLAUDE.md "Review lifecycle" |

## 5. The plan's other sections, and where their content survives

| plan section | what it held | where it is now |
|---|---|---|
| §9b | the state snapshot to read first | CLAUDE.md "Current state", and the git log |
| §5 (M2) | the pipeline specification | `docs/pipeline.md`, as built |
| M2 acceptance criteria | what M2 had to deliver | `scripts/verify_m2.py`, as executable checks |
| §7 | validation levels | the third level (the manual sample) is M3: `docs/validation.md`, `scripts/m3_sample.py`, `scripts/m3_score.py`. The wording of the other levels is lost. |
| M4b list | the topics the public page must cover | `TOPICS` in `scripts/verify_m4b.py` |
| M4c "Verification" | the acceptance criteria for figure provenance | `scripts/verify_m4c.py`, numbered as in the plan |
| M5 | the per-zone statistics panel, attribution, releases | only the one-line summary in CLAUDE.md survives. **M5 needs re-planning before work starts.** |
| parked options | rejected approaches, each with the number that rejected it | `docs/data-evaluation.md` (sources), `docs/design/scaling.md` (hosting), CLAUDE.md "Review lifecycle" (reviewers) |

## 6. Keeping this register

- A new decision gets an entry here when it is taken, with its date and the file
  that holds its evidence. A plan may still propose it first, but the plan is not
  where it lives.
- Never renumber. The code cites these numbers.
- Keep the figures in the evidence documents, not here. If an entry ever needs a
  number, it goes under the figure gate like any other section of `docs/`: generate
  it, or declare where it came from.
