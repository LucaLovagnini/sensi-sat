/**
 * Tests for the readout's arithmetic. `cd viewer && npm test`.
 *
 * Every fixture here is small enough that the expected number is worked out by hand
 * and written into the test. That is not fussiness: three ad-hoc scripts written
 * during this design were wrong before they were right — a window compared 891
 * pixels of grid against 900 of truth, "0.66 km² is the undated class" was assumed
 * and turned out to be 0.65 undated plus 0.01 of rounding, and a "whole cell" sum
 * added 11 pixels instead of 121. A harness has to be trusted before it is pointed
 * at real data.
 *
 * Each test is named for the failure it exists to catch.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';

import {
  YEAR_OFFSET, UNDATED, NEAR_MAX_PIXELS, FAR_ONLY_KINDS,
  regimeFor, pixelAreaM2, rowAreas, areaHistogram, statsFromHistogram,
  intersects, islandsInView, sumStats, describe, emptyStats,
} from './count.js';

const close = (a, b, eps = 1e-9) =>
  assert.ok(Math.abs(a - b) <= eps, `${a} !== ${b} (within ${eps})`);

/* ------------------------------------------------------------- the regime */

test('a view the near path can afford is answered the near way', () => {
  assert.equal(regimeFor('year', 1), 'near');
  assert.equal(regimeFor('year', NEAR_MAX_PIXELS), 'near');
});

test('one pixel over the budget switches regime, so the choice cannot drift', () => {
  // The failure: a silent switch to the wrong method. The boundary is the whole
  // point of the constant, so it is asserted rather than assumed.
  assert.equal(regimeFor('year', NEAR_MAX_PIXELS + 1), 'far');
});

test('the layers with no near path never take it, however small the view', () => {
  // density-trend is on GHSL's own 3-arcsecond grid with square metres per cell,
  // and loss-events reports four numbers per period. Counting either as if it were
  // a class raster on the 10 m grid would produce a plausible wrong answer.
  for (const kind of FAR_ONLY_KINDS) assert.equal(regimeFor(kind, 1), 'far');
});

/* --------------------------------------------------------------- the area */

const TABLE = {lat0: 27.0, step: 1.0, values: [90, 80, 70]};   // 27, 28, 29 degN

test('a sampled latitude reads its own value', () => {
  close(pixelAreaM2(TABLE, 27.0), 90);
  close(pixelAreaM2(TABLE, 28.0), 80);
  close(pixelAreaM2(TABLE, 29.0), 70);
});

test('between samples the table is interpolated, not rounded to a neighbour', () => {
  // Rounding to the nearest sample would step the area by a whole sample interval
  // at the midpoint — a discontinuity in a quantity that is smooth in reality.
  close(pixelAreaM2(TABLE, 27.25), 87.5);
  close(pixelAreaM2(TABLE, 28.75), 72.5);
});

test('outside the table the edge value is held, never extrapolated to nonsense', () => {
  close(pixelAreaM2(TABLE, 10), 90);
  close(pixelAreaM2(TABLE, 60), 70);
});

test('row areas are sampled at row CENTRES, not at the top edge', () => {
  // A half-pixel offset biases every row the same way, so the total still looks
  // reasonable and the error survives inspection. raster.row_areas_m2 uses
  // `arange(height) + 0.5`; this must match it exactly or the two disagree.
  const areas = rowAreas(TABLE, {north: 29.0, pixelDeg: 1.0, height: 2});
  close(areas[0], pixelAreaM2(TABLE, 28.5));
  close(areas[1], pixelAreaM2(TABLE, 27.5));
});

test('the module never works out a pixel area for itself', () => {
  // CLAUDE.md #2: a "10 m" pixel is ~88 m² at 28°N, not 100. The moment this file
  // computes its own areas there are two definitions of ground area in the project,
  // and the ~12 % error of counting-and-multiplying looks entirely plausible.
  const src = readFileSync(new URL('./count.js', import.meta.url), 'utf8');
  const code = src.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');   // strip the prose
  for (const forbidden of ['Math.cos', 'Math.PI', '8.983', '111', '1e5']) {
    assert.ok(!code.includes(forbidden), `count.js computes areas: found ${forbidden}`);
  }
});

/* ---------------------------------------------------------- the histogram */

//   value grid, 3 wide x 2 high      row area
//     0   1   1                        100 m²
//   255   1   0                        200 m²
const WINDOW = {values: Uint8Array.from([0, 1, 1, 255, 1, 0]),
                width: 3, height: 2, areas: Float64Array.from([100, 200])};
const HIST = areaHistogram(WINDOW.values, WINDOW);

