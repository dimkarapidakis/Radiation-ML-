# =====================================================================
# crew_routes.py
# Every 5 minutes:
#   1. WHERE is every astronaut: the crew schedule (badges), unless they are sheltering
#   2. read the dosimeter of every room; when the "rain" of protons is increasing:
#      EVERY astronaut goes to the SAFETY ROOM (the storm shelter), by the way with the least dose
#      (Dijkstra on the doors between rooms, every door weighted by the dose rate of its rooms now)
#   3. they stay there until the all clear (1 hour of quiet), then follow their schedule again
#   4. PERSONAL dose = dose rate of the room where the astronaut is x 5 minutes,
#      compared with the dose if there had been no warning (they had followed the schedule)
#
# Mission: 6 astronauts, 14 days.
# Input (written by the spacecraft, or by simulate_room_sensors.py for the demo):
#   warning/data/room_sensors_log.csv   time, room, dose_rate_msv_h   (every 5 min)
#   warning/data/crew_schedule.csv      time, astronaut, room, floor, x, y   (every hour)
# Output:
#   warning/data/crew_log.csv           every 5 min: astronaut, room, floor, x, y, planned room, dose rate, personal dose
#   warning/data/crew_routes.csv        every route that was given
#   warning/data/crew_status.json       the latest status (for the app)
#   warning/data/crew_routes_readable.json  the story of the mission in plain words (for the app)
#   warning/data/crew_map.gpkg          the 4 floors side by side with rooms, astronauts and routes,
#                                       with time fields for the ArcGIS time slider
#   warning/Figures/crew_dose.png       personal dose of every astronaut: sheltered vs. no warning
#
# The whole log is replayed in order, so the same script works for the demo and live.
# Run:  python warning/crew_routes.py
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import json
import os

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
import pyogrio
from shapely import affinity
from shapely.geometry import LineString, Point

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "warning", "data")
SENSORS_LOG = os.path.join(DATA, "room_sensors_log.csv")
SCHEDULE_FILE = os.path.join(DATA, "crew_schedule.csv")
FLOOR_PLANS = os.path.join(ROOT, "shielding", "cad", "orion_floor_plans.gpkg")
CREW_LOG = os.path.join(DATA, "crew_log.csv")
ROUTES_OUT = os.path.join(DATA, "crew_routes.csv")
STATUS_OUT = os.path.join(DATA, "crew_status.json")
READABLE_OUT = os.path.join(DATA, "crew_routes_readable.json")      # the story in plain words (for the app)
EARTH_MSV_PER_YEAR = 2.4  # natural radiation on Earth per year (UNSCEAR), to explain a dose
ROOM_NAMES = {"cockpit": "Cockpit", "seats": "Crew seats", "galley": "Galley", "exercise": "Exercise area",
              "hygiene": "Hygiene bay", "shelter": "Storm shelter", "sleep": "Sleeping area",
              "leb": "Lower equipment bay"}
MAP_OUT = os.path.join(DATA, "crew_map.gpkg")
FIGURE = os.path.join(ROOT, "warning", "Figures", "crew_dose.png")
os.makedirs(os.path.dirname(FIGURE), exist_ok=True)

STEP_MIN = 5
RATE_WARNING = 0.1        # mSv/h in any crew room: the rain has started (~5 x the cosmic rays, 0.02 mSv/h)
RISE_FACTOR = 1.5         # ... and it is rising: rate now > 1.5 x rate 15 minutes ago
RISE_LOOKBACK = 3         # 3 steps = 15 minutes
SAFETY_ROOM = "shelter"   # the storm shelter (floor 3, HDPE 15 cm): where everyone goes at a warning
RATE_ALL_CLEAR = 0.05     # all crew rooms below this for 1 hour -> back to the schedule
CLEAR_STEPS = 12          # 12 steps = 1 hour
LIMIT_MSV = 250
FLOOR_GAP = 6.0           # metres between the floor plans on the map (floor 1, 2, 3, 4 side by side)
SEED = 7                  # where inside the safety room an astronaut stands

