/**
 * SensiSat viewer.
 *
 * The one idea that makes this work without a server: our rasters encode the YEAR
 * a pixel was first built, not whether it was built in a given year. So moving the
 * time slider does not fetch anything — it changes a threshold in a GPU style
 * expression applied to pixels already in memory. One file per island per layer,
 * a few megabytes, read straight off static hosting by HTTP range request.
 *
 * That is also why the frontend is OpenLayers rather than MapLibre: colouring a
 * raster BY PIXEL VALUE is the whole mechanism, and MapLibre still cannot do it
 * (maplibre-gl-js#4479, open, unreleased). Without it every year would need its
 * own pre-rendered tiles — precisely the tile server this design avoids.
 */
import Map from 'ol/Map.js';
import View from 'ol/View.js';
import TileLayer from 'ol/layer/Tile.js';
import WebGLTileLayer from 'ol/layer/WebGLTile.js';
import XYZ from 'ol/source/XYZ.js';
import TileWMS from 'ol/source/TileWMS.js';
import GeoTIFF from 'ol/source/GeoTIFF.js';


const DATA = '../data/processed';
const YEAR_OFFSET = 1899;      // stored value = year - 1899 (see sensisat/encoding.py)
const UNDATED = 255;

const C = {
  built:   [255, 178, 0, 1],      // amber — dated built-up
  added:   [255, 90, 60, 1],      // red — appeared since the chosen year
  undated: [150, 110, 220, 1],    // violet — built, year unknown (never a guess)
  green:   [80, 210, 140, 1],
  loss:    [255, 70, 70, 1],
  gain:    [90, 200, 255, 1],
};

/**
 * How each published layer is read and drawn. Mirrors sensisat/layers.py — the
 * encodings are the contract between the build and this file.
 */
const LAYERS = {
  'buildings-dated': {
    title: 'Buildings, dated (cadastre)',
    note: 'Every registered building and the year it was built. One method from 1900 to 2020, so there is no seam anywhere in it.',
    kind: 'year', min: 1900, max: 2026, start: 2020,
  },
  'settlement-era-a': {
    title: 'Settlement extent to 2015',
    note: 'Settlement clusters including roads, from WSF Evolution. 43 % of the footprint has no year and is drawn in its own colour.',
    kind: 'year', min: 1985, max: 2015, start: 2015,
    seam: 'Ends at 2015. The 2016+ view is a different instrument, resolution and definition — extent drops 26–52 % at the join with nothing demolished.',
  },
  'settlement-era-b': {
    title: 'Settlement extent 2016 →',
    note: 'WSF Tracker, twice a year, greenhouses removed. Epoch 1 is a baseline: everything standing by July 2016, not what was built that year.',
    kind: 'epoch', min: 2016.5, max: 2026, start: 2026,
    seam: 'Starts at 2016 and is NOT continuous with the layer above. Do not add the two together — they share the 2016 baseline.',
  },
  'covered-agriculture': {
    title: 'Covered agriculture (greenhouses)',
    note: 'Removed from the urban layers and published separately: radar reads plastic as structure, so WSF Tracker calls 72 % of these parcels built-up.',
    kind: 'binary',
  },
  'density-current': {
    title: 'Sealed surface, 2024',
    note: 'Percent of each pixel sealed by anything impermeable — buildings, roads, car parks, paving. About 2.2× GHSL’s built surface; the gap is the roads.',
    kind: 'percent',
  },
  'density-trend': {
    title: 'Built surface trend (GHSL)',
    note: 'Square metres of built surface per ~92 m cell. The only source measuring density consistently across the 2015/2016 seam.',
    kind: 'trend', epochs: [1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020], start: 2020,
  },
  'loss-events': {
    title: 'Built-up gained and lost',
    note: 'The only layer that can show something disappear. Everything else here is growth-only by construction.',
    kind: 'change',
  },
};

const el = (id) => document.getElementById(id);
const status = (msg, bad) => { const s = el('status'); s.textContent = msg; s.classList.toggle('error', !!bad); };

const state = { catalog: null, stats: null, island: null, layer: 'buildings-dated', mode: 'state', year: 2020, basemap: 'light', playing: null };

/* ---------------------------------------------------------------- catalogue */
async function json(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}
const resolve = (base, href) => new URL(href, base).href;

