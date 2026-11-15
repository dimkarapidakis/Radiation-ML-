# =====================================================================
# shielding.py
# The whole shielding in ONE file, run by live/06_live.py every 5 minutes:
#
#   1. ANATOMY  Orion as a 3D grid of 5 cm cubes, every cube with a material and a density
#               (Avcoat / tiles -> aluminium 4 mm + ribs -> HDPE 5 cm; storm shelter: HDPE 15 cm)
#   2. RAYS     from the centre of every room, 400 rays in all directions; along every ray we add
#               the mass it crosses:  shielding = sum(density x aluminium equivalence x length)  [g/cm2]
#   3. STORM    the WORST CASE of the newest forecast of live/06_live.py
#               (forecast + 1.65 x error of the model; scaled up if the flux is already above the forecast)
#   4. DOSE     protons -> through every ray + the body -> energy left in the body (NIST) -> mSv;
#               dose of a room = average of its 400 rays
#   5. CREW     where is every astronaut now (demo: they walk smoothly and at random, room to room
#               through the doors; real spacecraft: badges) -> the BEST ROOM AROUND HIM:
#               the room, reachable within a few minutes, with the least
#                   dose on the way (Dijkstra on the doors) + storm dose in that room
#
# Steps 1 and 2 depend only on the spacecraft: they are made once (REBUILD = True to make them again).
#
# Output: shielding/data/room_doses.csv / .json, shielding/data/crew_orders.csv / .json (for the app),
#         shielding/data/crew_live.csv (where everyone is), shielding/data/crew_live_log.csv (every run),
#         shielding/data/shielding_readable.json (everything in plain words, for the crew screen),
#         the "alerts" table of the team's database (database/nasaspacechallenge.db) when someone must move,
#         shielding/data/room_doses_floors.gpkg (floor plans with dose, astronauts, routes: ArcGIS / QGIS),
#         shielding/Figures/room_doses_floors.png
# Run:  python shielding/shielding.py        (or automatically from live/06_live.py)
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import json
import os
import sqlite3

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import pyogrio
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch
from shapely.geometry import LineString, Point

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIELDING = os.path.join(ROOT, "shielding")
GRID_FILE = os.path.join(SHIELDING, "data", "orion_voxels.npz")
ROOMS_FILE = os.path.join(SHIELDING, "data", "rooms.json")
RAYS_FILE = os.path.join(SHIELDING, "data", "rays.csv")
FLOOR_PLANS = os.path.join(SHIELDING, "cad", "orion_floor_plans.gpkg")       # made by cad/floor_plans_gis.py
LIVE_LOG = os.path.join(ROOT, "live", "data", "live_log.csv")
MODEL_ERRORS = os.path.join(ROOT, "forecast", "data", "processed", "results.csv")
DESIGN_SPE = os.path.join(ROOT, "health", "nasa_design_spe_oct1989.csv")
DB_FILE = os.path.join(ROOT, "database", "nasaspacechallenge.db")      # the team's database
CREW_STATE = os.path.join(SHIELDING, "data", "crew_live.csv")         # where everyone is now (kept between runs)
CREW_LOG = os.path.join(SHIELDING, "data", "crew_live_log.csv")       # every run: where everyone was
OUT_ROOMS_CSV = os.path.join(SHIELDING, "data", "room_doses.csv")
OUT_ROOMS_JSON = os.path.join(SHIELDING, "data", "room_doses.json")
OUT_CREW_CSV = os.path.join(SHIELDING, "data", "crew_orders.csv")
OUT_CREW_JSON = os.path.join(SHIELDING, "data", "crew_orders.json")
OUT_READABLE = os.path.join(SHIELDING, "data", "shielding_readable.json")   # the same, in plain words (for the app)
OUT_FLOORS = os.path.join(SHIELDING, "data", "room_doses_floors.gpkg")
FIGURES = os.path.join(SHIELDING, "Figures")
os.makedirs(os.path.join(SHIELDING, "data"), exist_ok=True)
os.makedirs(FIGURES, exist_ok=True)

REBUILD = False              # True = make the anatomy and the rays again (after changing the spacecraft)

# --- the storm ---
#   "live"          the worst case of the newest forecast of live/06_live.py (no forecast = nobody moves)
#   "October 1989"  NASA design reference storm (NASA-STD-3001 Table 5), the worst case NASA designs for
STORM = "live"
WORST_CASE_Z = 1.65          # forecast + 1.65 x RMSE: worse than 95% of the storms
STORM_HOURS = 24             # how long the storm lasts (NASA: up to ~24 h in the shelter)

# --- the crew ---
CREW_SIZE = 6
names = []                                                      # the astronauts from the team's database
if os.path.exists(DB_FILE):
    db = sqlite3.connect(DB_FILE)
    names = [row[0] for row in db.execute("SELECT name FROM astronauts ORDER BY id")]
    db.close()