# floor 2 = lower equipment bay, floor 3 = crew deck, floor 4 = upper cabin
CREW_ROOMS = ["leb", "cockpit", "seats", "galley", "exercise", "hygiene", "shelter", "sleep"]
DOORS = [("seats", "cockpit", 0.5), ("seats", "exercise", 0.5), ("seats", "shelter", 0.5),
         ("exercise", "galley", 0.5), ("galley", "hygiene", 0.5), ("hygiene", "shelter", 0.5),
         ("seats", "leb", 1.0),                          # ladder: floor 3 -> floor 2
         ("seats", "sleep", 1.0), ("shelter", "sleep", 1.0)]   # ladder: floor 3 -> floor 4   (minutes, schematic)
rng = np.random.default_rng(SEED)


# =====================================================================
# 2. LOAD
# =====================================================================
log = pd.read_csv(SENSORS_LOG, parse_dates=["time"])
rates = log.pivot_table(index="time", columns="room", values="dose_rate_msv_h").sort_index()
schedule = pd.read_csv(SCHEDULE_FILE, parse_dates=["time"]).set_index(["time", "astronaut"])
CREW = sorted(schedule.index.get_level_values("astronaut").unique())

plans = pd.concat([gpd.read_file(FLOOR_PLANS, layer=layer) for layer in pyogrio.list_layers(FLOOR_PLANS)[:, 0]])
plans = gpd.GeoDataFrame(plans, crs="EPSG:3857")
room_shapes = plans[plans["type"] == "room"].set_index("room_key")


# =====================================================================
# 3. REPLAY, 5 MINUTES AT A TIME
# =====================================================================
dose = {a: 0.0 for a in CREW}
dose_if_no_warning = {a: 0.0 for a in CREW}
in_shelter = {}            # astronaut -> spot inside the shelter (while sheltering)
sheltering = False
quiet_steps = 0
crew_rows, route_rows = [], []

# the warning uses the average of the last 15 minutes (a single 5-minute value has 5% noise);
# the personal dose uses every 5-minute value
smooth = rates.rolling(RISE_LOOKBACK, min_periods=1).mean()
shelter_floor = int(room_shapes.loc[SAFETY_ROOM, "floor"])
shelter_shape = room_shapes.loc[SAFETY_ROOM, "geometry"]

