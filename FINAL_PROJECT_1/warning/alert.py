# =====================================================================
# alert.py
# The warning for the crew. Reads the newest forecast of live/06_live.py and
# decides ONE thing:  ALL CLEAR / WATCH / PREPARE SHELTER / GO TO SHELTER.
# When the dose goes over the limit, the message is simply:
#     ALL ASTRONAUTS: GO TO THE STORM SHELTER
#
# Mission: 6 astronauts, 14 days.
# The storm shelter is THE safe place: it has many layers of shielding (HDPE, water,
# stowage bags) that lower the dose to almost nothing. (TEAM ASSUMPTION)
#
# It never trusts the ML model alone:
#   1. MEASURED level: the flux now on the NOAA scale (S1 = 10 pfu ... S5 = 100,000 pfu).
#      No model involved, so it cannot underestimate.
#   2. WORST CASE of the forecast: forecast + 1.65 x error of the model (from 04_train.py),
#      so 95% of the storms are not bigger than this.
#   3. FORECAST EXCEEDED: if the flux now is already above the forecast peak, the forecast
#      was wrong -> it is scaled up to the measurement.
#   4. DOSE in the cabin for the worst case (rays of shielding/02_rays.py), outside the shelter:
#      the worst crew room, because we do not know where every astronaut is.
#   5. MISSION DOSE: cosmic rays (GCR) for 14 days + the storm, compared with the NASA limits
#      (NASA-STD-3001 Vol. 1 Rev. B, Table 3 and V1 4031).
#
#   GO TO SHELTER    measured flux S3 or more, OR the worst-case storm dose in the cabin
#                    reaches 15% of the 250 mSv limit (team rule)
#   PREPARE SHELTER  the worst-case forecast reaches S3: get the shelter ready (~1 hour)
#   WATCH            a storm, but none of the above
#   ALL CLEAR        no storm
#
# Output: warning/data/alert.json, warning/data/alert_readable.json (plain words, for the app),
#         warning/data/alerts_log.csv,
#         warning/data/alert_map.gpkg (the alert on the floor plans, for ArcGIS / QGIS)
# Run:    python warning/alert.py      (after live/06_live.py has written a forecast)
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import json
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
from shapely import affinity

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_LOG = os.path.join(ROOT, "live", "data", "live_log.csv")
MODEL_ERRORS = os.path.join(ROOT, "forecast", "data", "processed", "results.csv")
RAYS_FILE = os.path.join(ROOT, "shielding", "data", "rays.csv")
FLOOR_PLANS = os.path.join(ROOT, "shielding", "cad", "orion_floor_plans.gpkg")
OUT_FOLDER = os.path.join(ROOT, "warning", "data")
ALERT_JSON = os.path.join(OUT_FOLDER, "alert.json")
ALERT_READABLE = os.path.join(OUT_FOLDER, "alert_readable.json")      # the same in plain words (for the app)
EARTH_MSV_PER_YEAR = 2.4     # natural radiation on Earth per year (UNSCEAR), to explain a dose
STORM_NAMES = {0: "below storm level", 1: "S1 (minor)", 2: "S2 (moderate)", 3: "S3 (strong)", 4: "S4 (severe)",
               5: "S5 (extreme)"}
ALERT_LOG = os.path.join(OUT_FOLDER, "alerts_log.csv")
ALERT_MAP = os.path.join(OUT_FOLDER, "alert_map.gpkg")
os.makedirs(OUT_FOLDER, exist_ok=True)

# --- the mission ---
CREW = ["CDR", "PLT", "MS1", "MS2", "MS3", "MS4"]      # 6 astronauts
MISSION_DAYS = 14
GCR_MSV_PER_DAY = 0.5        # cosmic rays inside the spacecraft, every day (TEAM ASSUMPTION, deep space)
SHELTER = "shelter"          # the safe place
SHELTER_LEFT = 0.05          # part of the storm dose that gets into the shelter (TEAM ASSUMPTION: many layers)

