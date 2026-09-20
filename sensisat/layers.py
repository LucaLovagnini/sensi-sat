"""The seven layers SensiSat publishes, and how each one is made.

One module so the whole output of the project can be read in one sitting. Each
entry declares what it measures, at what resolution, in what encoding, and from
which sources — and then builds itself from the adapters in `datasets/` and the
operations in `derive.py`. `scripts/build.py` is only a command line over this.

    buildings-dated       cadastre           10 m   year first built   + provenance
    settlement-era-a      WSF Evolution      10 m   year first built   + provenance
    settlement-era-b      WSF Tracker        10 m   epoch first built
    covered-agriculture   Mapa de Cultivos   10 m   binary
    density-current       Copernicus IMD     10 m   % sealed           + confidence
    density-trend         GHSL               ~92 m  m2 built per cell, 10 epochs
    loss-events           Copernicus IBUC    20 m   change classes,    2 periods

**Why two settlement layers rather than one merged timeline.** The 2015/2016 join
is a change of instrument, resolution and definition all at once: crossing it, the
measured extent *drops* by 26-52 % although nothing was demolished. Publishing one
seamless raster would bake that artefact into the data and there would be no way
for a reader to tell it from a real event. So the eras stay separate, the viewer
declares the transition, and `derive.seam_record` ships the measured factors
alongside. This is decision 13, and it follows the CEOS land-product validation
practice of describing a discontinuity rather than blending across it.

**Why greenhouses come out of three layers and get one of their own.** Radar reads
plastic as structure, so WSF Tracker calls 72 % of Gran Canaria's greenhouse
parcels built-up and Copernicus Imperviousness reports 43.7 % mean sealing inside
them. Leaving that in would put 17 km2 of tomatoes in the urban total on one
island alone. Taking it out without publishing it would lose real ground cover
that matters to a conservation reader. So it is subtracted and published (M1.2),
and because `covered-agriculture` ships beside the others, anyone who disagrees
with the call can add it back exactly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from rasterio.transform import Affine
from rasterio.warp import Resampling

from . import derive
from . import encoding as enc
from .config import ISLAND_BBOX
from .grid import PIXEL_DEG, for_island, snap
from .raster import area_km2, row_areas_m2, weighted_km2


@dataclass(frozen=True)
class Companion:
    """A file published beside a layer, for readers who want it.

    Not every useful raster belongs in the layer everyone downloads. The
    imperviousness confidence grid is the case that forced this: it is genuinely
    useful to an analyst asking how far to trust a pixel, and it is also 52
    distinct values scattered over 23 million pixels, which compresses badly
    enough to cost 9.5 MB against the 4.2 MB of the data it annotates. Folded in
    as a second band it tripled the download for every visitor to buy something
    almost none of them would open. As its own asset it costs nothing until asked
    for, and STAC has exactly this concept, so nothing is lost and nothing is hidden.
    """

    key: str
    data: np.ndarray
    band_descriptions: list[str]
    title: str
    roles: list[str] = field(default_factory=lambda: ["metadata"])
    resampling: Resampling = Resampling.nearest


@dataclass(frozen=True)
class Built:
    """One finished layer for one island, ready to be written and catalogued.

    `resampling` is how the COG's overviews are built, and it is a display decision
    with a correctness constraint. Nearest-neighbour — the obvious choice for
    categorical data — picks one child pixel arbitrarily, so scattered 10 m
    buildings simply disappear as you zoom out and an island reads as empty until
    you are almost on top of it. Measured on a synthetic island at 0.5 % built:
    nearest keeps 0.47 % of pixels at 4x zoom-out, MODE keeps 7.67 %.

    So the categorical layers use MODE. Two properties make it the right choice
    rather than merely the visible one: nodata is 0 and GDAL excludes nodata from
    the aggregation, so "not built" cannot outvote a real value and sparse features
    survive; and mode always returns a value that was actually observed in the
    children, so unlike AVERAGE — which scores identically on visibility — it can
    never invent a year nothing was built in. At zoomed-out levels a pixel
    therefore shows a representative year for that cell, never a computed one.

    The percentage and surface layers use AVERAGE, because averaging a quantity is
    what averaging a quantity means.
    """

    data: np.ndarray                 # (height, width) or (bands, height, width)
    transform: Affine
    crs: str
    band_descriptions: list[str]
    properties: dict = field(default_factory=dict)
    nodata: float = 0
    resampling: Resampling = Resampling.mode
    companions: list[Companion] = field(default_factory=list)


@dataclass(frozen=True)
class LayerSpec:
    name: str
    title: str
    measure: str        # extent | surface | change
    encoding: str
    resolution_m: int
    sources: list[str]
    build: Callable[[str], Built]
    description: str = ""
    # The span of time the layer actually describes, which is what a catalogue
    # search needs — not the day we happened to build the file.
    start: str = "1975-01-01"
    end: str = "2026-01-01"
    # Can this layer commit a false positive that a negative control would catch?
    # Only for layers a classifier produced. `covered-agriculture` is a
    # rasterised official crop survey, so there is no classifier to be wrong — and
    # farming is permitted inside most protected areas, so greenhouses found there
    # are real. Testing it against a no-settlement control measured 0.333 % on La
    # Palma and read as a failure when it was the gate being misapplied.
    commission_risk: bool = True


# ---------------------------------------------------------------------------
# 1. buildings-dated — the primary pre-2016 timeline for Spain (M1.1)
# ---------------------------------------------------------------------------
def _buildings_dated(island: str) -> Built:
    from .datasets import cadastre

    transform, shape = for_island(island)
    years, _, crs = cadastre.year_first_built(island, transform=transform, shape=shape)
    land = derive.island_mask(island, transform, shape, crs)
    years = np.where(land, years, enc.NOT_BUILT).astype(enc.DTYPE)

    provenance = np.zeros(shape, "uint8")
    provenance[(years > 0) & (years != enc.UNDATED)] = enc.P_DATED
    provenance[years == enc.UNDATED] = enc.P_UNDATED

    codes = cadastre.codes_for(island)
    return Built(
        data=np.stack([years, provenance]),
        transform=transform, crs=crs,
        band_descriptions=["year first built (uint8, year-1899; 255 = undated)", "provenance"],
        properties={
            "municipalities": len(codes),
            "footprint_km2": round(area_km2(years > 0, transform), 3),
            "undated_km2": round(area_km2(years == enc.UNDATED, transform), 4),
            "extent_by_year": extent_by_year(years, transform),
            **derive.provenance_summary(provenance, transform),
        },
    )



def extent_by_year(years: np.ndarray, transform) -> dict[int, float]:
    """Cumulative built extent at each year the layer can express, in km2.

    The viewer's slider is a GPU threshold over a year-first-built raster, so the
    MAP already answers "what was built by year Y". The readout did not: it showed
    the layer's whole-island total whatever the slider said, which reads as a bug
    next to a map that visibly changes. This is the number the readout needs.

    Undated pixels are excluded. They are built, but no year can place them, and
    folding them into every year would overstate the early ones. The undated area
    is reported separately, and the viewer already hides that class in the change
    view for the same reason.
    """
    dated = (years > 0) & (years != enc.UNDATED)
    if not dated.any():
        return {}
    cell = row_areas_m2(years.shape, transform)
    yr = years.astype(np.int32) + enc.YEAR_OFFSET
    lo, hi = int(yr[dated].min()), int(yr[dated].max())
    # area added in each year, then a running sum — one pass, not one per year
    added = {y: float(((dated & (yr == y)) * cell).sum() / 1e6) for y in range(lo, hi + 1)}
    out, total = {}, 0.0
    for y in range(lo, hi + 1):
        total += added[y]
        out[y] = round(total, 3)
    return out


def extent_by_epoch(epochs: np.ndarray, transform, n: int) -> dict[int, float]:
    """The same thing for the epoch-coded era-b layer."""
    built = epochs > 0
    if not built.any():
        return {}
    cell = row_areas_m2(epochs.shape, transform)
    out, total = {}, 0.0
    for e in range(1, n + 1):
        total += float(((epochs == e) * cell).sum() / 1e6)
        out[e] = round(total, 3)
    return out

# ---------------------------------------------------------------------------
# 2. settlement-era-a — the global fallback timeline, draped to 10 m
# ---------------------------------------------------------------------------
def _settlement_era_a(island: str) -> Built:
    from .datasets import crops, wsf
    from .datasets import wsf_tracker as wt

    bbox = ISLAND_BBOX[island]
    transform, shape = for_island(island)

    evo, t_evo, c_evo = wsf.load("wsf_evolution", bbox)
    evo = np.where(evo > 2015, 0, evo)          # 2015 is Evolution's last year

    trk, t_trk, _ = wt.load(bbox)               # native grid == our grid (verified)
    gh, _, _ = crops.greenhouse_mask(island, transform=transform, shape=shape)
    land = derive.island_mask(island, transform, shape, "EPSG:4326")
    footprint = (trk == 1) & ~gh.astype(bool) & land

    years, provenance = drape_onto(evo, t_evo, c_evo, footprint, transform, "EPSG:4326")
    return Built(
        data=np.stack([years, provenance]),
        transform=transform, crs="EPSG:4326",
        band_descriptions=["year first built (uint8, year-1899; 255 = undated)", "provenance"],
        properties={
            "footprint_source": "WSF Tracker epoch 1 (built by 2016-07), greenhouse-masked",
            "date_source": "WSF Evolution 1985-2015 (30 m)",
            "greenhouse_survey_year": crops.survey_year(island),
            "footprint_km2": round(area_km2(years > 0, transform), 3),
            "extent_by_year": extent_by_year(years, transform),
            **derive.provenance_summary(provenance, transform),
        },
    )


def drape_onto(evo, t_evo, c_evo, footprint, transform, crs):
    """Thin wrapper so the drape reads the same way at both call sites."""
    return derive.drape(evo, t_evo, c_evo, footprint, transform, crs)


# ---------------------------------------------------------------------------
# 3. settlement-era-b — 2016 to today
# ---------------------------------------------------------------------------
def _settlement_era_b(island: str) -> Built:
    from .datasets import crops
    from .datasets import wsf_tracker as wt

    transform, shape = for_island(island)
    trk, t_trk, _ = wt.load(ISLAND_BBOX[island])
    gh, _, _ = crops.greenhouse_mask(island, transform=transform, shape=shape)
    land = derive.island_mask(island, transform, shape, "EPSG:4326")

    epochs = np.where(land & ~gh.astype(bool), np.clip(trk, 0, wt.N_EPOCHS), 0).astype("uint8")
    return Built(
        data=epochs, transform=transform, crs="EPSG:4326",
        band_descriptions=["epoch first built (1 = 2016-07 ... 20 = 2026-01; 0 = not built)"],
        properties={
            "epochs": wt.N_EPOCHS,
            "epoch_labels": {i: wt.epoch_to_label(i) for i in range(1, wt.N_EPOCHS + 1)},
            "greenhouse_masked": True,
            "greenhouse_survey_year": crops.survey_year(island),
            "greenhouse_removed_km2": round(
                area_km2((trk > 0) & gh.astype(bool) & land, transform), 3),
            "footprint_km2": round(area_km2(epochs > 0, transform), 3),
            "baseline_km2": round(area_km2(epochs == 1, transform), 3),
            "extent_by_epoch": extent_by_epoch(epochs, transform, wt.N_EPOCHS),
        },
    )


# ---------------------------------------------------------------------------
# 4. covered-agriculture — the greenhouses, as their own subject (M1.2)
# ---------------------------------------------------------------------------
def _covered_agriculture(island: str) -> Built:
    from .datasets import crops

    transform, shape = for_island(island)
    gh, _, _ = crops.greenhouse_mask(island, transform=transform, shape=shape)
    land = derive.island_mask(island, transform, shape, "EPSG:4326")
    gh = (gh.astype(bool) & land).astype("uint8")
    return Built(
        data=gh, transform=transform, crs="EPSG:4326",
        band_descriptions=["covered agriculture (1 = greenhouse parcel)"],
        properties={
            "survey_year": crops.survey_year(island),
            "area_km2": round(area_km2(gh > 0, transform), 3),
            "caveat": "a single-date parcel survey, applied to footprints of other years",
        },
    )


# ---------------------------------------------------------------------------
# 5. density-current — how sealed the ground is now (M1.3)
# ---------------------------------------------------------------------------
def _density_current(island: str) -> Built:
    from .datasets import copernicus as cop
    from .datasets import crops

    transform, shape = for_island(island)
    imd, _, _ = cop.on_grid("imd_2024", island, transform=transform, shape=shape)
    conf, _, _ = cop.on_grid("imdcl_2024", island, transform=transform, shape=shape,
                             resampling=Resampling.nearest)
    land = derive.island_mask(island, transform, shape, "EPSG:4326")
    gh, _, _ = crops.greenhouse_mask(island, transform=transform, shape=shape)

    sealed = np.where(imd > 100, 0, imd)        # 255 means "not measured", not "very sealed"
    sealed_all = np.where(land, sealed, 0).astype("uint8")
    sealed_urban = np.where(land & ~gh.astype(bool), sealed, 0).astype("uint8")
    conf = np.where(land & (conf <= 100), conf, 0).astype("uint8")

    return Built(
        data=sealed_urban,
        transform=transform, crs="EPSG:4326",
        band_descriptions=["% of pixel sealed, 2024 (greenhouses removed)"],
        companions=[Companion(
            key="confidence", data=conf,
            band_descriptions=["confidence %, Copernicus Imperviousness Density 2024"],
            title="Imperviousness confidence",
        )],
        properties={
            "sealed_km2": round(weighted_km2(sealed_urban / 100.0, transform), 3),
            "sealed_km2_including_greenhouses": round(weighted_km2(sealed_all / 100.0, transform), 3),
            "mean_confidence_pct": round(float(conf[land & (conf > 0)].mean()), 1) if (land & (conf > 0)).any() else None,
            "low_confidence_share_pct": round(
                100 * float(((conf > 0) & (conf < 80) & land).sum() / max(int(land.sum()), 1)), 2),
            "greenhouse_masked": True,
            "note": "sealing = buildings + roads + paving; ~2.2x GHSL built surface",
        },
        resampling=Resampling.average,          # a percentage may be averaged
    )


# ---------------------------------------------------------------------------
# 6. density-trend — how density changed since 1975 (M1.3)
# ---------------------------------------------------------------------------
TREND_EPOCHS = [1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020]


def _density_trend(island: str) -> Built:
    from .datasets import ghsl

    bbox = ISLAND_BBOX[island]
    bands, transform, crs = [], None, None
    for epoch in TREND_EPOCHS:
        arr, t, c = ghsl.load(epoch, bbox)
        transform, crs = transform or t, crs or c
        bands.append(arr.astype("uint16"))
    stack = np.stack(bands)
    land = derive.island_mask(island, transform, stack.shape[1:], crs)
    stack = np.where(land, stack, 0).astype("uint16")

    return Built(
        data=stack, transform=transform, crs=str(crs),
        band_descriptions=[f"built surface m2 per cell, {e} ({ghsl.is_observed(e)})"
                           for e in TREND_EPOCHS],
        properties={
            "epochs": TREND_EPOCHS,
            "observed": {e: ghsl.is_observed(e) for e in TREND_EPOCHS},
            "surface_km2": {e: round(float(stack[i].sum()) / 1e6, 3) for i, e in enumerate(TREND_EPOCHS)},
            "grid": "GHSL native EPSG:4326 3-arcsecond; NOT resampled to the 10 m grid",
            "why_native": (
                "the values are square metres per cell, so changing the cell size would "
                "require rescaling every value; keeping GHSL's own grid keeps the numbers "
                "exactly as JRC published them"
            ),
            "caveat": "growth-only by construction: JRC's process can never show a decrease",
        },
        resampling=Resampling.average,
    )


# ---------------------------------------------------------------------------
# 7. loss-events — the only layer that can show something disappear
# ---------------------------------------------------------------------------
LOSS_PERIODS = [("ibuc_2018_2021", "2018-2021"), ("ibuc_2021_2024", "2021-2024")]


def _loss_events(island: str) -> Built:
    from .datasets import copernicus as cop

    # 20 m sits on the same lattice as the 10 m grid: the origin is shared and the
    # pixel is exactly double, so every coarse boundary is also a fine boundary.
    transform, shape = snap(ISLAND_BBOX[island], PIXEL_DEG * 2)
    land = derive.island_mask(island, transform, shape, "EPSG:4326")

    bands, stats = [], {}
    for product, label in LOSS_PERIODS:
        arr, _, _ = cop.on_grid(product, island, transform=transform, shape=shape)
        arr = np.where(land & (arr != 255), arr, 0).astype("uint8")
        bands.append(arr)
        stats[label] = {
            "new_cover_km2": round(area_km2(arr == cop.NEW_COVER, transform), 4),
            "loss_of_cover_km2": round(area_km2(arr == cop.LOSS_OF_COVER, transform), 4),
        }

    return Built(
        data=np.stack(bands), transform=transform, crs="EPSG:4326",
        band_descriptions=[f"built-up change {label}" for _, label in LOSS_PERIODS],
        properties={
            "classes": cop.CHANGE_CLASSES,
            "periods": [label for _, label in LOSS_PERIODS],
            "change_km2": stats,
            "why_this_layer_exists": (
                "every other source here is growth-only by construction, so none of them "
                "can show the Tajogaite eruption burying Todoque in 2021"
            ),
            "never_do": "do not subtract two status layers from different releases; use these",
        },
    )


# ---------------------------------------------------------------------------
LAYERS: dict[str, LayerSpec] = {
    "buildings-dated": LayerSpec(
        "buildings-dated", "Buildings, dated by the cadastre", "extent", "year first built", 10,
        ["Catastro INSPIRE Buildings"], _buildings_dated,
        "Every building the Spanish register knows about, carrying the year it was built "
        "OR COMPREHENSIVELY REBUILT — the Catastro resets the year on a reforma "
        "integral, so a 1970 house rebuilt in 2019 reads as 2019. "
        "1900-2020. Sees dispersed rural buildings satellites miss; blind to roads, ports "
        "and anything demolished before today.",
        start="1900-01-01", end="2020-12-31",
    ),
    "settlement-era-a": LayerSpec(
        "settlement-era-a", "Settlement extent to 2015", "extent", "year first built", 10,
        ["WSF Evolution", "WSF Tracker", "Mapa de Cultivos"], _settlement_era_a,
        "Settlement clusters including roads and infrastructure, dated 1985-2015, draped "
        "from 30 m onto the 10 m footprint. The 43 % that cannot inherit a year is kept as "
        "an explicit undated class rather than given an invented one.",
        start="1985-01-01", end="2016-07-01",
    ),
    "settlement-era-b": LayerSpec(
        "settlement-era-b", "Settlement extent 2016 onward", "extent", "epoch first built", 10,
        ["WSF Tracker", "Mapa de Cultivos"], _settlement_era_b,
        "Twice-yearly settlement extent from 2016-07 to 2026-01, greenhouse-masked. "
        "Growth-only: a pixel keeps the epoch it was first seen built.",
        start="2016-07-01", end="2026-01-01",
    ),
    "covered-agriculture": LayerSpec(
        "covered-agriculture", "Covered agriculture (greenhouses)", "extent", "binary", 10,
        ["Mapa de Cultivos"], _covered_agriculture,
        "Greenhouse parcels, removed from the urban layers and published separately so the "
        "ground they cover is neither counted as town nor lost from view.",
        start="2021-01-01", end="2025-12-31", commission_risk=False,
    ),
    "density-current": LayerSpec(
        "density-current", "Sealed surface, 2024", "surface", "percent", 10,
        ["Copernicus Imperviousness Density 2024"], _density_current,
        "Percent of each pixel sealed by any impermeable cover — buildings, roads, car "
        "parks, paving. The broadest and finest measure in the project.",
        start="2024-01-01", end="2024-12-31",
    ),
    "density-trend": LayerSpec(
        "density-trend", "Built surface trend, 1975-2020", "surface", "amount", 92,
        ["GHS-BUILT-S R2023A"], _density_trend,
        "Square metres of built surface per cell at ten five-yearly epochs — the only "
        "source that measures density consistently across the 2015/2016 seam. "
        "Observed epochs are 1975, 1990 and 2000 (Landsat); the rest are interpolated, "
        "and that interpolation smooths real events away: GHSL puts its LARGEST "
        "increment in 2015-2020, when the cadastre records construction at 11 % of "
        "its pre-2008 rate. Sound for the long trend and for density; never use it to "
        "date recent growth (data-evaluation.md §12).",
        start="1975-01-01", end="2020-12-31",
    ),
    "loss-events": LayerSpec(
        "loss-events", "Built-up gained and lost", "change", "classes", 20,
        ["Copernicus Impervious Built-Up Change"], _loss_events,
        "Purpose-built change layers for 2018-2021 and 2021-2024, the only source here "
        "able to record built-up disappearing.",
        start="2018-01-01", end="2024-12-31",
    ),
}

TEN_METRE_LAYERS = [n for n, spec in LAYERS.items() if spec.resolution_m == 10]


def build(layer: str, island: str) -> Built:
    if layer not in LAYERS:
        raise ValueError(f"unknown layer {layer!r}; expected one of {sorted(LAYERS)}")
    return LAYERS[layer].build(island)