for k, (t, now) in enumerate(rates.iterrows()):
    crew_now = smooth.iloc[k][CREW_ROOMS]

    # --- 1. where everyone should be now: the schedule of this hour ---
    planned = schedule.loc[t.floor("h")]
    position = {}
    for astronaut in CREW:
        if astronaut in in_shelter:
            position[astronaut] = in_shelter[astronaut]
        else:
            position[astronaut] = planned.loc[astronaut][["room", "floor", "x", "y"]].to_dict()

    # --- 2. warning: the rain is increasing in some crew room ---
    before = smooth.iloc[max(k - RISE_LOOKBACK, 0)][CREW_ROOMS]
    rising = (crew_now > RATE_WARNING) & (crew_now > RISE_FACTOR * before)
    warning = bool(rising.any()) or (sheltering and crew_now.max() > RATE_WARNING)

    # --- everyone who is not in the safety room goes there, by the way with the least dose ---
    if warning:
        sheltering = True
        quiet_steps = 0
        graph = nx.Graph()
        for a, b, minutes in DOORS:
            graph.add_edge(a, b, minutes=minutes, dose=minutes / 60 * max(crew_now[a], crew_now[b]))
        for astronaut, where in position.items():
            if where["room"] == SAFETY_ROOM:
                continue
            path = nx.shortest_path(graph, where["room"], SAFETY_ROOM, weight="dose")
            on_the_way = nx.shortest_path_length(graph, where["room"], SAFETY_ROOM, weight="dose")
            minutes = sum(graph[a][b]["minutes"] for a, b in zip(path[:-1], path[1:]))
            route_rows.append({"time": t, "astronaut": astronaut, "from_room": where["room"], "to_room": SAFETY_ROOM,
                               "from_floor": where["floor"], "to_floor": shelter_floor,
                               "route": " -> ".join(path), "minutes": minutes,
                               "dose_on_the_way_msv": round(on_the_way, 4),
                               "rising_in": ", ".join(rising[rising].index)})
            dose[astronaut] += on_the_way
            point = Point(rng.uniform(*shelter_shape.bounds[0::2]), rng.uniform(*shelter_shape.bounds[1::2]))
            while not shelter_shape.contains(point):              # a free spot inside the safety room
                point = Point(rng.uniform(*shelter_shape.bounds[0::2]), rng.uniform(*shelter_shape.bounds[1::2]))
            in_shelter[astronaut] = {"room": SAFETY_ROOM, "floor": shelter_floor,
                                     "x": round(point.x, 3), "y": round(point.y, 3)}
            position[astronaut] = in_shelter[astronaut]

    # --- 3. all clear: an hour of quiet -> everyone follows the schedule again ---
    elif sheltering:
        quiet_steps = quiet_steps + 1 if crew_now.max() < RATE_ALL_CLEAR else 0
        if quiet_steps >= CLEAR_STEPS:
            sheltering = False
            in_shelter = {}

    # --- 4. personal dose: dose rate of the room x 5 minutes ---
    for astronaut, where in position.items():
        dose[astronaut] += now[where["room"]] * STEP_MIN / 60
        dose_if_no_warning[astronaut] += now[planned.loc[astronaut, "room"]] * STEP_MIN / 60
        crew_rows.append({"time": t, "astronaut": astronaut, "room": where["room"], "floor": where["floor"],
                          "x": where["x"], "y": where["y"], "planned_room": planned.loc[astronaut, "room"],
                          "dose_rate_msv_h": now[where["room"]], "dose_msv": dose[astronaut],
                          "dose_if_no_warning_msv": dose_if_no_warning[astronaut], "warning": warning})

crew = pd.DataFrame(crew_rows)
routes = pd.DataFrame(route_rows)
crew.round({"dose_rate_msv_h": 5, "dose_msv": 4, "dose_if_no_warning_msv": 4}).to_csv(CREW_LOG, index=False)
routes.to_csv(ROUTES_OUT, index=False)


# =====================================================================
# 4. PRINT AND THE STATUS FOR THE APP
# =====================================================================
last = crew[crew["time"] == crew["time"].max()].set_index("astronaut")
print(f"Replayed {len(rates)} steps ({len(rates) * STEP_MIN / 60 / 24:.0f} days), {len(routes)} routes given")
if len(routes) > 0:
    first = routes.iloc[0]
    sheltered = crew[crew["room"] == SAFETY_ROOM].groupby("astronaut")["time"].agg(["min", "max"])
    print(f"First warning at {first['time']}: rain rising in {first['rising_in']}")
    print(f"In the shelter from {sheltered['min'].min()} to {sheltered['max'].max()}")
    print(routes.groupby("astronaut").first()[["time", "route", "minutes"]].to_string())
print(f"\nPersonal dose of the {len(rates) * STEP_MIN / 60 / 24:.0f} days (mSv):")
summary = pd.DataFrame({"now in": last["room"], "dose": last["dose_msv"].round(2),
                        "no warning": last["dose_if_no_warning_msv"].round(2)})
summary["saved"] = (summary["no warning"] - summary["dose"]).round(2)
summary["% of limit"] = (100 * summary["dose"] / LIMIT_MSV).round(1)
print(summary.to_string())

