/**
 * The interpreter's tool for the accuracy assessment (M3).
 *
 * The whole point of this exercise is that the judgement is INDEPENDENT of the
 * map, so nothing here reveals what the map claims. The sample file carries only
 * a location; the map's own answer sits in a separate file the scorer reads later.
 * The points arrive shuffled, so the strata are not labelled in blocks either —
 * seeing thirty "new built" points in a row would tell you what they were.
 *
 * Imagery is fetched per point from the IGN PNOA historical WMS, one chip per
 * date. 100 m across, so the 10 m cell under judgement is a tenth of the frame:
 * big enough to read, small enough to keep its surroundings in view.
 */

const WMS_HISTORIC = 'https://www.ign.es/wms/pnoa-historico';
const WMS_CURRENT = 'https://www.ign.es/wms-inspire/pnoa-ma';
const CHIP_M = 100;          // metres across the chip
const CHIP_PX = 640;

/**
 * The two dates judged, and where each one's imagery comes from.
 *
 * PNOA flies the Canaries about every three years — 2005, 2009, 2012, 2015, 2018,
 * 2021, 2024 — and any other year returns a blank white frame.
 *
 * The recent date deliberately does NOT use the historical service's `PNOA2024`
 * layer. Measured against the current national mosaic, every historical year lines
 * up to within a metre except that one, which sits **20 m east and 10 m north**,
 * detected at thirteen times the confidence of any other comparison. A systematic
 * shift of two whole cells would mean judging different ground in each image, so
 * the recent date is taken from the current mosaic, which agrees with all the
 * historical years.
 */
const DATES = [
  {label: '2015', url: WMS_HISTORIC, layer: 'PNOA2015'},
  {label: '2024', url: WMS_CURRENT, layer: 'OI.OrthoimageCoverage'},
];
const YEARS = DATES.map((d) => d.label);

const state = { points: [], i: 0, labels: {}, island: '', sampleId: '' };

/**
 * Labels are stored per sample, not globally.
 *
 * 650 points is several sittings, so the work has to survive closing the tab — but
 * it must not survive the SAMPLE changing. Keying the store by a fingerprint of the
 * point ids means a redrawn sample starts clean instead of silently counting
 * answers that belong to points which no longer exist, which is exactly what
 * happened when the sampler was fixed mid-session: the progress bar read 5/12
 * while every point on screen was unanswered.
 */
function sampleFingerprint(points) {
  const joined = points.map((p) => p.id).join(',');
  let h = 0;
  for (let i = 0; i < joined.length; i++) h = (Math.imul(31, h) + joined.charCodeAt(i)) | 0;
  return `sensisat-m3-${points.length}-${(h >>> 0).toString(36)}`;
}

/** Has this point been judged on both dates? */
const isDone = (id) => {
  const l = state.labels[id];
  return Boolean(l && l['2015'] && l['2024']);
};

/** The first point still needing an answer — where a returning interpreter belongs. */
function firstUnanswered() {
  const i = state.points.findIndex((p) => !isDone(p.id));
  return i === -1 ? state.points.length - 1 : i;
}

const el = (id) => document.getElementById(id);
const metresToDegrees = (m, lat) => ({
  lat: m / 111_132,
  lon: m / (111_320 * Math.cos(lat * Math.PI / 180)),
});

function chipUrl(lon, lat, date) {
  const d = metresToDegrees(CHIP_M / 2, lat);
  // WMS 1.3.0 with EPSG:4326 takes the bbox as lat,lon — getting this the usual
  // way round silently returns imagery of somewhere else entirely.
  const bbox = [lat - d.lat, lon - d.lon, lat + d.lat, lon + d.lon].join(',');
  return `${date.url}?service=WMS&version=1.3.0&request=GetMap&layers=${date.layer}`
       + `&styles=&crs=EPSG:4326&bbox=${bbox}&width=${CHIP_PX}&height=${CHIP_PX}`
       + `&format=image/jpeg`;
}