CREW = names[:CREW_SIZE] + [f"Astronaut {i}" for i in range(len(names) + 1, CREW_SIZE + 1)]   # not in the database yet
TAG = "[Radiation-ML] storm:"   # our alerts in the database start with this
P_CHANGE_ROOM = 0.15         # every 5 minutes: chance that an astronaut walks to a neighbouring room
WALK = 0.4                   # every 5 minutes: part of the way to the spot he is walking to inside the room
MAX_MINUTES = 1.5            # "around him": rooms he can reach within 1.5 minutes
MIN_SAVE_MSV = 1.0           # move only if it saves at least 1 mSv (~2 days of cosmic rays)
SHELTER = "shelter"
SHELTER_LEFT = 0.05          # the shelter has many layers: 5% of the storm gets in (TEAM ASSUMPTION)
CREW_ROOMS = ["leb", "cockpit", "seats", "galley", "exercise", "hygiene", "shelter", "sleep"]
DOORS = [("seats", "cockpit", 0.5), ("seats", "exercise", 0.5), ("seats", "shelter", 0.5),
         ("exercise", "galley", 0.5), ("galley", "hygiene", 0.5), ("hygiene", "shelter", 0.5),
         ("seats", "leb", 1.0),                                  # ladder: floor 3 -> floor 2
         ("seats", "sleep", 1.0), ("shelter", "sleep", 1.0)]     # ladder: floor 3 -> floor 4   (minutes, schematic)

# --- the body and the limits (NASA-STD-3001 Vol. 1 Rev. B) ---
BODY_AL = 6.5                # g/cm2: depth of the blood-forming organs (~5 g/cm2 tissue)
QUALITY = 1.5                # RBE of protons (Table 4)
LIMIT_MSV = 250              # 30-day limit, blood-forming organs (Table 3)
LEVELS = [(5, "SAFE"), (15, "LOW"), (45, "MEDIUM"), (100000, "HIGH")]      # % of the limit
EARTH_MSV_PER_YEAR = 2.4     # natural radiation on Earth per year, world average (UNSCEAR): to explain a dose
ROOM_NAMES = {"cockpit": "Cockpit", "seats": "Crew seats", "galley": "Galley", "exercise": "Exercise area",
              "hygiene": "Hygiene bay", "shelter": "Storm shelter", "sleep": "Sleeping area",
              "leb": "Lower equipment bay"}
ROOM_WORDS = {"SAFE": "safe", "LOW": "low risk", "MEDIUM": "caution", "HIGH": "avoid"}
STORM_NAMES = {0: "below storm level", 1: "S1 (minor)", 2: "S2 (moderate)", 3: "S3 (strong)", 4: "S4 (severe)",
               5: "S5 (extreme)"}

# --- the spacecraft (TEAM ASSUMPTIONS, checked against Orion's known masses) ---
VOXEL = 0.05                 # m, size of one cube
VOXEL_CM = VOXEL * 100
X_RANGE, Y_RANGE, Z_RANGE = (-2.7, 2.7), (-0.2, 8.2), (-2.7, 2.7)
CM_BOTTOM = 4.7              # m, crew module starts here (Orion/main.py)
CABIN_FLOOR = 5.85           # m, floor of the crew deck
TOP_BULKHEAD = 2.40          # m above CM_BOTTOM: top of the pressure vessel
MATERIALS = pd.DataFrame([   # id, name, aluminium equivalence (NIST, ~100 MeV), colour
    (0, "vacuum / cabin air", 1.00, "#ffffff"), (1, "Avcoat (heat shield)", 1.15, "#7a4a2a"),
    (2, "backshell tiles + panels", 1.00, "#c8c8c8"), (3, "aluminium (skin + ribs)", 1.00, "#5b7a95"),
    (4, "HDPE liner (5 cm)", 1.30, "#f2c230"), (5, "HDPE shelter (15 cm)", 1.30, "#e07b00"),
    (6, "equipment / stowage", 1.00, "#4a4a4a"), (7, "water", 1.28, "#2a78d6"),
    (8, "propellant (MMH / MON)", 1.20, "#3fa79b"), (9, "parachutes", 1.25, "#d6553c"),
], columns=["id", "name", "al_equiv", "colour"])
AVCOAT, BACKSHELL_TILES = 2.0, 0.6                       # g/cm2
AL_DENSITY, AL_CM, AL_RIBS = 2.70, 0.4, 4.5              # g/cm3, cm, g/cm2
HDPE_DENSITY, HDPE_CM, HDPE_SHELTER_CM = 0.95, 5.0, 15.0
ESM_SKIN, CMA_RING = 2.0, 1.5                            # g/cm2
ESM_PROPELLANT, ESM_FLUIDS, ESM_EQUIPMENT = 0.70, 0.035, 0.13       # g/cm3
FORWARD_BAY, EQUIPMENT_BAY, CABIN_LINING = 0.30, 0.70, 0.60         # g/cm3
ROOM_FILL = {"cockpit": 0.05, "seats": 0.03, "galley": 0.10, "exercise": 0.05,
             "hygiene": 0.10, "shelter": 0.0, "sleep": 0.0}
