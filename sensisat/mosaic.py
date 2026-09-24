"""Join a layer's per-island COGs into one archipelago-wide COG.

**Why this exists.** The viewer used to need an island chosen before it could draw
anything, because the data was one file per island and OpenLayers cannot composite
several GeoTIFF sources into one layer — passing multiple `sources` makes them
*bands* of one image, asserted to share an origin and resolution. So there was no
view in which the Canary Islands appeared as an archipelago with data on them,
which for a project about the Canary Islands is a gap rather than a detail.

**What it is NOT for.** The per-island split was never what made range reads cheap.
A Cloud-Optimized GeoTIFF is read in slices whatever its extent; that is what a COG
*is*. `catalog.py` used to justify the split partly as "per-island files make the
viewer fetch only what is on screen", and that reasoning is wrong — measured, the
same view costs the same bytes either way.

**What actually matters is the block size.** The archipelago grid is 1.38 gigapixels
and about four fifths ocean. DEFLATE squashes the ocean to almost nothing, so the
file grows only ~20 %; the cost that bites is the tile-offset table, which a reader
must fetch *in full* before it can draw a single pixel (OpenLayers walks every
overview level up front, and geotiff.js reads each level's offsets array when it
parses it). Measured on `buildings-dated`:

    per-island, 256 px blocks        927 tiles      9.3 KiB of header
    archipelago, 256 px blocks    28,360 tiles    334.4 KiB
    archipelago, 1024 px blocks    1,804 tiles     23.2 KiB

334 KiB before the first pixel is more than an entire cold visit costs today. At
1024 it is 23 KiB, and the archipelago layout stops being expensive. Hence
`blocksize`, chosen per layer by the caller — with one exception that is easy to get
wrong: a layer with many bands must stay small, because tiles are pixel-interleaved
and reading one band still decodes the whole tile. `density-trend` carries ten
uint16 epochs, so a 1024 tile would decode 20 MB to answer a question about one
epoch, and it keeps 256.

**Memory.** `raster.write_cog` builds the whole image in a `MemoryFile`, which is
right for one island and wrong here: two bands at 1.38 Gpx is 2.76 GB. This streams
instead — one island read at a time into a tiled GeoTIFF on disk, then GDAL's COG
driver converts it in a second pass.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.enums import Resampling


def archipelago_grid(transforms: list[Affine], shapes: list[tuple[int, int]]
                     ) -> tuple[Affine, tuple[int, int], list[tuple[int, int]]]:
    """The grid covering every island, and each island's integer pixel offset in it.

    **The offsets must be whole pixels, and that is asserted rather than assumed.**
    Every published layer lands on one shared grid (`sensisat.grid`), so islands
    differ only by an integer number of rows and columns. If that ever stops being
    true, a mosaic would silently resample — and resampling a categorical layer
    invents years nothing was built in (CLAUDE.md #5). A half-pixel slip is invisible
    to every other check, which is why M2 added a grid-alignment gate; this is the
    same check at the packaging step.
    """
    px = abs(transforms[0].a)
    py = abs(transforms[0].e)
    for t in transforms:
        if abs(abs(t.a) - px) > 1e-12 or abs(abs(t.e) - py) > 1e-12:
            raise ValueError(f"islands differ in pixel size: {t.a} vs {px}")

    x0 = min(t.c for t in transforms)
    y0 = max(t.f for t in transforms)

    offsets: list[tuple[int, int]] = []
    for t in transforms:
        fcol = (t.c - x0) / px
        frow = (y0 - t.f) / py
        col, row = round(fcol), round(frow)
        # Tolerance in PIXELS, and deliberately not tighter. A transform's origin is
        # a float, and an offset of N pixels accumulates N * epsilon of error — on
        # GHSL's 1/1200-degree grid, which is not exactly representable in binary,
        # a real 1704-pixel offset measures 1704.000007. That is 0.6 mm of ground
        # and not a defect. The failure this guards against is a HALF-pixel slip,
        # three orders of magnitude larger, so 0.01 px sits comfortably between the
        # two: ~40x above the worst observed noise and 50x below a real slip.
        if abs(fcol - col) > 0.01 or abs(frow - row) > 0.01:
            raise ValueError(
                f"island is not on the shared grid: offset ({fcol:.6f}, {frow:.6f}) "
                "is not a whole number of pixels, so mosaicking would resample it")
        offsets.append((col, row))

    width = max(col + w for (col, _), (h, w) in zip(offsets, shapes, strict=True))
    height = max(row + h for (_, row), (h, w) in zip(offsets, shapes, strict=True))
    transform = Affine(px, 0.0, x0, 0.0, -py, y0)
    return transform, (height, width), offsets


def mosaic(paths: list[Path], out: Path, *, blocksize: int,
           resampling: Resampling, compress: str = "deflate",
           predictor: int = 2) -> Path:
    """Write one archipelago COG from a layer's per-island COGs.

    Islands are disjoint apart from overlapping bounding boxes (La Graciosa sits
    inside Lanzarote's box), so writing is nodata-aware: a source pixel equal to
    nodata never overwrites something already placed. Without that, whichever file
    was written last would blank its neighbour's data with its own ocean.
    """
    from rio_cogeo.cogeo import cog_translate

    paths = [Path(p) for p in paths]
    metas, transforms, shapes = [], [], []
    for p in paths:
        with rasterio.open(p) as src:
            metas.append(src.meta.copy())
            transforms.append(src.transform)
            shapes.append((src.height, src.width))

    first = metas[0]
    for m in metas[1:]:
        if m["count"] != first["count"] or m["dtype"] != first["dtype"]:
            raise ValueError("islands disagree on band count or dtype")

    transform, (height, width), offsets = archipelago_grid(transforms, shapes)
    nodata = first["nodata"] if first["nodata"] is not None else 0

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(paths[0]) as src:
        descriptions = list(src.descriptions)
        tags = src.tags()

    profile = {
        "driver": "GTiff", "height": height, "width": width, "count": first["count"],
        "dtype": first["dtype"], "crs": first["crs"], "transform": transform,
        "nodata": nodata, "tiled": True, "blockxsize": 512, "blockysize": 512,
        "compress": compress, "predictor": predictor, "BIGTIFF": "IF_SAFER",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        staged = Path(tmpdir) / "mosaic.tif"
        # "w+" rather than "w": the merge reads back what is already placed so an
        # island's ocean cannot blank its neighbour's land, and a write-only dataset
        # raises UnsupportedOperation on the first read.
        with rasterio.open(staged, "w+", **profile) as dst:
            for i, description in enumerate(descriptions, 1):
                if description:
                    dst.set_band_description(i, description)
            if tags:
                dst.update_tags(**{k: str(v) for k, v in tags.items()})
            for p, (col, row), (h, w) in zip(paths, offsets, shapes, strict=True):
                with rasterio.open(p) as src:
                    data = src.read()
                window = rasterio.windows.Window(col, row, w, h)
                existing = dst.read(window=window)
                keep = data != nodata
                dst.write(np.where(keep, data, existing), window=window)

        dst_profile = {
            "driver": "GTiff", "tiled": True,
            "blockxsize": blocksize, "blockysize": blocksize,
            "compress": compress, "predictor": predictor,
        }
        with rasterio.open(staged) as src:
            cog_translate(src, out, dst_profile,
                          overview_resampling=resampling.name,
                          forward_band_tags=True, use_cog_driver=True, quiet=True)
    return out
