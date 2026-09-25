# M4 — the viewer

**What exists:** an interactive map over M2's seven published layers, running from
static files with no server of any kind. Built and verified in a browser; **not yet
deployed** to public hosting.

```bash
python viewer/serve.py       # then open http://127.0.0.1:8777/viewer/
```

---

## 1. Why the time slider costs nothing
<!-- figures: measured:arithmetic stated in the text (years × zoom levels) @ 2026-09-20 -->

This is the idea the whole project was arranged around, and it is worth stating
plainly because it is what removes the infrastructure.

Our rasters encode **the year a pixel was first built**, not whether it was built
in some particular year. So "show me 1985" is not a different map — it is the same
map with a different threshold. Moving the slider changes one number in a GPU
shader applied to pixels already in memory. **No request is made. No tile is
rendered. Nothing is fetched.**

The alternative — a raster per year — would mean 120 pre-rendered tile sets per
layer and a server to cut them. Instead there is one file per layer per island, a
few megabytes, read straight off static hosting by HTTP range request.

## 2. Why OpenLayers, finally decided

Decision 12 left this provisional pending a prototype. It did not need one, because
one verified fact settles it: **MapLibre cannot colour a raster by pixel value**
([maplibre-gl-js#4479](https://github.com/maplibre/maplibre-gl-js/issues/4479),
open, unreleased — Mapbox added `raster-color` in January 2024 and MapLibre has
not followed). Colouring by pixel value *is* the mechanism above. Without it every
year needs its own pre-rendered tiles, which is exactly the tile server this design
exists to avoid. OpenLayers' `WebGLTile` does it natively.

## 3. Things that had to be got right, and were not obvious
<!-- figures: sensisat/raster.py; measured:M4 experiments on a synthetic island and Tenerife's building layer on 2026-09-20 @ 2026-09-20 -->

Each of these cost real time, and each is a property of the published data rather
than of the viewer code — which is why they are written down here.

**A Cloud-Optimized GeoTIFF must not be sparse.** `SPARSE_OK=TRUE` looks ideal for
islands surrounded by ocean: all-nodata blocks cost no bytes. But it writes
zero-length entries into the tile offset table, and **geotiff.js — the library
every browser-side COG reader is built on — cannot read them**. It fails with
`Cannot read properties of undefined (reading 'offset')` and the layer silently
never appears. Measured, sparse was buying almost nothing anyway: Gran Canaria's
building layer is 1.435 MiB sparse against 1.513 MiB dense, **a 5 % difference**,
because DEFLATE already compresses a 256×256 block of ocean to a few dozen bytes.

**Overviews must not use nearest-neighbour.** The obvious choice for categorical
data is the wrong one: nearest picks one child pixel arbitrarily, so scattered 10 m
buildings vanish as you zoom out and an island reads as empty until you are almost
on top of it. Measured on a synthetic island at 0.5 % built, nearest keeps 0.47 %
of pixels at 4× zoom-out and **mode keeps 7.67 %**. Mode wins for two reasons:
nodata is 0 and GDAL excludes it from the aggregation, so "not built" cannot
outvote a real value; and mode always returns a value that was actually observed,
so unlike *average* — which scores identically on visibility — it can never invent
a year in which nothing was built.

**The map view must be in the data's projection.** `WebGLTileLayer` does not
reproject. A GeoTIFF source whose projection differs from the view simply never
renders, with nothing in the console to say why. So the view is EPSG:4326, the
projection the COGs are already in, and the *basemap* is the thing reprojected —
which an ordinary raster tile layer handles fine.

**Only numbers may be style variables.** OpenLayers compiles `['var', x]` to a
`uniform float`, so putting a colour in a variable fails shader compilation with
`mismatching ternary operator operand types` — and then **nothing** renders,
basemap included. The year window travels as two numbers and the mode as a third;
every colour is a literal.

**A dev server must support HTTP range requests.** `python -m http.server` does
not — it ignores the `Range` header and returns the whole file with a 200, which
geotiff.js treats as a failure. `viewer/serve.py` exists for this, and speaks
HTTP/1.1 so that connections stay alive for the several parallel range requests a
COG read needs. This is not a local-only concern: range support is the one thing
the real host must provide, and every static host we would use (Cloudflare R2,
S3 + CloudFront, GitHub Pages) provides it.

## 4. What the viewer shows

All seven layers, any of the eight islands, read from the STAC catalogue rather
than from anything hard-coded — the layer picker is populated by what the catalogue
actually contains.

**Two display modes, from day one** (the plan's requirement):

- **State at year** — everything built up to that year.
- **Added since** — only what appeared after it. This exists because two states
  side by side *hide* change: Gran Canaria's settlement extent grew by a few per
  cent between 1995 and 2015 (the exact figure is in the viewer's note, generated
  from the layer) and the two maps look identical to the eye.

**"We don't know" survives to the screen.** The undated class — pixels that are
built but carry no year — is drawn in its own colour and never given an invented
date. In the "added since" view it is **hidden**, with the legend saying so,
because a pixel with no year cannot honestly be placed in a period.

**The 2015/2016 seam is announced, not smoothed.** Each settlement era carries a
note saying what it is and that it does not join continuously to the other, and
that the two must not be added together because they share the 2016 baseline.

Per-island figures come from the published statistics, so the number on screen is
the same number the build measured:

<!--[[[cog
cog.outl(f"{km2(area('buildings-dated', 'Gran Canaria'))} km² of buildings on Gran Canaria, "
         f"{km2(area('covered-agriculture', 'Gran Canaria'))} km² of greenhouses, "
         f"{km2(area('density-current', 'Gran Canaria'))} km² sealed.")
]]]-->
35.65 km² of buildings on Gran Canaria, 27.06 km² of greenhouses, 109.68 km² sealed.
<!--[[[end]]]-->

## 5. The readout follows the map
<!-- figures: viewer/count.js; scripts/publish.py; sensisat/raster.py; measured:browser decode timings and a slider sweep in Chrome against the published layers on 2026-09-25; measured:browser-versus-rasterio parity on identical windows over HTTP on 2026-09-25; measured:overview inflation read off the published buildings-dated mosaic at 8x and 32x, and per island, on 2026-09-25 — pinned in tests/test_coverage.py; tests/test_coverage.py @ 2026-09-25 -->

The number beside the map describes **what is on screen at that moment** —
the archipelago, an island, a city, a neighbourhood — and updates as you pan and
zoom. Over open sea it reads `0 km²`, which is an answer rather than a blank.

### Why it cannot simply count the pixels the map is drawing

A Cloud-Optimized GeoTIFF ships pre-made coarse copies of itself, called
**overviews**, so a zoomed-out map need not read every pixel. Ours are built with
`mode` resampling and `nodata` excluded, which means a coarse pixel reads "built"
if **any** of the pixels beneath it is built. That is the right rule for drawing —
otherwise villages vanish as you zoom out (§3, CLAUDE.md #13) — and it is
catastrophic for counting, because counting then assumes every one of those
children is full. On `buildings-dated`:

<!--[[[cog
cog.outl("| what the browser holds | implied built area |")
cog.outl("|---|---|")
cog.outl(f"| full resolution | **{km2(area('buildings-dated'))} km²** ← the published figure |")
cog.outl("| zoomed out 8× | 1,026.7 km² |")
cog.outl("| zoomed out 32× | **3,310.3 km²** |")
]]]-->
| what the browser holds | implied built area |
|---|---|
| full resolution | **104.33 km²** ← the published figure |
| zoomed out 8× | 1,026.7 km² |
| zoomed out 32× | **3,310.3 km²** |
<!--[[[end]]]-->

No correction factor exists, because the error depends on how clustered the
buildings are: at 32× it is 23.9× on dense Gran Canaria against 101.7× on
scattered El Hierro. `tests/test_coverage.py` pins both.

### Two regimes, and no new published data

**Near** — while the view is small enough, the raster is read at full resolution for
the window on screen and counted. This is not a second implementation of the build's
arithmetic: it reads the same bytes and applies the same rule. Checked in a browser
against `rasterio` on the identical integer-pixel window over HTTP — 0.477047 km²
against 0.477048, the difference being the viewer's own rounding.

**Far** — above it, the published `extent_by_year` of every island the view touches
is summed. Free, instant and exact, because those figures are already in
`index.json`.

The caption says which: `in view` near, the island names far. That distinction is
the honest cost of the design, not decoration — an island's published total covers
the whole island, which is more ground than the screen shows whenever the island
runs off the edge, so claiming "in view" there would be false and unfalsifiable at
a glance.

### The budget is in blocks, which is what the cost is actually paid in

The first version of this threshold counted the pixels in the view, and that
describes the wrong thing. A COG stores its pixels in fixed square tiles — ours are
1024 × 1024 — and a reader cannot fetch less than a whole one. The floor for **any**
count, however small the view, is therefore 1,048,576 pixels.

Measured on the published `buildings-dated` mosaic:

| view | window | blocks | time |
|---|---|---|---|
| 3.2 km | 82,364 px | 4 | ~280 ms |
| 12.6 km | 1,317,818 px | 6 | ~280 ms |
| 50.6 km | 21,085,093 px | 35 | ~2,500 ms |

The middle two rows differ sixteenfold in pixels and cost the same. So the budget is
`NEAR_MAX_BLOCKS = 12`, roughly a 25 km view — most of an island, which is the range
over which a reader expects the number to follow the map. Beyond it the published
island totals are instant and exact, and counting would buy nothing but seconds of
waiting.

**This was set by testing, not by argument.** A first attempt used a 2 km threshold,
and in use the number then sat unchanged on an island total across a tenfold zoom
range, which reads as a broken panel rather than a design.

### Decoding runs on workers

Even a modest window inflates more than a million pixels, and a 25 km view inflates
tens of millions, so `readRasters` is given a `geotiff.js` worker pool. Measured on a
25 km view over Tenerife: **533 and 601 ms with the pool, against 616, 878 and
1,013 ms without**. The pool survives bundling because geotiff.js embeds its worker
source and builds it from a Blob — which is not obvious, and is why the numbers are
recorded. It is constructed lazily inside a `try`, because worker creation is the
kind of thing a bundler or a strict CSP can break, and a slower readout beats one
that throws.

### The slider still fetches nothing

§1 is about the map; the same has to be true of the number, or the slider would
start a decode per year. It is, by construction: one pass accumulates the ground
area held by **every** stored value, and because the rasters encode the year a
pixel was first built, the running total of those bins *is* `extent_by_year` for
every year at once. Measured in Chrome with `fetch` and `XMLHttpRequest.open` both
instrumented, a sweep of all 127 years took 16 ms and issued **zero** requests.

### Ground areas ship as data

Turning a pixel count into square kilometres needs the true ground area of a pixel,
which varies with latitude: a "10 m" pixel is 9.98 m north-south but 8.83 m
east-west at 28°N, about 88 m² rather than 100 (CLAUDE.md #2). The viewer must not
work that out for itself — that would be a second definition of ground area, in a
language where nothing checks it, and the wrong answer looks entirely plausible.

`publish.py` writes 22 values into `index.json` (250 bytes), generated by
`raster.row_areas_m2`, the same function every published figure comes from; the
viewer interpolates between them. Sampling every 0.1° is enough because the
quantity follows `cos(latitude)` and moves only about 2 % across the archipelago.
`tests/test_viewer_count.py` runs the real JavaScript lookup over the real table
and compares it against the Python function at eight latitudes.

### What is deliberately not counted

`density-trend` and `loss-events` always report the far way and say so rather than
guessing. The first is on GHSL's native 3-arcsecond grid with values in square
metres per cell, so summing it needs that grid's own cell accounting; the second
reports gain and loss per period across separate bands, which is four numbers
rather than one.

### A defect only a browser could find

`import Map from 'ol/Map.js'` shadows the JavaScript built-in `Map` for the whole
module. The readout's file cache was the first `new Map()` this file had ever
contained, so it silently constructed an OpenLayers map, and every counted view
failed at `.has()` and fell back to island sums. Minified, it read
`yE.has is not a function`, nowhere near the import that caused it. The import is
now `OLMap`, and `viewer/app.test.js` refuses any import bound to the name of a
built-in.

## 6. Not done
<!-- figures: viewer/count.js @ 2026-09-25 -->

**A per-zone panel beyond what the view implies** — statistics for a named
municipality or protected area (M5) — and deep-linking of view state into the URL.
Views up to about most of an island are counted exactly; above that the answer is
whole islands, and a reader looking at two islands at once has no way to ask about
the ground between them. The options
were measured and are recorded in the plan: a coverage grid (retired — it cannot
carry per-year at acceptable size) and a sparse per-cell table, which does not need
a database to be useful because what makes it small is sparsity, not query
execution.

---

## 7. Deployment
<!-- figures: scripts/publish.py; scripts/upload_r2.py; measured:curl range-request pre-flight against the live site on 2026-09-20 and against R2 on 2026-09-24; measured:Worker CPU per invocation from wrangler tail and the Workers dashboard on 2026-09-23; external:Cloudflare Workers platform limits (CPU time per request on the Free plan) read 2026-09-23 @ 2026-09-24 -->

Live, unannounced, at **`https://sensisat.org`** (2026-09-20).

```bash
python scripts/build.py --all     # produce the layers
python scripts/publish.py         # bundle the JS, assemble dist/site and dist/data
python scripts/upload_r2.py       # dist/data/ -> R2   (only when the layers changed)
npx wrangler deploy               # dist/site/ -> Workers Assets
```

**Two trees, because they go to two hosts.** `dist/site/` is the shell — 7 files,
0.88 MiB — on Workers Assets, where requests to static assets are free and
unlimited. `dist/data/` is the published layers, served from R2 (§5 carries the current total). They are
split because the rasters need a host that implements `Range` and the assets platform
does not, and because Workers Assets offers no way to exclude a directory from upload
(`.assetsignore` was tried on 2026-09-24 and is not honoured — it uploads the ignore
file too). The repository is not the website: scripts, docs, raw downloads and
notebooks reach neither.

`dist/site/_headers` (from `viewer/_headers`) carries a Content Security Policy and
three hardening headers, applied to every response at no cost. **Its `connect-src`
must name the R2 origin.** Without it the browser blocks every raster fetch and the
map stays empty — with no network error any test would catch.

### The thing that nearly stopped this working

**Cloudflare's Workers Assets platform ignores the `Range` header.** Measured on
the live site: five consecutive requests for the first kilobyte of a 1.5 MB COG
all came back `200` with the whole file. Since a Cloud-Optimized GeoTIFF is
*defined* by being read in slices, and geotiff.js fails outright rather than
degrading, every data layer silently failed to render while the page itself looked
fine.

Neither obvious escape worked: classic Pages, which supported ranges, can no
longer be created for a new project, and R2 has to be enabled in the dashboard
first.

The first fix was `worker/index.js` — a Worker in front of the asset store doing the
slicing the platform does not, setting immutable cache headers on rasters while it
was there (guardrail G4). It needed `"run_worker_first"` in `wrangler.jsonc`, without
which a request matching a static asset is served straight from the asset store and
the Worker never runs — which is why the first deployment of it changed nothing at
all. It was verified on the live site for normal, suffix and mid-file ranges, and it
served the site from 2026-09-20 to 2026-09-24.

**It was always a workaround, and the measurement says why.** The Worker could not
ask the asset store for a byte range — that is precisely the thing that does not
work — so it had to pull each whole object into memory to return a few kilobytes of
it. Measured 2026-09-23 with `wrangler tail` and the Workers dashboard, that costs
**≈1.27 ms of CPU per MiB buffered** (a memcpy rate), so the Workers Free limit of
**10 ms** per request is crossed at about **8.5 MiB**. The published per-island
layers peak at 4.22 MiB, roughly **4.6 ms**, so the live site was never near the
limit — but the ceiling was real, and it was low enough to block a larger layer.

**Removed 2026-09-24.** R2 honours ranges at the storage layer, so the shim has no
reason to exist. `worker/index.js` is deleted and `wrangler.jsonc` carries no
`main`, no `binding` and no `run_worker_first`: the deployment has **no script at
all**. Cloudflare's API states it plainly — a tail request returns *"Cannot tail a
Worker which only has assets"* `[code: 100311]`. There is no CPU limit to exceed
because there is no execution. The pre-flight against R2 was run first, on a
throwaway bucket, for normal, suffix and unsatisfiable ranges, comparing returned
bytes against the local file; `docs/design/scaling.md` §6 records it and the four
traps it found.

### What a visit actually costs, measured in production

| | |
|---|---|
| requests to origin | **6** (was ~70 before the runtime index) |
| COG bytes read for Gran Canaria's buildings | **64.3 KiB** of a 1.5 MB file |
| JS bundle | 850 KB, 292 KB gzipped, cached forever after first visit |

That is the architecture working as designed: the file is big, the read is small,
and moving the time slider fetches nothing at all.
