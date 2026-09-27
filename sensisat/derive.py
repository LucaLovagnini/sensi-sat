"""Turning decoded sources into the layers SensiSat publishes.

Everything here is dataset-agnostic in the sense that matters: it takes arrays
with a declared meaning and returns arrays with a declared meaning. The adapters
in `datasets/` know where bytes come from; this module knows what to do with them.

Three operations carry most of the design:

1. **The drape** - WSF Evolution's 30 m years onto a 10 m footprint. This is the
   one place where a coarse product is allowed to inform a fine one, and it is
   allowed only because it never invents a *footprint*, only a *date*.
2. **The provenance band** - a second band recording where each pixel's year came
   from, so "we do not know" survives all the way to the viewer instead of being
   rounded into a year.
3. **The seam record** - the measured discontinuity at 2015/2016, per island,
   published as data rather than smoothed away.
"""

from __future__ import annotations

import numpy as np
from rasterio.transform import Affine
from rasterio.warp import Resampling

from . import encoding as enc
from .config import ISLAND_BBOX
from .grid import COARSE_DEG, for_island
from .raster import area_km2, fraction_grid, resample_to


# ---------------------------------------------------------------------------
# 1. The drape
# ---------------------------------------------------------------------------
def drape(years_coarse: np.ndarray, coarse_transform: Affine, coarse_crs,
          footprint: np.ndarray, fine_transform: Affine, fine_crs,
          ) -> tuple[np.ndarray, np.ndarray]:
    """Give a 10 m footprint the years of a 30 m dated product.

    Returns (encoded years, provenance), both on the footprint's grid.

    **What this does and does not claim.** The footprint decides *where* there is
    settlement; it comes from a 10 m product and is never altered here. The coarse
    product decides only *when*, and only for the pixels the footprint already
    marks as built. So a 30 m pixel cannot switch on 10 m ground that no 10 m
    product saw - the drape can misdate a pixel, but it cannot invent one.

    **Why nearest-neighbour.** A year is a label, not a quantity. Averaging 1994
    and 2006 to 2000 would produce a date at which nothing happened, in a layer
    whose entire purpose is to say when things happened.

    **The 43 %.** Only about 57 % of the 2016 footprint falls on a 30 m pixel that
    WSF Evolution ever dated; on Gran Canaria and Tenerife the remainder is largely
    greenhouses, but 58-91 % of it sits outside any farm parcel and is still
    unexplained (it is the subject of M3's dedicated sample). Those pixels become
    UNDATED, in their own provenance class. Dating them by nearest neighbour, or
    by the footprint's own first epoch, would manufacture 115 km2 of history.
    """
    if years_coarse.shape != footprint.shape or coarse_transform != fine_transform:
        years_on_fine = resample_to(
            years_coarse.astype("int32"), coarse_transform, coarse_crs,
            fine_transform, footprint.shape, fine_crs,
            nodata=0, resampling=Resampling.nearest,
        )
    else:
        years_on_fine = years_coarse.astype("int32")

    built = footprint.astype(bool)
    dated = built & (years_on_fine > 0)

    years = np.where(dated, enc.encode_year(years_on_fine), enc.NOT_BUILT).astype(enc.DTYPE)
    years = np.where(built & ~dated, enc.UNDATED, years).astype(enc.DTYPE)

    provenance = np.where(dated, enc.P_DATED, enc.P_NOT_BUILT).astype("uint8")
    provenance = np.where(built & ~dated, enc.P_UNDATED, provenance).astype("uint8")
    return years, provenance


def provenance_summary(provenance: np.ndarray, transform: Affine) -> dict[str, float]:
    """km2 in each provenance class — the 57/43 split, as a number per island."""
    out = {label: round(area_km2(provenance == code, transform), 3)
           for code, label in enc.PROVENANCE.items() if code != enc.P_NOT_BUILT}
    total = sum(out.values())
    out["dated_share_pct"] = round(100 * out["dated by the source"] / total, 1) if total else float("nan")
    return out


# ---------------------------------------------------------------------------
# 2. Masking
# ---------------------------------------------------------------------------
def apply_mask(arr: np.ndarray, mask: np.ndarray, fill=0) -> np.ndarray:
    """Remove masked ground from a layer (used for greenhouses, M1.2)."""
    return np.where(mask.astype(bool), fill, arr).astype(arr.dtype)


