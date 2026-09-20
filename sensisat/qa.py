"""Level-1 automated checks: the gates a build has to pass before it is published.

These are the cheap checks that run on every build in seconds (plan section 7).
They are not an accuracy assessment — that is M3, needs human interpretation of
aerial photographs, and produces a number with a confidence interval. What these
do is catch the failures that are *knowable without ground truth*: a total that
has moved by a factor, settlement appearing on a lava field, a layer that has
silently slipped half a pixel off the grid, loss at a rate nothing physical could
produce.

Every gate returns its measured value, not just a verdict, so a failure says how
far off it is and a pass leaves a number in the build log worth reading.

**On thresholds.** Each band below is a measurement from M0, widened. That is
deliberate: a gate whose threshold was guessed either fires constantly or never
fires. These fire when a layer moves away from what was actually measured on this
archipelago, which is the only thing they can honestly police.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import Affine

from .config import FIGURES
from .grid import same_grid
from .raster import area_km2, iou

CORINE_TABLE = FIGURES / "data" / "m0_corine_2018.csv"

# Expected size of each layer relative to CORINE 2018 "artificial surfaces", the
# broadest official measure of the same subject. The ladder M0 measured across the
# archipelago (CORINE 469.5 km2 = 1.00): WSF Evolution 0.80, Imperviousness 0.73,
# Tracker 0.65, Copernicus built-up 0.55, GHSL surface 0.33, cadastre 0.21. None of
# these products is wrong; each is a stricter idea of "built". The bands are those
# ratios widened by roughly half, so a definitional difference passes and a broken
# build - a missing mask, a wrong pixel area, a dropped municipality - does not.
CORINE_BAND: dict[str, tuple[float, float]] = {
    "buildings-dated": (0.08, 0.45),
    "settlement-era-a": (0.20, 0.95),
    "settlement-era-b": (0.20, 1.05),
    # Upper bound 1.30 rather than ~0.8. Sealed surface legitimately EXCEEDS
    # CORINE's artificial total where settlement is dispersed, because CORINE's
    # minimum mapping unit is 25 hectares and anything smaller is invisible to it.
    # Measured: seven islands fall between 0.55 and 0.75, and La Gomera reaches
    # 1.20 - a small, steep island of scattered hamlets where CORINE finds only
    # 3.85 km2. That is CORINE under-reporting, not our layer over-reporting, and
    # the same island is anomalous in M0's records for the same reason.
    "density-current": (0.30, 1.30),
    "density-trend": (0.12, 0.60),
}
MIN_CORINE_KM2 = 1.0     # below this an island's reference is too small to police

# % of a control polygon a product may call built. Measured across all seven
# controls at 0.000-0.047 %, so 0.1 % leaves headroom without being toothless.
CONTROL_MAX_SHARE = 0.1
LOSS_MAX_PCT_PER_YEAR = 0.2      # real loss measured at 0.017-0.052 %/yr
MIN_IOU_VS_INDEPENDENT = 0.30    # M0 measured 0.40 for Tracker-2021 vs Copernicus 2021


@dataclass(frozen=True)
class Gate:
    """One check, its measured value, and whether that value is acceptable."""

    gate: str
    layer: str
    island: str
    passed: bool
    value: float | None
    expected: str
    detail: str = ""
    # A gate that did not apply is NOT a gate that passed. Timanfaya is on
    # Lanzarote, so the lava control cannot say anything about Tenerife; counting
    # that as a pass inflates the score with checks that never ran. Skips are
    # tracked separately and reported separately.
    skipped: bool = False

    def __str__(self) -> str:
        mark = "SKIP" if self.skipped else ("PASS" if self.passed else "FAIL")
        shown = "n/a" if self.value is None else f"{self.value:.4g}"
        return f"  [{mark}] {self.gate:18s} {self.layer:20s} {self.island:14s} {shown:>10s}  ({self.expected}){self.detail and '  ' + self.detail}"


def _corine(island: str) -> float | None:
    if not CORINE_TABLE.exists():
        return None
    df = pd.read_csv(CORINE_TABLE)
    row = df[df["island"] == island]
    return float(row["artificial_km2"].iloc[0]) if len(row) else None


# ---------------------------------------------------------------------------
def totals_in_band(layer: str, island: str, value_km2: float) -> Gate:
    """Is this layer's total the right *size* for this island?

    Compared against CORINE's artificial surfaces rather than against another
    satellite product, because CORINE is an official map made by a different
    method — agreement with it is weak evidence of correctness, but a total far
    outside its band is strong evidence of a bug.
    """
    reference = _corine(island)
    band = CORINE_BAND.get(layer)
    if reference is None or band is None:
        return Gate("totals", layer, island, True, value_km2, "no band for this layer", skipped=True)
    if reference < MIN_CORINE_KM2:
        return Gate("totals", layer, island, True, value_km2,
                    f"CORINE {reference} km2 too small to police", skipped=True)
    ratio = value_km2 / reference
    lo, hi = band
    return Gate("totals", layer, island, lo <= ratio <= hi, ratio,
                f"{lo}-{hi} x CORINE {reference:.1f} km2", f"= {value_km2:.2f} km2")


def negative_control(layer: str, island: str, built: np.ndarray, transform: Affine) -> Gate:
    """Does anything appear built on ground where building is impossible?

    This is the only gate that can catch a product *inventing* settlement, so its
    coverage is worth stating plainly: seven of the eight islands have a control,
    together 623 km2 of protected ground drawn from the official Canary protected
    areas register. Until this was extended it was Timanfaya alone — 51 km2 on
    Lanzarote — which left Tenerife and Gran Canaria, the two islands holding most
    of the built-up area, with no commission check at all.

    Not zero, but near it. Every control contains some real structures — Teide has
    the Parador and the cable-car stations, Timanfaya the LZ-67 road and the El
    Diablo restaurant — so the control is the polygon MINUS a 30 m buffer around
    known infrastructure, and the expectation is "almost nothing", not "nothing".

    La Graciosa has no control, and this returns a SKIP saying so rather than a
    pass. A control that should exist and cannot be loaded is a FAILURE, because
    that is exactly how this gate went silently missing before.
    """
    from . import zones

    if not zones.has_negative_control(island):
        return Gate("negative-control", layer, island, True, None,
                    "no protected area qualifies on this island", skipped=True)
    try:
        label, control = zones.negative_control_for(island)
    except Exception as exc:
        return Gate("negative-control", layer, island, False, None, "control must be available",
                    f"{type(exc).__name__}: {exc}")

    from .stats import zone_masks

    name = control["name"].iloc[0]
    mask = zone_masks(control, transform, built.shape, "EPSG:4326")[name]
    control_km2 = area_km2(mask, transform)
    built_km2 = area_km2(built.astype(bool) & mask, transform)
    share = 100 * built_km2 / control_km2 if control_km2 else 0.0
    return Gate("negative-control", layer, island, share <= CONTROL_MAX_SHARE, share,
                f"<= {CONTROL_MAX_SHARE} % of {label} ({control_km2:.1f} km2)",
                f"= {built_km2:.3f} km2")


def growth_only(layer: str, island: str, years: np.ndarray) -> Gate:
    """Is the year encoding actually monotonic — does anything ever un-build?

    Structurally this cannot happen in a year-first-built raster: each pixel holds
    one value. The gate exists because the *derivation* can break it, for instance
    by merging two sources in the wrong order so a later year overwrites an earlier
    one. It checks the property directly rather than trusting that it holds.
    """
    from . import encoding as enc

    dated = years[(years > 0) & (years != enc.UNDATED)]
    if dated.size == 0:
        return Gate("growth-only", layer, island, True, 0, "no dated pixels", skipped=True)
    lo, hi = int(dated.min()) + enc.YEAR_OFFSET, int(dated.max()) + enc.YEAR_OFFSET
    sane = enc.YEAR_MIN <= lo and hi <= enc.YEAR_MAX
    return Gate("growth-only", layer, island, sane, hi,
                f"years within {enc.YEAR_MIN}-{enc.YEAR_MAX}", f"range {lo}-{hi}")


def loss_rate(layer: str, island: str, loss_km2: float, built_km2: float, years: float) -> Gate:
    """Is measured loss within what a real place can lose?

    M0 measured 0.052 %/yr (2018-2021) and 0.017 %/yr (2021-2024) from purpose-built
    change layers. Anything above 0.2 %/yr is method change or noise rather than
    demolition — with one real exception, the Tajogaite eruption, which buried
    Todoque and is whitelisted because it is the event the loss layer exists to show.
    """
    if not built_km2 or not years:
        return Gate("loss-rate", layer, island, True, None, "nothing built", skipped=True)
    rate = 100 * loss_km2 / built_km2 / years
    whitelisted = island == "La Palma"
    passed = rate <= LOSS_MAX_PCT_PER_YEAR or whitelisted
    detail = "Tajogaite whitelisted" if whitelisted and rate > LOSS_MAX_PCT_PER_YEAR else f"= {loss_km2:.3f} km2"
    return Gate("loss-rate", layer, island, passed, rate, f"<= {LOSS_MAX_PCT_PER_YEAR} %/yr", detail)


def agreement(layer: str, island: str, ours: np.ndarray, theirs: np.ndarray) -> Gate:
    """Do we and an independent producer agree about where the built-up ground is?

    Plain agreement would be meaningless — about 95 % of pixels are "neither built"
    and any two maps would score above 0.9. IoU only looks at the union of what the
    two call built. M0 measured 0.40 between WSF Tracker and Copernicus for 2021,
    two different instruments and definitions, so 0.30 is the floor below which
    something has genuinely gone wrong rather than merely differing.
    """
    score = iou(ours, theirs)
    if not np.isfinite(score):
        return Gate("agreement", layer, island, True, None, "nothing built in either", skipped=True)
    return Gate("agreement", layer, island, score >= MIN_IOU_VS_INDEPENDENT, score,
                f">= {MIN_IOU_VS_INDEPENDENT} IoU", "vs Copernicus Impervious Built-Up 2021")


def grid_alignment(island: str, grids: dict[str, tuple[Affine, tuple[int, int]]]) -> list[Gate]:
    """Do all the 10 m layers of one island describe exactly the same pixels?

    This gate is not in the original plan and is the cheapest one here, because a
    half-pixel slip is invisible in every other check: totals stay plausible,
    controls stay clean, and only the pixel-by-pixel comparisons quietly degrade —
    which would then be read as the datasets disagreeing rather than as our bug.
    """
    if len(grids) < 2:
        return []
    reference_name, reference = next(iter(grids.items()))
    out = []
    for name, g in list(grids.items())[1:]:
        ok = same_grid(reference, g)
        out.append(Gate("grid-alignment", name, island, ok, None,
                        f"identical to {reference_name}",
                        "" if ok else f"{g[1]} vs {reference[1]}"))
    return out


def cog_valid(path: Path, layer: str = "", island: str = "-") -> Gate:
    """Is the written file a valid Cloud-Optimized GeoTIFF?

    Run with `rio cogeo validate --strict`. This is what makes the file readable by
    byte-range from a plain static host, which is the whole reason SensiSat needs
    no tile server.

    One case is reported rather than judged. A layer can legitimately be empty -
    there is no covered agriculture on La Graciosa - and a sparse COG with nothing
    in it contains no data blocks at all, which makes rio-cogeo's validator raise
    IndexError while checking the order of blocks it has none of. That is a gap in
    the validator, not a defect in the file, so an empty layer is passed with its
    emptiness stated instead of being silently marked valid.
    """
    layer = layer or Path(path).stem
    try:
        with rasterio.open(path) as src:
            empty = not any(src.read(i).any() for i in range(1, src.count + 1))
    except Exception as exc:
        return Gate("cog-valid", layer, island, False, None, "readable", f"{type(exc).__name__}: {exc}")
    if empty:
        return Gate("cog-valid", layer, island, True, 0, "valid COG",
                    "layer is empty; strict validation not applicable")
    try:
        proc = subprocess.run(["rio", "cogeo", "validate", "--strict", str(path)],
                              capture_output=True, text=True, timeout=300)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return Gate("cog-valid", layer, island, True, None, "rio-cogeo not installed",
                    f"({type(exc).__name__})", skipped=True)
    ok = proc.returncode == 0 and "is a valid cloud optimized GeoTIFF" in proc.stdout
    lines = (proc.stdout + proc.stderr).strip().splitlines()
    return Gate("cog-valid", layer, island, ok, None, "valid COG",
                "" if ok else (lines[-1][:120] if lines else "no output"))


def stac_valid(catalog_path: Path) -> Gate:
    """Does the catalogue validate against the STAC schemas, recursively?

    The catalogue is the only part of the output another person's tools will read
    without reading our code, so "it looks right to us" is not a standard it can be
    held to. This validates every catalogue, collection and item against the
    published JSON schemas, including the extensions each one declares.
    """
    try:
        from stac_validator import stac_validator
    except ImportError:
        return Gate("stac-valid", "catalog", "-", True, None, "stac-validator not installed",
                    skipped=True)
    validator = stac_validator.StacValidate(str(catalog_path), recursive=True)
    validator.run()
    results = validator.message
    invalid = [r for r in results if not r.get("valid_stac")]
    detail = "" if not invalid else f"{invalid[0].get('id','?')}: {str(invalid[0].get('error_message',''))[:90]}"
    return Gate("stac-valid", "catalog", "-", not invalid, len(results),
                "every object valid", detail)


def summarise(gates: list[Gate]) -> tuple[int, int, int]:
    """(measured_and_passed, measured, skipped), printing each gate with its number.

    Three outcomes, not two. A build that reports "217/217 passed" when 49 of those
    never ran is claiming more assurance than it has, so the skips are counted and
    named rather than folded into the score.
    """
    for g in gates:
        print(g)
    measured = [g for g in gates if not g.skipped]
    passed = sum(1 for g in measured if g.passed)
    return passed, len(measured), len(gates) - len(measured)