ROOMS = {   # centre (x, y, z) and size (width, height, depth), metres, from Orion/main.py
    "cockpit": [-0.6, 6.75, -1.3, 1.9, 0.8, 0.5], "seats": [-0.6, 6.05, -0.3, 1.6, 0.8, 2.1],
    "galley": [1.35, 6.4, 0.95, 0.55, 0.65, 0.75], "exercise": [1.4, 6.1, -0.1, 0.65, 0.55, 0.95],
    "hygiene": [0.08, 6.25, 1.3, 0.68, 0.8, 0.68], "shelter": [0.55, 6.3, 0.0, 0.8, 1.1, 2.1],
    "sleep": [0.0, 7.0, 0.0, 2.0, 0.5, 1.7], "leb": [0.0, 5.55, 0.0, 3.2, 0.65, 3.2]}
ESM_TANKS = [0.0, 2.2, 0.0, 2.6, 1.9, 2.6]
ESM_FLUID_BOXES = [[0.0, 0.85, 0.0, 2.7, 0.7, 2.7], [0.0, 3.35, 0.0, 2.7, 0.7, 2.7]]
N_RAYS, STEP, MAX_LENGTH = 400, 0.01, 12.0               # rays per room, step (m), length (m)
SIDES = {"Up": (0, 1, 0), "Down": (0, -1, 0), "Right": (1, 0, 0),
         "Left": (-1, 0, 0), "Front": (0, 0, -1), "Back": (0, 0, 1)}

BANDS = {"pred_log_fluence_10_30": (10, 30), "pred_log_fluence_30_50": (30, 50),
         "pred_log_fluence_50_100": (50, 100), "pred_log_fluence_100": (100, 500)}
NIST = pd.DataFrame({        # NIST PSTAR: energy (MeV), range in aluminium (g/cm2), stopping power in water
    "energy": [1, 2, 5, 10, 20, 30, 50, 70, 100, 150, 200, 300, 500, 1000],
    "range_al": [0.0040, 0.0123, 0.0563, 0.170, 0.580, 1.21, 2.97, 5.40, 9.98, 19.6, 31.4, 59.5, 125, 310],
    "stopping_water": [260.8, 162.4, 79.11, 45.67, 26.07, 18.76, 12.45, 9.559, 7.289, 5.445, 4.492, 3.52, 2.743, 2.211],
})


