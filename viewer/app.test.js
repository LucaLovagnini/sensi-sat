/**
 * Source-level invariants of app.js.
 *
 * These read the file rather than run it, because app.js needs a browser: it builds
 * an OpenLayers map against a DOM and a WebGL context. That rules out asserting its
 * behaviour here — but several of its defects are visible in the text, and each one
 * below is a defect that actually happened.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

const SRC = readFileSync(new URL('./app.js', import.meta.url), 'utf8');
/** The file with comments and template/quoted strings removed. */
const CODE = SRC
  .replace(/\/\*[\s\S]*?\*\//g, '')
  .replace(/^\s*\/\/.*$/gm, '');

test('no import shadows a JavaScript built-in', () => {
  // This one cost real time. `import Map from 'ol/Map.js'` shadows the built-in Map
  // for the whole module, so `new Map()` silently constructs an OpenLayers map —
  // which then fails at the first `.has()` with "yE.has is not a function", in
  // minified code, nowhere near the import that caused it. The readout's file cache
  // was the first `new Map()` this file ever had, so the trap lay unsprung for
  // months.
  // Node's own globals, plus the browser constructors Node does not have. A
  // hand-written list alone would miss the next one nobody thought of.
  const builtins = [...Object.getOwnPropertyNames(globalThis),
                    'Image', 'Text', 'Range', 'Node', 'Element', 'Document', 'Window',
                    'Option', 'Audio', 'Selection', 'Location', 'History', 'Screen'];
  // Every name the import clause binds: `import X`, `import {A, B as C}` and
  // `import X, {A}` alike.
  for (const [, clause] of CODE.matchAll(/^import\s+([^'"]+?)\s+from\s/gm)) {
    for (const name of clause.replace(/[{}]/g, '').replace(/^\*\s+as\s+/, '').split(',')) {
      const local = name.includes(' as ') ? name.split(' as ')[1] : name;
      assert.ok(!builtins.includes(local.trim()),
                `app.js imports something as "${local.trim()}", shadowing the built-in`);
    }
  }
});

test('the encoding constants are imported, not restated', () => {
  // sensisat/encoding.py is the definition and count.js is its one JavaScript
  // mirror. A third copy here would drift in silence: the map keeps drawing and
  // every year is simply wrong.
  assert.ok(/import\s*\{[^}]*\bYEAR_OFFSET\b[^}]*\}\s*from\s*'\.\/count\.js'/s.test(CODE),
            'app.js must import YEAR_OFFSET from count.js');
  assert.ok(!/^const\s+(YEAR_OFFSET|UNDATED)\s*=/m.test(CODE),
            'app.js redefines an encoding constant that count.js already owns');
});

test('moving the slider does not re-read the raster', () => {
  // The viewer's central design property: the year is a threshold in a GPU style
  // expression over pixels already in memory, and the readout is a lookup in a
  // histogram already computed. The slider handler may restyle and re-render; it
  // must never call the things that fetch.
  const handler = CODE.slice(CODE.indexOf("el('year').oninput"));
  const body = handler.slice(0, handler.indexOf('\n  };'));
  for (const forbidden of ['updateScope', 'scheduleScope', 'showLayer', 'fetch']) {
    assert.ok(!body.includes(forbidden),
              `the slider handler calls ${forbidden}, which can issue a request`);
  }
});

test('the readout is recomputed when the map settles, not on every frame of a pan', () => {
  // `change:center` fires hundreds of times during a drag and would start a decode
  // for each. Only the view the user stops on is worth measuring.
  assert.ok(/map\.on\('moveend'/.test(CODE), 'nothing recomputes the readout on moveend');
  assert.ok(!/map\.on\('change:center'/.test(CODE));
  assert.ok(/setTimeout\(updateScope/.test(CODE), 'moveend is not debounced');
});

test('the dead statistics/layers.json fetch is gone', () => {
  // C2 moved those figures into index.json. It stayed on the critical path for a
  // while afterwards, ~10 KiB fetched on every cold load for no consumer at all.
  assert.ok(!CODE.includes('statistics/layers.json'));
  assert.ok(!/\bstate\.stats\b/.test(CODE));
});

test('the readout counts full resolution, never an overview', () => {
  // getImage(0) is the full-resolution image; 1..n are the pre-made coarse copies.
  // Counting an overview reads 104.3 km² as 3,310.3 (see count.js).
  assert.ok(/getImage\(0\)/.test(CODE),
            'the counting path must open image 0, the full-resolution one');
});

test('the published data root carries no branch-only prefix', () => {
  // A constant marked BRANCH ONLY is a note, not a defence. This one pointed at a
  // `v2/` prefix while the archipelago viewer ran beside production, and merging it
  // would have pointed the live site at a path only the preview had. publish.py now
  // emits both index shapes into the one file at the root, so there is nothing to
  // remember on merge day — and nothing here to get wrong.
  const m = CODE.match(/const R2_DATA = '([^']+)'/);
  assert.ok(m, 'R2_DATA is not declared');
  const url = new URL(m[1]);
  assert.equal(url.pathname.replace(/\/$/, ''), '',
               `R2_DATA points at "${url.pathname}", not the bucket root`);
  assert.ok(!/BRANCH ONLY/i.test(SRC), 'app.js still carries a BRANCH ONLY marker');
});

test('the decode runs off the main thread', () => {
  // A 25 km view inflates tens of millions of pixels out of the COG's compressed
  // blocks. On the main thread that is a visibly frozen page: 616, 878 and 1,013 ms
  // measured without the worker pool against 533 and 601 with it.
  //
  // Nothing else in the suite would notice if `pool: pool()` were dropped. Every
  // number stays correct — the page merely stops responding for a second — and node
  // cannot observe a freeze at all. So the wiring is asserted in the source, which
  // is the only place it is visible outside a browser.
  assert.ok(/import\s*\{[^}]*\bPool\b[^}]*\}\s*from\s*'geotiff'/.test(CODE),
            "app.js must import geotiff's Pool");
  assert.equal(CODE.split('.readRasters(').length - 1, 1,
               'a second decode call has appeared; this test checks only the first');
  const call = CODE.slice(CODE.indexOf('.readRasters('));
  assert.ok(/\bpool:\s*pool\(\)/.test(call.slice(0, call.indexOf('})'))),
            'readRasters decodes on the main thread, freezing the page for ~1 s');
});

test('the decode pool is built lazily and survives failing to be built', () => {
  // Two separate ways this goes wrong, neither of them a wrong number.
  //
  // At module scope, `new Pool()` spawns workers on every page load — including the
  // far-only layers, and including a reader who never zooms in far enough to count
  // anything.
  //
  // Unguarded, it takes the readout down with it. Worker construction is exactly
  // what a bundler or a strict CSP breaks, and the R2 migration has already shown
  // how a CSP failure looks from the outside: nothing, until the number is missing.
  // A readout that is merely slower is better than no readout.
  assert.ok(!/^\s*(const|let|var)\s+\w+\s*=\s*new Pool\(/m.test(CODE),
            'the pool is constructed at module scope, so every page load spawns workers');
  const fn = CODE.slice(CODE.indexOf('function pool()'));
  const body = fn.slice(0, fn.indexOf('\n}'));
  assert.ok(/try\s*\{[\s\S]*new Pool\(\)[\s\S]*\}\s*catch/.test(body),
            'new Pool() is unguarded; if it throws the reader gets no number at all');
});

test('era-b cannot be asked for growth from before its July-2016 baseline', () => {
  // WSF Tracker's epoch 1 is July 2016 — the settlement ALREADY STANDING when the
  // series opens, not growth. "Added since" subtracts the running total at an
  // epoch, so asking from epoch 1 answers with epochs 2..n, which is the intent.
  // Asking from epoch 0 would answer with the whole stock and label it new
  // construction. On Gran Canaria that is the difference between a few km² and
  // essentially the entire built island.
  //
  // The only thing between the two is the Math.max(1, ...) in toEpoch, and this is
  // the one rule in app.js that is pure arithmetic — so it is extracted from the
  // file this test already reads and run, rather than pattern-matched. If it stops
  // being a one-line expression, this fails and says so.
  const m = CODE.match(/const toEpoch = (\(\w+\) => [^;]+);/);
  assert.ok(m, 'toEpoch is no longer the one-line rule this test knows how to read');
  const toEpoch = new Function('return ' + m[1])();

  assert.equal(toEpoch(1900), 1, 'a year before the series clamps to the baseline');
  assert.equal(toEpoch(2016), 1, 'the baseline itself is epoch 1');
  assert.equal(toEpoch(2016.5), 1);
  assert.equal(toEpoch(2017), 2, 'the first epoch that can hold growth');
  assert.equal(toEpoch(2026), 20, 'the last published epoch');
  assert.equal(toEpoch(2100), 20, 'and it does not run off the end either');
  // The step is half a year, the layer's own cadence: epoch 6 is 2019.0 and epoch 7
  // is 2019.5. It ROUNDS rather than truncating, so a slider sitting between two
  // epochs picks the nearer one instead of always the older.
  assert.equal(toEpoch(2019), 6);
  assert.equal(toEpoch(2019.4), 7);
});

test('the island sum is taken from one layer, never across the two eras', () => {
  // Decision 13: era-a (WSF Evolution, 1985-2015) and era-b (WSF Tracker, 2016-2026)
  // SHARE the 2016 baseline, so their extents must never be added — era-b's epoch 1
  // is era-a's 2015 total over again, and a sum counts most of the archipelago twice.
  //
  // No path can do it today, and that is the point of pinning it: sumStats is called
  // once, over the islands of ONE catalogue entry, and the eras are separate entries.
  // This is a regression guard, not a defect to go and find.
  assert.equal(CODE.split('sumStats(').length - 1, 1,
               'sumStats now has more than one call site; each needs checking');
  const line = CODE.slice(CODE.indexOf('sumStats('));
  assert.ok(/^sumStats\(\w+\.map\(\(\w+\) => entry\.islands\[\w+\]\.stats\)\)/.test(line),
            'the sum no longer draws its islands from a single catalogue entry');
  assert.ok(/const entry = state\.catalog\?\.\[state\.layer\]/.test(CODE),
            '`entry` is no longer one layer, so "one entry" no longer means one era');
});
