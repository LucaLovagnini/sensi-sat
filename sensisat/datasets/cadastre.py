"""Spanish Catastro, INSPIRE Buildings — the primary pre-2016 timeline (M1.1).

This is the only source in SensiSat that is not derived from satellite imagery. It
is the official building register: every building the state knows about, as a
polygon, with the year it was built. That makes it categorically different from
everything else here, with a different set of strengths and blind spots.

**What it is good at.** It sees individual buildings, including the dispersed
rural ones a 30 m satellite pixel cannot resolve — WSF Evolution misses about half
the 100 m cells that contain a pre-1985 building, and 89 % of them on La Gomera.
It carries a construction year for 98.5 % of Canary buildings, from 1900 to 2020,
produced by one method throughout, so there is no seam anywhere in that range.

**What it cannot see.**

1. *Roads, ports, airports, quarries.* Verified by reading the raw feed for Santa
   Lucia de Tirajana: `building.gml` holds 12,481 buildings, `buildingpart.gml`
   39,537 parts, and `otherconstruction.gml` just 87 features - every one of them
   an open-air swimming pool. There is not one road reference in any of the three
   files. Roads were ~17 % of WSF's 1985 baseline, which is why WSF Evolution
   stays in the roster as a complementary layer (M1.4) rather than being replaced.
2. *Demolished buildings.* The register describes what stands today. A building
   put up in 1960 and demolished in 1995 is simply absent, so the further back you
   look the more the cadastre reads as a floor rather than a count. This is
   survivorship bias, and it is the price of the 1900 start date.
3. *Spain.* There is no cadastre outside it, which is why era-a is a plug-in with
   WSF Evolution as the global fallback.

**Encoding.** One band, uint8:

    0          no building
    1..200     year first built, offset by 1899 (1 = 1900, 121 = 2020)
    255        a building stands here, construction year unknown

255 is deliberately not folded into "no building" and not given an invented year.
It is the same honesty the `pre-2016 undated` class buys in era-a: a pixel we know
is built but cannot date is a third state, not a missing one.

License: the Catastro's INSPIRE services are free to reuse with attribution
(Direccion General del Catastro). Source: catastro.hacienda.gob.es/webinspire
"""

from __future__ import annotations

import json
import re
import warnings
import zipfile
from pathlib import Path

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import Affine

from ..config import ISLAND_BBOX, RAW
from ..download import fetch
from ..encoding import UNDATED, YEAR_MAX, YEAR_MIN, YEAR_OFFSET, decode_year  # noqa: F401
from ..encoding import built_by as _built_by
from ..encoding import merge_oldest as _merge_oldest
from ..grid import for_island

NAME = "Catastro INSPIRE Buildings (Direccion General del Catastro)"
MEASURE = "extent"
ENCODING = "year first built"
RESOLUTION_M = 10
LICENSE = "Free reuse with attribution (Direccion General del Catastro)"
SOURCE_URL = "https://www.catastro.hacienda.gob.es/webinspire/index.html"

ATOM = "https://www.catastro.hacienda.gob.es/INSPIRE/buildings/{prov}/ES.SDGC.bu.atom_{prov}.xml"
PROVINCES = ("35", "38")  # Las Palmas; Santa Cruz de Tenerife

DEST = RAW / "catastro"
INDEX = DEST / "municipality_index.json"

_ENTRY = re.compile(r'href="([^"]*A\.ES\.SDGC\.BU\.(\d{5})\.zip)"')


# ---------------------------------------------------------------------------
# Discovery and download
# ---------------------------------------------------------------------------
def municipalities(province: str) -> list[tuple[str, str]]:
    """[(code, zip url)] for one province, from its ATOM feed.

    The feed is the authoritative list; hard-coding 88 municipality codes would be
    a hand-typed table that silently rots when a code changes.
    """
    import requests

    from ..config import HTTP_HEADERS

    r = requests.get(ATOM.format(prov=province), headers=HTTP_HEADERS, timeout=120)
    r.raise_for_status()
    seen: dict[str, str] = {}
    for url, code in _ENTRY.findall(r.text):
        seen.setdefault(code, url)
    return sorted(seen.items())


def all_municipalities() -> list[tuple[str, str]]:
    """Every Canary municipality across both provinces (88 as of 2026-09)."""
    out: list[tuple[str, str]] = []
    for prov in PROVINCES:
        out.extend(municipalities(prov))
    return out


# Each municipality zip holds three feature files. Only `building` is used, and
# `buildingpart` is by far the largest - 1.6 GiB against 866 MiB across the
# archipelago - so it is left compressed. `otherconstruction` is small and is kept
# because it is the file that proves the cadastre holds no roads (87 features on
# Santa Lucia, every one a swimming pool).
WANTED_SUFFIXES = (".building.gml", ".otherconstruction.gml", ".xml")


def fetch_municipality(code: str, url: str, *, quiet: bool = True) -> Path:
    """Download one municipality and unzip the parts we use. Returns its directory."""
    zip_path = fetch(url, DEST / f"A.ES.SDGC.BU.{code}.zip", quiet=quiet).path
    out_dir = DEST / code
    gml = out_dir / f"A.ES.SDGC.BU.{code}.building.gml"
    if not gml.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                if member.endswith(WANTED_SUFFIXES):
                    zf.extract(member, out_dir)
    return out_dir