# ---------------------------------------------------------------------------
# 3. The common 100 m grid
# ---------------------------------------------------------------------------
def to_fraction(mask: np.ndarray, transform: Affine, cell_deg: float = COARSE_DEG):
    """Share of each ~100 m cell that is built, plus that grid's transform.

    This is the common support on which an extent product and a surface product
    can be compared cell by cell. It is worth being precise about what it does
    *not* do, because the plan once claimed otherwise: averaging a binary mask
    preserves total area, so it does not remove the inflation that makes a 30 m
    extent product read larger than a 10 m one. Nothing removes that; it is a
    property of the definition, not of the grid.
    """
    return fraction_grid(mask, transform, None, cell_deg=cell_deg)


# ---------------------------------------------------------------------------
# 4. Clipping to an island
# ---------------------------------------------------------------------------
def island_mask(island: str, transform: Affine, shape: tuple[int, int], crs="EPSG:4326") -> np.ndarray:
    """Boolean mask of one island's land on a given grid.

    Every published layer is clipped to this. Two reasons, one of which is not
    obvious: the bounding boxes of Lanzarote and La Graciosa *overlap*, so layers
    clipped only to their boxes would count the same ground twice and an
    archipelago total built by summing islands would be wrong. Clipping to the
    polygon makes the per-island layers disjoint and their totals additive.

    The polygons are OpenStreetMap boundaries, whose areas agree with published
    island areas to within 7 % (measured in M0). They are the same polygons every
    M0 number was computed inside, so results stay comparable across milestones.
    """
    from . import zones
    from .stats import zone_masks

    isl = zones.islands()
    one = isl[isl["name"] == island]
    if one.empty:
        raise LookupError(f"no boundary polygon cached for {island!r}")
    return zone_masks(one, transform, shape, crs)[island]


# ---------------------------------------------------------------------------
# 5. The seam record
# ---------------------------------------------------------------------------
def seam_record(island: str) -> dict:
    """The measured 2015/2016 discontinuity for one island.

    The two eras are made by different instruments at different resolutions with
    different definitions, so their extents do not line up - and the plan's rule
    is that the join is declared, never blended. This reproduces the M0 table so
    the declaration ships beside the data:

      resolution factor  same producer, same year, 30 m vs 10 m (x2.1-2.6)
      definition factor  same resolution, 18 months apart, before and after the
                         greenhouse mask (x1.24-2.02 raw, x1.24-1.56 masked)
      net factor         what a reader would see crossing the seam (x0.48-0.74)

    A net factor below 1 means the extent *drops* at the join by 26-52 %. Nothing
    was demolished in 2016; the map simply started being made a different way.
    """
    from .datasets import crops, wsf
    from .datasets import wsf_tracker as wt

    bbox = ISLAND_BBOX[island]
    transform, shape = for_island(island)

    evo, t_evo, c_evo = wsf.load("wsf_evolution", bbox)
    evo15 = (evo > 0) & (evo <= 2015) & island_mask(island, t_evo, evo.shape, c_evo)
    w15, t15, c15 = wsf.built_mask("wsf2015", bbox)
    w15 = w15 & island_mask(island, t15, w15.shape, c15)
    trk, t_trk, c_trk = wt.load(bbox)
    e1 = (trk == 1) & island_mask(island, t_trk, trk.shape, c_trk)
    gh, _, _ = crops.greenhouse_mask(island, transform=t_trk, shape=trk.shape)
    e1m = e1 & ~gh.astype(bool)

    a = {
        "evo30": round(area_km2(evo15, t_evo), 2),
        "wsf15": round(area_km2(w15, t15), 2),
        "trk_e1": round(area_km2(e1, t_trk), 2),
        "trk_e1_nogh": round(area_km2(e1m, t_trk), 2),
    }
    return {
        "island": island, **a,
        "resolution_factor": _ratio(a["evo30"], a["wsf15"]),
        "definition_factor_raw": _ratio(a["trk_e1"], a["wsf15"]),
        "definition_factor_masked": _ratio(a["trk_e1_nogh"], a["wsf15"]),
        "greenhouse_removed_km2": round(a["trk_e1"] - a["trk_e1_nogh"], 2),
        "net_evo_to_tracker_masked": _ratio(a["trk_e1_nogh"], a["evo30"]),
        "greenhouse_survey_year": crops.survey_year(island),
    }


def _ratio(num: float, den: float) -> float:
    return round(num / den, 2) if den else float("nan")
