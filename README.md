# SensiSat

Mapping how built-up land in the **Canary Islands** grew from 1900 to today, from
open satellite and cadastral data, for researchers, conservation NGOs and planners.

The project is also a way to learn the geospatial domain properly, so the
documentation explains its terms rather than assuming them. If a word here is new,
`docs/concepts.md` defines it with a worked example.

**Every published figure, with the conditions under which it is true, is on the
public page: [sensisat.org/about-the-data.html](https://sensisat.org/about-the-data.html).**
The numbers below are M0's measurements of the *source* products (2026-09-19), not
the totals of the layers SensiSat publishes; the page states the difference.

## The finding that shapes everything else

There is no single number for "how much of the Canaries is built". Measured across
the archipelago by six independent, respected products:

| source | what it counts | km² |
|---|---|---|
| CORINE 2018 | "artificial surfaces", incl. quarries and sports grounds | 469.5 |
| WSF Evolution | 30 m pixels containing any settlement | 376.9 |
| Copernicus Imperviousness | m² sealed by anything, incl. roads and paving | 341.5 |
| Copernicus Impervious Built-Up | 10 m pixels containing buildings | 259.3 |
| GHSL | m² of built surface | 152.9 |
| Spanish cadastre | building footprints | 100.3 |

None of these is wrong. Each is a stricter idea of what "built" means, and they
sit in a consistent order. Choosing between them *is* the design of this project,
so every layer SensiSat publishes states which definition it uses.

A seventh product, Google Dynamic World, reported 308 km² for **Gran Canaria
alone** — more than double every artificial thing CORINE can find on that island.
It was disqualified, along with five other global candidates, in `docs/data-evaluation.md`.

## Where things are

| | |
|---|---|
| `docs/concepts.md` | the domain primer — raster, projection, extent vs surface, with reproducible figures |
| `docs/data-evaluation.md` | M0: every candidate dataset, tested, with a go/no-go and the number behind it |
| `docs/design/seam-harmonization.md` | why the 2015/2016 join is declared rather than blended |
| `docs/pipeline.md` | M2: the seven published layers, the shared grid, the QA gates |
| `sensisat/` | the package: dataset adapters, area maths, derivation, QA, catalogue |
| `scripts/analysis_*.py` | the M0 analyses — every number in the docs is reproducible from these |
| `scripts/build.py` | the M2 build: produce, check and catalogue the layers |

## Running it

```bash
pip install -e ".[zarr,dev]"
python scripts/build.py --all      # seven layers x eight islands -> data/processed/
pytest                             # the unit tests
```

Downloads are cached under `data/` with a manifest recording each file's size and
SHA-256. `data/` is not tracked in git.

The Copernicus layers are the one exception to "just run it": they sit behind a
free land.copernicus.eu account and have to be placed in `data/raw/hrl/` by hand.
Every other source downloads itself.

## Status

M0 (data evaluation), M1 (which sources), M2 (the pipeline), M3 (accuracy assessment
against aerial photography), M4 (the viewer, live at sensisat.org),
M4b (the public page) and M4c (every published number accounted for) are complete.
Next is M5: a per-zone statistics panel, attribution, releases.

## Licence

Code: MIT (`LICENSE`). Published layers, statistics, evidence tables, documentation
and the public page: **CC BY 4.0** (`LICENSE-DATA.md`, which also lists every
source's own terms and the attribution to give when reusing).

There is deliberately no cloud infrastructure yet. The complete archipelago
timeline is a few megabytes, which a browser can read directly from static files —
so nothing here needs a tile server, and none is built until something does.