def fetch_all(*, quiet: bool = True, progress: bool = True) -> list[tuple[str, Path]]:
    """Download all 88 municipalities (~500 MiB, cached). Returns [(code, dir)]."""
    entries = all_municipalities()
    out = []
    for i, (code, url) in enumerate(entries, 1):
        if progress:
            print(f"\r  cadastre {i:3d}/{len(entries)}  {code}", end="", flush=True)
        try:
            out.append((code, fetch_municipality(code, url, quiet=quiet)))
        except Exception as exc:  # a single missing municipality must not stop a build
            print(f"\n  ! {code}: {type(exc).__name__}: {exc}")
    if progress:
        print()
    return out


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------
def buildings(code: str, *, columns=("beginning", "conditionOfConstruction", "end")):
    """Buildings of one municipality as a GeoDataFrame, with an integer `year`.

    **What the year actually means** (established 2026-09-20 against the Catastro's
    own methodology, not inferred). It is NOT the year the building went up. The
    Direccion General del Catastro defines it verbatim as:

        "Fecha de finalizacion de la construccion que consta en la base de datos
         catastral. En el supuesto de rehabilitacion integral de una construccion,
         la fecha de finalizacion de dicha rehabilitacion tiene la consideracion de
         fecha de construccion."

    A comprehensive rehabilitation RESETS the year, and the Catastro's own published
    map from this field is titled "Fecha de construccion o reforma integral". So a
    1970 house rebuilt in 2019 is a 2019 building here. This is correct for the
    register's purpose, which is taxation, and it is the measured cause of M3's
    finding that a quarter to a third of what we date 2016-2024 was already standing
    in 2015. See `docs/data-evaluation.md` and `scripts/analysis_20_*`.

    `beginning` is an ISO timestamp. Buildings with no parseable date keep year 0
    and become the UNDATED class, never a guess. Dates before 1900 are clamped to
    1900: they are real, but they are also the range where the register is least
    reliable, and the published HISDAC-ES derivative starts at 1900 too, so
    clamping keeps the two comparable.

    Two fields invite misreading, so both were checked against the raw feed:

    - `end` is *not* a demolition date, and it is *not* the end of a construction
      period either -- an earlier version of this docstring said so and was wrong.
      A Building here is a container of several CONSTRUCTION UNITS; per the INSPIRE
      dataset specification, `beginning` carries the oldest unit's date and `end`
      the newest. Measured across the feed the gap reaches 213 years, which no
      construction period explains. **Taking `beginning` is therefore right**: it is
      the oldest date the register still holds, so it is the least
      rehabilitation-contaminated estimate available. Nothing here uses `end` to
      retire a building; the register simply omits what no longer stands.
    - the 163 undated rows (1.3 %) are undated because their dates are malformed -
      `--01-01T00:00:00` with no year at all, or `88-01-01T00:00:00`, which could
      be 1888 or 1988. A two-digit year is ambiguous, so it stays UNDATED instead
      of being resolved to whichever century looks likelier.
    """
    import geopandas as gpd

    gml = DEST / code / f"A.ES.SDGC.BU.{code}.building.gml"
    if not gml.exists():
        raise FileNotFoundError(f"{gml} - run fetch_municipality({code!r}, url) first")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gdf = gpd.read_file(gml)

    year = (
        gdf["beginning"].astype("string").str.slice(0, 4)
        if "beginning" in gdf.columns else None
    )
    if year is None:
        gdf["year"] = 0
    else:
        y = year.str.extract(r"^(\d{4})$", expand=False).astype("Float64")
        y = y.where(y.notna(), 0).astype("int64")
        gdf["year"] = np.where(y == 0, 0, np.clip(y, YEAR_MIN, YEAR_MAX))
    keep = [c for c in columns if c in gdf.columns]
    return gdf[[*keep, "year", "geometry"]]


_GFS_EXTENT = re.compile(
    r"<ExtentXMin>([\d.eE+-]+)</ExtentXMin>\s*<ExtentXMax>([\d.eE+-]+)</ExtentXMax>\s*"
    r"<ExtentYMin>([\d.eE+-]+)</ExtentYMin>\s*<ExtentYMax>([\d.eE+-]+)</ExtentYMax>",
    re.S,
)
_GFS_SRS = re.compile(r"<SRSName>([^<]+)</SRSName>")


