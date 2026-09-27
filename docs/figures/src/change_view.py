"""State view vs change view, and extent vs surface on real data.

Panel 1: a CHANGE map (grey = built by 1995, red = added 1996–2015) — the view that makes a
         +9 % change visible where two side-by-side 'state' maps look identical.
Panel 2: south-coast close-up where the 1990s–2000s tourist build-out is visible at native scale.
Panel 3: growth of Gran Canaria indexed to 1990 in WSF Evolution (an EXTENT product) and in
         GHSL built surface (a SURFACE product) — they disagree by ~5x on the growth rate.
GHSL numbers come from docs/figures/data/ghsl_built_surface_gran_canaria_km2.json
(Earth Engine, JRC/GHSL/P2023A/GHS_BUILT_S, sum of built_surface over a 30 km buffer, 2026-09-19).
Run:  python docs/figures/src/change_view.py
"""
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from scipy.ndimage import maximum_filter

from common import (ESRI_GRAY, ESRI_SAT, FIG, GC_BBOX, basemap_window, built_by, km2, load_wsf_evo, mosaic, overlay_on,
                    tile_bounds_3857, tile_xy)

GHSL_JSON = FIG / "data" / "ghsl_built_surface_gran_canaria_km2.json"
GHSL_OBSERVED_EPOCHS = (1975, 1990, 2000, 2014, 2018)   # JRC GHSL Data Package 2023: the rest is interpolated
YEARS = list(range(1985, 2016))


def main():
    arr, tr, crs = load_wsf_evo(GC_BBOX)
    wsf = {y: km2(built_by(arr, y)) for y in YEARS}
    ghsl = {int(k): v for k, v in json.load(open(GHSL_JSON)).items() if k.isdigit()}

    # Panel 1 at zoom 12 (~34 m per screen pixel ≈ one data pixel per screen pixel)
    gray, b, ext = basemap_window(GC_BBOX, 12, ESRI_GRAY)
    o = overlay_on(arr, tr, crs, b, gray.width, gray.height)
    old = (o > 0) & (o <= 1995)
    new = o > 1995
    new_vis = maximum_filter(new.astype(np.uint8), size=3) > 0      # thicken by 1 px so isolated pixels survive downscaling
    # Panel 2: Meloneras → Arguineguín → Puerto Rico at zoom 13
    cx, cy = tile_xy(-15.64, 27.77, 13)
    bc = tile_bounds_3857(cx - 1, cy - 1, cx + 1, cy, 13)
    satc = mosaic(ESRI_SAT, cx - 1, cy - 1, cx + 1, cy, 13)
    oc = overlay_on(arr, tr, crs, bc, 768, 512)
    extc = (bc[0], bc[2], bc[1], bc[3])

    cmap = plt.get_cmap("plasma", len(YEARS))
    norm = BoundaryNorm([y - 0.5 for y in YEARS] + [2015.5], cmap.N)
    fig = plt.figure(figsize=(16, 15))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1])
    ax1, ax2, ax3 = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])

    ax1.imshow(np.asarray(gray), extent=ext)
    ax1.imshow(np.ma.masked_where(~old, old), cmap=ListedColormap(["#6b6b6b"]), extent=ext, alpha=0.9, interpolation="nearest")
    ax1.imshow(np.ma.masked_where(~new_vis, new_vis), cmap=ListedColormap(["#e60000"]), extent=ext, interpolation="nearest")
    added = wsf[2015] - wsf[1995]
    ax1.set_title(f"1. CHANGE view, Gran Canaria (WSF Evolution)\ngrey = built by 1995 ({wsf[1995]:.0f} km²) · RED = added 1996–2015 "
                  f"(+{added:.1f} km², +{100 * added / wsf[1995]:.0f} %)\n(red thickened by 1 pixel so it survives shrinking to screen size)", fontsize=11)
    ax1.set_xticks([]); ax1.set_yticks([])

    ax2.imshow(np.asarray(satc), extent=extc)
    im = ax2.imshow(np.ma.masked_where(oc == 0, oc), cmap=cmap, norm=norm, extent=extc, alpha=0.85, interpolation="nearest")
    ax2.set_title("2. South coast close-up (Meloneras → Arguineguín → Puerto Rico), 30 m pixels\n"
                  "colour = year first built; here the 1990s–2000s tourist build-out IS visible", fontsize=11)
    ax2.set_xticks([]); ax2.set_yticks([])
    cb = fig.colorbar(im, ax=ax2, fraction=0.04, pad=0.02, ticks=[1985, 1990, 1995, 2000, 2005, 2010, 2015]); cb.set_label("year first built")

    wy, gy = sorted(wsf), sorted(ghsl)
    ax3.plot(wy, [100 * wsf[y] / wsf[1990] for y in wy], "o-", color="#1f4e79",
             label=f"WSF Evolution (30 m pixels containing settlement): {wsf[1990]:.0f} → {wsf[2015]:.0f} km², 1990→2015 = +{100 * (wsf[2015] / wsf[1990] - 1):.0f} %")
    ax3.plot(gy, [100 * ghsl[y] / ghsl[1990] for y in gy], "s-", color="#c00000",
             label=f"GHSL built surface (m² of built cover): {ghsl[1990]:.0f} → {ghsl[2015]:.0f} km², 1990→2015 = +{100 * (ghsl[2015] / ghsl[1990] - 1):.0f} %")
    for y in GHSL_OBSERVED_EPOCHS:
        ax3.axvline(y, color="#c00000", alpha=0.15, lw=6)
    ax3.text(1976, 101, "red bands = GHSL epochs with real imagery\n(1975, 1990, 2000, 2014, 2018); GHSL values between them are interpolated", fontsize=9, color="#7a0000")
    ax3.set_xlim(1974, 2021); ax3.set_ylabel("built-up, index 1990 = 100"); ax3.set_xlabel("year"); ax3.grid(alpha=0.3); ax3.legend(loc="upper left", fontsize=10)
    ax3.set_title("3. The two reference products DISAGREE on how fast Gran Canaria grew — same island, different definitions and methods", fontsize=11)
    fig.suptitle("Why 1995 and 2015 looked alike: growth is +9 % on a large 1985 base — and WSF may be under-stating it", fontsize=13)
    fig.text(0.5, 0.005, "Basemaps: Esri World Light Gray · Esri World Imagery (streamed). Overlay: WSF Evolution © DLR CC-BY-4.0. GHSL © European Union, JRC, CC BY 4.0.", ha="center", fontsize=8)
    out = FIG / "sensisat_change_preview.png"
    plt.savefig(out, dpi=110, bbox_inches="tight")
    print("saved", out, {y: round(wsf[y], 1) for y in (1985, 1990, 1995, 2000, 2005, 2010, 2015)})


if __name__ == "__main__":
    main()
