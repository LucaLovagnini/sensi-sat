# Scaling, cost, and guardrails

What happens if SensiSat gets popular — and how to make a surprise bill
structurally impossible rather than merely unlikely.

Evidence tags: `[measured]` on this build · `[est]` arithmetic from measured
numbers · `[list price]` a provider's published price, which changes and must be
re-checked before committing.

---

## 1. What one visitor actually costs

The important correction first: **the per-island file sizes are not what a visitor
downloads.** A Cloud-Optimized GeoTIFF is read by HTTP range request — the client
fetches a header, learns the layout, and then asks only for the overview level and
tiles on screen. Tenerife's building layer is a 1.5 MiB file; rendering it at
island zoom cost **64 KiB** `[measured]`.

A cold visit — first time, nothing cached — measured on this build:

| | requests | bytes (gzipped) |
|---|---|---|
| app shell (HTML + CSS + JS) | 3 | 11 KiB |
| STAC catalogue walk | **64** | 77 KiB |
| COG range reads (one layer, island + one city zoom) | ~2 | ~64 KiB |
| **total from our origin** | **~70** | **~150 KiB** |

A repeat visit costs ~0: everything is static and cacheable.

For planning, assume an *engaged* visitor who opens several layers and islands:
**~400 KiB and ~120 requests** `[est]`. That is the number used below, and it is
deliberately about 2.5× the measured cold visit.

## 2. What that costs at each scale

| visitors / month | egress `[est]` | requests `[est]` |
|---|---|---|
| 1,000 (design target) | 0.4 GB | 120 k |
| 10,000 | 4 GB | 1.2 M |
| 100,000 | 40 GB | 12 M |
| 1,000,000 | 400 GB | 120 M |
| 10,000,000 (front page of everything) | 4 TB | 1.2 B |

Against hosts, at the 4 TB row — the "it went genuinely viral" case `[list price]`:

| host | egress cost at 4 TB/month | note |
|---|---|---|
| **Cloudflare Pages / R2** | **$0** | egress is free by design, not by allowance |
| S3 + CloudFront | ~$255 | 1 TB/month free, then ~$0.085/GB |
| GitHub Pages | — | 100 GB/month soft limit; not for this |
| Netlify | ~$2,145 | 100 GB free, then ~$55 per 100 GB |

Request costs land differently: R2 bills reads (~$0.36/million after 10 M free),
but a CDN in front collapses origin reads to near zero because every visitor wants
the same handful of files. CloudFront bills requests too, and at 1.2 B they would
dominate the bill.

**The conclusion is not "Cloudflare is cheaper".** It is that Cloudflare's egress
is *structurally* zero, so no traffic event can produce a bandwidth bill at all.
Everywhere else, cost is a function of popularity and must be watched.

## 3. The risk that is not cost

At a million visitors our own bandwidth is free and our origin is nearly idle. The
things that actually break are **other people's servers**:

- **IGN's PNOA WMS.** The aerial basemaps are a public service run by the Spanish
  national mapping agency. They have no contract with us and no reason to absorb a
  traffic spike. Hammering them is a courtesy and terms-of-use problem, and the
  realistic outcome is being blocked — which breaks the feature for everyone.
- **Esri's tile service.** Same shape, commercial terms.
- **esm.sh.** The viewer imports OpenLayers as ES modules, which costs **248
  module requests** on a cold load `[measured]`. That is a third party on the
  critical path of every page load, and a performance problem before it is
  anything else.

None of these bill us. All of them can take the site down.

## 4. Guardrails

Ordered by how much they protect, not by effort.

**G1 — Host where egress is free.** Cloudflare. This is the only guardrail that
removes the failure mode instead of bounding it: there is no bandwidth meter to run
away. **Status: DONE — deployed 2026-09-20 to `sensisat.ensi-at.workers.dev`.**

> **A platform limitation worth knowing before anyone repeats this.** Cloudflare's
> Workers Assets platform **ignores the `Range` header**: measured on the live
> site, five consecutive requests for the first kilobyte of a 1.5 MB COG all
> returned `200` with the entire file. That breaks the premise the project is built
> on, and geotiff.js fails outright rather than degrading, so no data layer
> rendered at all.
>
> Classic Pages, which did support ranges, can no longer be created — `wrangler
> pages project create` always targets the new platform, and `pages deploy --force`
> needs a project that already exists there. R2 supports ranges but must be enabled
> in the dashboard first.
>
> The fix is `worker/index.js`: a Worker in front of the asset store that does the
> slicing the platform does not. It needs **`run_worker_first: true`** in
> `wrangler.jsonc` — without it a request matching a static asset is served
> directly and the Worker never runs, which is why the first attempt changed
> nothing. Verified working for normal (`bytes=0-1023`), suffix (`bytes=-500`) and
> mid-file ranges.

