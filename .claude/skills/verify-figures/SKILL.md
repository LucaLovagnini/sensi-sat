---
name: verify-figures
description: Review every published number the figure gate cannot judge — is each generated figure from the right fact, is anything in the registry a live claim, does each section declaration fit — and attest the review so publish.py and the pre-push hook accept the current state.
---

# /verify-figures — the three judgements, then the attestation

The figure gate (`pytest tests/test_documented_numbers.py`) proves every number a
reader can see is generated, declared or excepted. It cannot prove three things,
and this skill is how a human (or you, named as the reviewer) supplies them.

## Procedure

1. Run the gate first; do not review a failing state:
   `python -m pytest tests/test_documented_numbers.py -q`
2. `python scripts/review_figures.py --list` and read all of it. For each block:
   - **Generated regions** — read the `code` and the `output` together. Ask: does the
     fact match the sentence? (`area("buildings-dated")` in a sentence about sealed
     surface is the failure this exists to catch.) Check units and the rounding the
     sentence implies.
   - **Registry** — for each entry ask: is this a measurement frozen on purpose
     (the number that disqualified a dataset), or a claim about the layers we
     publish today, which would move with a rebuild? The second kind must become
     a generated figure. This is how `43 %` survived two builds.
   - **Declarations** — for each section, does the named script or data file
     plausibly produce the numbers in that section? Spot-check two or three by
     opening the script's docstring or the CSV's columns.
3. Fix anything found, re-run the gate, and only then attest — with the three
   judgements written out in a sentence each, naming what you checked:
   ```
   python scripts/review_figures.py --attest --reviewer "Name (how)" \
     --generated "…" --registry "…" --declarations "…"
   ```
4. Commit `docs/figures-review.json` with the change that prompted the review.

## What the attestation does and does not do

It hashes the SET of figures — tokens, generated regions, registry keys, section
declarations, live values — so rewording prose leaves it valid and changing one
figure expires it. `scripts/publish.py` refuses to assemble `dist/` while it is
stale; `.githooks/pre-push` refuses to push (enable once per clone:
`git config core.hooksPath .githooks`). It records that someone looked, and at
what. It cannot make the looking careful; that is the reviewer's job.