/** Read the STAC catalogue: which layers exist, for which islands, and where. */
async function loadCatalog() {
  const rootUrl = new URL(`${DATA}/catalog.json`, location.href).href;
  const root = await json(rootUrl);
  const out = {};
  for (const link of root.links.filter((l) => l.rel === 'child')) {
    const colUrl = resolve(rootUrl, link.href);
    const col = await json(colUrl);
    const islands = {};
    for (const itemLink of col.links.filter((l) => l.rel === 'item')) {
      const itemUrl = resolve(colUrl, itemLink.href);
      const item = await json(itemUrl);
      islands[item.properties.island] = {
        asset: resolve(itemUrl, item.assets.data.href),
        stats: item.properties['sensisat:statistics'] || {},
        bbox: item.bbox,
      };
    }
    out[col.id] = {title: col.title, islands};
  }
  return out;
}

/* -------------------------------------------------------------------- style */
/**
 * Colour expressions.
 *
 * One rule governs the shape of everything here: **only numbers may be style
 * variables; colours must be literals.** OpenLayers compiles `['var', x]` to a
 * `uniform float`, so putting a colour in a variable makes the fragment shader
 * fail to compile with "mismatching ternary operator operand types 'uniform highp
 * float' and 'const 4-component vector of float'" — and the map then renders
 * nothing at all, basemap included, with the failure only visible in the console.
 *
 * So the year window travels as two numbers (`lo`, `hi`) and the mode as a third
 * (`since`), and every branch below returns a literal vec4.
 */
const NONE = [0, 0, 0, 0];

function colourFor(name) {
  const def = LAYERS[name];
  const band = ['band', 1];

  if (def.kind === 'year' || def.kind === 'epoch') {
    const undated = def.kind === 'year'
      // "Built, year unknown" is a real third state, never a guess — but it cannot
      // belong to a period either, so the "added since" view must not claim it.
      ? [['==', band, UNDATED], ['case', ['==', ['var', 'since'], 1], NONE, C.undated]]
      : [];
    return ['case',
      ['==', band, 0], NONE,
      ...undated,
      ['<', band, ['var', 'lo']], NONE,
      ['>', band, ['var', 'hi']], NONE,
      ['==', ['var', 'since'], 1], C.added,
      C.built];
  }
  if (def.kind === 'binary') {
    return ['case', ['>', band, 0], C.green, NONE];
  }
  if (def.kind === 'percent') {
    return ['case', ['<=', band, 0], NONE,
      ['interpolate', ['linear'], band,
        1, [255, 245, 200, 0.75],
        30, [255, 190, 90, 0.85],
        60, [240, 120, 50, 0.92],
        100, [150, 25, 20, 1]]];
  }
  if (def.kind === 'trend') {
    return ['case', ['<=', band, 0], NONE,
      ['interpolate', ['linear'], band,
        1, [255, 245, 200, 0.7],
        1500, [255, 180, 70, 0.85],
        4000, [230, 100, 40, 0.92],
        8500, [140, 20, 20, 1]]];
  }
  if (def.kind === 'change') {
    return ['case',
      ['==', band, 1], C.gain,
      ['==', band, 2], C.loss,
      ['==', band, 11], [120, 190, 255, 0.85],
      ['==', band, 12], [255, 150, 150, 0.85],
      ['==', band, 10], [110, 130, 150, 0.35],
      NONE];
  }
  return ['case', ['>', band, 0], C.built, NONE];
}

/** Numeric style variables. Changing these re-renders on the GPU and fetches nothing. */
function variables() {
  const def = LAYERS[state.layer];
  const since = state.mode === 'since' ? 1 : 0;

  if (def.kind === 'year') {
    const enc = (y) => y - YEAR_OFFSET;
    return since
      ? {lo: enc(state.sinceYear) + 1, hi: UNDATED - 1, since}
      : {lo: 1, hi: enc(state.year), since};
  }
  if (def.kind === 'epoch') {
    const toEpoch = (y) => Math.max(1, Math.min(20, Math.round((y - 2016) / 0.5)));
    return since
      ? {lo: toEpoch(state.sinceYear) + 1, hi: 20, since}
      : {lo: 1, hi: toEpoch(state.year), since};
  }
  return {lo: 0, hi: 255, since: 0};
}

