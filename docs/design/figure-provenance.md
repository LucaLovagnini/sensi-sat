# Design — figure provenance: every published number accounted for
<!-- figures: sensisat/figures.py; tests/test_documented_numbers.py; scripts/review_figures.py; measured:the runs of this mechanism on 2026-09-21, recorded in the M4c commits @ 2026-09-21 -->

Status: **implemented 2026-09-21** (M4c). Acceptance: `python scripts/verify_m4c.py`.
This document was written after the mechanism, from what building it measured; an
earlier version written before the counting was deleted because the counting
disproved two of its claims.

<!--[[[cog cog.outl(f.contract()) ]]]-->
**About the numbers in this document.** Figures fall into two kinds.

*Live figures* are generated from the current build — the same `data/processed/statistics/layers.json` that produced the 7 published layers — by `scripts/sync_docs.py`. They cannot be stale: `scripts/build.py` regenerates them, `pytest` checks them, and `scripts/publish.py` refuses to assemble the site while any disagrees.

*Historical measurements* are recorded as they were when they were taken, and are deliberately NOT updated. They are the evidence for a decision — the number that disqualified a dataset, or justified a threshold — and rewriting them to match a later build would destroy the reasoning they exist to support. Where one is reported, its analysis script is named, so it can be re-run and compared rather than trusted.
<!--[[[end]]]-->

## 1. The problem in one paragraph
<!-- figures: sensisat/facts.py; scripts/analysis_03_seam_factors.py; docs/figures/data/m0_seam_factors.csv @ 2026-09-21 -->

Every number a reader sees is a **copy** of something the pipeline computed, and a
copy goes stale in silence: nothing on disk is wrong, no QA gate applies, and the
only symptom is a document asserting last week's measurement. On 2026-09-21 the
public page, the viewer and all 56 STAC items said the settlement layer was
**43 %** undated when the layer we publish holds **37 %** — an M0 measurement of the
raw product, quoted for our masked, land-clipped layer. Three other viewer figures
were wrong the same way (a 2.2× ratio that our layers give as 2.1×, a 9 % growth
that our series gives as 5 %, a seam range true only for the five main islands
and not saying so). Fixing one place left the others wrong for a day. The guard
that existed — a test with a regex deciding what counted as a figure — had already
exempted the whole ladder-of-definitions table twice, by accident, and nobody
noticed. **The change is to invert the default**: every run of digits a reader can
see must resolve to *generated*, *declared* or *excepted*, and anything unresolved
fails the build naming itself.

## 2. What a figure is, mechanically
<!-- figures: sensisat/figures.py; tests/fixtures/figure_exemptions.json @ 2026-09-21 -->

`sensisat/figures.py` holds the one definition. A **token** is a run of digits as
the reader reads it: composite claims are one token ("98 times in 100",
"463 ± 83 km²", "26–52 %"), a unit stays attached ("30 m", "1.5 MiB"), and one
spelling is kept per unit ("30 metres" and "30-metre" are the same claim as
"30 m"). Identifiers are not numbers: `M3`, `km2`, `analysis_01` and `EPSG:4326`
are excluded by a look-behind and a reference rule, along with "section 7",
"decision 4", "epoch 1" and "#4479". **Structure a reader never reads as a
number** is removed before tokenising: DOIs, URLs, CSS colours and angles, licence
versions (`CC BY 4.0`), HTML entities, footnote superscripts, `${…}` interpolations,
and HTML comments — which is also what lets the section declarations below cost
nothing.

Then three classes:

- **generated** — inside a cog region (the `cog`/`end` marker pair, recognised in
  any comment syntax), written by `scripts/sync_docs.py` from `sensisat/facts.py`;
- **declared** — a key in `sensisat/provenance.HISTORICAL` (token-level surfaces),
  or inside a section carrying a `<!-- figures: … @ date -->` declaration
  (section-level surfaces);
- **excepted** — a year or a year range, a date, a Markdown list marker *by
  position* (the shape rule `^\d{1,2}\.$` once exempted "reached 12.").