# --- NASA-STD-3001 Vol. 1 Rev. B ---
LIMIT_MSV = 250              # 30-day limit of the blood-forming organs (Table 3), and one storm (V1 4031)
QUALITY = 1.5                # RBE of protons > 2 MeV (Table 4)
BODY_AL = 6.5                # g/cm2: depth of the blood-forming organs in the body

# --- the rules ---
WORST_CASE_Z = 1.65          # forecast + 1.65 x RMSE: worse than 95% of the storms
SHELTER_RULE_PCT = 15        # team rule: worst-case storm dose in the cabin >= 15% of the limit -> shelter
SHELTER_IF_MEASURED_S = 3    # measured S3 (1,000 pfu) or more -> shelter, whatever the model says
PREPARE_IF_WORST_S = 3       # worst-case forecast S3 or more -> prepare the shelter (~1 hour)
CREW_ROOMS = ["cockpit", "seats", "galley", "exercise", "hygiene", "sleep"]     # outside the shelter
ROOM_LEVELS = [(5, "SAFE"), (15, "LOW"), (45, "MEDIUM"), (100000, "HIGH")]     # % of the limit, for the map

BANDS = {"pred_log_fluence_10_30": (10, 30), "pred_log_fluence_30_50": (30, 50),
         "pred_log_fluence_50_100": (50, 100), "pred_log_fluence_100": (100, 500)}
NIST = pd.DataFrame({
    "energy": [1, 2, 5, 10, 20, 30, 50, 70, 100, 150, 200, 300, 500, 1000],
    "range_al": [0.0040, 0.0123, 0.0563, 0.170, 0.580, 1.21, 2.97, 5.40, 9.98, 19.6, 31.4, 59.5, 125, 310],
    "stopping_water": [260.8, 162.4, 79.11, 45.67, 26.07, 18.76, 12.45, 9.559, 7.289, 5.445, 4.492, 3.52, 2.743, 2.211],
})


# =====================================================================
# 2. THE NEWEST FORECAST
# =====================================================================
log = pd.read_csv(LIVE_LOG)
now = log.iloc[-1]
p10_now = float(now["p10_now"])
has_forecast = not pd.isna(now["pred_log_peak"])


# =====================================================================
# 3. LEVEL FROM THE MEASUREMENT (no model)
# =====================================================================
s_measured = int(np.clip(np.floor(np.log10(max(p10_now, 1e-3))), 0, 5))     # 10 pfu = S1, 100 = S2 ...


# =====================================================================
# 4. WORST CASE OF THE FORECAST, AND "FORECAST EXCEEDED"
# =====================================================================
alert = {"time": str(now["time"]), "status": str(now["status"]), "flux_now_pfu": round(p10_now, 1),
         "s_measured": s_measured, "forecast_exceeded": False}

if has_forecast:
    hours = float(now["hours_since_onset"])
    errors = pd.read_csv(MODEL_ERRORS)
    rmse = {}
    for target in ["log_peak"] + [c.replace("pred_", "") for c in BANDS]:
        e = errors[errors["target"] == target].sort_values("hours_since_onset")
        rmse[target] = float(np.interp(min(hours, 6), e["hours_since_onset"], e["RMSE"]))

    log_peak = float(now["pred_log_peak"])
    log_peak_worst = log_peak + WORST_CASE_Z * rmse["log_peak"]
    fluence_worst = np.array([float(now[c]) + WORST_CASE_Z * rmse[c.replace("pred_", "")] for c in BANDS])

    # the flux now is already above the forecast peak: the forecast was too low, scale it up
    if np.log10(max(p10_now, 1e-3)) > log_peak:
        alert["forecast_exceeded"] = True
        shift = np.log10(p10_now) - log_peak
        log_peak_worst = max(log_peak_worst, np.log10(p10_now) + WORST_CASE_Z * rmse["log_peak"])
        fluence_worst = fluence_worst + shift

    alert.update({"forecast_peak_pfu": round(10 ** log_peak, 1),
                  "worst_case_peak_pfu": round(10 ** log_peak_worst, 1),
                  "s_worst_case": int(np.clip(np.floor(log_peak_worst), 0, 5)),
                  "prob_peak_passed": None if pd.isna(now["prob_peak_passed"]) else round(float(now["prob_peak_passed"]), 2),
                  "prob_peak_within_6h": None if pd.isna(now["prob_peak_within_6h"]) else round(float(now["prob_peak_within_6h"]), 2)})


