# Every number accounted for — the fail-closed design

**Status: designed 2026-09-21, not yet implemented.** Decided with Luca after the
partial version let two published figures go wrong.

## The problem, stated exactly

Numbers reach a reader through three documents-worth of prose, and every one of them
is a copy of something computed elsewhere. Three mechanisms now guard them, and each
was added after the previous one failed:

1. **Cog generates the live figures** (`sensisat/facts.py`, `scripts/sync_docs.py`).
   A generated number cannot go stale. But cog is a *generator, not a scanner*: it
   is blind to a number nobody marked.
2. **A registry declares the historical ones** (`sensisat/provenance.py`), so a
   figure that must never change still has to say where it came from.
3. **A test requires every figure on the published page to be one or the other.**

The third closed the obvious hole. It did not close the real one, which is that
**a regex decides what counts as a figure**. That is fail-open: anything the pattern
misses is silently exempt. It has already happened twice in one day —

- requiring a unit beside the number exempted the entire ladder-of-definitions
  table, six of the most-quoted totals we publish, because their unit lives in a
  column header;
- the DOI exclusion rejected any match with a `/` nearby, and every table cell ends
  in `</td>`, so the widened rule re-excluded exactly the table it was written to
  catch, while appearing to work.

Both were found by accident. A rule whose failures are invisible is not a guard.

## The change

**Invert the default.** Extract *every* run of digits. Each must resolve to exactly
one of three outcomes, and anything unresolved fails the build:

| outcome | meaning | where it lives |
|---|---|---|
| **generated** | derived from the current build; cannot be stale | a cog marker, computed by `sensisat/facts.py` |
| **declared** | a historical measurement, frozen on purpose | `sensisat/provenance.py`, with what it is and which analysis produced it |
| **excepted** | not a measurement at all | a narrow pattern with a stated reason |

Nothing is ignored by default. Changing the prose, restructuring a table, or adding
a figure all force a classification rather than slipping past a pattern.

## Two granularities, because one does not fit both

Token-level classification everywhere would be **1,423 entries** — measured, not
guessed. That is not maintainable and would be abandoned, which is worse than not
starting. Measured burden per document, after excepting only years and list markers:

| document | tokens to classify | headings |
|---|---:|---:|
| `viewer/about-the-data.html` | 73 | 11 |
| `docs/data-evaluation.md` | 760 | 34 |
| `docs/validation.md` | 161 | 18 |
| `docs/design/seam-harmonization.md` | 143 | 9 |
| `docs/pipeline.md` | 108 | 14 |
| `docs/concepts.md` | 84 | 9 |
| `docs/design/scaling.md` | 55 | 12 |
| `docs/viewer.md` | 39 | 9 |
| **total** | **1,423** | **116** |

So:

- **The published page: token-level.** 73 entries. It is the only thing a reader
  outside the project sees, its figures get quoted, and it has no per-section
  analysis structure to inherit from. Each number is declared individually.
- **`docs/*.md`: section-level.** ~106 declarations instead of ~1,350. Each heading
  states where its numbers come from — almost always one analysis script, which the
  documents already name in prose. A number inside a declared section inherits that
  provenance; a section with no declaration **fails**. Still fail-closed: a new
  section cannot appear unclassified, and neither can a document.

This is not a weaker guarantee for `docs/`, it is a coarser one. It cannot catch a
single mistyped digit inside a declared section. It *can* catch the thing that
actually goes wrong: a whole block of numbers whose source nobody recorded.

## Exceptions must be narrow, and that is the load-bearing rule

An exception pattern that is too broad silently re-creates the failure this design
exists to remove. Two qualify today:

```
^(18|19|20)\d\d[.,]?$    a year — a date, not a measurement
^\d{1,2}\.$              a list marker — "3." in a numbered list
```

**`^\d{1,3}$` does NOT qualify**, though it would have collapsed a third of the
work. It would swallow a bare `377` in a table cell, which is WSF Evolution's
archipelago extent — exactly the class of figure the ladder-table bug exempted.

Two tests keep the patterns honest:

- **no exception may match a token carrying a unit** — if it has km² or % beside it,
  it is a measurement whatever its shape;
- **each pattern reports how many tokens it exempts**, and a pattern that starts
  exempting far more than when it was written is a signal to look, not a
  convenience.

## Known weaknesses, recorded rather than hidden

1. **Repeated tokens with different meanings.** `2 %` appears twice on the page —
   the share of built pixels a growth-only view misplaces, and the share of "empty"
   squares holding a building. A registry keyed by the literal conflates them. The
   entry must describe both, which is honest but clumsy. Keying by occurrence index
   was rejected: any edit renumbers it.
2. **Prose churn.** Rewriting a sentence changes its tokens and the check will name
   them. That is the intended cost — but it makes editing prose slightly heavier,
   and a contributor who does not know why will find it obstructive. Hence the
   failure message says what to do, not just what is wrong.
3. **`docs/` inherits at section granularity**, so a wrong digit inside a correctly
   declared section passes. Accepted: the alternative is 1,350 entries nobody
   maintains.

## Order of work

1. **The published page to token-level.** 73 entries, and it is the only document
   with readers outside the project. Includes promoting live figures to generated
   where they exist — the last pass through it found two published wrong.
2. **`docs/validation.md` and `docs/pipeline.md`.** The M3 and M2 results: the most
   likely to be quoted back at us and the most likely to drift, since both describe
   the current build.
3. **`docs/data-evaluation.md`.** The largest, but also the most stable — it is M0's
   record and is almost entirely historical by nature.
4. **The remaining four**, which are mostly prose.

## Effort

`[est]` One working session for the page, one for steps 2–4 together. Recorded with
a caveat this project has earned: every point-level effort estimate here has been
**6–20× too pessimistic** (`validation.md` §8), so treat these as ceilings.

## Enforcement

Already wired and unchanged by this design: `scripts/build.py` regenerates,
`pytest` checks, `scripts/publish.py` refuses to assemble `dist/`. This change
alters *what* is checked, not *where*.
