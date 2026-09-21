# Contributing

Thank you for looking. Two things about this repository are unusual, and a
contributor should know them before running anything.

## The documents execute code

Every number in `docs/*.md`, `CLAUDE.md`, `README.md` and the public page is either
**generated** or **declared** (see `docs/design/figure-provenance.md`). Generated
figures sit inside cog regions — HTML comments holding a line of Python that
`scripts/sync_docs.py` runs to write the number beside it. That Python runs whenever
you run `pytest`, `python scripts/build.py`, `python scripts/publish.py`, or push
with the hook enabled.

So **a change to a Markdown file can be a change to what your machine executes.**
Reviewers: before running the tests on a branch you did not write, read the diff of
every `[[[cog` block. Contributors: keep cog blocks to calls into `sensisat.facts`;
a block that imports anything else, touches the filesystem or the network will be
asked about.

If continuous integration is ever added, workflows triggered by pull requests from
forks must run with **no secrets and no deploy token** for the same reason.

## Every number is accounted for

Adding a number to any document makes the figure gate fail until you say where it
came from — the failure message tells you how. In short: a figure from the current
build is generated (`sensisat/facts.py` + a cog region, or a key in
`viewer/facts.generated.js` for the viewer); a historical measurement is declared
(`sensisat/provenance.py` for the page, viewer and README; a
`<!-- figures: … @ date -->` line under the section heading in `docs/`). A quantity
written in words carries its digits: "a quarter (28 %)".

```bash
pip install -e ".[zarr,dev]"
python -m pytest -q && ruff check .        # includes the figure gate
python scripts/review_figures.py --list    # what a reviewer still judges by eye
```

## Licence

Code is MIT (`LICENSE`); published data, documentation and the page are CC BY 4.0
(`LICENSE-DATA.md`). By contributing you agree your contribution is licensed the
same way.
