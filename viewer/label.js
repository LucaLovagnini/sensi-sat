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

const WMS = 'https://www.ign.es/wms/pnoa-historico';
const CHIP_M = 100;          // metres across the chip
const CHIP_PX = 640;
// PNOA flies the Canaries about every three years: 2005, 2009, 2012, 2015, 2018,
// 2021, 2024. Any other year returns a blank white frame, so the pair judged here
// must be chosen from flights that exist.
const YEARS = [2015, 2024];

const state = { points: [], i: 0, labels: {}, island: '' };

const el = (id) => document.getElementById(id);
const metresToDegrees = (m, lat) => ({
  lat: m / 111_132,
  lon: m / (111_320 * Math.cos(lat * Math.PI / 180)),
});

function chipUrl(lon, lat, year) {
  const d = metresToDegrees(CHIP_M / 2, lat);
  // WMS 1.3.0 with EPSG:4326 takes the bbox as lat,lon — getting this the usual
  // way round silently returns imagery of somewhere else entirely.
  const bbox = [lat - d.lat, lon - d.lon, lat + d.lat, lon + d.lon].join(',');
  return `${WMS}?service=WMS&version=1.3.0&request=GetMap&layers=PNOA${year}`
       + `&styles=&crs=EPSG:4326&bbox=${bbox}&width=${CHIP_PX}&height=${CHIP_PX}`
       + `&format=image/jpeg`;
}

function render() {
  const p = state.points[state.i];
  if (!p) return;
  el('img2015').src = chipUrl(p.lon, p.lat, YEARS[0]);
  el('img2024').src = chipUrl(p.lon, p.lat, YEARS[1]);

  const label = state.labels[p.id] || {};
  document.querySelectorAll('.answer').forEach((row) => {
    const year = row.dataset.year;
    row.querySelectorAll('button').forEach((b) => {
      b.classList.toggle('on', label[year] === b.dataset.v);
    });
  });
  el('note').value = label.note || '';

  const done = Object.values(state.labels).filter((l) => l['2015'] && l['2024']).length;
  el('count').textContent = `${done} / ${state.points.length} complete · point ${state.i + 1}`;
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

const next = () => { if (state.i < state.points.length - 1) { state.i++; render(); } };
const back = () => { if (state.i > 0) { state.i--; render(); } };

const KEY = {'1': ['2015','built'], '2': ['2015','not'], '3': ['2015','unsure'],
             'q': ['2024','built'], 'w': ['2024','not'], 'e': ['2024','unsure']};

function save() {
  try { localStorage.setItem('sensisat-m3-labels', JSON.stringify(state.labels)); } catch {}
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
  const sample = await (await fetch('../data/processed/m3_demo/points.json')).json();
  state.points = sample.points;
  state.island = sample.island;
  try { state.labels = JSON.parse(localStorage.getItem('sensisat-m3-labels') || '{}'); } catch {}

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
