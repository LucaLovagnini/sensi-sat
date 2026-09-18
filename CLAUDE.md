# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SensiSat is an open-source geospatial platform that visualizes urban expansion in the Canary Islands across time using satellite-derived land-cover datasets. It targets researchers, conservation NGOs, and environmental planners interested in how urbanization affects ecosystems and biodiversity.

**Geographic scope:** Canary Islands (Spain) — bounding box roughly Lat 27.5–29.5, Lon -18.5 to -13.0.

**Temporal scope:** 1985–present, combining two datasets:
- **WSF Evolution** (1985–2015): 30m resolution, yearly, binary settlement/non-settlement
- **Google Dynamic World** (2015–present): 10m resolution, scene-level (~5–10 days), multi-class land cover

**GEE project identifier:** `sensiblesat`

## Current State

The project is in early prototyping. All code lives in Jupyter Notebooks under `geeLocalTesting/`. There is no Python package structure, dependency management, tests, or CI yet.

### Running Notebooks

```bash
pip install earthengine-api geemap
earthengine authenticate
```

Open notebooks in JupyterLab and run cells top-to-bottom. GEE must be initialized with `ee.Initialize(project='sensiblesat')`.

### Existing Notebooks

- **`geeLocalTesting/urban_expansion_canarias.ipynb`** — Clean, production-ready analysis. Dynamic World `label` band + `mode()` aggregation, Gran Canaria scope. Outputs stable/new/removed categories with km² stats and a three-color map. Includes `ee.profilePrinting()` for compute monitoring.
- **`geeLocalTesting/gee_building_comparison.ipynb`** — NDBI spectral index approach using Sentinel-2. Computes NDBI from bands B11/B8, applies threshold-based masking, detects change between two years.
- **`geeLocalTesting/Test GEE.ipynb`** — Experimental notebook (preserved as history). Iterates through multiple approaches; the final proven methodology was distilled into `urban_expansion_canarias.ipynb`.

### Cache Directory

`geeLocalTesting/cache/` contains cached OpenStreetMap Nominatim geocoding responses (GeoJSON boundaries), hashed by request URL.

## Planned Architecture

### Data Pipeline

Lazy materialization: data is generated once via GEE, exported as Cloud Optimized GeoTIFF (COG), stored in AWS S3, and served many times. A STAC metadata catalog indexes all datasets by time/bbox/dataset/asset location. Missing data triggers on-demand GEE processing jobs.

```
STAC lookup → asset not found → GEE processing job → COG to S3 → STAC updated
```

### Storage (S3)

```
s3://urban-canaries/
  wsf/          # WSF Evolution yearly TIFs (1985-2015)
  dynamic-world/ # Dynamic World monthly composites (2015-present)
  density/       # Derived urban density layers
```

### Tile Serving

TiTiler on AWS Lambda converts COGs to 256x256 PNG map tiles on demand:
```
/tiles/{dataset}/{date}/{z}/{x}/{y}
```

### Frontend

MapLibre GL or Mapbox GL for interactive mapping with time slider animation. Requests tiles via URL template from TiTiler.

### Backend

FastAPI handling STAC queries, dataset availability checks, job triggering, and tile serving coordination.

### Urban Density

Computed as `urban_pixels / window_area` at configurable window sizes (300m, 500m, 1km), producing heatmaps with levels: none / sparse / medium / dense.

## Key GEE Patterns

- **Sentinel-2 composites:** `COPERNICUS/S2_SR_HARMONIZED`, filtered by cloud percentage < 20%, `median()` aggregation
- **Dynamic World labels:** `GOOGLE/DYNAMICWORLD/V1`, `label` band with `mode()` is preferred over `built` probability with `median()` for temporal stability
- **Built class:** Dynamic World class 6 = "Built", class 0 = "Water"
- **Water masking:** Essential for island/coastal regions to prevent false positives
- **Area calculation:** `image.multiply(ee.Image.pixelArea()).reduceRegion()` with scale 30 for speed, scale 10 for precision
- **Profiling:** Wrap `getInfo()` calls in `with ee.profilePrinting():` to see EECU-seconds and memory per operation

## GEE Compute Budget

The `sensiblesat` project is on the noncommercial free tier. Quota tiers take effect April 27, 2026:

| Tier | Monthly Limit | Requirements |
|------|--------------|--------------|
| Community (default) | 150 EECU-hours | None |
| Contributor | 1,000 EECU-hours | Billing account (not charged) |
| Partner | 100,000 EECU-hours | Application for high-impact sustainability work |

**Benchmark (Gran Canaria, 2-period analysis):** ~0.49 EECU-hours per run. The `reduce.mode` over a full year of Dynamic World scenes accounts for ~93% of compute. Scaling to all Canary Islands would roughly 3-4x this cost. Quotas are soft limits — exceeding them throttles parallelism rather than blocking requests.