test('a pixel contributes the area of the row it is in, not a nominal one', () => {
  close(HIST[0], 100 + 200);           // one zero in row 0, one in row 1
  close(HIST[1], 100 * 2 + 200);       // two ones in row 0, one in row 1
  close(HIST[UNDATED], 200);           // one in row 1
});

test('a window whose shape does not match its values is refused, not counted', () => {
  // The 891-versus-900 bug: an origin that lines up and a width that does not.
  // Counting it silently reports an error that is not there.
  assert.throws(() => areaHistogram(WINDOW.values, {...WINDOW, width: 2}), /window/);
  assert.throws(() => areaHistogram(WINDOW.values, {...WINDOW, areas: [100]}), /row areas/);
});

/* --------------------------------------------------------- across the years */

const YEARS = [1900, 1901, 1902];
const YEAR_STATS = statsFromHistogram(HIST, {kind: 'year', years: YEARS});

test('the year series is cumulative — the map shows everything built BY a year', () => {
  // value 1 is 1900 (stored = year - 1899). 400 m² of it, and nothing later.
  close(YEAR_STATS.extent_by_year['1900'], 0.0004);
  close(YEAR_STATS.extent_by_year['1901'], 0.0004);
  close(YEAR_STATS.extent_by_year['1902'], 0.0004);
});

test('undated ground is in the footprint and in no year bin at all', () => {
  // A pixel with no year cannot be placed in a period, which is also why the
  // "appeared since" view refuses to draw it. 0.0006 = 0.0004 dated + 0.0002 undated.
  close(YEAR_STATS.undated_km2, 0.0002);
  close(YEAR_STATS.footprint_km2, 0.0006);
  for (const v of Object.values(YEAR_STATS.extent_by_year)) {
    assert.ok(v <= YEAR_STATS.footprint_km2 - YEAR_STATS.undated_km2 + 1e-12);
  }
});

test('"added since X" is a subtraction of two cumulative totals, in either regime', () => {
  const hist = new Float64Array(256);
  hist[1990 - YEAR_OFFSET] = 1e6;        // 1 km² built in 1990
  hist[2000 - YEAR_OFFSET] = 3e6;        // 3 km² built in 2000
  const s = statsFromHistogram(hist, {kind: 'year', years: [1989, 1990, 1999, 2000]});
  close(s.extent_by_year['1989'], 0);
  close(s.extent_by_year['1990'], 1);
  close(s.extent_by_year['1999'], 1);
  close(s.extent_by_year['2000'], 4);
  close(s.extent_by_year['2000'] - s.extent_by_year['1990'], 3);   // added since 1990
});

test('years the build did not publish are not invented', () => {
  // The two regimes are compared key by key, so the near path emits the published
  // keys rather than a range of its own choosing.
  assert.deepEqual(Object.keys(YEAR_STATS.extent_by_year), ['1900', '1901', '1902']);
});

test('epochs accumulate the same way, and the last one is the footprint', () => {
  const hist = new Float64Array(256);
  hist[1] = 2e6; hist[3] = 1e6;          // epoch 1 baseline, epoch 3 growth
  const s = statsFromHistogram(hist, {kind: 'epoch', epochs: [1, 2, 3]});
  close(s.extent_by_epoch['1'], 2);
  close(s.extent_by_epoch['2'], 2);
  close(s.extent_by_epoch['3'], 3);
  close(s.footprint_km2, 3);
});

/* -------------------------------------------------- the non-year layers */

test('a percentage layer is weighted by its value, never counted as whole pixels', () => {
  // density-current stores how much of each pixel is sealed. Counting a 30 %-sealed
  // pixel as sealed ground overstates it by more than threefold.
  const hist = new Float64Array(256);
  hist[30] = 1e6;                         // 1 km² of ground, 30 % sealed
  hist[100] = 2e6;                        // 2 km² of ground, fully sealed
  close(statsFromHistogram(hist, {kind: 'percent'}).sealed_km2, 0.3 + 2);
});

test('a binary layer counts every non-zero class once', () => {
  const hist = new Float64Array(256);
  hist[0] = 9e6; hist[1] = 1e6; hist[2] = 1e6;
  close(statsFromHistogram(hist, {kind: 'binary'}).area_km2, 2);
});

test('a layer with no near path says so rather than guessing', () => {
  assert.throws(() => statsFromHistogram(new Float64Array(256), {kind: 'trend'}),
                /no near path/);
});

/* ------------------------------------------------------------ open sea */

test('open sea reads 0 km², which is an answer and not a missing value', () => {
  // The requirement, literally: "If no buildings are shown, it should show 0 km²."
  const s = emptyStats('year', {years: [1900, 2020]});
  close(s.extent_by_year['2020'], 0);
  close(s.footprint_km2, 0);
  close(s.undated_km2, 0);
  for (const v of Object.values(s.extent_by_year)) assert.ok(Number.isFinite(v));
});

