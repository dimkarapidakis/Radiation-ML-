# =====================================================================
# simulate_room_sensors.py   (DEMO DATA, until the real sensors exist)
# Makes the files that the spacecraft would write:
#
#   warning/data/room_sensors_log.csv   time, room, dose_rate_msv_h   every 5 min (one dosimeter per room)
#   warning/data/crew_schedule.csv      time, astronaut, room, floor, x, y   every hour (crew badges)
#
# The mission: 6 astronauts, 14 days, 5-19 November 2025. The real storm of 11 November 2025
# (GLE 77, hard spectrum) happens on mission day 7.
#
# OUTSIDE -> INSIDE (the dosimeters):
#   outside: the real proton flux measured by GOES-19 every 5 minutes, all 14 days
#   inside:  dose rate of a room = flux of every energy band x what gets through the walls of that room
#            (the 400 rays of shielding/02_rays.py) x 3600 s
#            + cosmic rays (GCR), the same in every room (TEAM ASSUMPTION: 0.5 mSv/day)
#            the storm shelter = THE safe place, many layers: 5% of the storm gets in (TEAM ASSUMPTION)
#            + 5% noise, like a real dosimeter
#
# WHERE EVERYONE IS (the locations): a daily plan for every astronaut
#   23:00-07:00  sleep (sleeping area, floor 4)
#   12:00, 19:00 meal (galley, floor 3)
#   1 hour       exercise (exercise area, floor 3), at a different hour for every astronaut
#   other hours  work: a random work room (any crew floor), new room every 2 hours
#   every time the room changes: a random point inside the room
#
# Run:  python warning/simulate_room_sensors.py
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import os
import sqlite3

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely.geometry import Point

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOES_FILE = os.path.join(ROOT, "forecast", "data", "processed", "GOESR", "goesr_goes19_2025-04-01_2026-12-01.csv")
RAYS_FILE = os.path.join(ROOT, "shielding", "data", "rays.csv")
DB_FILE = os.path.join(ROOT, "database", "nasaspacechallenge.db")      # the team's database: who the astronauts are
FLOOR_PLANS = os.path.join(ROOT, "shielding", "cad", "orion_floor_plans.gpkg")
OUT_FOLDER = os.path.join(ROOT, "warning", "data")
SENSORS_LOG = os.path.join(OUT_FOLDER, "room_sensors_log.csv")
SCHEDULE_FILE = os.path.join(OUT_FOLDER, "crew_schedule.csv")
os.makedirs(OUT_FOLDER, exist_ok=True)

# --- the mission ---
START = pd.Timestamp("2025-11-05 00:00")      # the storm of 11 November 2025 = mission day 7
MISSION_DAYS = 14
CREW_SIZE = 6
names = []                                                      # the astronauts from the team's database
if os.path.exists(DB_FILE):
    db = sqlite3.connect(DB_FILE)
    names = [row[0] for row in db.execute("SELECT name FROM astronauts ORDER BY id")]
    db.close()
CREW = names[:CREW_SIZE] + [f"Astronaut {i}" for i in range(len(names) + 1, CREW_SIZE + 1)]   # not in the database yet
GCR_MSV_PER_DAY = 0.5                          # cosmic rays in every room (TEAM ASSUMPTION)
SHELTER = "shelter"
SHELTER_LEFT = 0.05                            # the shelter has many layers: 5% of the storm gets in (TEAM ASSUMPTION)
NOISE = 0.05                                   # 5% noise of a dosimeter
SEED = 7

# --- the daily plan ---
SLEEP_ROOM = "sleep"
MEAL_ROOM = "galley"
MEAL_HOURS = [12, 19]
EXERCISE_ROOM = "exercise"
EXERCISE_HOURS = [8, 9, 10, 14, 15, 16]        # 1st astronaut at 8:00, 2nd at 9:00 ...
WORK_ROOMS = ["cockpit", "seats", "leb", "hygiene", "exercise", "galley"]
WORK_BLOCK_HOURS = 2

# --- physics (same as shielding/03_dose.py) ---
BODY_AL = 6.5
QUALITY = 1.5
BANDS = {"10-30": (10, 30), "30-50": (30, 50), "50-100": (50, 100), ">100": (100, 500)}
POINTS_PER_BAND = 200
NIST = pd.DataFrame({
    "energy": [1, 2, 5, 10, 20, 30, 50, 70, 100, 150, 200, 300, 500, 1000],
    "range_al": [0.0040, 0.0123, 0.0563, 0.170, 0.580, 1.21, 2.97, 5.40, 9.98, 19.6, 31.4, 59.5, 125, 310],
    "stopping_water": [260.8, 162.4, 79.11, 45.67, 26.07, 18.76, 12.45, 9.559, 7.289, 5.445, 4.492, 3.52, 2.743, 2.211],
})
rng = np.random.default_rng(SEED)
END = START + pd.Timedelta(days=MISSION_DAYS) - pd.Timedelta(minutes=5)