# =====================================================================
# 2. ANATOMY AND RAYS (only when they do not exist yet, or REBUILD = True)
# =====================================================================
if REBUILD or not os.path.exists(GRID_FILE) or not os.path.exists(RAYS_FILE):
    print("Making the anatomy and the rays ...")

    # --- the grid: the centre of every cube ---
    x = np.arange(X_RANGE[0] + VOXEL / 2, X_RANGE[1], VOXEL)
    y = np.arange(Y_RANGE[0] + VOXEL / 2, Y_RANGE[1], VOXEL)
    z = np.arange(Z_RANGE[0] + VOXEL / 2, Z_RANGE[1], VOXEL)
    X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
    R = np.sqrt(X ** 2 + Z ** 2)                         # distance from the spacecraft axis
    density = np.zeros(X.shape, dtype=np.float32)        # g/cm3
    material = np.zeros(X.shape, dtype=np.int8)

    # --- service module (y = 0 to 4): cylinder of radius 2.05 m ---
    esm_inside = (R <= 2.05) & (Y >= 0) & (Y <= 4.0)
    density[esm_inside], material[esm_inside] = ESM_EQUIPMENT, 6
    tanks = ((np.abs(X - ESM_TANKS[0]) <= ESM_TANKS[3] / 2) & (np.abs(Y - ESM_TANKS[1]) <= ESM_TANKS[4] / 2)
             & (np.abs(Z - ESM_TANKS[2]) <= ESM_TANKS[5] / 2) & esm_inside)
    density[tanks], material[tanks] = ESM_PROPELLANT, 8
    for box in ESM_FLUID_BOXES:
        fluids = ((np.abs(X - box[0]) <= box[3] / 2) & (np.abs(Y - box[1]) <= box[4] / 2)
                  & (np.abs(Z - box[2]) <= box[5] / 2) & esm_inside)
        density[fluids], material[fluids] = ESM_FLUIDS, 7
    esm_skin = esm_inside & ((R > 2.05 - VOXEL) | (Y < VOXEL) | (Y > 4.0 - VOXEL))
    density[esm_skin], material[esm_skin] = ESM_SKIN / VOXEL_CM, 3
    adapter = (R <= 2.28) & (R > 2.28 - VOXEL) & (Y > 4.0) & (Y <= CM_BOTTOM + 0.5)
    density[adapter], material[adapter] = CMA_RING / VOXEL_CM, 3

    # --- crew module: inside volumes first, wall layers on top ---
    h = Y - CM_BOTTOM
    wall_radius = np.where(h < 0.76, 2.51, 2.47 - (h - 0.76) * 0.668)
    cm_inside = (h >= 0.50) & (h <= 3.30) & (R <= wall_radius)
    forward_bay = cm_inside & (h >= TOP_BULKHEAD)
    density[forward_bay], material[forward_bay] = FORWARD_BAY, 9
    leb = ROOMS["leb"]
    equipment_bay = (cm_inside & (np.abs(X - leb[0]) <= leb[3] / 2) & (Y < CABIN_FLOOR)
                     & (np.abs(Y - leb[1]) <= leb[4] / 2) & (np.abs(Z - leb[2]) <= leb[5] / 2))
    density[equipment_bay], material[equipment_bay] = EQUIPMENT_BAY, 6
    for name, fill in ROOM_FILL.items():
        room = ROOMS[name]
        inside_room = ((np.abs(X - room[0]) <= room[3] / 2) & (np.abs(Y - room[1]) <= room[4] / 2)
                       & (np.abs(Z - room[2]) <= room[5] / 2) & cm_inside & (h < TOP_BULKHEAD))
        density[inside_room], material[inside_room] = fill, (6 if fill > 0 else 0)

    # depth of every cube from the nearest outer surface, in cubes (0 = outermost)
    side_depth = np.floor((wall_radius - R) / VOXEL)
    aft_depth = np.floor((h - 0.50) / VOXEL)
    top_depth = np.floor((TOP_BULKHEAD - h) / VOXEL) + 1
    depth = np.minimum(np.minimum(side_depth, aft_depth), top_depth)
    nearest_aft = aft_depth <= np.minimum(side_depth, top_depth)
    pressure_vessel = cm_inside & (h < TOP_BULKHEAD)

    lining = pressure_vessel & (depth >= 3) & (depth <= 4) & (Y > CABIN_FLOOR) & ~nearest_aft
    density[lining], material[lining] = CABIN_LINING, 6
    layer0 = pressure_vessel & (depth == 0)                                   # Avcoat or tiles
    density[layer0 & nearest_aft], material[layer0 & nearest_aft] = AVCOAT / VOXEL_CM, 1
    density[layer0 & ~nearest_aft], material[layer0 & ~nearest_aft] = BACKSHELL_TILES / VOXEL_CM, 2
    layer1 = pressure_vessel & (depth == 1)                                   # aluminium 4 mm + ribs
    density[layer1], material[layer1] = (AL_DENSITY * AL_CM + AL_RIBS) / VOXEL_CM, 3
    liner = pressure_vessel & (depth == 2) & (Y >= CABIN_FLOOR) & ~nearest_aft    # HDPE 5 cm walls
    density[liner], material[liner] = HDPE_DENSITY * HDPE_CM / VOXEL_CM, 4
    floor_liner = pressure_vessel & (Y >= CABIN_FLOOR) & (Y < CABIN_FLOOR + VOXEL) & (depth >= 2)
    density[floor_liner], material[floor_liner] = HDPE_DENSITY * HDPE_CM / VOXEL_CM, 4
    s = ROOMS["shelter"]                                                      # shelter: HDPE 15 cm
    t = HDPE_SHELTER_CM / 100
    shelter_outer = ((np.abs(X - s[0]) <= s[3] / 2 + t) & (np.abs(Y - s[1]) <= s[4] / 2 + t)
                     & (np.abs(Z - s[2]) <= s[5] / 2 + t))
    shelter_inner = ((np.abs(X - s[0]) < s[3] / 2) & (np.abs(Y - s[1]) < s[4] / 2) & (np.abs(Z - s[2]) < s[5] / 2))
    shelter_wall = shelter_outer & ~shelter_inner & pressure_vessel
    density[shelter_wall], material[shelter_wall] = HDPE_DENSITY, 5
    density[shelter_inner], material[shelter_inner] = 0.0, 0
    al_equiv = MATERIALS.set_index("id")["al_equiv"].values[material].astype(np.float32)

    cube_kg = density * VOXEL_CM ** 3 / 1000
    print(f"  HDPE added: {cube_kg[(material == 4) | (material == 5)].sum():.0f} kg")
    np.savez_compressed(GRID_FILE, density=density, material=material, al_equiv=al_equiv,
                        x=x, y=y, z=z, voxel=VOXEL, material_names=MATERIALS["name"].values)
    with open(ROOMS_FILE, "w") as f:
        json.dump(ROOMS, f, indent=2)

    # --- figure: the materials in two cuts ---
    cmap = ListedColormap(MATERIALS["colour"].values)
    fig, axes = plt.subplots(1, 2, figsize=(15, 8))
    k = np.argmin(np.abs(z))
    axes[0].imshow(material[:, :, k].T, origin="lower", cmap=cmap, vmin=-0.5, vmax=len(MATERIALS) - 0.5,
                   extent=[x[0], x[-1], y[0], y[-1]], interpolation="nearest")
    axes[0].set_title("Side cut (z = 0)")
    axes[0].set_ylim(4.5, 8.2)
    j = np.argmin(np.abs(y - 6.3))
    axes[1].imshow(material[:, j, :].T, origin="lower", cmap=cmap, vmin=-0.5, vmax=len(MATERIALS) - 0.5,
                   extent=[x[0], x[-1], z[0], z[-1]], interpolation="nearest")
    axes[1].set_title("Cabin cut (y = 6.3 m, crew deck)")
    fig.legend(handles=[Patch(color=m["colour"], label=m["name"]) for _, m in MATERIALS.iterrows() if m["id"] > 0],
               loc="lower center", ncol=5, fontsize=9)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(os.path.join(FIGURES, "anatomy_materials.png"), dpi=130)
    plt.close(fig)

    # --- rays: 400 directions spread evenly on a sphere (Fibonacci sphere) ---
    k = np.arange(N_RAYS) + 0.5
    polar = np.arccos(1 - 2 * k / N_RAYS)
    azimuth = np.pi * (1 + 5 ** 0.5) * k
    directions = np.column_stack([np.sin(polar) * np.cos(azimuth), np.cos(polar), np.sin(polar) * np.sin(azimuth)])
    side_of_ray = np.array(list(SIDES))[np.argmax(directions @ np.array(list(SIDES.values())).T, axis=1)]
    mass_per_cm = density * al_equiv                     # g/cm3, aluminium equivalent
    steps = np.arange(0, MAX_LENGTH, STEP) + STEP / 2
    rows = []
    for name, (cx, cy, cz, w, hh, d) in ROOMS.items():
        points = np.array([cx, cy, cz]) + directions[:, None, :] * steps[None, :, None]
        i = np.floor((points[..., 0] - x[0] + VOXEL / 2) / VOXEL).astype(int)
        j = np.floor((points[..., 1] - y[0] + VOXEL / 2) / VOXEL).astype(int)
        l = np.floor((points[..., 2] - z[0] + VOXEL / 2) / VOXEL).astype(int)
        inside = (i >= 0) & (i < len(x)) & (j >= 0) & (j < len(y)) & (l >= 0) & (l < len(z))
        crossed = np.where(inside, mass_per_cm[np.clip(i, 0, len(x) - 1), np.clip(j, 0, len(y) - 1),
                                               np.clip(l, 0, len(z) - 1)], 0.0)
        shielding = crossed.sum(axis=1) * STEP * 100     # g/cm2
        for r in range(N_RAYS):
            rows.append({"room": name, "ray": r, "dx": directions[r, 0], "dy": directions[r, 1],
                         "dz": directions[r, 2], "side": side_of_ray[r], "shielding_g_cm2": shielding[r]})
    pd.DataFrame(rows).to_csv(RAYS_FILE, index=False)
    print("  saved:", GRID_FILE, RAYS_FILE)