**The exceptions are the fail-open surface**, so what they do is pinned: the number
of tokens each pattern removes, per file, is recorded in
`tests/fixtures/figure_exemptions.json` and any change fails until the fixture is
rewritten on purpose and its diff reviewed. No exception may match a token
carrying a unit.

## 3. The surfaces, and the burden each carries
<!-- figures: sensisat/figures.py; scripts/review_figures.py; docs/figures/data/manifest.json @ 2026-09-21 -->

Counts below are generated from the mechanism itself, so they are current.

<!--[[[cog
import sensisat.figures as g
fs = g.figure_set()
tok = fs["tokens"]
n_sections = sum(len(v) for v in fs["sections"].values())
n_decl = sum(len(v) for v in fs["declarations"].values())
n_gen = sum(len(v) for v in fs["generated"].values())
cog.outl("| surface | unit of accounting | today |")
cog.outl("|---|---|---|")
cog.outl(f"| `viewer/about-the-data.html` — the public page | every token | {len(tok['viewer/about-the-data.html'])} declared tokens, plus generated regions |")
for _rel in sorted(k for k in tok if k.startswith("viewer/") and k.endswith(".js")):
    cog.outl(f"| `{_rel}` — strings the UI renders | every token; live values via `viewer/facts.generated.js` | {len(tok[_rel])} declared tokens |")
cog.outl(f"| `README.md` | every token | {len(tok['README.md'])} declared tokens |")
cog.outl(f"| `sensisat/layers.py` → STAC descriptions | templates filled by `catalog._fill` at write time | 2 placeholders |")
cog.outl(f"| `docs/**/*.md` and `CLAUDE.md` | the section | {n_sections} sections carrying figures, {n_decl} declarations |")
cog.outl(f"| generated regions, all prose | `cog` from `facts.py` | {n_gen} |")
cog.outl(f"| `sensisat/provenance.HISTORICAL` | the registry | {len(fs['registry'])} entries |")
cog.outl(f"| `docs/figures/data/` | a script that names the file, or the manifest | 36 files, 13 in the manifest |")
]]]-->
| surface | unit of accounting | today |
|---|---|---|
| `viewer/about-the-data.html` — the public page | every token | 60 declared tokens, plus generated regions |
| `viewer/app.js` — strings the UI renders | every token; live values via `viewer/facts.generated.js` | 5 declared tokens |
| `viewer/count.js` — strings the UI renders | every token; live values via `viewer/facts.generated.js` | 0 declared tokens |
| `README.md` | every token | 9 declared tokens |
| `sensisat/layers.py` → STAC descriptions | templates filled by `catalog._fill` at write time | 2 placeholders |
| `docs/**/*.md` and `CLAUDE.md` | the section | 79 sections carrying figures, 81 declarations |
| generated regions, all prose | `cog` from `facts.py` | 21 |
| `sensisat/provenance.HISTORICAL` | the registry | 63 entries |
| `docs/figures/data/` | a script that names the file, or the manifest | 36 files, 13 in the manifest |
<!--[[[end]]]-->

Token-level everywhere would have been about 1,400 registry entries and would have
been abandoned; that measurement is why `docs/` is accounted for by section.
Charts (`docs/figures/*.png`) and git history are out of reach and recorded as such.
Code and configuration are out of scope: a number in a test fixture is not a claim
to a reader.

## 4. The mechanism, piece by piece
<!-- figures: sensisat/facts.py; sensisat/catalog.py; scripts/sync_docs.py; sensisat/figures.py; measured:the runs of this mechanism on 2026-09-21 @ 2026-09-21 -->

**The key store.** `sensisat/facts.py` defines each live figure once, as a function
over `data/processed/statistics/layers.json` (committed for exactly this reason).
Three consumers read it — the DITA `keyref` idea, one definition many references:

1. **Prose**: cog regions inside HTML comments, in HTML and Markdown, rewritten by
   `scripts/sync_docs.py` (which `build.py` runs, because a rebuild is what makes
   them stale) and verified by `sync_docs.py --check` (which `pytest` and
   `publish.py` run). In Markdown a region **generates whole lines and stands
   alone** between blank lines: a comment line ends the paragraph it interrupts, so
   a region set mid-sentence renders as three paragraphs. A test enforces it.
