# =====================================================================
# floor_plans_gis.py
# The 4 floor plans of Orion as GIS layers (polygons with attributes),
# for ArcGIS Pro / QGIS: one GeoPackage with one layer per floor.
#
#   shielding/cad/orion_floor_plans.gpkg
#       floor1_service_module, floor2_equipment_bay, floor3_crew_deck, floor4_upper_cabin
#
# Every polygon has: floor, type (hull / room / equipment), name, room_key, area_m2.
# room_key is the same name as in shielding/data/room_doses.csv, so the dose
# can be joined to the rooms (Add Join) and shown as a colour map.
#
# Coordinates: metres, local (origin = spacecraft axis), stored as EPSG:3857.
# Plan view from above: plan X = x, plan Y = -z (like floor_plans.py).
#
# Needs:  pip install geopandas shapely
# Run:    python shielding/cad/floor_plans_gis.py
# =====================================================================


# =====================================================================
# 1. SETTINGS (the same geometry as floor_plans.py)
# =====================================================================
import math
import os

import geopandas as gpd
from shapely import affinity
from shapely.geometry import Point, box

FOLDER = os.path.dirname(os.path.abspath(__file__))
GPKG = os.path.join(FOLDER, "orion_floor_plans.gpkg")

CM_Y = 4.7
CM_WALL = 0.10
ESM_R = 2.05
ESM_SKIN = 0.03

FLOORS = [
    # layer name,               title,                     bottom, top, cut (m)
    ("floor1_service_module", "Service Module",           0.00, 4.00, 2.20),
    ("floor2_equipment_bay",  "Lower Equipment Bay",      5.20, 5.85, 5.55),
    ("floor3_crew_deck",      "Crew Deck",                5.85, 6.80, 6.30),
    ("floor4_upper_cabin",    "Upper Cabin",              6.80, 7.30, 7.00),
]

# rooms: name, key in room_doses.csv, centre (x, y, z), size (width, height, depth) in m
ROOMS = [
    ("Lower Equipment Bay", "leb",      0.0, 5.55, 0.0, 3.2, 0.65, 3.2),
    ("Crew Seats",          "seats",   -0.6, 6.05, -0.3, 1.6, 0.8, 2.1),
    ("Storm Shelter",       "shelter",  0.55, 6.3, 0.0, 0.8, 1.1, 2.1),
    ("Exercise",            "exercise", 1.4, 6.1, -0.1, 0.65, 0.55, 0.95),
    ("Galley",              "galley",   1.35, 6.4, 0.95, 0.55, 0.65, 0.75),
    ("Hygiene",             "hygiene",  0.08, 6.25, 1.3, 0.68, 0.8, 0.68),
    ("Cockpit",             "cockpit", -0.6, 6.75, -1.3, 1.9, 0.8, 0.5),
    ("Sleeping Area",       "sleep",    0.0, 7.0, 0.0, 2.0, 0.5, 1.7),
]

# equipment: name, kind, centre x, z, size, bottom, top (m), rotation (deg)
EQUIPMENT = []
for tx, tz, fuel in [(0.95, 0.95, "MON"), (-0.95, 0.95, "MON"), (0.95, -0.95, "MMH"), (-0.95, -0.95, "MMH")]:
    EQUIPMENT.append((f"{fuel} Tank", "circle", tx, tz, 0.55, 1.08, 3.32, 0))
for k in range(3):
    a = k * 2 * math.pi / 3
    EQUIPMENT.append(("Water/O2 Tank", "circle", 1.3 * math.cos(a), 1.3 * math.sin(a), 0.22, 3.13, 3.57, 0))
for k in range(8):
    a = k * math.pi / 4 + 0.2
    EQUIPMENT.append(("Avionics Box", "rect", 1.45 * math.cos(a), 1.45 * math.sin(a), (0.5, 0.32), 5.35, 5.75, -math.degrees(a)))
for x in [-0.6, 0.6]:
    EQUIPMENT.append(("Tank", "circle", x, 0.0, 0.28, 5.30, 5.80, 0))
for z in [-0.5, 0.5]:
    EQUIPMENT.append(("Shelter Locker", "rect", 0.55, z, (0.6, 0.9), 5.85, 6.75, 0))
for x in [-0.9, -0.3, 0.3, 0.9]:
    EQUIPMENT.append(("Sleeping Bag", "rect", x, 0.0, (0.32, 1.72), 6.84, 7.16, 0))


# =====================================================================
# 2. ONE LAYER PER FLOOR
# =====================================================================
if os.path.exists(GPKG):
    os.remove(GPKG)

for f, (layer, title, bottom, top, cut) in enumerate(FLOORS, start=1):
    rows = []

    # hull at the cut height: a ring (outer circle minus inner circle)
    if cut <= 4.0:
        outer_r, inner_r = ESM_R, ESM_R - ESM_SKIN
    else:
        h = cut - CM_Y
        outer_r = 2.51 if h < 0.76 else 2.47 - (h - 0.76) * 0.668
        inner_r = outer_r - CM_WALL
    inside = Point(0, 0).buffer(inner_r, 128)
    hull = Point(0, 0).buffer(outer_r, 128).difference(inside)
    rows.append({"floor": f, "floor_name": title, "type": "hull", "name": "Hull wall",
                 "room_key": "", "area_m2": round(inside.area, 2), "geometry": hull})

    # rooms whose centre is on this floor, cut by the hull
    for name, key, cx, cy, cz, w, hgt, d in ROOMS:
        if not (bottom <= cy < top):
            continue
        room = box(cx - w / 2, -cz - d / 2, cx + w / 2, -cz + d / 2).intersection(inside)
        rows.append({"floor": f, "floor_name": title, "type": "room", "name": name,
                     "room_key": key, "area_m2": round(room.area, 2), "geometry": room})

    # equipment whose centre is on this floor
    for name, kind, ex, ez, size, e_bottom, e_top, rot in EQUIPMENT:
        if not (bottom <= (e_bottom + e_top) / 2 < top):
            continue
        if kind == "circle":
            shape = Point(ex, -ez).buffer(size, 64)
        else:
            shape = affinity.rotate(box(ex - size[0] / 2, -ez - size[1] / 2, ex + size[0] / 2, -ez + size[1] / 2),
                                    rot, origin=(ex, -ez))
        rows.append({"floor": f, "floor_name": title, "type": "equipment", "name": name,
                     "room_key": "", "area_m2": round(shape.area, 2), "geometry": shape})

    gdf = gpd.GeoDataFrame(rows, crs="EPSG:3857")
    gdf.to_file(GPKG, layer=layer, driver="GPKG")
    print(f"{layer}: {len(gdf)} polygons ({(gdf['type'] == 'room').sum()} rooms)")

print("Saved:", GPKG)