rays = pd.read_csv(RAYS_FILE)


# =====================================================================
# 3. THE STORM: protons per energy (all directions, protons / cm2)
# =====================================================================
energies, protons, source = None, None, None
if STORM == "live":
    log = pd.read_csv(LIVE_LOG)
    now = log.iloc[-1]
    source = f"live {now['time']} ({now['status']})"
    if not pd.isna(now["pred_log_peak"]):
        # worst case: forecast + 1.65 x RMSE of the model at this hour of the storm
        hours = float(now["hours_since_onset"])
        errors = pd.read_csv(MODEL_ERRORS)
        log_fluence = []
        for column in BANDS:
            e = errors[errors["target"] == column.replace("pred_", "")].sort_values("hours_since_onset")
            rmse = float(np.interp(min(hours, 6), e["hours_since_onset"], e["RMSE"]))
            log_fluence.append(float(now[column]) + WORST_CASE_Z * rmse)
        # the flux now is already above the forecast peak: the forecast was too low, scale it up
        if np.log10(max(float(now["p10_now"]), 1e-3)) > float(now["pred_log_peak"]):
            log_fluence = [f + np.log10(float(now["p10_now"])) - float(now["pred_log_peak"]) for f in log_fluence]
            source += ", forecast exceeded -> scaled up"
        energies, protons = [], []
        for log_f, (low, high) in zip(log_fluence, BANDS.values()):
            energies.append(np.logspace(np.log10(low), np.log10(high), 200))
            protons.append(np.full(200, 4 * np.pi * 10 ** log_f / 200))     # per sr -> all directions
        energies, protons = np.concatenate(energies), np.concatenate(protons)
        source += ", WORST CASE (forecast + 1.65 x error)"
elif STORM == "October 1989":
    table5 = pd.read_csv(DESIGN_SPE, comment="#")
    table5 = table5[table5["energy_mev"] >= 1]
    energies = table5["energy_mev"].values
    protons = table5["fluence_per_cm2_mev"].values * np.gradient(energies)
    source = "October 1989, NASA design reference storm (NASA-STD-3001 Table 5)"
print("Storm:", source)


# =====================================================================
# 4. DOSE IN EVERY ROOM
#    a table "dose behind t g/cm2" for every thickness: a proton gets through if its range is longer
#    than t; what is left of its range gives its energy, and that energy (stopping power) the dose
# =====================================================================
room_dose = pd.Series(0.0, index=CREW_ROOMS)
if energies is not None:
    log_E, log_R, log_S = (np.log(NIST[c].values) for c in ["energy", "range_al", "stopping_water"])
    proton_range = np.exp(np.interp(np.log(energies), log_E, log_R))
    thickness = np.concatenate([np.linspace(0, 50, 501), np.linspace(50.5, 600, 1100)])
    dose_table = []
    for t in thickness:
        left = proton_range - t
        through = left > NIST["range_al"].iloc[0]
        energy_after = np.exp(np.interp(np.log(left[through]), log_R, log_E))
        stopping = np.exp(np.interp(np.log(energy_after), log_E, log_S))
        dose_table.append(1.602e-10 * (protons[through] * stopping).sum() * 1000 * QUALITY)    # mSv
    rays["dose_msv"] = np.interp(rays["shielding_g_cm2"] + BODY_AL, thickness, dose_table)
    room_dose = rays.groupby("room")["dose_msv"].mean()[CREW_ROOMS]
    room_dose[SHELTER] = room_dose[SHELTER] * SHELTER_LEFT          # the safe place (team assumption)

