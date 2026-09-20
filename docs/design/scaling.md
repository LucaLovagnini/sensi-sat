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

**G1 — Host where egress is free.** Cloudflare Pages (or R2 behind the CDN). This
is the only guardrail that removes the failure mode instead of bounding it: there
is no bandwidth meter to run away. **Status: decision pending, blocks M4
publishing.**

**G2 — Collapse the STAC walk to one request.** The viewer currently fetches 64
JSON files to learn what exists — a catalogue, 7 collections and 56 items. STAC's
nested form is right for a *catalogue*; it is wrong for a *page load*. Publish one
combined index alongside it and the cold load drops from ~70 requests to ~7.
Biggest single win, for both cost and speed. **Status: not done.**

**G3 — Bundle the JavaScript.** One file instead of 248 module requests, and no
runtime dependency on esm.sh being up. **Status: not done.**

**G4 — Immutable caching.** Serve the published layers with
`Cache-Control: public, max-age=31536000, immutable` on versioned paths, so the
CDN answers essentially every request and the origin is touched once per edge per
version. **Status: not done — the dev server deliberately sends `no-cache`.**

**G5 — Do not default to someone else's aerial imagery.** The default basemap
stays the light map; PNOA and Esri are opt-in per session, which is already how the
viewer behaves. If traffic ever justifies it, cache tiles at our own edge rather
than proxying more load onto IGN. **Status: done.**

**G6 — A published-size budget in CI.** The build already measures total published
bytes; make it fail above a threshold (say 100 MiB) so a future layer cannot
quietly multiply what every visitor pays for. The sealing layer is already 37 MiB
of the 60 MiB total — this is not hypothetical. **Status: not done.**

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
