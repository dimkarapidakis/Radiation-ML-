# =====================================================================
# floor_plans.py
# The 4 floor plans (κατόψεις) of Orion, as a DXF for AutoCAD
# (open it and SAVEAS .dwg) and a PNG preview.
#
#   Floor 1  Service Module         propellant tanks              (y 0 - 4 m)
#   Floor 2  Lower Equipment Bay    avionics, tanks, under floor  (y 5.2 - 5.85 m)
#   Floor 3  Crew Deck              seats, cockpit, shelter ...   (y 5.85 - 6.8 m)
#   Floor 4  Upper Cabin            sleeping area                 (y 6.8 - 7.3 m)
#
# Every room / piece of equipment is drawn on the floor where its centre is.
#
# Geometry: the same as Orion/main.py and orion_cad.py (interior schematic).
# Plan view from above (looking down the spacecraft axis): plan X = x, plan Y = -z.
# Units: mm.
#
# Needs:  pip install ezdxf shapely matplotlib
# Run:    python shielding/cad/floor_plans.py
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import math
import os

import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Point, Polygon, box
from shapely import affinity

FOLDER = os.path.dirname(os.path.abspath(__file__))
DXF_FILE = os.path.join(FOLDER, "orion_floor_plans.dxf")
PNG_FILE = os.path.join(FOLDER, "orion_floor_plans.png")

CM_Y = 4.7                 # crew module starts here (m)
CM_WALL = 0.10             # crew module wall thickness (m)
ESM_R = 2.05               # service module radius (m)
ESM_SKIN = 0.03
SPACING = 6.0              # distance between the plans in the drawing (m)

FLOORS = [
    # name,                    bottom, top,  cut height (m)
    ("FLOOR 1 - SERVICE MODULE", 0.00, 4.00, 2.20),
    ("FLOOR 2 - LOWER EQUIPMENT BAY", 5.20, 5.85, 5.55),
    ("FLOOR 3 - CREW DECK", 5.85, 6.80, 6.30),
    ("FLOOR 4 - UPPER CABIN", 6.80, 7.30, 7.00),
]

# rooms: centre (x, y, z), size (width, height, depth) in m, from Orion/main.py
ROOMS = {
    "LOWER EQUIPMENT BAY": [0.0, 5.55, 0.0, 3.2, 0.65, 3.2],
    "CREW SEATS": [-0.6, 6.05, -0.3, 1.6, 0.8, 2.1],
    "STORM SHELTER": [0.55, 6.3, 0.0, 0.8, 1.1, 2.1],
    "EXERCISE": [1.4, 6.1, -0.1, 0.65, 0.55, 0.95],
    "GALLEY": [1.35, 6.4, 0.95, 0.55, 0.65, 0.75],
    "HYGIENE": [0.08, 6.25, 1.3, 0.68, 0.8, 0.68],
    "COCKPIT": [-0.6, 6.75, -1.3, 1.9, 0.8, 0.5],
    "SLEEPING AREA": [0.0, 7.0, 0.0, 2.0, 0.5, 1.7],
}

# equipment: name, kind, centre x, z (m), size, bottom, top (m), rotation (deg)
#   kind "circle": size = radius ; kind "rect": size = (width, depth)
EQUIPMENT = []
for k, (tx, tz, fuel) in enumerate([(0.95, 0.95, "MON"), (-0.95, 0.95, "MON"), (0.95, -0.95, "MMH"), (-0.95, -0.95, "MMH")]):
    EQUIPMENT.append((f"{fuel} TANK", "circle", tx, tz, 0.55, 1.08, 3.32, 0))
for k in range(3):
    a = k * 2 * math.pi / 3
    EQUIPMENT.append(("H2O/O2", "circle", 1.3 * math.cos(a), 1.3 * math.sin(a), 0.22, 3.13, 3.57, 0))
for k in range(8):
    a = k * math.pi / 4 + 0.2
    EQUIPMENT.append(("AVIONICS", "rect", 1.45 * math.cos(a), 1.45 * math.sin(a), (0.5, 0.32), 5.35, 5.75, -math.degrees(a)))
for x in [-0.6, 0.6]:
    EQUIPMENT.append(("TANK", "circle", x, 0.0, 0.28, 5.30, 5.80, 0))
for z in [-0.5, 0.5]:
    EQUIPMENT.append(("LOCKER", "rect", 0.55, z, (0.6, 0.9), 5.85, 6.75, 0))
for x in [-0.9, -0.3, 0.3, 0.9]:
    EQUIPMENT.append(("SLEEPING BAG", "rect", x, 0.0, (0.32, 1.72), 6.84, 7.16, 0))


# =====================================================================
# 2. THE DRAWING: layers
# =====================================================================
doc = ezdxf.new("R2018", setup=True)
doc.header["$INSUNITS"] = 4                       # millimetres
msp = doc.modelspace()
for name, color in [("HULL", 7), ("HULL_INNER", 8), ("ROOMS", 3), ("EQUIPMENT", 5),
                    ("TEXT", 7), ("ABOVE_BELOW", 9), ("TITLE", 2)]:
    doc.layers.add(name, color=color)
doc.layers.get("ABOVE_BELOW").dxf.linetype = "DASHED"

fig, axes = plt.subplots(2, 2, figsize=(14, 14))