def _bounds_of(code: str) -> tuple[float, float, float, float]:
    """Lon/lat bounds of a municipality.

    Read from the `.gfs` sidecar GDAL writes beside the GML on first open, which
    records the layer's extent and CRS - parsing a few hundred bytes instead of
    re-reading tens of megabytes of XML. The GML is only opened when that sidecar
    is missing, which also creates it for next time.
    """
    import geopandas as gpd
    from pyproj import Transformer

    gml = DEST / code / f"A.ES.SDGC.BU.{code}.building.gml"
    gfs = gml.with_suffix(".gfs")
    if gfs.exists():
        text = gfs.read_text(errors="ignore")
        extent, srs = _GFS_EXTENT.search(text), _GFS_SRS.search(text)
        if extent and srs:
            xmin, xmax, ymin, ymax = (float(v) for v in extent.groups())
            epsg = srs.group(1).rsplit(":", 1)[-1]
            tf = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
            (lon_min, lon_max), (lat_min, lat_max) = tf.transform([xmin, xmax], [ymin, ymax])
            return lon_min, lat_min, lon_max, lat_max

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        g = gpd.read_file(gml, columns=[])
    return tuple(g.to_crs("EPSG:4326").total_bounds)


def build_index(*, rebuild: bool = False) -> dict[str, dict]:
    """{municipality code: {island, bounds}}, derived from the data and cached.

    The ATOM feed carries no bounding box, so which island a municipality sits on
    is not knowable without looking at its geometry. Rather than hand-type 88
    assignments, each municipality's own bounds are read once and cached.

    Both fields matter, for a reason that only shows up in one place. `island` is
    the island a municipality's centre falls on; `bounds` is what `codes_for` uses.
    They differ for La Graciosa, which is not a municipality at all - it belongs to
    Teguise, whose centre is on Lanzarote. Selecting by centre would leave La
    Graciosa with no buildings; selecting by overlap gives it Teguise's, which is
    where its buildings actually are.
    """
    if INDEX.exists() and not rebuild:
        cached = json.loads(INDEX.read_text())
        if cached and isinstance(next(iter(cached.values())), dict):
            return cached

    index: dict[str, dict] = {}
    entries = all_municipalities()
    for i, (code, url) in enumerate(entries, 1):
        print(f"\r  indexing {i:3d}/{len(entries)}  {code}", end="", flush=True)
        try:
            fetch_municipality(code, url)
            bounds = _bounds_of(code)
        except Exception as exc:
            print(f"\n  ! {code}: {type(exc).__name__}")
            index[code] = {"island": None, "bounds": None}
            continue
        minx, miny, maxx, maxy = bounds
        cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
        index[code] = {
            "island": next((name for name, (lo, la, hi, ha) in ISLAND_BBOX.items()
                            if lo <= cx <= hi and la <= cy <= ha), None),
            "bounds": [round(v, 6) for v in bounds],
        }
    print()
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(index, indent=2, sort_keys=True))
    return index


def codes_for(island: str) -> list[str]:
    """Municipality codes whose extent overlaps an island's box.

    Overlap, not containment: a municipality that straddles two islands is built
    into both, and the rasteriser clips it to each island's boundary anyway, so
    including one municipality too many costs a little time and changes no number.
    Missing one, by contrast, silently loses every building it holds.
    """
    lo, la, hi, ha = ISLAND_BBOX[island]
    out = []
    for code, entry in build_index().items():
        b = entry.get("bounds")
        if b and not (b[2] < lo or b[0] > hi or b[3] < la or b[1] > ha):
            out.append(code)
    return sorted(out)


def year_first_built(island: str, *, codes: list[str] | None = None,
                     transform: Affine | None = None, shape: tuple[int, int] | None = None,
                     progress: bool = True) -> tuple[np.ndarray, Affine, str]:
    """Rasterise an island's buildings onto the shared 10 m grid.

    Returns (uint8 array, transform, crs) in the encoding documented above.

    **Paint order is the whole algorithm.** Where buildings overlap a pixel, the
    pixel must carry the year it FIRST became built - so shapes are painted newest
    first and oldest last, letting the oldest win. Undated buildings are painted
    before all of them, so any dated neighbour overrides them: a known year always
    beats "built, year unknown".
    """
    if transform is None or shape is None:
        transform, shape = for_island(island)
    codes = codes if codes is not None else codes_for(island)
    if not codes:
        raise LookupError(f"no cadastral municipalities indexed for {island!r}")

    out = np.zeros(shape, dtype="uint8")
    for i, code in enumerate(codes, 1):
        if progress:
            print(f"\r  {island}: municipality {i:3d}/{len(codes)}  {code}", end="", flush=True)
        gdf = buildings(code).to_crs("EPSG:4326")
        if gdf.empty:
            continue
        undated = gdf[gdf["year"] == 0]
        dated = gdf[gdf["year"] > 0].sort_values("year", ascending=False)

        shapes = [(g, UNDATED) for g in undated.geometry if g is not None and not g.is_empty]
        shapes += [(g, int(y) - YEAR_OFFSET) for g, y in zip(dated.geometry, dated["year"], strict=True)
                   if g is not None and not g.is_empty]
        if not shapes:
            continue
        burnt = rasterize(shapes, out_shape=shape, transform=transform, fill=0, dtype="uint8")

        # Combine municipalities: an already-dated pixel keeps the older year.
        out = _merge_oldest(out, burnt)
    if progress:
        print()
    return out, transform, "EPSG:4326"


def built_mask(arr: np.ndarray, year: int | None = None) -> np.ndarray:
    """Boolean "a building stands here by `year`" — see sensisat.encoding."""
    return _built_by(arr, year)