/* ---------------------------------------------------------------------- map */
/**
 * Basemaps.
 *
 * Two of these are aerial photography, and that is the point: the fastest way to
 * tell whether a flagged pixel is a real building — or whether a real building was
 * missed — is to look at a photograph of the ground.
 *
 * **PNOA** is Spain's national orthophoto programme at 12–25 cm, an order of
 * magnitude sharper than the global satellite mosaics, and it is served natively
 * in EPSG:4326, so it needs no reprojection and stays crisp. It is also the exact
 * imagery M3's accuracy assessment will be interpreted from, which means checking
 * a layer against it here is checking it against the reference.
 *
 * **PNOA at the slider year** is the one worth knowing about. The historical
 * service publishes a separate layer per year, PNOA2004 to PNOA2024, so the
 * photograph underneath can follow the time slider: set the year to 2010 and you
 * are comparing what we say was built by 2010 against what the aeroplane saw in
 * 2010. Outside that range it clamps to the nearest available year and says so.
 *
 * Esri's global mosaic stays as the fallback that works outside Spain, which
 * matters the day this is pointed at anywhere else.
 */
/**
 * The cadastre bucketed unknown construction dates onto round years until 1980.
 * Measured (analysis 19): 15 spike years between 1900 and 1980 hold 34.8 % of every
 * dated building in the archipelago — 1900 alone holds 25,971, which is 1,146x its
 * neighbouring years and the largest single year in the register. After 1980 there
 * is not one spike in 46 years. So a date before 1980 is reliable to about a
 * decade, not to a year, and the viewer says so rather than implying precision the
 * register never had.
 */
const CADASTRE_BUCKETED_UNTIL = 1980;
const CADASTRE_SPIKE_YEARS = new Set([1900, 1905, 1910, 1915, 1920, 1925, 1930, 1935,
  1940, 1945, 1950, 1960, 1970, 1975, 1980]);

const PNOA_FIRST_YEAR = 2004;
const PNOA_LAST_YEAR = 2024;

const BASEMAPS = {
  light: {
    title: 'Map', kind: 'xyz',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    attributions: 'Tiles © Esri',
  },
  pnoa: {
    title: 'Aerial', kind: 'wms',
    url: 'https://www.ign.es/wms-inspire/pnoa-ma',
    layers: 'OI.OrthoimageCoverage',
    attributions: 'PNOA © Instituto Geográfico Nacional de España',
  },
  pnoaYear: {
    title: 'Aerial by year', kind: 'wms-year',
    url: 'https://www.ign.es/wms/pnoa-historico',
    attributions: 'PNOA histórico © Instituto Geográfico Nacional de España',
  },
  satellite: {
    title: 'Satellite', kind: 'xyz',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attributions: 'Imagery © Esri, Maxar, Earthstar Geographics',
  },
};

/** The PNOA year actually available for a requested year, clamped to the archive. */
function pnoaYearFor(year) {
  return Math.max(PNOA_FIRST_YEAR, Math.min(PNOA_LAST_YEAR, Math.round(year)));
}

function basemapSource(key) {
  const b = BASEMAPS[key];
  if (b.kind === 'xyz') {
    return new XYZ({url: b.url, attributions: b.attributions, maxZoom: 19, crossOrigin: 'anonymous'});
  }
  const layers = b.kind === 'wms-year' ? `PNOA${pnoaYearFor(activeYear())}` : b.layers;
  // No `serverType`. It makes OpenLayers send GeoServer vendor parameters and ask
  // for hi-dpi tiles, and IGN does not run GeoServer — every tile request then
  // fails, with nothing in the console to say so.
  const source = new TileWMS({
    url: b.url, attributions: b.attributions, crossOrigin: 'anonymous',
    params: {LAYERS: layers, FORMAT: 'image/jpeg'},
    transition: 250, ratio: 1,
  });
  source.on('tileloaderror', () => {
    el('basemap-note').textContent = 'Aerial imagery unavailable here — PNOA covers Spain only.';
  });
  return source;
}

/** The basemap layer, looked up from the map rather than held in a variable. */
function baseLayer() {
  return map.getLayers().item(0);
}

/** Which basemap is selected — read from the lit button, the thing the user can see. */
function activeBasemap() {
  return document.querySelector('#basemaps button.on')?.dataset.base ?? 'light';
}

/** The year the aerial photograph should show: whatever the slider points at. */
function activeYear() {
  const def = LAYERS[state.layer];
  if (!def || !['year', 'epoch', 'trend'].includes(def.kind)) return PNOA_LAST_YEAR;
  return sliderYear();
}