test('a view over open water names no island, and says so', () => {
  const islands = {Tenerife: {bbox: [-16.95, 27.95, -16.05, 28.65]}};
  assert.deepEqual(islandsInView([-20, 30, -19, 31], islands), []);
  assert.equal(describe('far', [], 8), 'no island in view');
});

/* --------------------------------------------------- which islands are in view */

const ISLANDS = {
  'El Hierro':    {bbox: [-18.20, 27.60, -17.85, 27.90]},
  'La Palma':     {bbox: [-18.05, 28.40, -17.70, 28.90]},
  'Tenerife':     {bbox: [-16.95, 27.95, -16.05, 28.65]},
  'Gran Canaria': {bbox: [-15.90, 27.68, -15.30, 28.25]},
};

test('touching along an edge is not overlapping', () => {
  assert.equal(intersects([0, 0, 1, 1], [1, 0, 2, 1]), false);
  assert.equal(intersects([0, 0, 1, 1], [0.999, 0, 2, 1]), true);
});

test('the islands in view come back west to east, as the map reads', () => {
  const all = islandsInView([-19, 27, -15, 29], ISLANDS);
  assert.deepEqual(all, ['El Hierro', 'La Palma', 'Tenerife', 'Gran Canaria']);
});

test('an island the view only partly covers still counts — and that is the cost', () => {
  // Half of Tenerife on screen still returns Tenerife, whose published figure covers
  // all of it. That is why the far caption names the island instead of saying
  // "in view": the claim would be false and nobody could tell by looking.
  assert.deepEqual(islandsInView([-16.5, 28.0, -16.0, 28.3], ISLANDS), ['Tenerife']);
});

/* ---------------------------------------------------------------- summing */

test('percentages are left out of a sum rather than averaged', () => {
  // A share of one island is not a share of two. A footprint-weighted mean of eight
  // shares lands 0.01 from the published figure — nearly right, which is worse than
  // absent because nothing downstream can tell.
  const out = sumStats([
    {footprint_km2: 1, dated_share_pct: 96.3, low_confidence_share_pct: 4.5},
    {footprint_km2: 3, dated_share_pct: 88.1, low_confidence_share_pct: 9.5},
  ]);
  close(out.footprint_km2, 4);
  assert.ok(!('dated_share_pct' in out));
  assert.ok(!('low_confidence_share_pct' in out));
});

test('a per-year series is summed year by year, not concatenated', () => {
  const out = sumStats([
    {extent_by_year: {1900: 1, 1901: 2}},
    {extent_by_year: {1900: 10, 1901: 20}},
  ]);
  assert.deepEqual(out.extent_by_year, {1900: 11, 1901: 22});
});

test('the change layer keeps gain and loss apart inside each period', () => {
  // Four numbers per period, not one. Collapsing them loses the only thing this
  // layer exists to show.
  const out = sumStats([
    {change_km2: {'2018-2021': {new_cover_km2: 1, loss_of_cover_km2: 0.5}}},
    {change_km2: {'2018-2021': {new_cover_km2: 2, loss_of_cover_km2: 0.25}}},
  ]);
  assert.deepEqual(out.change_km2, {'2018-2021': {new_cover_km2: 3, loss_of_cover_km2: 0.75}});
});

test('labels and flags pass through, because they are the same on every island', () => {
  const out = sumStats([
    {epoch_labels: {1: '2016-07'}, greenhouse_masked: true, epochs: [1975, 1980]},
    {epoch_labels: {1: '2016-07'}, greenhouse_masked: true, epochs: [1975, 1980]},
  ]);
  assert.deepEqual(out.epoch_labels, {1: '2016-07'});
  assert.equal(out.greenhouse_masked, true);
  assert.deepEqual(out.epochs, [1975, 1980]);
});

test('an island missing a key does not drag the sum to nothing', () => {
  // covered-agriculture has no figure on an island with no greenhouses; the sum is
  // over the islands that have one.
  close(sumStats([{area_km2: 5}, {survey_year: 2022}]).area_km2, 5);
});

/* --------------------------------------------------------------- captions */

test('the caption says what was counted, and the two regimes say different things', () => {
  assert.equal(describe('near', ['Tenerife'], 8), 'in view');
  assert.equal(describe('far', ['Tenerife'], 8), 'Tenerife');
  assert.equal(describe('far', ['Tenerife', 'Gran Canaria'], 8), 'Tenerife and Gran Canaria');
  assert.equal(describe('far', ['A', 'B', 'C'], 8), 'A, B and C');
  assert.equal(describe('far', ['A', 'B', 'C', 'D'], 8), '4 islands');
  assert.equal(describe('far', Array(8).fill('x'), 8), 'all eight islands');
});
