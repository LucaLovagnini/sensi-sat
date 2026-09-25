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
  const builtins = ['Map', 'Set', 'Array', 'Object', 'Image', 'Event', 'Error',
                    'Promise', 'Date', 'Number', 'String', 'Text', 'Range'];
  for (const [, bound] of CODE.matchAll(/^import\s+(\{[^}]*\}|[A-Za-z_$][\w$]*)/gm)) {
    for (const name of bound.replace(/[{}]/g, '').split(',')) {
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
