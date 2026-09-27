"""Where are the 'pre-2016, undated' pixels, and what do they look like?

WSF Tracker says these were built by July 2016; WSF Evolution never flagged them in
any year. The roads hypothesis failed (analysis 11). This figure lets a human look:
the class over satellite imagery for one island, its patch-size distribution against
the dated class, and close-ups of the largest clusters.
Run:  python docs/figures/src/undated_pixels.py [island]
"""

from __future__ import annotations

import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from scipy import ndimage

from sensisat import zones
from sensisat.config import ESRI_SATELLITE, FIGURES, ISLAND_BBOX
from sensisat.datasets import wsf, wsf_tracker as wt
from sensisat.raster import area_km2, resample_to, to_web_mercator
from sensisat.stats import zone_masks
from sensisat.tiles import basemap_window, mosaic, tile_bounds_3857, tile_xy


def main(island: str = "Gran Canaria"):
    bbox = ISLAND_BBOX[island]
    isl = zones.islands()
    z = isl[isl["name"] == island]
    trk, tt, tc = wt.load(bbox)
    evo, te, ec = wsf.load("wsf_evolution", bbox)
    evo10 = resample_to(evo, te, ec, tt, trk.shape, tc)
    m = zone_masks(z, tt, trk.shape, tc)[island]
    baseline = (trk == 1) & m
    dated = baseline & (evo10 > 0)
    undated = baseline & (evo10 == 0)

    # --- patch statistics ------------------------------------------------------
    def patches(mask):
        lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
        sizes = np.bincount(lab.ravel())[1:] if n else np.array([])
        return n, sizes

    n_d, s_d = patches(dated)
    n_u, s_u = patches(undated)
    px_ha = 0.0079  # ~79 m2 per 10 m Tracker pixel at 28 N, in hectares
    print(f"{island}: dated {area_km2(dated, tt):.1f} km2 in {n_d:,} patches, median {np.median(s_d) * px_ha * 1e4:.0f} m2, "
          f"largest {s_d.max() * px_ha:.1f} ha")
    print(f"{'':{len(island)}}  undated {area_km2(undated, tt):.1f} km2 in {n_u:,} patches, median {np.median(s_u) * px_ha * 1e4:.0f} m2, "
          f"largest {s_u.max() * px_ha:.1f} ha")
    share_small_u = (s_u <= 4).sum() / len(s_u)
    share_small_d = (s_d <= 4).sum() / len(s_d)
    print(f"  share of patches <= 4 pixels: dated {100 * share_small_d:.0f} %, undated {100 * share_small_u:.0f} %")
    area_in_big_u = s_u[s_u >= 100].sum() / s_u.sum()
    print(f"  share of UNDATED area in patches >= 1 ha: {100 * area_in_big_u:.0f} %")

    # --- island overview -------------------------------------------------------
    sat, b, ext = basemap_window(bbox, 11, ESRI_SATELLITE)
    ov_d = to_web_mercator(dated.astype("uint8"), tt, tc, b, sat.width, sat.height)
    ov_u = to_web_mercator(undated.astype("uint8"), tt, tc, b, sat.width, sat.height)

    # --- two largest undated clusters -----------------------------------------
    lab, _ = ndimage.label(undated, structure=np.ones((3, 3)))
    order = np.argsort(-s_u)[:2] + 1
    centres = []
    for k in order:
        rr, cc = np.nonzero(lab == k)
        r, c = rr.mean(), cc.mean()
        lon, lat = tt * (c + 0.5, r + 0.5)
        centres.append((lon, lat, s_u[k - 1] * px_ha))

    fig, axs = plt.subplots(2, 2, figsize=(16, 15))
    ax = axs[0, 0]
    ax.imshow(np.asarray(sat), extent=ext)
    ax.imshow(np.ma.masked_where(ov_d == 0, ov_d), cmap=ListedColormap(["#4a90c0"]), extent=ext, alpha=0.9, interpolation="nearest")
    ax.imshow(np.ma.masked_where(ov_u == 0, ov_u), cmap=ListedColormap(["#ff2d2d"]), extent=ext, alpha=0.95, interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"1. {island}, Tracker 'built by July 2016'.\nBLUE = has a WSF Evolution year ({area_km2(dated, tt):.0f} km²) · "
                 f"RED = undated, Evolution never flagged it ({area_km2(undated, tt):.0f} km²)", fontsize=11)

    ax = axs[0, 1]
    bins = np.logspace(0, 4, 30)
    ax.hist(s_d, bins=bins, alpha=0.6, color="#4a90c0", label=f"dated: {n_d:,} patches")
    ax.hist(s_u, bins=bins, alpha=0.6, color="#ff2d2d", label=f"undated: {n_u:,} patches")
    ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xlabel("patch size, pixels (10 m)"); ax.set_ylabel("count")
    ax.legend(); ax.grid(alpha=.3)
    ax.set_title(f"2. Patch sizes. Undated: {100 * share_small_u:.0f} % of patches are ≤ 4 pixels,\n"
                 f"but {100 * area_in_big_u:.0f} % of the undated AREA sits in patches ≥ 1 ha", fontsize=11)

    for ax, (lon, lat, ha) in zip(axs[1], centres):
        cx, cy = tile_xy(lon, lat, 15)
        bc = tile_bounds_3857(cx - 1, cy - 1, cx + 1, cy + 1, 15)
        satc = mosaic(ESRI_SATELLITE, cx - 1, cy - 1, cx + 1, cy + 1, 15)
        oc_u = to_web_mercator(undated.astype("uint8"), tt, tc, bc, 768, 768)
        oc_d = to_web_mercator(dated.astype("uint8"), tt, tc, bc, 768, 768)
        extc = (bc[0], bc[2], bc[1], bc[3])
        ax.imshow(np.asarray(satc), extent=extc)
        ax.imshow(np.ma.masked_where(oc_d == 0, oc_d), cmap=ListedColormap(["#4a90c0"]), extent=extc, alpha=0.55, interpolation="nearest")
        ax.imshow(np.ma.masked_where(oc_u == 0, oc_u), cmap=ListedColormap(["#ff2d2d"]), extent=extc, alpha=0.6, interpolation="nearest")
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_title(f"3. Largest undated cluster: {ha:.0f} ha at {lat:.3f} N, {lon:.3f} W\n(red = undated, blue = dated; today's imagery)", fontsize=11)

    fig.suptitle("The 'pre-2016, undated' class — Tracker says built by 2016, WSF Evolution never saw it", fontsize=13)
    fig.text(0.5, 0.005, "Imagery: Esri World Imagery (streamed). WSF Tracker © DLR/MindEarth CC BY 4.0 · WSF Evolution © DLR CC-BY-4.0.",
             ha="center", fontsize=8)
    plt.tight_layout(rect=(0, 0.015, 1, 0.96))
    out = FIGURES / f"undated_pixels_{island.replace(' ', '_').lower()}.png"
    plt.savefig(out, dpi=110)
    print("saved", out)
    for lon, lat, ha in centres:
        print(f"  cluster {ha:.0f} ha at https://www.google.com/maps/@{lat:.5f},{lon:.5f},16z")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Gran Canaria")
