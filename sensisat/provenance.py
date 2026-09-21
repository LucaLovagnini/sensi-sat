"""Where every hand-written figure on the public page came from.

Cog generates the LIVE figures — anything derived from the current build — and
those cannot go stale. It is a generator, though, not a scanner: it is blind to a
number nobody marked. So a figure could be added to the published page tomorrow
with no marking at all, and nothing would notice. That is the hole this closes.

`tests/test_documented_numbers.py` extracts every figure carrying a unit from
`viewer/about-the-data.html`, removes the regions cog owns, and requires each
survivor to appear here. Adding an unregistered number fails the build. The author
then has to choose: mark it live, or say where it came from.

Every entry below is a HISTORICAL measurement — recorded when it was taken and
deliberately frozen. Rewriting one to match a later build would destroy the
reasoning it exists to support: the 308 km² is why Dynamic World was disqualified,
and a 2026 re-measurement of it would say nothing about a decision made in 2026-09.

The key is the figure exactly as it appears in the page's source.
"""

from __future__ import annotations

#: figure -> what it is, and which analysis produced it
HISTORICAL: dict[str, str] = {
    # --- M0: the ladder of definitions, and the product that failed it -------
    "308 km²": "Dynamic World over Gran Canaria — the figure that disqualified it (M0, analysis 01)",
    "377 km²": "WSF Evolution 2015 archipelago extent, DLR's own product total (M0)",
    "470 km²": "CORINE 2018 artificial surfaces, the sanity band (M0, analysis 01)",

    # --- M0: extent versus surface, and how the gap reverses -----------------
    "11 %": "Gran Canaria extent growth 1990-2015, WSF Evolution (M0)",
    "57 %": "Gran Canaria built-surface growth 1990-2015, GHSL (M0)",
    "400 %": "Fuerteventura extent growth 1990-2015 — sprawl, not infill (M0)",
    "162 %": "Fuerteventura built-surface growth over the same period (M0)",

    # --- M0/M1: the 2015-2016 seam -------------------------------------------
    "52 %": "upper bound of the apparent extent drop at the seam, 26-52 % (M0, seam record)",
    "115 km²": "Tracker's 2016 baseline with no WSF Evolution year — the history a blend would invent (M0, analysis 11)",

    # --- data-evaluation §10: the cadastre's bucketed years ------------------
    "33.8 %": "share of dated buildings on the ten round-year buckets (analysis 19)",
    "44.8 %": "share falling in 1981-2026, which contains no bucket at all (analysis 19)",
    "37 %": "pre-1981 buildings carrying a genuine year rather than a bucket (analysis 19)",
    "50.3 %": "La Gomera, share of cadastral dates in a bucket year (analysis 19)",
    "45.5 %": "La Palma, same measure (analysis 19)",
    "43.2 %": "El Hierro, same measure (analysis 19)",
    "35.4 %": "Gran Canaria, same measure (analysis 19)",
    "34.8 %": "Tenerife, same measure (analysis 19)",
    "24.9 %": "Lanzarote, same measure (analysis 19)",
    "19.0 %": "Fuerteventura, same measure (analysis 19)",
    "24.5 %": "share of El Hierro's settlement footprint WSF Evolution can date (M0)",
    "68 %": "the same for Gran Canaria and Fuerteventura, 66-68 % (M0)",

    # --- M0: real loss, which decided the growth-only encoding ---------------
    "0.052 %": "built-up loss per year, Copernicus change layer 2018-2021 (M0, analysis 13)",
    "2 %": "share of built pixels a growth-only view misplaces over forty years (M0) "
           "— also, separately, the share of 'empty' 30 m squares holding a building (M3)",
    "0.909 km²": "built-up inside the Tajogaite flow, 2018 (M0, analysis 13)",
    "0.011 km²": "the same ground in 2024, after the eruption (M0, analysis 13)",

    # --- M0: greenhouses, which decided the mask ----------------------------
    "72 %": "share of Gran Canaria greenhouse parcels WSF Tracker flags built-up (M0)",
    "9.5 %": "the same parcels in Copernicus Impervious Built-Up (M0)",
    "17 km²": "greenhouse area that would enter one island's urban total unmasked (M0)",

    # --- M3: the accuracy assessment, a dated result -------------------------
    "121 m²": "median Canary cadastral building footprint (analysis 20)",
    "95 %": "share of the archipelago that is empty land (M3, 30 m strata)",
    "28 %": "undated 30 m squares showing no building (M3, second pass)",
    "91 %": "median Copernicus sealing where photographs found a building (M3)",
    "3 %": "the same where they found nothing (M3)",
    "83 km²": "half-width of the 95 % interval on the error-adjusted area (M3)",
    "324 km²": "30 m squares the map marks as holding a building (M3, strata)",
    "85 %": "share of the building layer dated before 2005, where no imagery exists (validation §7b)",

    # --- M0: the ladder table itself. Each is the SOURCE product's own published
    #     total, not our layer's — which is why they differ from the generated
    #     figures in the same section, and why the page now says so.
    "469.5": "CORINE 2018 artificial surfaces, archipelago (M0, analysis 01)",
    "376.9": "WSF Evolution 2015 extent, archipelago (M0, analysis 01)",
    "341.5": "Copernicus Imperviousness 2024 sealed surface (M0, analysis 18)",
    "259.3": "Copernicus Impervious Built-Up 2024 (M0, analysis 13)",
    "152.9": "GHSL built surface 2020 (M0, analysis 01)",
    "100.3": "HISDAC-ES cadastral footprint — the published derivative, not our "
             "10 m rasterisation, which reads higher (M0, analysis 08)",
    "4.7": "the spread across those six products, 469.5 / 100.3 (M0)",
    "4.7×": "the same spread, written as a factor (M0)",

    # --- the cadastre's own counts -------------------------------------------
    "474,292": "buildings in the 88 Canary municipality feeds (analysis 20)",
    "25,971": "buildings the register dates to 1900 alone (analysis 19)",
    "1,146": "how many times its neighbouring years that is (analysis 19)",

    # --- M0: the lower bound of the measured loss rate -----------------------
    "0.017": "built-up loss per year, Copernicus change layer 2021-2024 (M0, analysis 13)",

    # --- M3: the two confidence intervals quoted in the accuracy table -------
    "2.7": "half-width of the 95 % interval on 'built before 2015' accuracy (M3)",
    "1.2": "the same for 'nothing is built here' (M3)",
}