# =====================================================================
# 5. WORST-CASE STORM DOSE IN EVERY ROOM (rays of shielding/02_rays.py)
#    a proton gets through the walls if its range is longer than the shielding;
#    what is left of its range gives the energy it brings to the body, and that energy the dose
# =====================================================================
room_dose = {}
if has_forecast:
    energies, protons = [], []
    for log_f, (low, high) in zip(fluence_worst, BANDS.values()):
        energies.append(np.logspace(np.log10(low), np.log10(high), 200))
        protons.append(np.full(200, 4 * np.pi * 10 ** log_f / 200))
    energies = np.concatenate(energies)
    protons = np.concatenate(protons)
    log_E, log_R, log_S = (np.log(NIST[c].values) for c in ["energy", "range_al", "stopping_water"])
    proton_range = np.exp(np.interp(np.log(energies), log_E, log_R))
    thickness = np.concatenate([np.linspace(0, 50, 501), np.linspace(50.5, 600, 1100)])
    dose_table = []
    for t in thickness:
        left = proton_range - t
        through = left > NIST["range_al"].iloc[0]
        energy_after = np.exp(np.interp(np.log(left[through]), log_R, log_E))
        stopping = np.exp(np.interp(np.log(energy_after), log_E, log_S))
        dose_table.append(1.602e-10 * (protons[through] * stopping).sum() * 1000 * QUALITY)
    dose_table = np.array(dose_table)

    rays = pd.read_csv(RAYS_FILE)
    rays["dose_msv"] = np.interp(rays["shielding_g_cm2"] + BODY_AL, thickness, dose_table)
    room_dose = rays.groupby("room")["dose_msv"].mean().to_dict()

cabin = {r: d for r, d in room_dose.items() if r in CREW_ROOMS}
storm_cabin = max(cabin.values()) if cabin else 0.0              # the worst crew room: we do not know where everyone is
storm_shelter = storm_cabin * SHELTER_LEFT


# =====================================================================
# 6. MISSION DOSE OF EVERY ASTRONAUT: cosmic rays for 14 days + the storm
#    (the same for all 6, because the cabin is one space and nobody is tracked one by one)
# =====================================================================
gcr = GCR_MSV_PER_DAY * MISSION_DAYS
mission_if_cabin = gcr + storm_cabin
mission_if_shelter = gcr + storm_shelter
alert["mission"] = {"crew": CREW, "days": MISSION_DAYS, "gcr_msv": round(gcr, 1),
                    "storm_worst_case_cabin_msv": round(storm_cabin, 1),
                    "storm_in_shelter_msv": round(storm_shelter, 1),
                    "total_if_they_stay_in_the_cabin_msv": round(mission_if_cabin, 1),
                    "total_if_they_go_to_the_shelter_msv": round(mission_if_shelter, 1),
                    "pct_limit_cabin": round(100 * mission_if_cabin / LIMIT_MSV, 1),
                    "pct_limit_shelter": round(100 * mission_if_shelter / LIMIT_MSV, 1)}


# =====================================================================
# 7. DECISION: the most severe of measurement, worst case and dose
# =====================================================================
storm_pct = 100 * storm_cabin / LIMIT_MSV
reasons = []
if s_measured >= SHELTER_IF_MEASURED_S:
    reasons.append(f"measured flux is S{s_measured}")
if storm_pct >= SHELTER_RULE_PCT:
    reasons.append(f"worst-case storm dose in the cabin = {storm_cabin:.0f} mSv = {storm_pct:.0f}% of the limit")
if alert["forecast_exceeded"]:
    reasons.append("the flux is already above the forecast")

if now["status"] == "ALL CLEAR" and s_measured == 0:
    level = "ALL CLEAR"
elif s_measured >= SHELTER_IF_MEASURED_S or storm_pct >= SHELTER_RULE_PCT:
    level = "GO TO SHELTER"
