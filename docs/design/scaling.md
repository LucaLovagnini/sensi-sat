# Scaling, cost, and guardrails

What happens if SensiSat gets popular — and how to make a surprise bill
structurally impossible rather than merely unlikely.

Evidence tags: `[measured]` on this build · `[est]` arithmetic from measured
numbers · `[list price]` a provider's published price, which changes and must be
re-checked before committing.

---

## 1. What one visitor actually costs
<!-- figures: measured:Chrome DevTools network panel over the local viewer on 2026-09-20 @ 2026-09-20 -->

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
<!-- figures: external:Cloudflare / AWS / Netlify list prices read 2026-09-20; measured:arithmetic on §1's per-visit cost @ 2026-09-20 -->

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
<!-- figures: measured:Chrome DevTools network panel on 2026-09-20 @ 2026-09-20 -->

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
<!-- figures: scripts/publish.py; measured:curl range-request pre-flight against the live site on 2026-09-20 @ 2026-09-20 -->

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

## 6. R2, and no Worker at all — **done 2026-09-24**
<!-- figures: scripts/publish.py; scripts/upload_r2.py; external:Cloudflare R2 pricing and documentation read 2026-09-20; external:Cloudflare Workers platform limits read 2026-09-23; measured:Worker CPU per invocation from wrangler tail and the Workers dashboard on 2026-09-23; measured:R2 range pre-flight on r2.dev and on data.sensisat.org, 2026-09-24 @ 2026-09-24 -->

Decided 2026-09-20, deferred until a domain existed, **shipped 2026-09-24**. The
site now serves its shell from Workers Assets and its rasters from R2, and runs **no
Worker script at all**. Cloudflare's API is the plainest proof: a tail request
returns *"Cannot tail a Worker which only has assets"* `[code: 100311]`.

### Why the Worker existed, and what it cost

Workers Assets ignores the `Range` header (§4, G1), so `worker/index.js` fetched each
raster and sliced it by hand. It worked, it was verified, and it was free at our
scale. It was also a workaround, for a reason worth stating precisely: **the Worker
could not ask the asset store for a byte range, because that is the exact thing that
does not work.** So it pulled each whole object into memory to return a few kilobytes
of it.

Measured on a throwaway Worker on 2026-09-23, with `wrangler tail` and the Workers
dashboard, that costs about **1.27 ms of CPU per MiB buffered** — a memcpy rate, not
a bug to optimise away:

| asset | size | CPU (median) |
|---|---|---|
| `covered-agriculture` | 2.20 MiB | 2 ms |
| `density-trend` | 4.88 MiB | 5 ms |
| `settlement-era-a` | 6.98 MiB | 7 ms |
| `density-current` | 12.43 MiB | 15 ms |

The Workers Free limit is **10 ms of CPU per request**, so the line is crossed at
about **8.5 MiB**. The published per-island layers peak at 4.22 MiB, roughly 4.6 ms,
so the live site was never near it — but the ceiling was real, and low enough that a
single larger layer would have broken the map for everyone. Cloudflare allows an
isolate "flexibility ... for cases where your Worker **infrequently** runs over" and
terminates with **Error 1102** when one "starts hitting the limit **consistently**",
so the failure would have arrived exactly when the site got attention.

**R2 does the slicing at the storage layer**, so the shim has no reason to exist.
There is no CPU limit to exceed because there is no execution, and the
invocation cap (100,000/day) no longer applies either.

### What it costs — measured against published limits `[list price 2026-09-20]`

| | R2 free tier | our usage at 10k visitors/month | headroom |
|---|---|---|---|
| storage | 10 GB-month | **0.06 GB** | 165x |
| Class B reads (a GET, including a range request) | 10M/month | ~20,000 | **500x** |
| Class A writes | 1M/month | ~140 per data change | irrelevant |
| egress | — | — | **free, no tier** |

The read allowance runs out at roughly **5 million visits a month**; beyond that
reads are $0.36/million, so 10M visits would be about **$4**. That is *more* headroom
than the Workers path it replaced, which was free to ~1.5M visits/month.

### The architecture

- **`dist/data/`** — the COGs, STAC and `index.json` — in bucket `sensisat-data` on
  `data.sensisat.org`. Native ranges, free egress, Cloudflare cache in front.
- **`dist/site/`** — HTML, CSS, one JS bundle — on Workers Assets, where
  *"requests to static assets are free and unlimited"*.
- **no Worker.** `worker/index.js`, the `run_worker_first` routing and the
  invocation budget are all gone.

`publish.py` writes the two trees; `scripts/upload_r2.py` uploads the data one, only
what changed, by SHA-256. They are separate trees rather than one because **Workers
Assets has no way to exclude a directory from upload**: `.assetsignore` was tried on
2026-09-24 and is not honoured by wrangler 4.135 — it merely uploads the ignore file
as well.

### The pre-flight, run before the domain was bought

Step 6 below was done *first*, deliberately, on the `r2.dev` dev URL. Cloudflare
restricts that URL for serving production traffic, not for testing, and this whole
detour exists because a platform's documented behaviour was trusted once already.
Verified: a normal range returns `206` with the right `Content-Range` **and bytes
identical to the local file** (`cmp` — a 206-shaped reply is not the same as a
correct one); the suffix range `bytes=-500` that geotiff.js uses to find the COG
footer works; a range past the end returns `416`, not `200` with the whole object.
All three were re-verified on `data.sensisat.org` after the real upload.

### Four traps, every one of which fails silently

1. **`wrangler r2 object put` defaults to a LOCAL simulated bucket** and prints
   "Upload complete" either way. Pass `--remote`. Eight uploads went into a directory
   on the laptop before `bucket info` reading `object_count: 0` gave it away — and
   that field is itself eventually consistent, so verify by fetching an object.
2. **R2's CORS document is `{"rules": [...]}`**, not S3's top-level array, and the
   default is *no* CORS: the OPTIONS preflight returns `403` until configured.
   `content-range` must be listed in `exposeHeaders`. Note that CORS is a browser
   policy and **never access control** — a client sending no `Origin` still receives
   every byte.
3. **The CSP in `viewer/_headers` must name the data origin in `connect-src`**, or
   the browser blocks every raster fetch and the map stays empty with no network
   error any test would catch.
4. **`viewer/app.js` fetches `<data>/statistics/layers.json` with `.catch(() => null)`** —
   forget to upload it and the statistics disappear silently. The same shape as the
   stale-`index.json` trap (CLAUDE.md #20).

### What is still open

Putting the **site itself** on `sensisat.org` is a separate change: the canonical URL
appears in the page's "How to cite" block, in `LICENSE-DATA.md`'s attribution, and in
`verify_m4b.py`'s live link checks, so it is a deliberate edit with a re-attestation,
not a DNS switch. The **WAF rate-limiting rule** from the security review is now
possible too, since it also needed a zone.