/** Keep the year-following aerial in step with the slider. */
function syncBasemapYear() {
  if (activeBasemap() !== 'pnoaYear') return;
  const wanted = `PNOA${pnoaYearFor(activeYear())}`;
  const source = baseLayer().getSource();
  if (source?.getParams && source.getParams().LAYERS !== wanted) {
    source.updateParams({LAYERS: wanted});
  }
  const shown = pnoaYearFor(activeYear());
  el('basemap-note').textContent = shown === Math.round(activeYear())
    ? `Aerial photograph from ${shown}.`
    : `Aerial photograph from ${shown} — PNOA only covers ${PNOA_FIRST_YEAR}–${PNOA_LAST_YEAR}.`;
}

const base = new TileLayer({source: basemapSource('light')});

/**
 * The view is EPSG:4326 — the projection our COGs are already in — and NOT the
 * usual EPSG:3857. This is forced, not a preference: a WebGLTileLayer cannot
 * reproject, so a GeoTIFF source whose projection differs from the view simply
 * never renders, with no error to say why. The basemap is the piece that gets
 * reprojected instead, which an ordinary raster TileLayer does support.
 */
const map = new Map({
  target: 'map', layers: [base],
  view: new View({projection: 'EPSG:4326', center: [-15.6, 28.0], zoom: 9, maxZoom: 19}),
});
let dataLayer = null;

async function showLayer() {
  const entry = state.catalog[state.layer]?.islands?.[state.island];
  if (!entry) { status(`no ${state.layer} for ${state.island}`, true); return; }
  status('loading raster…');

  const def = LAYERS[state.layer];
  const bandIndex = def.kind === 'trend' ? def.epochs.indexOf(state.year) + 1 : 1;

  const source = new GeoTIFF({
    sources: [{url: entry.asset, bands: [bandIndex || 1], nodata: 0}],
    normalize: false, interpolate: false, convertToRGB: false,
  });
  const layer = new WebGLTileLayer({
    source, style: {color: colourFor(state.layer), variables: variables()}, opacity: 0.92,
  });

  if (dataLayer) map.removeLayer(dataLayer);
  dataLayer = layer;
  map.addLayer(layer);

  source.on('error', (e) => status(`raster error: ${e.error?.message || e.message}`, true));
  try {
    await source.getView();
    map.getView().fit(entry.bbox, {padding: [30, 30, 30, 30], duration: 350});
    status(`${def.title} — ${state.island}`);
  } catch (err) {
    console.error(err);
    status(`could not read the raster: ${err.message}`, true);
  }
  renderLegend();
  renderReadout(entry);
}

function restyle() {
  if (!dataLayer) return;
  const def = LAYERS[state.layer];
  if (def.kind === 'trend') { showLayer(); return; }   // a different band, so a new read
  dataLayer.updateStyleVariables(variables());
  renderReadout(state.catalog[state.layer].islands[state.island]);
}

/* ------------------------------------------------------------------ panel */
/** Whichever year the slider is currently pointing at, given the mode. */
function sliderYear() {
  const def = LAYERS[state.layer];
  return state.mode === 'since' && def.kind !== 'trend' ? state.sinceYear : state.year;
}

/** Warn when the slider sits in the part of the cadastre that was bucketed. */
function precisionNote() {
  if (state.layer !== 'buildings-dated') return '';
  const y = Math.round(sliderYear());
  if (y > CADASTRE_BUCKETED_UNTIL) return '';
  if (CADASTRE_SPIKE_YEARS.has(y)) {
    return `⚠ ${y} is one of the years the cadastre used for "old, date unknown". `
         + `It holds far more buildings than the years either side, so treat this frame `
         + `as "by about ${y}", not as ${y} exactly.`;
  }
  return `⚠ Before ${CADASTRE_BUCKETED_UNTIL} the cadastre rounded unknown dates onto `
       + `whole decades, so this frame is reliable to roughly a decade rather than a year.`;
}

function modeNote() {
  if (state.mode !== 'since') return '';
  return `Showing only what appeared after ${state.sinceYear}. Two states side by side hide `
       + `change: Gran Canaria grew 9 % between 1995 and 2015 and the two maps look identical.`;
}

