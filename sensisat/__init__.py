"""SensiSat — urban expansion in the Canary Islands from open datasets.

Milestone 0 is a local evaluation of candidate datasets: no cloud, no website.
The package is deliberately thin and is organised the way the eventual pipeline
will be (see docs/architecture notes in the plan):

    fetch -> decode          per dataset, in sensisat.datasets.*
    normalize -> harmonize   shared, in sensisat.raster
    measure                  shared, in sensisat.stats

Start here:
    from sensisat import config, datasets, raster, stats
"""

from . import config, download, raster, stats, tiles, zones  # noqa: F401

__version__ = "0.1.0"
__all__ = ["config", "download", "raster", "stats", "tiles", "zones", "datasets"]