rooms = pd.DataFrame({"dose_msv": room_dose, "pct_limit": 100 * room_dose / LIMIT_MSV})
rooms["level"] = "HIGH"
for top, level in reversed(LEVELS):
    rooms.loc[rooms["pct_limit"] < top, "level"] = level
rooms = rooms.sort_values("dose_msv")


# =====================================================================
# 5. WHERE IS EVERY ASTRONAUT NOW (demo: random walk, kept in CREW_STATE between the runs)
#    every 5 minutes: walk a bit towards a spot inside the room; sometimes go through a door to a
#    neighbouring room (ladders too); while sheltering: stay in the room he was sent to
# =====================================================================
plans_raw = pd.concat([gpd.read_file(FLOOR_PLANS, layer=layer) for layer in pyogrio.list_layers(FLOOR_PLANS)[:, 0]])
room_shapes = plans_raw[plans_raw["type"] == "room"].set_index("room_key")
when = pd.Timestamp(str(now["time"])) if STORM == "live" else pd.Timestamp.now().floor("5min")
rng = np.random.default_rng()                        # different every run: the crew walks at random

# 200 free spots inside every room, to pick from
spots = {}
for key, shape in room_shapes.geometry.items():
    x0, y0, x1, y1 = shape.bounds
    candidates = np.random.default_rng(0).uniform([x0, y0], [x1, y1], size=(3000, 2))
    spots[key] = candidates[[shape.contains(Point(a, b)) for a, b in candidates]][:200]

graph = nx.Graph()
rate = room_dose / STORM_HOURS                       # mSv per hour in every room during the storm
for a, b, minutes in DOORS:
    graph.add_edge(a, b, minutes=minutes, dose=minutes / 60 * max(rate[a], rate[b]))

crew = pd.read_csv(CREW_STATE).set_index("astronaut") if os.path.exists(CREW_STATE) else None
if crew is None or sorted(crew.index) != sorted(CREW):   # first run, or the crew changed: everyone in a random room
    rows = []
    for astronaut in CREW:
        room = rng.choice(CREW_ROOMS)
        spot = spots[room][rng.integers(len(spots[room]))]
        target = spots[room][rng.integers(len(spots[room]))]
        rows.append({"astronaut": astronaut, "room": room, "x": spot[0], "y": spot[1],
                     "target_x": target[0], "target_y": target[1], "sheltering": False})
    crew = pd.DataFrame(rows).set_index("astronaut")
crew["sheltering"] = crew["sheltering"].astype(bool)

storm_on = bool(room_dose.max() - room_dose.min() >= MIN_SAVE_MSV)
if not storm_on:
    crew["sheltering"] = False                       # the storm is over: free to walk again

for astronaut, c in crew.iterrows():
    if not c["sheltering"] and rng.random() < P_CHANGE_ROOM:          # through a door to a neighbouring room
        room = rng.choice(list(graph.neighbors(c["room"])))
        spot = spots[room][rng.integers(len(spots[room]))]
        crew.loc[astronaut, ["room", "x", "y"]] = [room, spot[0], spot[1]]
        target = spots[room][rng.integers(len(spots[room]))]
        crew.loc[astronaut, ["target_x", "target_y"]] = [target[0], target[1]]
    else:                                                              # walk a bit inside the room
        c = crew.loc[astronaut]
        crew.loc[astronaut, "x"] = c["x"] + WALK * (c["target_x"] - c["x"])
        crew.loc[astronaut, "y"] = c["y"] + WALK * (c["target_y"] - c["y"])
        if np.hypot(c["target_x"] - c["x"], c["target_y"] - c["y"]) < 0.1:   # arrived: a new spot
            target = spots[c["room"]][rng.integers(len(spots[c["room"]]))]
            crew.loc[astronaut, ["target_x", "target_y"]] = [target[0], target[1]]
crew["floor"] = crew["room"].map(room_shapes["floor"]).astype(int)


