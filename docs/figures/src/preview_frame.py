"""What a SensiSat map frame is: a third-party basemap plus our thin overlay.

Downloads the two DLR WSF Evolution tiles covering Gran Canaria (public, CC-BY-4.0),
measures how small the overlay is once encoded the way we would publish it, and renders
four panels: satellite basemap alone, the overlay at two slider positions (same file,
different threshold), and a close-up showing that our data are pixels, not outlines.
Run:  python docs/figures/src/preview_frame.py
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import BoundaryNorm

from common import (ATTRIBUTION, DATA, ESRI_GRAY, ESRI_SAT, FIG, GC_BBOX, basemap_window, load_wsf_evo, overlay_on,
                    tile_bounds_3857, tile_xy, mosaic)

YEARS = list(range(1985, 2016))


def overlay_size_kib(arr, tr, crs) -> int:
    """Encode the Gran Canaria 'year first built' raster as we would publish it (uint8, DEFLATE, sparse)."""
    u8 = np.where(arr > 0, (arr - 1984).astype(np.uint8), 0)     # 1985 → 1 … 2015 → 31, 0 = not built
    out = DATA / "grancanaria_year_first_built.tif"
    profile = dict(driver="GTiff", height=u8.shape[0], width=u8.shape[1], count=1, dtype="uint8", crs=crs, transform=tr,
                   nodata=0, tiled=True, blockxsize=256, blockysize=256, compress="deflate", predictor=2, SPARSE_OK=True)
    with rasterio.open(out, "w", **profile) as dst:
        dst.write(u8, 1)
    return out.stat().st_size // 1024


def main():
    arr, tr, crs = load_wsf_evo(GC_BBOX)
    kib = overlay_size_kib(arr, tr, crs)

    # Island view (zoom 11) and a Las Palmas close-up (zoom 14)
    light, b, ext = basemap_window(GC_BBOX, 11, ESRI_GRAY)
    sat, _, _ = basemap_window(GC_BBOX, 11, ESRI_SAT)
    ov = overlay_on(arr, tr, crs, b, light.width, light.height)
    cx, cy = tile_xy(-15.435, 28.115, 14)
    bc = tile_bounds_3857(cx - 1, cy - 1, cx + 1, cy + 1, 14)
    satc = mosaic(ESRI_SAT, cx - 1, cy - 1, cx + 1, cy + 1, 14)
    ovc = overlay_on(arr, tr, crs, bc, 768, 768)
    extc = (bc[0], bc[2], bc[1], bc[3])

    cmap = plt.get_cmap("plasma", len(YEARS))
    norm = BoundaryNorm([y - 0.5 for y in YEARS] + [2015.5], cmap.N)

    def show(ax, img, ovr, upto, title, extent):
        ax.imshow(np.asarray(img), extent=extent)
        m = np.ma.masked_where((ovr == 0) | (ovr > upto), ovr)
        im = ax.imshow(m, cmap=cmap, norm=norm, extent=extent, alpha=0.9, interpolation="nearest")
        ax.set_title(title, fontsize=11); ax.set_xticks([]); ax.set_yticks([])
        return im

    fig, axs = plt.subplots(2, 2, figsize=(15, 15))
    axs[0, 0].imshow(np.asarray(sat), extent=ext); axs[0, 0].set_xticks([]); axs[0, 0].set_yticks([])
    axs[0, 0].set_title("A. Third-party basemap (satellite photo).\nNOT our data — streamed from the provider, like any web map.", fontsize=11)
    show(axs[0, 1], light, ov, 1995, "B. SensiSat layer, slider at 1995\n(only pixels first built ≤ 1995 are drawn)", ext)
    im = show(axs[1, 0], light, ov, 2015, "C. SensiSat layer, slider at 2015 — SAME FILE as B,\ncoloured by year first built (dark blue = already built by 1985)", ext)
    show(axs[1, 1], satc, ovc, 2015, "D. Close-up, Las Palmas: our data are 30 m PIXELS on top of the photo,\nnot building outlines. Colour = year first built.", extc)
    cb = fig.colorbar(im, ax=axs.ravel().tolist(), fraction=0.025, pad=0.01, ticks=[1985, 1990, 1995, 2000, 2005, 2010, 2015])
    cb.set_label("Year first built (WSF Evolution, DLR, 30 m). 1985 = built by 1985, the first year observed")
    fig.suptitle(f"What a SensiSat frame is: someone else's basemap + our thin overlay.\n"
                 f"The overlay for Gran Canaria, ALL years 1985–2015, is one file of {kib} KiB.", fontsize=13)
    fig.text(0.5, 0.005, ATTRIBUTION, ha="center", fontsize=8)
    out = FIG / "sensisat_preview.png"
    plt.savefig(out, dpi=110, bbox_inches="tight")
    print("saved", out, f"overlay = {kib} KiB")


if __name__ == "__main__":
    main()
