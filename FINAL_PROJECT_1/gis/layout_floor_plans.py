# =====================================================================
# layout_floor_plans.py
# The 4 floor plans of Orion on one sheet, WITHOUT radiation values:
# for the presentation, and the same drawing is the base of the interactive simulation
# (warning/simulation.py uses the same colours).
#
# All 4 floors are drawn at the SAME scale, so their sizes can be compared.
#
# Input:   shielding/cad/orion_floor_plans.gpkg   (shielding/cad/floor_plans_gis.py)
# Output:  gis/layout/floor_plans_layout.png  (300 dpi, for slides)
#          gis/layout/floor_plans_layout.pdf  and .svg  (vector, for print / editing)
#
# Run:  python gis/layout_floor_plans.py
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import logging
import os

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import pyogrio
from matplotlib.patches import Patch
from shapely.geometry import Polygon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOOR_PLANS = os.path.join(ROOT, "shielding", "cad", "orion_floor_plans.gpkg")
OUT = os.path.join(ROOT, "gis", "layout")
os.makedirs(OUT, exist_ok=True)

FLOOR_TITLES = {1: "FLOOR 1\nService Module (no crew)", 2: "FLOOR 2\nLower Equipment Bay",
                3: "FLOOR 3\nCrew Deck", 4: "FLOOR 4\nUpper Cabin"}
COLORS = {"hull": "#5b6770", "room": "#dce9f5", "shelter": "#cfe8d6", "equipment": "#b9bec4",
          "ink": "#1f2a33", "muted": "#6b7680", "paper": "#ffffff"}
plt.rcParams["font.family"] = ["Inter", "Segoe UI", "Helvetica", "DejaVu Sans"]
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)   # no "font not found" messages


# =====================================================================
# 2. LOAD
# =====================================================================
plans = pd.concat([gpd.read_file(FLOOR_PLANS, layer=layer) for layer in pyogrio.list_layers(FLOOR_PLANS)[:, 0]])
plans = gpd.GeoDataFrame(plans, crs="EPSG:3857")
half = plans.geometry.bounds[["maxx", "maxy"]].max().max() + 0.25        # same extent for every floor


# =====================================================================
# 3. DRAW: one panel per floor
# =====================================================================
fig, axes = plt.subplots(1, 4, figsize=(16, 5.6), facecolor=COLORS["paper"])
for ax, (floor, g) in zip(axes, plans.groupby("floor")):
    hull = g[g["type"] == "hull"]
    inside = Polygon(hull.geometry.iloc[0].interiors[0])          # the free space inside the hull wall
    rooms = g[g["type"] == "room"].copy()
    rooms["geometry"] = rooms.geometry.intersection(inside)         # nothing sticks out of the wall
    equipment = g[g["type"] == "equipment"].copy()
    equipment["geometry"] = equipment.geometry.intersection(inside)

    hull.plot(ax=ax, color=COLORS["hull"], edgecolor=COLORS["hull"], lw=0.5)
    rooms.plot(ax=ax, color=[COLORS["shelter"] if k == "shelter" else COLORS["room"] for k in rooms["room_key"]],
               edgecolor=COLORS["ink"], lw=0.8)
    equipment.plot(ax=ax, color=COLORS["equipment"], edgecolor=COLORS["paper"], lw=0.8, alpha=0.9)

    # room names (+ area); small rooms get a smaller font
    for _, r in rooms.iterrows():
        p = r.geometry.centroid
        size = 8 if r["area_m2"] > 1 else 6 if r["area_m2"] > 0.4 else 5
        if r["room_key"] == "shelter":                    # long and narrow: vertical label on the lockers
            ax.text(0.55, 0, f"{r['name']}  {r['area_m2']:.2f} m²", ha="center", va="center", rotation=90,
                    fontsize=6.5, color=COLORS["ink"], fontweight="medium",
                    bbox={"facecolor": COLORS["shelter"], "edgecolor": "none", "pad": 1})
            continue
        ax.text(p.x, p.y, f"{r['name']}\n{r['area_m2']:.2f} m²", ha="center",
                va="center", fontsize=size, color=COLORS["ink"], fontweight="medium", linespacing=1.15)
    # equipment names only on floors 1 and 4, where there is space
    if floor in (1, 4):
        for _, r in equipment.drop_duplicates("name").iterrows():
            p = r.geometry.representative_point()
            ax.text(p.x, p.y, r["name"].replace(" ", "\n", 1), ha="center", va="center", fontsize=6,
                    color=COLORS["ink"], rotation=90 if floor == 4 else 0)

    diameter = 2 * hull.geometry.bounds["maxx"].max()
    ax.set_title(FLOOR_TITLES[floor], fontsize=11, color=COLORS["ink"], fontweight="semibold", loc="left")
    ax.text(0, -half + 0.05, f"Ø {diameter:.2f} m", ha="center", va="bottom", fontsize=8, color=COLORS["muted"])
    ax.set_xlim(-half, half)
    ax.set_ylim(-half, half)
    ax.set_aspect("equal")
    ax.axis("off")

# scale bar (1 m) on the first panel
ax = axes[0]
ax.plot([-half + 0.15, -half + 1.15], [half - 0.15, half - 0.15], color=COLORS["ink"], lw=2.5,
        solid_capstyle="butt")
ax.text(-half + 0.65, half - 0.25, "1 m", ha="center", va="top", fontsize=8, color=COLORS["ink"])

legend = [Patch(facecolor=COLORS["hull"], label="Hull wall (Avcoat / aluminium / HDPE)"),
          Patch(facecolor=COLORS["room"], edgecolor=COLORS["ink"], label="Crew room"),
          Patch(facecolor=COLORS["shelter"], edgecolor=COLORS["ink"], label="Storm shelter (HDPE 15 cm)"),
          Patch(facecolor=COLORS["equipment"], label="Equipment / tanks")]
fig.legend(handles=legend, loc="lower center", ncol=4, frameon=False, fontsize=9)
fig.suptitle("Orion spacecraft: floor plans", x=0.012, ha="left", fontsize=15, fontweight="bold", color=COLORS["ink"])
fig.text(0.012, 0.905, "Same scale for all floors · schematic interior · from shielding/cad/orion_floor_plans.gpkg",
         fontsize=9, color=COLORS["muted"])
fig.subplots_adjust(left=0.01, right=0.99, top=0.8, bottom=0.1, wspace=0.05)

for ext in ("png", "pdf", "svg"):
    fig.savefig(os.path.join(OUT, f"floor_plans_layout.{ext}"), dpi=300)
plt.close(fig)
print("Saved:", os.path.join(OUT, "floor_plans_layout.png / .pdf / .svg"))