function render() {
  const p = state.points[state.i];
  if (!p) return;
  el('img2015').src = chipUrl(p.lon, p.lat, DATES[0]);
  el('img2024').src = chipUrl(p.lon, p.lat, DATES[1]);

  const label = state.labels[p.id] || {};
  document.querySelectorAll('.answer').forEach((row) => {
    const year = row.dataset.year;
    row.querySelectorAll('button').forEach((b) => {
      b.classList.toggle('on', label[year] === b.dataset.v);
    });
  });
  el('note').value = label.note || '';

  const done = state.points.filter((q) => isDone(q.id)).length;
  const already = isDone(p.id) ? ' · already answered' : '';
  el('count').textContent = `${done} / ${state.points.length} complete · point ${state.i + 1}${already}`;
  el('fill').style.width = `${100 * done / state.points.length}%`;
  el('sub').textContent = `${state.island} · ${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`;
}

function setAnswer(year, value) {
  const p = state.points[state.i];
  const label = state.labels[p.id] || (state.labels[p.id] = {});
  label[year] = value;
  label.note = el('note').value || undefined;
  save();
  render();
  // Advance only when both dates are answered, so an accidental click does not
  // skip past a point that is still half judged.
  if (label['2015'] && label['2024']) setTimeout(next, 180);
}

/** Skip forward over anything already judged, so revisiting never means redoing. */
const next = () => {
  for (let k = state.i + 1; k < state.points.length; k++) {
    if (!isDone(state.points[k].id)) { state.i = k; render(); return; }
  }
  if (state.i < state.points.length - 1) { state.i = state.points.length - 1; render(); }
};
const back = () => { if (state.i > 0) { state.i--; render(); } };

const KEY = {'1': ['2015','built'], '2': ['2015','not'], '3': ['2015','unsure'],
             'q': ['2024','built'], 'w': ['2024','not'], 'e': ['2024','unsure']};

function save() {
  try { localStorage.setItem(state.sampleId, JSON.stringify(state.labels)); } catch {}
}

function download() {
  const rows = state.points.map((p) => ({
    id: p.id, lon: p.lon, lat: p.lat,
    label_2015: state.labels[p.id]?.['2015'] ?? null,
    label_2024: state.labels[p.id]?.['2024'] ?? null,
    note: state.labels[p.id]?.note ?? null,
  }));
  const blob = new Blob([JSON.stringify({island: state.island, labelled: new Date().toISOString(),
                                         interpreter_saw_the_map: false, labels: rows}, null, 1)],
                        {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'm3-labels.json';
  a.click();
}

(async () => {
  // ?sample=m3_demo loads the twelve-point trial; the default is the real sample.
  const which = new URLSearchParams(location.search).get('sample') || 'm3';
  const sample = await (await fetch(`../data/processed/${which}/points.json`)).json();
  state.points = sample.points;
  state.island = sample.island;
  state.sampleId = sampleFingerprint(sample.points);
  try { state.labels = JSON.parse(localStorage.getItem(state.sampleId) || '{}'); } catch {}
  state.i = firstUnanswered();   // resume where the last sitting stopped

  document.querySelectorAll('.answer button').forEach((b) => {
    b.onclick = () => setAnswer(b.closest('.answer').dataset.year, b.dataset.v);
  });
  el('back').onclick = back;
  el('skip').onclick = next;
  el('save').onclick = download;
  el('note').onchange = () => { const p = state.points[state.i];
    (state.labels[p.id] || (state.labels[p.id] = {})).note = el('note').value || undefined; save(); };

  addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    const k = KEY[e.key.toLowerCase()];
    if (k) { e.preventDefault(); setAnswer(k[0], k[1]); }
    else if (e.key === 'ArrowRight') next();
    else if (e.key === 'ArrowLeft') back();
  });

  render();
})();