function renderLegend() {
  const def = LAYERS[state.layer];
  const key = (colour, label) =>
    `<div class="key"><span class="sw" style="background:rgba(${colour[0]},${colour[1]},${colour[2]},${colour[3]})"></span><span>${label}</span></div>`;
  const ramp = (stops, label) =>
    `<div class="key"><span class="ramp" style="background:linear-gradient(90deg,${stops})"></span></div><div class="cap">${label}</div>`;

  let html = '';
  if (def.kind === 'year' || def.kind === 'epoch') {
    if (state.mode === 'since') {
      html += key(C.added, `Appeared after ${state.sinceYear}`);
      // The undated class is deliberately absent here: a pixel with no year cannot
      // be placed in a period, so the change view must not imply that it can.
      if (def.kind === 'year') html += `<div class="cap">Undated pixels are hidden — they cannot be assigned to a period.</div>`;
    } else {
      html += key(C.built, `Built by ${state.year}`);
      if (def.kind === 'year') html += key(C.undated, 'Built, year unknown');
    }
  } else if (def.kind === 'binary') {
    html += key(C.green, 'Greenhouse parcel');
  } else if (def.kind === 'percent') {
    html += ramp('rgba(255,245,200,.8),rgba(255,190,90,.9),rgba(240,120,50,.95),rgba(150,25,20,1)', '1 % → 100 % of the pixel sealed');
  } else if (def.kind === 'trend') {
    html += ramp('rgba(255,245,200,.8),rgba(255,180,70,.9),rgba(230,100,40,.95),rgba(140,20,20,1)', `m² built per cell, ${state.year}`);
  } else if (def.kind === 'change') {
    html += key(C.gain, 'New built-up cover') + key(C.loss, 'Loss of cover')
         + key([110, 130, 150, 0.6], 'Unchanged built-up');
  }
  el('legend').innerHTML = html;
}

function renderReadout(entry) {
  const def = LAYERS[state.layer];
  const s = entry?.stats || {};

  // The trend layer's number is per epoch, and the loss layer's is per period —
  // neither has a single "how much is there" figure, so each says what it has.
  if (def.kind === 'trend' && s.surface_km2) {
    const now = s.surface_km2[state.year], first = s.surface_km2[def.epochs[0]];
    const growth = first ? Math.round(100 * (now / first - 1)) : null;
    el('readout').innerHTML = `<div class="big">${now} km²</div>`
      + `<div class="cap">built surface in ${state.year}`
      + (growth == null ? '' : ` · ${growth >= 0 ? '+' : ''}${growth} % since ${def.epochs[0]}`)
      + ` · ${s.observed?.[state.year] ?? ''}</div>`;
    return;
  }
  if (def.kind === 'change' && s.change_km2) {
    const rows = Object.entries(s.change_km2).map(([period, v]) =>
      `<div class="cap">${period}: <b>+${v.new_cover_km2}</b> km² new, <b>−${v.loss_of_cover_km2}</b> km² lost</div>`).join('');
    el('readout').innerHTML = `<div class="cap">Built-up change, whole island</div>${rows}`;
    return;
  }

  const km2 = s.footprint_km2 ?? s.area_km2 ?? s.sealed_km2 ?? null;
  let extra = '';
  if (s['pre-2016, undated'] != null) extra = `${s['dated_share_pct']} % of it carries a year`;
  else if (s.greenhouse_removed_km2 != null) extra = `${s.greenhouse_removed_km2} km² of greenhouses removed`;
  else if (s.survey_year) extra = `surveyed ${s.survey_year}`;
  el('readout').innerHTML = km2 == null ? ''
    : `<div class="big">${km2} km²</div><div class="cap">${def.title.toLowerCase()}, whole island${extra ? ' · ' + extra : ''}</div>`;
}

function syncTimeControls() {
  const def = LAYERS[state.layer];
  const timed = ['year', 'epoch', 'trend'].includes(def.kind);
  el('time-controls').style.display = timed ? '' : 'none';
  el('layer-note').textContent = def.note || '';
  el('seam-note').textContent = def.seam || '';
  if (!timed) { renderLegend(); return; }

  const slider = el('year');
  if (def.kind === 'trend') {
    slider.min = 0; slider.max = def.epochs.length - 1; slider.step = 1;
    slider.value = def.epochs.indexOf(state.year);
    el('tick-min').textContent = def.epochs[0];
    el('tick-max').textContent = def.epochs.at(-1);
  } else {
    slider.min = Math.ceil(def.min); slider.max = Math.floor(def.max); slider.step = 1;
    slider.value = sliderYear();
    el('tick-min').textContent = Math.ceil(def.min);
    el('tick-max').textContent = Math.floor(def.max);
  }
  el('year-out').textContent = sliderYear();
  el('mode-note').textContent = modeNote();
  el('precision-note').textContent = precisionNote();
}

