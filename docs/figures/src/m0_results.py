"""Milestone 0 results at a glance.

Panel 1: every product's built-up figure per island, plus Dynamic World, on one
         axis - the visual form of "one island in DW exceeds eight in everything else".
Panel 2: growth 1990-2015, extent vs surface, per island - the reversal.
Panel 3: WSF Evolution's 1985 baseline share per island.
Panel 4: the WSF 2015 -> 2019 jump against WSF Evolution's own growth rate.

Reads docs/figures/data/m0_totals.csv (written by scripts/analysis_01_totals.py).
Run:  python docs/figures/src/m0_results.py
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from sensisat.config import FIGURES, ISLAND_AREA_KM2

DATA = FIGURES / "data" / "m0_totals.csv"
DW_GRAN_CANARIA_2016 = 307.8   # from the project's original Dynamic World notebook
OFFICIAL_ARTIFICIAL_PCT = 6.0  # official artificial-land share of the archipelago


def main():
    df = pd.read_csv(DATA)
    islands = [i for i in ISLAND_AREA_KM2 if i in set(df.island)]
    order = sorted(islands, key=lambda i: -ISLAND_AREA_KM2[i])

    fig, axs = plt.subplots(2, 2, figsize=(16, 12))

    # --- 1. absolute built-up per island, every product -----------------------
    ax = axs[0, 0]
    series = [("WSF Evolution", 2015, "WSF Evolution 2015 (extent, 30 m)", "#1f4e79"),
              ("WSF 2019", 2019, "WSF 2019 (extent, 10 m)", "#4a90c0"),
              ("GHSL built surface", 2020, "GHSL 2020 (surface, ~92 m)", "#c00000")]
    x = np.arange(len(order))
    width = 0.26
    for k, (ds, yr, label, colour) in enumerate(series):
        vals = [float(df[(df.island == i) & (df.dataset == ds) & (df.year == yr)]["built_km2"].iloc[0])
                for i in order]
        ax.bar(x + (k - 1) * width, vals, width, label=label, color=colour)
    ax.axhline(DW_GRAN_CANARIA_2016, color="#ff8c00", ls="--", lw=2)
    ax.text(len(order) - 0.4, DW_GRAN_CANARIA_2016, f" Dynamic World:\n {DW_GRAN_CANARIA_2016:.0f} km² for\n Gran Canaria ALONE",
            va="center", ha="right", fontsize=9, color="#cc6600", fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(order, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("built-up, km²"); ax.legend(fontsize=9)
    ax.set_title("1. Built-up per island. The dashed line is Dynamic World's figure for\n"
                 "ONE island — above every independent product's figure for any island.", fontsize=11)

    # --- 2. extent vs surface growth, the reversal ----------------------------
    ax = axs[0, 1]
    ext, sur = [], []
    for i in order:
        w = df[(df.island == i) & (df.dataset == "WSF Evolution")].set_index("year")["built_km2"]
        g = df[(df.island == i) & (df.dataset == "GHSL built surface")].set_index("year")["built_km2"]
        ext.append(100 * (w[2015] / w[1990] - 1))
        sur.append(100 * (g[2015] / g[1990] - 1))
    ax.barh(x - 0.2, ext, 0.38, label="EXTENT — land urbanised (WSF, 30 m)", color="#e08a8a")
    ax.barh(x + 0.2, sur, 0.38, label="SURFACE — amount built (GHSL)", color="#7a1f1f")
    ax.set_yticks(x); ax.set_yticklabels(order, fontsize=9); ax.invert_yaxis()
    ax.set_xscale("symlog", linthresh=10)
    ax.set_xlabel("growth 1990 → 2015, % (log scale)"); ax.legend(fontsize=9, loc="lower right")
    ax.set_title("2. The two measures disagree in OPPOSITE directions.\n"
                 "Dense islands: surface outruns extent. Sparse islands: the reverse.", fontsize=11)
    for xi, (e, s, isl) in enumerate(zip(ext, sur, order)):
        note = "saturated" if s > e * 2 else ("sparse" if e > s * 1.5 else "")
        if note:
            ax.text(max(e, s) * 1.15, xi, note, va="center", fontsize=8, style="italic", color="#555")

    # --- 3. how much of WSF Evolution is already in its first frame -----------
    ax = axs[1, 0]
    shares, growth = [], []
    for i in order:
        w = df[(df.island == i) & (df.dataset == "WSF Evolution")].set_index("year")["built_km2"]
        shares.append(100 * w[1985] / w[2015])
        growth.append(w[2015] / w[1985])
    colours = ["#c00000" if s > 80 else ("#e8a33d" if s > 50 else "#2e7d32") for s in shares]
    ax.bar(x, shares, 0.6, color=colours)
    for xi, (s, g) in enumerate(zip(shares, growth)):
        ax.text(xi, s + 1.5, f"×{g:.1f}", ha="center", fontsize=9)
    ax.set_xticks(x); ax.set_xticklabels(order, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("% of 2015 extent already present in 1985"); ax.set_ylim(0, 105)
    ax.set_title("3. WSF Evolution's first frame is a BASELINE, not a growth year.\n"
                 "Red: the product has little left to say. Labels: total growth 1985→2015.", fontsize=11)

    # --- 4. the WSF 2015 -> 2019 method break --------------------------------
    ax = axs[1, 1]
    implied, own = [], []
    for i in order:
        w15 = float(df[(df.island == i) & (df.dataset == "WSF 2015")]["built_km2"].iloc[0])
        w19 = float(df[(df.island == i) & (df.dataset == "WSF 2019")]["built_km2"].iloc[0])
        evo = df[(df.island == i) & (df.dataset == "WSF Evolution")].set_index("year")["built_km2"]
        implied.append(100 * (w19 / w15 - 1) / 4)
        own.append(100 * (evo[2015] / evo[2011] - 1) / 4)
    ax.bar(x - 0.2, implied, 0.38, label="implied by WSF 2015 → WSF 2019", color="#c00000")
    ax.bar(x + 0.2, own, 0.38, label="WSF Evolution's own 2011–2015 rate", color="#1f4e79")
    ax.set_xticks(x); ax.set_xticklabels(order, rotation=30, ha="right", fontsize=9)
    ax.set_ylabel("growth, % per year"); ax.legend(fontsize=9)
    ax.set_title("4. WSF 2015 and WSF 2019 are NOT a time series.\n"
                 "They imply up to 20 %/yr growth; the annual product says ~0.5 %/yr.", fontsize=11)

    fig.suptitle("Milestone 0 — what the candidate datasets actually say about the Canary Islands\n"
                 "All figures measured locally from public files, 2026-09-19", fontsize=13)
    fig.text(0.5, 0.005,
             "WSF Evolution / 2015 / 2019 © DLR (CC-BY-4.0, CC0-1.0) · GHS-BUILT-S R2023A © European Union, JRC (CC BY 4.0) · "
             "island boundaries © OpenStreetMap contributors (ODbL)",
             ha="center", fontsize=8)
    plt.tight_layout(rect=(0, 0.015, 1, 0.96))
    out = FIGURES / "m0_results.png"
    plt.savefig(out, dpi=110)
    print("saved", out)


if __name__ == "__main__":
    main()
