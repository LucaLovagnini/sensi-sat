"""Decision 7: there must never be a second implementation of the statistics.

Per-zone numbers are precomputed now and may be served by an API later. The risk
that creates is specific and well known: the batch job and the web endpoint drift
apart, and the website starts quoting numbers the published tables do not contain.

The defence is that `stats.zonal` is one function with no I/O assumptions, and
both callers pass it the same arrays. This test builds the second caller — a
throwaway FastAPI route, thrown away at the end of the test — and checks that what
it serves is byte-identical to what the build writes.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sensisat.stats import zonal

pytest.importorskip("httpx", reason="FastAPI's TestClient needs httpx")


def _payload(raster, transform, crs, zones, **kwargs) -> str:
    """What the build writes: zonal() serialised to JSON."""
    return zonal(raster, transform, crs, zones, **kwargs).to_json(orient="records")


def test_route_and_build_agree_byte_for_byte(tiny_transform, square_mask, zones_gdf):
    raster = square_mask.astype("uint8")

    app = FastAPI()

    @app.get("/statistics")
    def statistics():
        # Exactly the same call the build makes — same function, same arguments.
        df = zonal(raster, tiny_transform, "EPSG:4326", zones_gdf,
                   kind="binary", label="built")
        return json.loads(df.to_json(orient="records"))

    served = TestClient(app).get("/statistics").json()
    from_build = json.loads(_payload(raster, tiny_transform, "EPSG:4326", zones_gdf,
                                     kind="binary", label="built"))

    assert served == from_build
    assert json.dumps(served, sort_keys=True) == json.dumps(from_build, sort_keys=True)
    assert served[0]["zone"] == "left half"
    assert served[0]["measure"] == "extent"


def test_extent_and_surface_are_not_interchangeable(tiny_transform, zones_gdf):
    """The same array read as extent and as surface must give different answers.

    A half-sealed pixel covers a whole pixel of ground but only half a pixel of
    built surface. Confusing the two is how a 100 km2 island grows to 200.
    """
    half_sealed = np.full((10, 10), 0.5, dtype="float32")

    extent = zonal((half_sealed > 0).astype("uint8"), tiny_transform, "EPSG:4326",
                   zones_gdf, kind="binary", label="v")
    surface = zonal(half_sealed, tiny_transform, "EPSG:4326", zones_gdf,
                    kind="fraction", label="v")

    assert extent["measure"].iloc[0] == "extent"
    assert surface["measure"].iloc[0] == "surface"
    assert surface["v_km2"].iloc[0] == pytest.approx(extent["v_km2"].iloc[0] / 2, rel=1e-6)