/* ------------------------------------------------------------------- wiring */
function setLayer(name) {
  state.layer = name;
  const def = LAYERS[name];
  if (def.kind === 'trend') state.year = def.start;
  else if (def.kind === 'year' || def.kind === 'epoch') state.year = Math.floor(def.start ?? def.max);
  state.sinceYear = def.kind ? Math.floor(((def.min ?? 1900) + (def.max ?? 2020)) / 2) : 2000;
  syncTimeControls();
  showLayer();
}

function init(catalog, stats) {
  state.catalog = catalog; state.stats = stats;
  const islandSel = el('island'), layerSel = el('layer');

  const islands = Object.keys(catalog['buildings-dated']?.islands || {}).sort();
  islandSel.innerHTML = islands.map((i) => `<option>${i}</option>`).join('');
  state.island = islands.includes('Gran Canaria') ? 'Gran Canaria' : islands[0];
  islandSel.value = state.island;

  layerSel.innerHTML = Object.entries(LAYERS)
    .filter(([id]) => catalog[id])
    .map(([id, d]) => `<option value="${id}">${d.title}</option>`).join('');
  layerSel.value = state.layer;

  const basemapBox = el('basemaps');
  basemapBox.innerHTML = Object.entries(BASEMAPS)
    .map(([k, b], i) => `<button data-base="${k}"${i === 0 ? ' class="on"' : ''}>${b.title}</button>`).join('');
  basemapBox.querySelectorAll('button').forEach((b) => {
    b.onclick = () => {
      basemapBox.querySelectorAll('button').forEach((x) => x.classList.remove('on'));
      b.classList.add('on');
      state.basemap = b.dataset.base;
      el('basemap-note').textContent = '';
      baseLayer().setSource(basemapSource(b.dataset.base));
      syncBasemapYear();
      map.renderSync();
    };
  });

  islandSel.onchange = () => { state.island = islandSel.value; showLayer(); };
  layerSel.onchange = () => setLayer(layerSel.value);

  // Scoped to #viewmodes, NOT to `.modes button`. The basemap switcher reuses the
  // `.modes` class for its styling, so the broad selector matched those buttons too
  // and this loop overwrote their click handlers — clicking "Aerial" ran the
  // view-mode handler, which lit the button, left the basemap untouched, and set
  // state.mode to undefined. Style classes must never be used as behaviour selectors.
  const viewModes = el('viewmodes');
  viewModes.querySelectorAll('button').forEach((b) => {
    b.onclick = () => {
      viewModes.querySelectorAll('button').forEach((x) => x.classList.remove('on'));
      b.classList.add('on');
      state.mode = b.dataset.mode;
      syncTimeControls(); restyle(); renderLegend();
    };
  });

  el('year').oninput = (e) => {
    const def = LAYERS[state.layer];
    const value = def.kind === 'trend' ? def.epochs[+e.target.value] : +e.target.value;
    // The slider means "up to this year" in state mode and "since this year" in
    // change mode. One control, because the user is always pointing at one year.
    if (state.mode === 'since' && def.kind !== 'trend') state.sinceYear = value;
    else state.year = value;
    el('year-out').textContent = value;
    el('mode-note').textContent = modeNote();
    el('precision-note').textContent = precisionNote();
    syncBasemapYear();
    restyle(); renderLegend();
  };

  el('play').onclick = () => {
    const btn = el('play');
    if (state.playing) { clearInterval(state.playing); state.playing = null; btn.classList.remove('on'); btn.innerHTML = '&#9658;'; return; }
    btn.classList.add('on'); btn.innerHTML = '&#10073;&#10073;';
    const slider = el('year');
    state.playing = setInterval(() => {
      let v = +slider.value + 1;
      if (v > +slider.max) v = +slider.min;
      slider.value = v; slider.dispatchEvent(new Event('input'));
    }, 130);
  };

  setLayer(state.layer);

  // Exposed for debugging and for driving the viewer from a test harness. The
  // module scope is otherwise closed, so there is no other way to inspect what the
  // map is actually doing from outside.
  window.sensisat = {map, state, LAYERS, showLayer, restyle, get layer() { return dataLayer; }};
}

(async () => {
  try {
    const [catalog, stats] = await Promise.all([
      loadCatalog(),
      json(new URL(`${DATA}/statistics/layers.json`, location.href).href).catch(() => null),
    ]);
    init(catalog, stats);
  } catch (err) {
    status(`could not load the catalogue: ${err.message}`, true);
    console.error(err);
  }
})();
