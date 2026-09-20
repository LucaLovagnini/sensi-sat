# M4 — the viewer

**What exists:** an interactive map over M2's seven published layers, running from
static files with no server of any kind. Built and verified in a browser; **not yet
deployed** to public hosting.

```bash
python viewer/serve.py       # then open http://127.0.0.1:8777/viewer/
```

---

## 1. Why the time slider costs nothing

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
  side by side *hide* change: Gran Canaria grew 9 % between 1995 and 2015 and the
  two maps look identical to the eye.

**"We don't know" survives to the screen.** The undated class — pixels that are
built but carry no year — is drawn in its own colour and never given an invented
date. In the "added since" view it is **hidden**, with the legend saying so,
because a pixel with no year cannot honestly be placed in a period.

**The 2015/2016 seam is announced, not smoothed.** Each settlement era carries a
note saying what it is and that it does not join continuously to the other, and
that the two must not be added together because they share the 2016 baseline.

Per-island figures come from the published statistics, so the number on screen is
the same number the build measured: 35.647 km² of buildings on Gran Canaria,
27.058 km² of greenhouses, 109.682 km² sealed.

## 5. Not done

**Publishing.** The plan's M4 is "publish + viewer"; this is the viewer. The output
is already exactly what a static host would serve, so deployment is an upload plus
a decision about where — Cloudflare R2 or S3 + CloudFront — and that decision has
not been taken.

Also absent: a per-zone statistics panel beyond the island total (M5), and any
deep-linking of state into the URL.

---

## 6. Deployment

Live, unannounced, at **`https://sensisat.ensi-at.workers.dev`** (2026-09-20).

```bash
python scripts/build.py --all     # produce the layers
python scripts/publish.py         # bundle the JS, assemble dist/, check the size budget
npx wrangler deploy               # deploy (needs `wrangler login` once)
```

`dist/` holds the viewer at its root and the published layers under `data/` — 137
files, 60.6 MiB. The repository is not the website: scripts, docs, raw downloads
and notebooks never reach the public host.

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

The fix is `worker/index.js` — a Worker in front of the asset store that does the
slicing the platform does not, and sets the immutable cache headers on rasters
while it is there (guardrail G4). It only works with:

```jsonc
"assets": { "directory": "dist", "binding": "ASSETS", "run_worker_first": true }
```

Without `run_worker_first`, a request matching a static asset is served straight
from the asset store and the Worker never runs — which is why the first deployment
of it changed nothing at all.

Verified on the live site for normal, suffix and mid-file ranges.

### What a visit actually costs, measured in production

| | |
|---|---|
| requests to origin | **6** (was ~70 before the runtime index) |
| COG bytes read for Gran Canaria's buildings | **64.3 KiB** of a 1.5 MB file |
| JS bundle | 850 KB, 292 KB gzipped, cached forever after first visit |

That is the architecture working as designed: the file is big, the read is small,
and moving the time slider fetches nothing at all.