2. **The viewer**: `viewer/facts.generated.js`, an ES module `app.js` imports and
   splices into its notes as `${FACTS.undated_pct}`. Not cog: cog cannot parse
   JavaScript whose nested array literals end in three closing brackets, its own
   end-of-code token,
   and a marker inside a string literal would be rendered to the reader. A test
   asserts no cog marker exists in `app.js` or `layers.py`.
3. **The catalogue**: `LayerSpec.description` is a template (`{undated_pct}`)
   filled by `catalog._fill` when each item is written, from that run's own
   statistics — so Gran Canaria's item states Gran Canaria's share and the
   collection the archipelago's. A figure written into `layers.py` would lag the
   build that produced it by one run, forever, because the module is imported
   before the build writes its statistics.

**The registry.** `sensisat/provenance.HISTORICAL` maps a token to what it is and
which analysis produced it. Everything in it is a measurement frozen on purpose —
the number that disqualified a dataset — and must never be updated to match a
later build. An entry for a figure on no surface fails as dead.

**Section declarations.** `<!-- figures: <source>[; <source>…] @ <YYYY-MM-DD> -->`
under a heading; a section needs one iff it holds a token that is neither
generated nor excepted; the H1 preamble is a section. A source is a repository
file that must exist, or `external:<what>` (a price list, a paper) or
`measured:<how>` (a browser's network panel) for a number that has no file — the
honest form, counted and shown by the review. Sources are separated by `;` so a
label may contain commas. A declaration records **origin, not correctness**.

**The collision check** is what closes the drift hole in `docs/` without a registry
entry per number: every headline value `facts.py` computes — areas per layer and
island, sizes, shares, the sealed-to-built ratio, growth, the construction crash —
is searched for in all prose outside generated regions, **with its unit attached**,
at one and two decimals. A hit is a live figure someone typed, which the next
build orphans. It is fail-closed: every hit must be generated instead, or
allow-listed in `tests/fixtures/figure_collisions.json` as a historical
measurement that coincides with the current build, with the reason written down.
Values below 1 are skipped (at two decimals they collide by coincidence —
`$0.36/million` matched La Graciosa's extent) and the seam record's per-island
fields are not searched (the M2 seam reproduces M0's CSV to the published decimal,
so every one collides by construction).

**The quantity-word lint** closes the perverse incentive a digit-based gate
creates: a number written as words is invisible to it. A narrow list — "a third",
"a quarter", "a fifth", "a tenth", "two thirds", "three quarters", "N in ten",
"N-fold"; deliberately not "half", "twice", "double" or "most", which are ordinary
English — must have a figure within 60 characters in the same paragraph; a year
does not count; a quoted phrase is a mention, not a use (which is why this
paragraph passes); three ordinals that share a spelling ("a third party",
"as a third", "a third surface") are listed by name.
CLAUDE.md #23 is the writing rule; this is its enforcement.

**Section numbers on the page are CSS counters** (`about.css`), so the source
holds no typed heading number and the list-marker exception is Markdown-only.

**The data-file manifest** (`docs/figures/data/manifest.json`) records, for every
table no code names, the commit that introduced it and what it is. "Named by
code" is the mechanical notion of *produced by*; grep cannot tell a read from a
write, so the CORINE band — read by `qa.py`, written by nothing — is listed too.

## 5. The judgements the gate cannot make
<!-- figures: scripts/review_figures.py; docs/figures-review.json; .githooks/pre-push @ 2026-09-21 -->

Three questions only reading answers: **is each generated figure generated from the
right fact** (the most dangerous hole — `area("buildings-dated")` in a sentence
about sealed surface passes every check and carries the authority of being
generated); **is anything in the registry actually a live claim** mis-filed as
history (how 43 % survived two builds); **does each declared source plausibly
produce the section's numbers**.

`scripts/review_figures.py --list` prints everything to judge — each generated
figure inside the sentence it lands in, the registry, the registry keys that
coincide with a live value today (a hand-typed copy of that live value would hide
behind the historical entry), and every declaration. `--attest` records the
reviewer and the three judgements in `docs/figures-review.json` under a hash over
the **set of figures**: tokens per surface, each section's figures, every generated
region's code and output, the registry, the declarations, the live values.
Rewording prose leaves it valid; one changed figure, declaration or registry key
expires it (tested). `--check` says what moved. `publish.py` refuses to assemble
`dist/` while it is stale; `.githooks/pre-push` refuses to push. The procedure is
`.claude/skills/verify-figures/SKILL.md`.

The first review, in the implementing session, found exactly the kind of error the
gate cannot see: `facts.dated_share()` is a share of footprint **area**, and the
page sentence read it as a share of the 474,292 **buildings** (the count-based
figure is 98.92 %). The sentence was reworded.

## 6. What the enforcement really enforces
<!-- figures: .githooks/pre-push; scripts/publish.py @ 2026-09-21 -->

| mechanism | strength |
|---|---|
| `sync_docs --check`, the classification gate, the collision check, the lint, the baseline, the manifest | **enforce** — pure computation, run by `pytest`, `build.py` (exit 4) and `publish.py` (exit 3) |
| the attestation, checked by `publish.py` and the `pre-push` hook | **remind, loudly, at the right moment** — a named reviewer looked at this set of figures |
| making the repository public | **nothing runs** — a settings click; the checklist in CLAUDE.md |

Demonstrated against a throwaway local remote: with a current review the push goes
through; with one added figure the hook blocks it and nothing is transmitted.
`git push --no-verify` bypasses it and `.git/hooks` is unversioned, so the hook
lives in `.githooks/` and is enabled per clone with
`git config core.hooksPath .githooks`. In a single-author repository nothing
defends against the author: the hook covers *you forgot*, never *you decided*.

## 7. Honest limits
<!-- figures: measured:the runs of this mechanism on 2026-09-21 @ 2026-09-21 -->

1. **A generated figure can be generated from the wrong fact** and carry false
   authority. Only reading catches it — and the first reading did catch one.
2. **A live figure mis-classified as historical** passes. The registry is a human
   decision per figure; the review lists the keys that coincide with a live value
   so the reviewer knows where to look.
3. **A declaration or registry entry is an assertion, not a verification.** Checked
   for existence and grammar, never for truth. A historical digit mis-typed once is
   caught by nothing mechanical.
4. **Repeated tokens with different meanings** ("2 %" twice on the page) share one
   entry. Occurrence-index keying was rejected: any edit renumbers it.
5. **The collision check** sees only values ≥ 1, only with a unit attached, only
   headline facts. A bare table cell holding a live value is not seen.
6. **`external:` and `measured:` sources** are labels; the mechanism cannot check a
   price list or a DevTools reading. Six external and nine measured today.
7. **"Produced by" means "named by code"**; a script that reads a file counts.
8. **Charts and git history** are unreachable; **code and configuration** are out of
   scope by decision.
9. **Prose churn**: editing a sentence changes its tokens and expires the
   attestation. The failure says what to do, not only what is wrong.
10. **CLAUDE.md declarations** cost context tokens every session — a few short
    comments, accepted.

## 8. What building it found
<!-- figures: measured:the runs of this mechanism on 2026-09-21, recorded in the M4c commits @ 2026-09-21 -->

Each of these was invisible before the corresponding piece existed.

- **Four viewer figures wrong or stale** on the deployed site: 43 % → 37 %
  undated; 2.2× → 2.1× sealed-to-built; 9 % → 5 % Gran Canaria growth 1995–2015;
  the seam range with no "five main islands" (over all eight it runs from −83 % to
  +56 %: La Gomera *gains* at the join, its 2016 footprint being 3 km²).
- **45 tokens the old regex had silently exempted** on the page, the viewer and the
  README, surfaced by the first fail-closed run; each classified.
- **17 quantity words with no digits**, not the 2 a page-only scan had reported;
  two were loose claims the digits corrected — the greenhouse mask removes
  32–46 % of the definitional jump, not "a third"; 61 % of the M3 sample is open
  countryside, not "two-thirds".
- **11 collisions** of a live value with hand-typed prose: 7 real, all in
  `pipeline.md`'s M2 results table (now generated whole — and its greenhouse gap
  reads 42.8 km², not the 42.7 typed from a rounded subtraction); 4 coincidences,
  allow-listed with reasons.
- **Stale live figures in `docs/`**: viewer.md's 9 % growth and three-decimal areas
  the UI no longer shows; validation.md's 43 % undated share.
- **13 evidence files no code writes**, including both analyses (15 and 17) named
  in headings that never had a script of their own.
- **One wrong-fact match** the gate could never see, found by the first review
  (§5).

## 9. Alternatives considered
<!-- figures: external:Inline XBRL, DITA keyref and Sphinx substitutions, Quarto — their public documentation, read 2026-09-21 @ 2026-09-21 -->

| approach | who uses it | what was taken |
|---|---|---|
| **Inline XBRL** | filed financial statements | the principle — tag the fact where it appears — and nothing else; taxonomies and validators are far too heavy |
| **Single-sourcing: DITA `keyref`, Sphinx substitutions** | enterprise technical writing | **the pattern under-used before**: define a value once, reference it by key everywhere, so copies cannot diverge (`facts.py`, `facts.generated.js`, `_fill`) |
| **Quarto / R Markdown inline code** | reproducible research | the idea; wrong shape for hand-written HTML — cog gives the same guarantee inside the files we have |
| **Token-level registry everywhere** | — | rejected by measurement: ~1,400 entries; `docs/` is accounted for by section instead |
| **A server rendering figures** | — | solves retrieval, not classification; costs a page that prints, archives and works offline; needs infrastructure decision 4 avoids |
| **Cog markers in `app.js` / `layers.py`** | — | tried and failed: nested array literals end in cog's own end token; markers inside strings render; `layers.py` is circular with the build |

## 10. Working with it
<!-- figures: scripts/sync_docs.py; scripts/review_figures.py @ 2026-09-21 -->

- **Adding a number to the page, the viewer or the README.** If it comes from the
  build: a function in `facts.py`, a cog region (page, README) or a key in
  `render_facts_js` (viewer). If it is historical: an entry in
  `provenance.HISTORICAL` saying what it is and which analysis produced it. The
  gate tells you which you forgot.
- **Adding a number to `docs/` or CLAUDE.md.** Make sure the section's declaration
  names the source that produced it; if the value is one the build computes,
  generate it instead — the collision check will say so.
- **Writing a fraction in words.** Put the digits beside it: "a quarter (28 %)".
- **After a rebuild.** `build.py` regenerates the documents; review the diff; if
  the exit code is 4, a document has an unaccounted figure.
- **Editing an exception pattern.** The baseline fails; rewrite it with
  `python tests/test_documented_numbers.py --write-baseline` and review its diff —
  if you did not touch the fixture and it changed, the pattern widened.
- **Before pushing.** `python scripts/review_figures.py --check`; if stale, run the
  `/verify-figures` procedure and attest. The hook enforces this once
  `core.hooksPath` is set.
- **Before going public.** The checklist in CLAUDE.md.

## 11. Verification
<!-- figures: scripts/verify_m4c.py @ 2026-09-21 -->

`python scripts/verify_m4c.py` runs the acceptance criteria written in the plan
(M4c): the gate itself; a doctored page fails naming the figure; a deleted registry
entry fails; the exceptions match their baseline and never swallow a unit; one
perturbed statistics file moves the page, the viewer module and the STAC template
together; a doctored generated figure fails `sync_docs --check`; no marker in code;
the STAC descriptions carry their own island's figure; zero collisions outside the
allow-list; the lint fixtures; every section declared with existing sources; CSS
counters; the manifest; the fingerprint's behaviour; the hook blocking a stale
state; this document passing the same gate. Two criteria are human and are
reported as recorded, not verified: the review attestation on file, and
`core.hooksPath` set in the clone.
