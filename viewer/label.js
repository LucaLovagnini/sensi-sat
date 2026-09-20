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
const CHIP_M = 150;          // metres across the chip (30 m cell = 20 % of it)
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
  el('flag').innerHTML = flagFor(label);

  const done = state.points.filter((q) => isDone(q.id)).length;
  const already = isDone(p.id) ? ' · already answered' : '';
  el('count').textContent = `${done} / ${state.points.length} complete · point ${state.i + 1}${already}`;
  el('fill').style.width = `${100 * done / state.points.length}%`;
  el('sub').textContent = `${state.island} · ${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`;
}

/**
 * Some answers deserve a second look before moving on.
 *
 * "Built in 2015, not built in 2024" means a demolition, and that is rare: real
 * loss runs at 0.017-0.052 % a year, and the cadastre this is measuring is
 * growth-only by construction, so it can never report one. A genuine demolition is
 * therefore a real finding; an accidental one is a keystroke away, since `1` and
 * `W` sit next to each other.
 *
 * This shows a banner rather than a confirmation dialog, and the difference
 * matters. A dialog on one specific answer makes that answer more costly to give,
 * which would quietly push an interpreter away from recording demolitions — the
 * exact events we most want to hear about. The banner informs without charging a
 * price. Auto-advance is suspended for this pair alone, so the note is seen rather
 * than flashing past.
 */
function flagFor(label) {
  if (label['2015'] === 'built' && label['2024'] === 'not') {
    return 'You have marked this as <strong>demolished between 2015 and 2024</strong>. '
         + 'That is rare — real loss runs at about 0.02–0.05 % a year — and the map '
         + 'being checked cannot report it at all, so a genuine one is a real finding. '
         + 'If that is what you see, add a note and press Next. If it was a slip, just '
         + 'answer again.';
  }
  return '';
}

function setAnswer(year, value) {
  const p = state.points[state.i];
  const label = state.labels[p.id] || (state.labels[p.id] = {});
  // Whether this point was already finished BEFORE this click. Correcting a past
  // answer must not move the page: going back to fix two dates on one point, only
  // to be thrown forward after the first click, loses the second correction.
  const wasComplete = Boolean(label['2015'] && label['2024']);
  label[year] = value;
  label.note = el('note').value || undefined;
  // When this point was first judged. Recorded so the published effort figure is a
  // measurement rather than the plan's estimate; the scorer ignores it entirely.
  label.t = label.t || Date.now();
  save();
  render();
  // Advance only when both dates are answered, so an accidental click does not
  // skip past a point that is still half judged — and never advance automatically
  // out of a flagged pair, so its banner is actually read.
  if (!wasComplete && label['2015'] && label['2024'] && !flagFor(label)) setTimeout(next, 180);
}

/**
 * Next moves by exactly one, in both directions, always.
 *
 * It used to skip forward over anything already judged, which is right while
 * labelling and wrong while reviewing: stepping back three points to fix them meant
 * the first correction catapulted you to the far end of the sample. Resuming a
 * sitting is a different intention from stepping, so it gets its own control —
 * `resume`, which is also what the tool does on load.
 */
const next = () => { if (state.i < state.points.length - 1) { state.i++; render(); } };
const back = () => { if (state.i > 0) { state.i--; render(); } };
const resume = () => { state.i = firstUnanswered(); render(); };

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
    t: state.labels[p.id]?.t ?? null,
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
  el('next').onclick = next;
  el('resume').onclick = resume;
  el('save').onclick = download;
  el('note').onchange = () => { const p = state.points[state.i];
    (state.labels[p.id] || (state.labels[p.id] = {})).note = el('note').value || undefined; save(); };

  addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    const k = KEY[e.key.toLowerCase()];
    if (k) { e.preventDefault(); setAnswer(k[0], k[1]); }
    else if (e.key === 'ArrowRight') next();
    else if (e.key === 'ArrowLeft') back();
    else if (e.key === 'r' || e.key === 'R') resume();
  });

  render();
})();