**G2 — Collapse the STAC walk to one request. Status: DONE.** A cold load went
from ~70 requests to **6**, measured on the live site. The viewer currently fetches 64
JSON files to learn what exists — a catalogue, 7 collections and 56 items. STAC's
nested form is right for a *catalogue*; it is wrong for a *page load*. Publish one
combined index alongside it and the cold load drops from ~70 requests to ~7.
Biggest single win, for both cost and speed.

**G3 — Bundle the JavaScript. Status: DONE.** One file (850 KB, **292 KB
gzipped**) instead of 248 module requests, and no runtime dependency on esm.sh
being up. Built with esbuild via `npm run build` in `viewer/`.

**G4 — Immutable caching.** Serve the published layers with
`Cache-Control: public, max-age=31536000, immutable` on versioned paths, so the
CDN answers essentially every request and the origin is touched once per edge per
version. **Status: not done — the dev server deliberately sends `no-cache`.**

**G5 — Do not default to someone else's aerial imagery.** The default basemap
stays the light map; PNOA and Esri are opt-in per session, which is already how the
viewer behaves. If traffic ever justifies it, cache tiles at our own edge rather
than proxying more load onto IGN. **Status: done.**

**G6 — A published-size budget. Status: DONE.** `scripts/publish.py` fails above
100 MiB. Currently 60.6 MiB, of which the sealing layer and its confidence
companion are more than half — this was never hypothetical.

**G7 — Billing alerts, not just free tiers.** Whatever the host, set an alert at a
figure that would be surprising (say $5). Free tiers end; alerts notice.
**Status: not done.**

## 5. What this means for the architecture

Nothing needs to change. The design that came out of M0 — static files, no tile
server, year-first-built encoding so the time slider fetches nothing — is also the
design that scales, because there is no compute per visitor to scale. A million
visitors and a thousand visitors differ only in how many times a CDN serves the
same bytes.

The tile server that was parked in decision 4 stays parked. It would add a
per-request cost exactly where there currently is none.

---

## 6. The intended end state: R2, and no Worker at all

Decided 2026-09-20, **deferred until `sensisat.org` is registered**. Recorded here
because the current deployment is a workaround, and workarounds that are not
written down become permanent by accident.

### Why the Worker exists, and why it should not

Cloudflare's Workers Assets platform ignores the `Range` header (§4, G1), so
`worker/index.js` fetches each raster and slices it by hand. It works, it is
verified, and it is free at our scale. It is also ~90 lines of our code on the
critical path of every map tile, pulling a whole object into memory to return a
few kilobytes of it.

**R2 does this properly at the storage layer.** Range requests are fundamental to
object storage, so an R2-hosted COG needs no shim at all.

### What it would cost — measured against published limits `[list price 2026-09-20]`

| | R2 free tier | our usage at 10k visitors/month | headroom |
|---|---|---|---|
| storage | 10 GB-month | **0.06 GB** (the whole site is 60.6 MiB) | 165× |
| Class B reads (a GET, including a range request) | 10M/month | ~20,000 | **500×** |
| Class A writes | 1M/month | ~137 per deploy | irrelevant |
| egress | — | — | **free, no tier** |

The read allowance runs out at roughly **5 million visits a month**; beyond that
reads are $0.36/million, so 10M visits would be about **$4**.

That is *more* headroom than the present setup, not less. Workers allows 100,000
requests/day (~3M/month), so today we are free to ~1.5M visits/month; R2 would be
free to ~5M.

### The architecture it produces

- `data/` (the COGs, STAC and index) in an R2 bucket on a subdomain — native
  ranges, free egress, Cloudflare cache in front.
- the viewer shell (HTML, CSS, the JS bundle) stays on Workers Assets, where
  *"requests to static assets are free and unlimited"*.
- **no Worker.** `worker/index.js`, the `run_worker_first` routing and the billing
  alert that exists only because of them all go away.

### Why it is blocked

R2 has exactly two ways to be public, and only one is usable. Cloudflare's own
wording on the first: the `r2.dev` subdomain is *"rate-limited and should only be
used for development purposes"*, *"intended for non-production traffic"*. The
second — a custom domain — requires the domain to be **a zone in the same
Cloudflare account**.

So this waits on `sensisat.org` being registered and its DNS moved to Cloudflare.

### The steps, when that happens

1. Register `sensisat.org` (Cloudflare Registrar sells at cost) and add it as a zone.
2. Enable R2 in the dashboard — a one-time click that also accepts its terms.
3. `wrangler r2 bucket create sensisat-data`, upload `dist/data/`, attach it to a
   subdomain such as `data.sensisat.org`, and set a CORS rule allowing the site's
   origin.
4. Point `DATA_CANDIDATES` in `viewer/app.js` at that subdomain.
5. Delete `worker/index.js`, drop `main` and `run_worker_first` from
   `wrangler.jsonc`, and redeploy.
6. Re-run the range-request pre-flight against the new origin before trusting it —
   the whole reason this section exists is that the platform's behaviour was not
   what its documentation implied.
