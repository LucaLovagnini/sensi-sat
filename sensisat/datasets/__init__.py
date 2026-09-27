"""Per-dataset adapters.

Each module here knows exactly two things about its dataset: where to fetch it
(URLs, tiling, authentication) and how to decode it (file layout, value encoding).
Everything downstream — clipping, area, comparison, statistics — is shared code in
`sensisat.raster` and `sensisat.stats` and must stay dataset-agnostic.

Each adapter exposes:
    NAME, MEASURE ("extent" | "surface"), ENCODING, RESOLUTION_M, YEARS, LICENSE, SOURCE_URL
    fetch(...)  -> list[Path]      download (cached) the files covering an area
    load(...)   -> (array, transform, crs)   decoded values for a bounding box
"""

from . import ghsl, wsf  # noqa: F401

__all__ = ["wsf", "ghsl"]