# =====================================================================
# 2. OUTSIDE: the GOES flux in 4 energy bands (protons / cm2 / s / sr), every 5 minutes
#    GOES gives >10, >30, >50, >100 MeV; a band = difference of two of them
# =====================================================================
goes = pd.read_csv(GOES_FILE, parse_dates=["time_tag"]).set_index("time_tag").loc[START:END]
goes = goes.interpolate(limit_direction="both")
flux = pd.DataFrame({
    "10-30": goes["flux_gt10MeV"] - goes["flux_gt30MeV"],
    "30-50": goes["flux_gt30MeV"] - goes["flux_gt50MeV"],
    "50-100": goes["flux_gt50MeV"] - goes["flux_gt100MeV"],
    ">100": goes["flux_gt100MeV"],
}).clip(lower=0)
print(f"GOES-19 {START:%d %b} -> {END:%d %b %Y}: {len(flux)} times, peak >10 MeV = "
      f"{goes['flux_gt10MeV'].max():,.0f} pfu on {goes['flux_gt10MeV'].idxmax():%d %b %H:%M}")


# =====================================================================
# 3. INSIDE: what gets through the walls of every room, per band
#    coefficient[room, band] = mSv in the room for 1 proton/cm2/sr of that band
# =====================================================================
log_E = np.log(NIST["energy"].values)
log_R = np.log(NIST["range_al"].values)
log_S = np.log(NIST["stopping_water"].values)
thickness = np.concatenate([np.linspace(0, 50, 501), np.linspace(50.5, 600, 1100)])   # g/cm2
rays = pd.read_csv(RAYS_FILE)

coefficient = pd.DataFrame(index=sorted(rays["room"].unique()), columns=list(BANDS), dtype=float)
for band, (low, high) in BANDS.items():
    energies = np.logspace(np.log10(low), np.log10(high), POINTS_PER_BAND)
    protons = np.full(POINTS_PER_BAND, 4 * np.pi / POINTS_PER_BAND)                      # 1 proton/cm2/sr
    proton_range = np.exp(np.interp(np.log(energies), log_E, log_R))
    table = []
    for t in thickness:
        left = proton_range - t
        through = left > NIST["range_al"].iloc[0]
        energy_after = np.exp(np.interp(np.log(left[through]), log_R, log_E))
        stopping = np.exp(np.interp(np.log(energy_after), log_E, log_S))
        table.append(1.602e-10 * (protons[through] * stopping).sum() * 1000 * QUALITY)    # mSv
    rays["dose"] = np.interp(rays["shielding_g_cm2"] + BODY_AL, thickness, table)
    coefficient[band] = rays.groupby("room")["dose"].mean()

# dose rate (mSv/h) = sum over bands of flux (per s) x coefficient x 3600 s  + cosmic rays
rate = pd.DataFrame(flux.values @ coefficient.T.values * 3600, index=flux.index, columns=coefficient.index)
rate[SHELTER] = rate[SHELTER] * SHELTER_LEFT          # the safe place: only 5% of the storm gets in
rate = rate + GCR_MSV_PER_DAY / 24
rate = rate * (1 + NOISE * rng.standard_normal(rate.shape))
rate = rate.clip(lower=0)


# =====================================================================
# 4. WHERE EVERYONE IS: the daily plan, every hour, and a random point inside the room
# =====================================================================
plans = pd.concat([gpd.read_file(FLOOR_PLANS, layer=layer) for layer in pyogrio.list_layers(FLOOR_PLANS)[:, 0]])
rooms = plans[plans["type"] == "room"].set_index("room_key")

schedule = []
for k, astronaut in enumerate(CREW):
    room_before = None
    point = None
    work_room = rng.choice(WORK_ROOMS)
    for hour_start in pd.date_range(START, END, freq="1h"):
        h = hour_start.hour
        if h >= 23 or h < 7:
            room = SLEEP_ROOM
        elif h in MEAL_HOURS:
            room = MEAL_ROOM
        elif h == EXERCISE_HOURS[k]:
            room = EXERCISE_ROOM
        else:
            if (h - 7) % WORK_BLOCK_HOURS == 0:            # a new work block: maybe a new room
                work_room = rng.choice(WORK_ROOMS)
            room = work_room
        if room != room_before:                            # moved: a random free spot inside the new room
            shape = rooms.loc[room, "geometry"]
            x0, y0, x1, y1 = shape.bounds
            point = Point(rng.uniform(x0, x1), rng.uniform(y0, y1))
            while not shape.contains(point):
                point = Point(rng.uniform(x0, x1), rng.uniform(y0, y1))
        room_before = room
        schedule.append({"time": hour_start, "astronaut": astronaut, "room": room,
                         "floor": int(rooms.loc[room, "floor"]), "x": round(point.x, 3), "y": round(point.y, 3)})
schedule = pd.DataFrame(schedule)


# =====================================================================
# 5. SAVE
# =====================================================================
log = rate.round(5).rename_axis("time").reset_index().melt(id_vars="time", var_name="room",
                                                            value_name="dose_rate_msv_h")
log.sort_values(["time", "room"]).to_csv(SENSORS_LOG, index=False)
schedule.to_csv(SCHEDULE_FILE, index=False)

print(f"\nDose of the 14 days if you stay all the time in one room (mSv, cosmic rays {GCR_MSV_PER_DAY * MISSION_DAYS:.0f} included):")
print((rate.sum() * 5 / 60).sort_values().round(1).to_string())
print("\nHours spent in every room (14 days):")
print(schedule.pivot_table(index="astronaut", columns="room", values="time", aggfunc="count").fillna(0).astype(int).to_string())
print("\nSaved:", SENSORS_LOG, SCHEDULE_FILE)