status = {"time": str(crew["time"].max()), "sheltering": sheltering, "safety_room": SAFETY_ROOM,
          "rooms_dose_rate_msv_h": rates.iloc[-1][CREW_ROOMS].round(4).to_dict(),
          "crew": {a: {"room": r["now in"], "floor": int(last.loc[a, "floor"]), "x": float(last.loc[a, "x"]),
                       "y": float(last.loc[a, "y"]), "dose_msv": float(r["dose"]), "pct_limit": float(r["% of limit"])}
                   for a, r in summary.iterrows()},
          "last_routes": routes.tail(len(CREW)).astype(str).to_dict("records")}
with open(STATUS_OUT, "w") as f:
    json.dump(status, f, indent=2)

# --- the story in plain words, for the crew screen ---
days = len(rates) * STEP_MIN / 60 / 24
readable = {"module": "crew_routes", "updated": str(crew["time"].max()), "crew": {}}
if len(routes) > 0:
    hours_in = (sheltered["max"].max() - sheltered["min"].min()).total_seconds() / 3600
    readable["level"] = "green"
    readable["headline"] = (f"The storm shelter cut the crew's dose in half: {summary['dose'].mean():.0f} mSv each "
                            f"instead of {summary['no warning'].mean():.0f}")
    readable["what_to_do"] = "Nothing: the storm is over."
    readable["why"] = [
        f"On {first['time']:%d %B at %H:%M} the dosimeters saw the radiation rising "
        f"({', '.join(ROOM_NAMES[r] for r in first['rising_in'].split(', '))}).",
        f"Every astronaut was in the storm shelter within {routes['minutes'].max():.0f} minute(s) "
        f"and stayed there {hours_in:.0f} hours.",
        f"{days:.0f} days in space gave each astronaut {summary['dose'].mean():.0f} mSv, like "
        f"{summary['dose'].mean() / EARTH_MSV_PER_YEAR:.0f} years of natural radiation on Earth, "
        f"{summary['% of limit'].mean():.0f}% of the monthly allowance."]
    for astronaut, r in summary.iterrows():
        route = routes[routes["astronaut"] == astronaut].iloc[0]
        path = " -> ".join(ROOM_NAMES[x] for x in route["route"].split(" -> "))
        readable["crew"][astronaut] = {
            "level": "green",
            "message": f"When the warning came you were in the {ROOM_NAMES[route['from_room']]}: you went {path} "
                       f"({route['minutes'] * 60:.0f} seconds). Your dose: {r['dose']:.0f} mSv; without the "
                       f"warning it would be {r['no warning']:.0f} mSv. You saved {r['saved']:.0f} mSv."}
else:
    readable["level"] = "green"
    readable["headline"] = f"No storm in {days:.0f} days: nobody had to move"
    readable["what_to_do"] = "Normal work."
    readable["why"] = [f"Each astronaut got about {summary['dose'].mean():.0f} mSv from cosmic rays "
                       f"({summary['% of limit'].mean():.0f}% of the monthly allowance)."]
with open(READABLE_OUT, "w") as f:
    json.dump(readable, f, indent=2)
print("\n" + readable["headline"])
for line in readable["why"]:
    print("  " + line)


# =====================================================================
# 5. MAP (GIS): the 4 floors side by side, FLOOR_GAP metres apart
#    static:   hull, equipment, rooms (highest dose rate), crew_now, routes
#    with time (ArcGIS time slider): rooms_time (dose rate every hour), crew_track (astronauts every 5 min),
#              routes (shown from "time" to "time_end")
# =====================================================================
if os.path.exists(MAP_OUT):
    try:
        os.remove(MAP_OUT)
    except PermissionError:
        MAP_OUT = MAP_OUT.replace(".gpkg", pd.Timestamp.now().strftime("_%Y%m%d_%H%M%S.gpkg"))
        print("crew_map.gpkg is open in another program, saving a new copy:", MAP_OUT)