elif has_forecast and alert["s_worst_case"] >= PREPARE_IF_WORST_S:
    level = "PREPARE SHELTER"
    reasons.append(f"worst-case forecast reaches S{alert['s_worst_case']}: get the shelter ready (~1 hour)")
else:
    level = "WATCH"

MESSAGES = {"ALL CLEAR": "No storm. Normal work.",
            "WATCH": "A storm has started. Keep working, follow the next alerts.",
            "PREPARE SHELTER": "Get the storm shelter ready now. Be ready to go in.",
            "GO TO SHELTER": f"ALL {len(CREW)} ASTRONAUTS: GO TO THE STORM SHELTER NOW."}
alert.update({"level": level, "message": MESSAGES[level], "reasons": reasons,
              "storm_worst_case_pct_limit": round(storm_pct, 1),
              "rooms_worst_case_msv": {r: round(d, 1) for r, d in sorted(cabin.items(), key=lambda kv: kv[1])}})

timing = "no forecast yet (first 30 minutes)" if not has_forecast else "peak time not reliable yet"
if has_forecast and alert["prob_peak_within_6h"] is not None:
    timing = f"peak within 6 h: {alert['prob_peak_within_6h']:.0%}"
if has_forecast and alert["prob_peak_passed"] is not None:
    timing += f" | peak already passed: {alert['prob_peak_passed']:.0%}"
alert["timing"] = timing


# =====================================================================
# 8. SHOW, SAVE
# =====================================================================
line = "=" * 64
print(line)
print(f"  {level}   ({alert['time']} UTC)")
print(f"  {MESSAGES[level]}")
print(line)
print(f"  flux now: {p10_now:.1f} pfu (S{s_measured})")
if has_forecast:
    print(f"  forecast peak: {alert['forecast_peak_pfu']:,.0f} pfu | worst case: "
          f"{alert['worst_case_peak_pfu']:,.0f} pfu (S{alert['s_worst_case']})")
    print(f"  worst-case storm dose in the cabin: {storm_cabin:.1f} mSv ({storm_pct:.0f}% of the limit)")
for r in reasons:
    print("  reason:", r)
print(f"  mission ({len(CREW)} astronauts, {MISSION_DAYS} days): cosmic rays {gcr:.1f} mSv + storm")
print(f"     stay in the cabin:  {mission_if_cabin:.1f} mSv = {alert['mission']['pct_limit_cabin']:.0f}% of the {LIMIT_MSV} mSv limit")
print(f"     go to the shelter:  {mission_if_shelter:.1f} mSv = {alert['mission']['pct_limit_shelter']:.0f}%")
print("  " + timing)
print(line)

with open(ALERT_JSON, "w") as f:
    json.dump(alert, f, indent=2)
row = {"time": alert["time"], "level": level, "flux_now_pfu": alert["flux_now_pfu"], "s_measured": s_measured,
       "forecast_peak_pfu": alert.get("forecast_peak_pfu"), "worst_case_peak_pfu": alert.get("worst_case_peak_pfu"),
       "storm_worst_case_cabin_msv": round(storm_cabin, 2), "mission_if_cabin_msv": round(mission_if_cabin, 2),
       "forecast_exceeded": alert["forecast_exceeded"]}
pd.DataFrame([row]).to_csv(ALERT_LOG, mode="a", header=not os.path.exists(ALERT_LOG), index=False)

# --- in plain words, for the crew screen ---
COLOURS = {"ALL CLEAR": "green", "WATCH": "yellow", "PREPARE SHELTER": "yellow", "GO TO SHELTER": "red"}
HEADLINES = {"ALL CLEAR": "All clear: the Sun is quiet",
             "WATCH": "A solar storm has started: keep working",
             "PREPARE SHELTER": "Get the storm shelter ready",
             "GO TO SHELTER": "GO TO THE STORM SHELTER NOW"}
TO_DO = {"ALL CLEAR": "Normal work.",
         "WATCH": "Keep working near the shelter. We check again every 5 minutes.",
         "PREPARE SHELTER": "Build the shelter now (it takes about 1 hour), so it is ready if the storm grows.",
         "GO TO SHELTER": f"All {len(CREW)} astronauts go to the storm shelter and stay there until the all clear."}