# =====================================================================
# 3. ONE PLAN PER FLOOR
# =====================================================================
for f, (title, bottom, top, cut) in enumerate(FLOORS):
    ox = f * SPACING                                # where this plan sits in the drawing (m)
    ax = axes.flat[f]

    # ----- hull at the cut height -----
    if cut <= 4.0:
        outer_r, inner_r = ESM_R, ESM_R - ESM_SKIN
    else:
        h = cut - CM_Y
        outer_r = 2.51 if h < 0.76 else 2.47 - (h - 0.76) * 0.668
        inner_r = outer_r - CM_WALL
    hull_inside = Point(0, 0).buffer(inner_r, 128)
    msp.add_circle(((ox) * 1000, 0), outer_r * 1000, dxfattribs={"layer": "HULL"})
    msp.add_circle(((ox) * 1000, 0), inner_r * 1000, dxfattribs={"layer": "HULL_INNER"})
    ax.add_patch(plt.Circle((0, 0), outer_r, fill=False, color="black", lw=2))
    ax.add_patch(plt.Circle((0, 0), inner_r, fill=False, color="grey", lw=1))

    # ----- rooms that are on this floor, cut by the hull -----
    for name, (cx, cy, cz, w, hgt, d) in ROOMS.items():
        if not (bottom <= cy < top):                  # the room belongs to the floor of its centre
            continue
        room = box(cx - w / 2, -cz - d / 2, cx + w / 2, -cz + d / 2).intersection(hull_inside)
        points = [(ox * 1000 + px * 1000, py * 1000) for px, py in room.exterior.coords]
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": "ROOMS"})
        label = f"{name}\\P{room.area:.2f} m2"
        msp.add_mtext(label, dxfattribs={"layer": "TEXT", "char_height": 70}).set_location(
            ((ox + room.centroid.x) * 1000, room.centroid.y * 1000), attachment_point=5)
        xs, ys = room.exterior.xy
        ax.fill(xs, ys, color="#2a9d55", alpha=0.18)
        ax.plot(xs, ys, color="#2a9d55", lw=1.2)
        ax.text(room.centroid.x, room.centroid.y, f"{name}\n{room.area:.2f} m²", ha="center", va="center", fontsize=7)

    # ----- equipment: solid if it crosses the cut, dashed if it is only above/below on this floor -----
    for name, kind, ex, ez, size, e_bottom, e_top, rot in EQUIPMENT:
        if not (bottom <= (e_bottom + e_top) / 2 < top):
            continue
        at_cut = e_bottom <= cut <= e_top
        layer = "EQUIPMENT" if at_cut else "ABOVE_BELOW"
        if kind == "circle":
            shape = Point(ex, -ez).buffer(size, 64)
        else:
            shape = affinity.rotate(box(ex - size[0] / 2, -ez - size[1] / 2, ex + size[0] / 2, -ez + size[1] / 2),
                                    rot, origin=(ex, -ez))
        points = [(ox * 1000 + px * 1000, py * 1000) for px, py in shape.exterior.coords]
        msp.add_lwpolyline(points, close=True, dxfattribs={"layer": layer})
        if name in ("MON TANK", "MMH TANK", "LOCKER", "TANK"):
            msp.add_text(name, height=60, dxfattribs={"layer": "TEXT"}).set_placement(
                ((ox + ex) * 1000, -ez * 1000), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
        xs, ys = shape.exterior.xy
        ax.plot(xs, ys, color="#2a78d6", lw=1, ls="-" if at_cut else "--")
        if name in ("MON TANK", "MMH TANK", "LOCKER", "TANK"):
            ax.text(ex, -ez, name, ha="center", va="center", fontsize=6, color="#2a78d6")

    # ----- title, scale bar, axes -----
    msp.add_text(title, height=150, dxfattribs={"layer": "TITLE"}).set_placement(
        (ox * 1000, -2900), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    msp.add_text(f"cut at y = {cut:.2f} m | floor {bottom:.2f} - {top:.2f} m", height=80,
                 dxfattribs={"layer": "TITLE"}).set_placement((ox * 1000, -3150),
                                                                align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    msp.add_line(((ox - 2.5) * 1000, -2550), ((ox - 1.5) * 1000, -2550), dxfattribs={"layer": "TEXT"})
    msp.add_text("1 m", height=60, dxfattribs={"layer": "TEXT"}).set_placement(((ox - 2.0) * 1000, -2450))
    msp.add_line((ox * 1000, 0), ((ox + 0.4) * 1000, 0), dxfattribs={"layer": "HULL_INNER"})     # +x axis
    msp.add_text("+X", height=50, dxfattribs={"layer": "TEXT"}).set_placement(((ox + 0.45) * 1000, 0))

    ax.set_title(f"{title}\ncut at y = {cut:.2f} m", fontsize=10)
    ax.plot([-2.5, -1.5], [-2.55, -2.55], color="black", lw=2)
    ax.text(-2.0, -2.45, "1 m", ha="center", fontsize=8)
    ax.set_xlim(-2.7, 2.7)
    ax.set_ylim(-2.7, 2.7)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


# =====================================================================
# 4. SAVE
# =====================================================================
doc.saveas(DXF_FILE)
fig.suptitle("ORION - floor plans (schematic interior)", fontsize=14)
fig.text(0.5, 0.02, "solid = cut by the plane   dashed = above / below on the same floor   areas inside the hull",
         ha="center", fontsize=9)
fig.tight_layout(rect=(0, 0.03, 1, 0.97))
fig.savefig(PNG_FILE, dpi=130)
plt.close(fig)
print("Saved:", DXF_FILE)
print("Saved:", PNG_FILE)