shifted = plans.copy()
shifted["geometry"] = [affinity.translate(g, xoff=FLOOR_GAP * (f - 1)) for g, f in zip(plans.geometry, plans["floor"])]
shifted[shifted["type"] == "hull"].to_file(MAP_OUT, layer="hull", driver="GPKG")
shifted[shifted["type"] == "equipment"].to_file(MAP_OUT, layer="equipment", driver="GPKG")
rooms = shifted[shifted["type"] == "room"].copy()
rooms["max_rate_msv_h"] = rooms["room_key"].map(rates.max())
rooms.to_file(MAP_OUT, layer="rooms", driver="GPKG")

rooms_time = []
for t, now in rates.resample("1h").mean().iterrows():                    # every hour (14 days)
    r = rooms[["floor", "name", "room_key", "geometry"]].copy()
    r["time"] = t
    r["dose_rate_msv_h"] = r["room_key"].map(now)
    rooms_time.append(r)
gpd.GeoDataFrame(pd.concat(rooms_time), crs="EPSG:3857").to_file(MAP_OUT, layer="rooms_time", driver="GPKG")

track = crew.copy()
track_points = [Point(x + FLOOR_GAP * (f - 1), y) for x, y, f in zip(track["x"], track["y"], track["floor"])]
gpd.GeoDataFrame(track, geometry=track_points, crs="EPSG:3857").to_file(MAP_OUT, layer="crew_track", driver="GPKG")

now_points = [Point(x + FLOOR_GAP * (f - 1), y) for x, y, f in zip(last["x"], last["y"], last["floor"])]
gpd.GeoDataFrame(summary.reset_index().rename(columns={"index": "astronaut"}), geometry=now_points,
                 crs="EPSG:3857").to_file(MAP_OUT, layer="crew_now", driver="GPKG")

if len(routes) > 0:
    centre = rooms.set_index("room_key").geometry.representative_point()
    lines = routes.copy()
    lines["time_end"] = lines["time"] + pd.Timedelta(minutes=30)          # the route stays on the map for 30 min
    lines_geometry = [LineString([centre[r] for r in p.split(" -> ")]) for p in routes["route"]]
    gpd.GeoDataFrame(lines, geometry=lines_geometry, crs="EPSG:3857").to_file(MAP_OUT, layer="routes", driver="GPKG")
print("\nSaved:", CREW_LOG, ROUTES_OUT, STATUS_OUT, MAP_OUT)


# =====================================================================
# 6. FIGURE: dose rate of the rooms (top), personal dose sheltered (solid) vs. no warning (dashed)
# =====================================================================
fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
for room in CREW_ROOMS:
    axes[0].plot(rates.index, rates[room], label=room, lw=0.8)
axes[0].axhline(RATE_WARNING, color="grey", ls=":", label="warning level")
axes[0].set_yscale("log")
axes[0].set_ylabel("dose rate (mSv/h)")
axes[0].set_title("Dosimeters of the rooms, every 5 minutes (cosmic rays + the storm of 11 November 2025)")
axes[0].legend(fontsize=7, ncol=5)

for astronaut, g in crew.groupby("astronaut"):
    line, = axes[1].plot(g["time"], g["dose_msv"], label=f"{astronaut}")
    axes[1].plot(g["time"], g["dose_if_no_warning_msv"], ls="--", color=line.get_color())
if len(routes) > 0:                                   # the time in the shelter
    for ax in axes:
        ax.axvspan(sheltered["min"].min(), sheltered["max"].max(), color="tab:green", alpha=0.15, lw=0)
axes[1].set_ylabel("personal dose (mSv)")
axes[1].set_title("Personal dose of every astronaut: solid = went to the shelter, dashed = no warning "
                  "(green = in the shelter)")
axes[1].legend(fontsize=8, ncol=6)
fig.tight_layout()
fig.savefig(FIGURE, dpi=130)
plt.close(fig)
print("Figure:", FIGURE)