# =====================================================================
# 6. THE BEST ROOM AROUND EVERY ASTRONAUT
#    cost of a room = dose on the way (Dijkstra, every door: minutes x dose rate of its rooms)
#                     + storm dose in that room;   only rooms within MAX_MINUTES
# =====================================================================
orders = []
for astronaut, p in crew.iterrows():
    reach = nx.single_source_dijkstra_path_length(graph, p["room"], weight="minutes")
    best, best_cost, best_path = p["room"], room_dose[p["room"]], [p["room"]]
    for room, minutes in reach.items():
        if minutes > MAX_MINUTES or room == p["room"]:
            continue
        path = nx.shortest_path(graph, p["room"], room, weight="dose")
        cost = nx.shortest_path_length(graph, p["room"], room, weight="dose") + room_dose[room]
        if cost < best_cost:
            best, best_cost, best_path = room, cost, path
    saved = room_dose[p["room"]] - best_cost
    move = saved >= MIN_SAVE_MSV
    orders.append({"time": when, "astronaut": astronaut, "now_in": p["room"], "floor": int(p["floor"]),
                   "x": round(p["x"], 3), "y": round(p["y"], 3),
                   "go_to": best if move else p["room"], "route": " -> ".join(best_path) if move else "",
                   "minutes": sum(graph[a][b]["minutes"] for a, b in zip(best_path[:-1], best_path[1:])) if move else 0,
                   "dose_if_stays_msv": round(room_dose[p["room"]], 2),
                   "dose_if_goes_msv": round(best_cost if move else room_dose[p["room"]], 2),
                   "saves_msv": round(saved if move else 0, 2)})
    if move:                                          # he follows the order: next time he is there, and stays
        spot = spots[best][rng.integers(len(spots[best]))]
        crew.loc[astronaut, ["room", "x", "y", "target_x", "target_y", "sheltering"]] = [
            best, spot[0], spot[1], spot[0], spot[1], True]
orders = pd.DataFrame(orders)
crew.drop(columns="floor").round(3).to_csv(CREW_STATE)

# every new order to move -> a "critical" alert in the database of the team (once: then he is sheltering)
if os.path.exists(DB_FILE) and len(orders[orders["route"] != ""]) > 0:
    db = sqlite3.connect(DB_FILE)
    ids = dict(db.execute("SELECT name, id FROM astronauts"))
    for _, o in orders[orders["route"] != ""].iterrows():
        if o["astronaut"] in ids:
            db.execute("INSERT INTO alerts (astronaut_id, severity, message, created_at, acknowledged) VALUES (?, 'critical', ?, datetime('now'), 0)",
                       (ids[o["astronaut"]], f"{TAG} go to the {o['go_to']} now: {o['route']} "
                                             f"({o['minutes'] * 60:.0f} s). Staying could give up to "
                                             f"{o['dose_if_stays_msv']:.0f} mSv."))
    db.commit()
    db.close()
orders.to_csv(CREW_LOG, mode="a", header=not os.path.exists(CREW_LOG), index=False)


# =====================================================================
# 7. PRINT AND SAVE
# =====================================================================
pd.set_option("display.width", 200)
print(f"\nWorst-case storm dose per room (mSv, {SHELTER} = {SHELTER_LEFT:.0%} of its storm dose):")
print(rooms.round(2).to_string())
print(f"\nCrew at {when:%Y-%m-%d %H:%M}:")
print(orders[["astronaut", "now_in", "go_to", "route", "minutes", "dose_if_stays_msv", "dose_if_goes_msv",
              "saves_msv"]].to_string(index=False))

rooms.round(4).to_csv(OUT_ROOMS_CSV)
orders.to_csv(OUT_CREW_CSV, index=False)
with open(OUT_ROOMS_JSON, "w") as f:
    json.dump({"storm": source, "rooms": rooms.round(3).to_dict("index")}, f, indent=2)
with open(OUT_CREW_JSON, "w") as f:
    json.dump({"storm": source, "time": str(when), "orders": orders.astype({"time": str}).to_dict("records")},
              f, indent=2)


# =====================================================================
# 8. FLOOR PLANS: dose of every room, every astronaut and his route (GIS layers + figure)
# =====================================================================
if os.path.exists(OUT_FLOORS):
    try:
        os.remove(OUT_FLOORS)
    except PermissionError:
        OUT_FLOORS = OUT_FLOORS.replace(".gpkg", pd.Timestamp.now().strftime("_%Y%m%d_%H%M%S.gpkg"))
plans = gpd.GeoDataFrame(plans_raw, crs="EPSG:3857")
plans = plans.merge(rooms, left_on="room_key", right_index=True, how="left")
plans.to_file(OUT_FLOORS, layer="floors_dose", driver="GPKG")
centre = plans[plans["type"] == "room"].set_index("room_key").geometry.representative_point()
gpd.GeoDataFrame(orders, geometry=[Point(a, b) for a, b in zip(orders["x"], orders["y"])],
                 crs="EPSG:3857").to_file(OUT_FLOORS, layer="crew", driver="GPKG")
moving = orders[orders["route"] != ""]
if len(moving) > 0:
    gpd.GeoDataFrame(moving, geometry=[LineString([centre[r] for r in p.split(" -> ")]) for p in moving["route"]],
                     crs="EPSG:3857").to_file(OUT_FLOORS, layer="routes", driver="GPKG")

