"""M0 analysis 9 — how big is the data, really?

The plan's storage and hosting argument rests on the claim that a whole-archipelago
layer is a few MB. This measures it for every dataset in hand: the raw download size
(from data/raw/manifest.json) and the size of the Canary window re-encoded the way we
would publish it (uint8/uint16 GeoTIFF, DEFLATE, SPARSE_OK, overviews).

Output: docs/figures/data/m0_sizes.csv
    python scripts/analysis_09_sizes.py
"""
from __future__ import annotations
import warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
from sensisat.config import CANARIES_BBOX, FIGURES, INTERIM, ISLAND_BBOX
from sensisat.datasets import ghsl, wsf, wsf_tracker as wt
from sensisat.download import manifest_table
from sensisat.raster import write_cog

out = INTERIM/"sizes"; out.mkdir(parents=True, exist_ok=True)
rows=[]
def rec(name, path, note):
    mib = path.stat().st_size/1048576; rows.append(dict(layer=name, published_MiB=round(mib,3), note=note)); print(f"  {name:48s} {mib:8.3f} MiB  {note}")

print("Re-encoding the Canary window of each dataset as a sparse COG:")
evo, te, ec = wsf.load("wsf_evolution", CANARIES_BBOX)
u8 = np.where(evo>0, (evo-1984).astype("uint8"), 0); rec("WSF Evolution 1985-2015, year-first-built (30 m)", write_cog(out/"wsf_evo_years.tif", u8, te, ec), "all 31 years in one file")
for p, yr in (("wsf2015",2015),("wsf2019",2019)):
    m, t, c = wsf.built_mask(p, CANARIES_BBOX); rec(f"WSF {yr} binary (10 m)", write_cog(out/f"{p}.tif", m.astype("uint8"), t, c), "one year")
g, tg, cg = ghsl.load(2020, CANARIES_BBOX); rec("GHSL built surface 2020 (3 arcsec, uint16 m2)", write_cog(out/"ghsl_2020.tif", g.astype("uint16"), tg, cg), "one epoch")
tot=0
for island, bbox in ISLAND_BBOX.items():
    d, t, c = wt.load(bbox); p = write_cog(out/f"tracker_{island.replace(' ','_')}.tif", d.astype("int8").view("uint8"), t, c); tot += p.stat().st_size
rows.append(dict(layer="WSF Tracker 2016-2026, epoch-first-built (10 m), 8 island windows", published_MiB=round(tot/1048576,3), note="all 20 epochs in one file per island")); print(f"  {'WSF Tracker epochs (10 m), 8 islands':48s} {tot/1048576:8.3f} MiB")
df = pd.DataFrame(rows)
man = manifest_table(); raw = man.groupby(man['path'].str.split('/').str[2])['MiB'].sum()
print("\nRaw downloads by dataset folder (MiB):"); print(raw.round(1).to_string())
print(f"\nTOTAL published layers above: {df.published_MiB.sum():.1f} MiB | raw cache: {man['MiB'].sum():.0f} MiB")
df.to_csv(FIGURES/"data"/"m0_sizes.csv", index=False); raw.to_csv(FIGURES/"data"/"m0_sizes_raw.csv")
