"""Extent vs surface — a synthetic 90 m x 90 m neighbourhood over three dates.

Extent  = area of 30 m pixels that contain ANY building (what WSF-style products count).
Surface = square metres actually covered by buildings and roads (what GHSL built-surface counts).
Infill adds surface but no extent once a pixel is already touched; extent saturates.
Run:  python docs/figures/src/extent_vs_surface.py
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from common import FIG

HOUSE_W, HOUSE_H = 15, 10                      # metres → 150 m² per house
HOUSES = {                                     # (x, y) of lower-left corner, by year built
    1985: [(5, 5), (65, 10), (40, 70)],
    2000: [(20, 5), (5, 50), (70, 40), (35, 20), (65, 65)],
    2015: [(50, 5), (70, 25), (5, 70), (20, 70), (60, 75), (35, 50), (5, 25), (75, 55), (20, 32), (50, 30), (40, 78)],
}
ROADS = {2015: (0, 42, 90, 6)}                 # x, y, width, height → 540 m²
YEARS = [1985, 2000, 2015]


def state(year):
    houses = [h for y, lst in HOUSES.items() if y <= year for h in lst]
    roads = [r for y, r in ROADS.items() if y <= year]
    return houses, roads


def metrics(year):
    houses, roads = state(year)
    touched = set()
    for x, y in houses:
        for px in range(x // 30, (x + HOUSE_W - 1) // 30 + 1):
            for py in range(y // 30, (y + HOUSE_H - 1) // 30 + 1):
                touched.add((px, py))
    for x, y, w, h in roads:
        for px in range(x // 30, (x + w - 1) // 30 + 1):
            for py in range(y // 30, (y + h - 1) // 30 + 1):
                touched.add((px, py))
    assert all(0 <= px < 3 and 0 <= py < 3 for px, py in touched), "geometry outside the 90 m square"
    surface = len(houses) * HOUSE_W * HOUSE_H + sum(w * h for _, _, w, h in roads)
    return touched, surface


def main():
    fig, axs = plt.subplots(2, 3, figsize=(15, 10), gridspec_kw={"height_ratios": [1.3, 1]})
    for ax, yr in zip(axs[0], YEARS):
        touched, surface = metrics(yr)
        houses, roads = state(yr)
        for px in range(3):
            for py in range(3):
                face = "#f4b6b6" if (px, py) in touched else "#e9f5e1"
                ax.add_patch(Rectangle((px * 30, py * 30), 30, 30, facecolor=face, edgecolor="#555", lw=1.2))
        for x, y, w, h in roads:
            ax.add_patch(Rectangle((x, y), w, h, facecolor="#444", edgecolor="none"))
        for x, y in houses:
            ax.add_patch(Rectangle((x, y), HOUSE_W, HOUSE_H, facecolor="#7a1f1f", edgecolor="black", lw=0.6))
        ax.set_xlim(0, 90); ax.set_ylim(0, 90); ax.set_aspect("equal")
        ax.set_xticks([0, 30, 60, 90]); ax.set_yticks([0, 30, 60, 90]); ax.tick_params(labelsize=8)
        ax.set_title(f"{yr}\nEXTENT: {len(touched)} of 9 pixels 'built' = {len(touched) * 900:,} m²\n"
                     f"SURFACE: {len(houses)} houses{' + road' if roads else ''} = {surface:,} m² actually built", fontsize=11)

    ext = [len(metrics(y)[0]) * 900 for y in YEARS]
    sur = [metrics(y)[1] for y in YEARS]
    labels = [str(y) for y in YEARS]
    ax = axs[1][0]
    ax.bar(labels, ext, color="#e08a8a"); ax.set_title("Extent (m² of 30 m pixels touched)\n— what WSF Evolution counts", fontsize=11)
    for i, v in enumerate(ext): ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=10)
    ax = axs[1][1]
    ax.bar(labels, sur, color="#7a1f1f"); ax.set_title("Surface (m² of buildings + road)\n— what GHSL built-surface counts", fontsize=11)
    for i, v in enumerate(sur): ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=10)
    ax = axs[1][2]
    ax.plot(YEARS, [100 * e / ext[0] for e in ext], "o-", color="#e08a8a", lw=3, label=f"extent: ×{ext[-1] / ext[0]:.1f} since 1985 — saturated at 9/9 in 2015")
    ax.plot(YEARS, [100 * s / sur[0] for s in sur], "s-", color="#7a1f1f", lw=3, label=f"surface: ×{sur[-1] / sur[0]:.1f} since 1985 — can keep growing")
    ax.set_title("Same neighbourhood, two growth curves\n(index 1985 = 100)", fontsize=11); ax.legend(fontsize=10); ax.grid(alpha=.3)
    fig.suptitle("Extent vs surface: pink = a 30 m pixel that contains ANY building (counts fully as 'urbanised');\n"
                 "dark red = the buildings themselves. Infill adds surface but no extent once a pixel is already touched.", fontsize=12)
    plt.tight_layout()
    out = FIG / "extent_vs_surface.png"
    plt.savefig(out, dpi=110)
    print("saved", out, "extent:", ext, "surface:", sur)


if __name__ == "__main__":
    main()