colors = {"SAFE": "#2a9d55", "LOW": "#8bbf3f", "MEDIUM": "#e9a23b", "HIGH": "#d64541"}
fig, axes = plt.subplots(1, 3, figsize=(18, 6.5))
for ax, (floor, g) in zip(axes, plans[plans["floor"] >= 2].groupby("floor")):
    g[g["type"] == "hull"].plot(ax=ax, color="#bbbbbb")
    r = g[g["type"] == "room"]
    r.plot(ax=ax, color=r["level"].map(colors).fillna("#eeeeee"), edgecolor="black", lw=0.8, alpha=0.85)
    for _, room in r.iterrows():
        c = room.geometry.representative_point()
        ax.text(c.x, c.y, f"{room['name']}\n{room['dose_msv']:.1f} mSv", ha="center", va="center", fontsize=7)
    for _, o in orders[orders["floor"] == floor].iterrows():
        ax.plot(o["x"], o["y"], "o", color="#14213d", ms=8)
        ax.annotate(f"{o['astronaut']} -> {o['go_to']}" if o["route"] else o["astronaut"], (o["x"], o["y"]),
                    xytext=(5, 5), textcoords="offset points", fontsize=8, color="#14213d", weight="bold")
    ax.set_title(g["floor_name"].iloc[0])
    ax.set_aspect("equal")
    ax.set_axis_off()
fig.suptitle(f"Worst-case storm dose per room and where every astronaut goes\n{source}", fontsize=12)
fig.tight_layout()
fig.savefig(os.path.join(FIGURES, "room_doses_floors.png"), dpi=120)
plt.close(fig)
print("\nSaved:", OUT_ROOMS_JSON, OUT_CREW_JSON, OUT_FLOORS)


# =====================================================================
# 9. IN PLAIN WORDS, for the crew screen (the astronaut does not read mSv tables)
#    a dose is told as % of the monthly allowance and as years of natural radiation on Earth
# =====================================================================
readable = {"module": "shielding", "updated": str(when), "crew": {}, "rooms": {}}
worst = orders["dose_if_stays_msv"].max()
if len(moving) > 0:
    readable["level"] = "red"
    readable["headline"] = "GO TO THE STORM SHELTER NOW"
    readable["what_to_do"] = "Follow the route on your card. Stay there until the all clear."
elif energies is not None and worst >= 0.05:
    readable["level"] = "yellow"
    readable["headline"] = "Solar storm: keep working, the walls protect you"
    readable["what_to_do"] = "No need to move. We check again every 5 minutes."
else:
    readable["level"] = "green"
    readable["headline"] = "All clear: the Sun is quiet"
    readable["what_to_do"] = "Normal work."

why = []
if STORM == "live" and not pd.isna(now["pred_log_peak"]):
    peak = 10 ** float(now["pred_log_peak"])
    why.append(f"A solar storm started {float(now['hours_since_onset']):.1f} hours ago. It is expected to reach "
               f"{STORM_NAMES[min(int(np.log10(peak)), 5) if peak >= 10 else 0]}.")
    if not pd.isna(now["prob_peak_passed"]):
        why.append(f"Chance that the worst is already over: {float(now['prob_peak_passed']):.0%}.")
elif STORM == "live" and now["status"] == "STORM STARTED":
    why.append("A solar storm has just started. The first forecast comes 30 minutes after the start.")
elif STORM != "live":
    why.append(f"Test with {source}.")
if worst >= 0.05:
    why.append(f"In the worst case, the most exposed place would get {worst:.0f} mSv during this storm: "
               f"{100 * worst / LIMIT_MSV:.0f}% of your monthly allowance, like {worst / EARTH_MSV_PER_YEAR:.0f} "
               f"years of natural radiation on Earth.")
    why.append(f"The storm shelter would get {room_dose[SHELTER]:.1f} mSv.")
readable["why"] = why

for _, o in orders.iterrows():
    where = ROOM_NAMES[o["now_in"]]
    if o["route"]:
        path = " -> ".join(ROOM_NAMES[r] for r in o["route"].split(" -> "))
        readable["crew"][o["astronaut"]] = {
            "level": "red",
            "message": f"Go to the {ROOM_NAMES[o['go_to']]} now: {path} ({o['minutes'] * 60:.0f} seconds). "
                       f"Staying in the {where} could give you up to {o['dose_if_stays_msv']:.0f} mSv "
                       f"({100 * o['dose_if_stays_msv'] / LIMIT_MSV:.0f}% of your monthly allowance); "
                       f"there you get {o['dose_if_goes_msv']:.1f} mSv."}
    elif o["dose_if_stays_msv"] >= 0.05:
        readable["crew"][o["astronaut"]] = {
            "level": "yellow",
            "message": f"Stay in the {where}. Worst case here: {o['dose_if_stays_msv']:.1f} mSv "
                       f"({100 * o['dose_if_stays_msv'] / LIMIT_MSV:.1f}% of your monthly allowance), "
                       f"not worth moving."}
    else:
        readable["crew"][o["astronaut"]] = {"level": "green", "message": f"Normal work (you are in the {where})."}

for room, r in rooms.iterrows():
    readable["rooms"][ROOM_NAMES[room]] = (f"{ROOM_WORDS[r['level']]}: up to {r['dose_msv']:.1f} mSv in this storm"
                                           if r["dose_msv"] >= 0.05 else "safe")
with open(OUT_READABLE, "w") as f:
    json.dump(readable, f, indent=2)
print("\n" + readable["headline"].upper() + ". " + readable["what_to_do"])
for astronaut, c in readable["crew"].items():
    print(f"  {astronaut}: {c['message']}")