why = [f"Protons outside the spacecraft now: {STORM_NAMES[s_measured]}."]
if has_forecast:
    why.append(f"Forecast: the storm will reach {STORM_NAMES[alert['s_worst_case']]} in the worst case "
               f"(95% of storms are smaller than this).")
    if alert["forecast_exceeded"]:
        why.append("The storm is already bigger than the forecast, so we use the measurement instead.")
    if storm_cabin >= 0.05:
        why.append(f"Worst case without the shelter: {storm_cabin:.0f} mSv, {storm_pct:.0f}% of your monthly "
                   f"allowance, like {storm_cabin / EARTH_MSV_PER_YEAR:.0f} years of natural radiation on Earth. "
                   f"In the shelter: {storm_shelter:.1f} mSv.")
    if alert["prob_peak_passed"] is not None:
        why.append(f"Chance that the worst is already over: {alert['prob_peak_passed']:.0%}.")
    elif alert["prob_peak_within_6h"] is not None:
        why.append(f"Chance that the worst comes within 6 hours: {alert['prob_peak_within_6h']:.0%}.")
    else:
        why.append("It is too early to say when the worst comes.")
elif now["status"] == "STORM STARTED":
    why.append("The first forecast comes 30 minutes after the start of the storm.")
why.append(f"Your mission ({MISSION_DAYS} days): cosmic rays alone give about {gcr:.0f} mSv "
           f"({100 * gcr / LIMIT_MSV:.0f}% of the monthly allowance).")
readable = {"module": "alert", "updated": alert["time"], "level": COLOURS[level], "headline": HEADLINES[level],
            "what_to_do": TO_DO[level], "why": why}
with open(ALERT_READABLE, "w") as f:
    json.dump(readable, f, indent=2)
print("Saved:", ALERT_JSON, ALERT_READABLE)


# =====================================================================
# 9. THE ALERT ON THE FLOOR PLANS (GIS): crew floors 2, 3, 4 side by side,
#    rooms coloured by the worst-case storm dose, the shelter = the safe place
# =====================================================================
if os.path.exists(ALERT_MAP):
    try:
        os.remove(ALERT_MAP)
    except PermissionError:
        ALERT_MAP = ALERT_MAP.replace(".gpkg", pd.Timestamp.now().strftime("_%Y%m%d_%H%M%S.gpkg"))
        print("alert_map.gpkg is open in another program, saving a new copy:", ALERT_MAP)

plans = pd.concat([gpd.read_file(FLOOR_PLANS, layer=layer) for layer in pyogrio.list_layers(FLOOR_PLANS)[:, 0]])
plans = gpd.GeoDataFrame(plans, crs="EPSG:3857")
plans = plans[plans["floor"] >= 2].copy()
plans["geometry"] = [affinity.translate(g, xoff=6.0 * (f - 2)) for g, f in zip(plans.geometry, plans["floor"])]
rooms_map = plans[plans["type"] == "room"].copy()
rooms_map["dose_worst_msv"] = rooms_map["room_key"].map(room_dose)
rooms_map.loc[rooms_map["room_key"] == SHELTER, "dose_worst_msv"] = storm_shelter
rooms_map["pct_limit"] = 100 * rooms_map["dose_worst_msv"] / LIMIT_MSV
rooms_map["room_level"] = "NO FORECAST"
for top, name in reversed(ROOM_LEVELS):
    rooms_map.loc[rooms_map["pct_limit"] < top, "room_level"] = name
rooms_map.loc[rooms_map["room_key"] == SHELTER, "room_level"] = "SAFE"
rooms_map["go_here"] = (rooms_map["room_key"] == SHELTER) & (level in ("GO TO SHELTER", "PREPARE SHELTER"))
rooms_map["alert_level"] = level
rooms_map["alert_time"] = alert["time"]
rooms_map.to_file(ALERT_MAP, layer="alert_rooms", driver="GPKG")
plans[plans["type"] == "hull"].to_file(ALERT_MAP, layer="alert_hull", driver="GPKG")
print("Alert map:", ALERT_MAP)
