# =====================================================================
# biomarkers.py
# Health monitoring of the crew: is any biomarker of any astronaut unusual FOR THAT ASTRONAUT?
#
# WHERE THE DATA COME FROM
#   the team's database (database/nasaspacechallenge.db, branch "database"): the astronauts and their
#   measurements: every day heart rate, body temperature, blood pressure (systolic, diastolic), sleep;
#   blood tests (lymphocytes, white blood cells) some days.
#   His baseline = the days between baseline_start and baseline_end of the table "astronauts";
#   flight day 1 = the day after baseline_end.
#   An astronaut is read from the database when every daily biomarker has at least 10 days there.
#   Until then his values are SIMULATED (column "source"). Nothing simulated is written into the database.
#
# THE SIMULATION
#   (only for astronauts that are not in the database yet)
#   6 astronauts, 7 days before the flight (their baseline) + 14 days in flight.
#   Two problems are put in on purpose to test the detection: the 5th astronaut a clear fever
#   (flight days 9-11), the 3rd a mild start of an illness (days 5-7, see anomaly_detection.py).
#   Radiation does NOT change the biomarkers: at the doses of the mission no measurable signal is expected.
#
# Statistics, no machine learning:
#   z = (value - mean before flight) / standard deviation before flight     (per astronaut)
#   ALERT when |z| >= 3 in 2 measurements in a row.
#   Why 2 in a row: 6 astronauts x 8 biomarkers x 14 days = hundreds of checks; with |z| >= 3 alone
#   many false alarms would come just by chance.
#   PRIORITY for the medical team: alert + high radiation dose (from organ_dose.py).
#
# Output:  health/data/biomarkers.csv        (all measurements, with their source)
#          health/data/health_alerts.csv     (every alert)
#          health/data/health_status.json    (for the app)
#          health/Figures/biomarkers.png
#
# Run:  python health/biomarkers.py      (after health/organ_dose.py)
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import json
import os
import sqlite3

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(ROOT, "database", "nasaspacechallenge.db")     # the team's database
ORGAN_DOSES = os.path.join(ROOT, "health", "data", "organ_doses.json")
OUT_FOLDER = os.path.join(ROOT, "health", "data")
FIGURE = os.path.join(ROOT, "health", "Figures", "biomarkers.png")
os.makedirs(OUT_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(FIGURE), exist_ok=True)

CREW_SIZE = 6
BASELINE_DAYS = 7            # days before the flight (simulation)
MISSION_DAYS = 14            # flight days (simulation)
MIN_DB_DAYS = 10             # days in the database to use an astronaut's real values
BLOOD_EVERY = 3              # days between blood tests
Z_ALERT = 3.0
IN_A_ROW = 2
DOSE_PRIORITY_PCT = 15       # blood-forming organs above 15% of the NASA limit -> priority (team rule)
SEED = 3

# biomarker (name = "slug" of the database): (unit, typical value, spread between people, day-to-day spread,
#                                             blood test?)
BIOMARKERS = {
    "heart_rate":          ("bpm",          60,   6,    2.5,  False),
    "body_temperature":    ("°C",           36.6, 0.15, 0.12, False),
    "systolic_bp":         ("mmHg",         118,  8,    3.0,  False),
    "diastolic_bp":        ("mmHg",         76,   6,    2.5,  False),
    "sleep_duration":      ("hours",        7.0,  0.4,  0.5,  False),
    "lymphocyte_count":    ("10^9/L",       2.0,  0.4,  0.15, True),
    "wbc_count":           ("10^9/L",       6.5,  1.0,  0.4,  True),
}
DAILY = [name for name, b in BIOMARKERS.items() if not b[4]]
rng = np.random.default_rng(SEED)


# =====================================================================
# 2. THE CREW AND THEIR MEASUREMENTS FROM THE DATABASE
# =====================================================================
names, measured = [], pd.DataFrame(columns=["astronaut", "biomarker", "value", "measured_at"])
flight_start = {}                                               # astronaut -> his flight day 1
if os.path.exists(DB_FILE):
    db = sqlite3.connect(DB_FILE)
    for name, baseline_end in db.execute("SELECT name, baseline_end FROM astronauts ORDER BY id"):
        names.append(name)
        if baseline_end:
            flight_start[name] = pd.Timestamp(baseline_end).normalize() + pd.Timedelta(days=1)
    measured = pd.read_sql("SELECT a.name AS astronaut, i.slug AS biomarker, m.value, m.measured_at "
                           "FROM measurements m JOIN astronauts a ON a.id = m.astronaut_id "
                           "JOIN indicators i ON i.id = m.indicator_id", db, parse_dates=["measured_at"])
    db.close()
CREW = names[:CREW_SIZE] + [f"Astronaut {i}" for i in range(len(names) + 1, CREW_SIZE + 1)]   # not in the database yet

# the problems put in on purpose (simulation): astronaut, first and last flight day, change (in day-to-day spreads)
#   5th astronaut: a clear fever (every biomarker far away)            -> found by the z-score
#   3rd astronaut: a mild start of an illness / exhaustion: every biomarker only ~2 spreads away (below 3),
#                  but ALL together the same days                     -> found only by anomaly_detection.py
INJECTED = [{"astronaut": CREW[4], "from_day": 9, "to_day": 11,
             "change": {"body_temperature": 8, "heart_rate": 6, "systolic_bp": 3, "wbc_count": 5,
                        "sleep_duration": -3}},
            {"astronaut": CREW[2], "from_day": 5, "to_day": 7,
             "change": {"body_temperature": 2, "heart_rate": 2, "systolic_bp": 2, "diastolic_bp": 2,
                        "sleep_duration": -2}}]


# =====================================================================
# 3. ONE VALUE PER ASTRONAUT, BIOMARKER AND DAY
#    real (database) when the astronaut has enough days, otherwise simulated:
#    every astronaut has their own normal value; every day adds noise;
#    in flight: a small slow change of microgravity (heart rate -3%, sleep -0.5 h)
# =====================================================================
rows = []
days = list(range(-BASELINE_DAYS, 0)) + list(range(1, MISSION_DAYS + 1))      # negative = before the flight
for astronaut in CREW:
    mine = measured[(measured["astronaut"] == astronaut) & measured["biomarker"].isin(list(BIOMARKERS))].copy()
    mine["date"] = pd.to_datetime(mine["measured_at"]).dt.normalize()     # works also when there is nothing
    per_day = mine.groupby(["biomarker", "date"])["value"].mean().reset_index()     # several check-ins a day -> mean
    from_database = astronaut in flight_start and all((per_day["biomarker"] == b).sum() >= MIN_DB_DAYS for b in DAILY)

    if from_database:          # day of the flight: 1 = the day after his baseline, negative = baseline
        for _, m in per_day.iterrows():
            day = (m["date"] - flight_start[astronaut]).days
            rows.append({"astronaut": astronaut, "day": day + 1 if day >= 0 else day, "biomarker": m["biomarker"],
                         "unit": BIOMARKERS[m["biomarker"]][0], "value": round(m["value"], 2), "source": "database"})

    for name, (unit, typical, between, daily, blood) in BIOMARKERS.items():
        if from_database:
            continue
        own = typical + between * rng.standard_normal()                       # this astronaut's normal value
        for day in days:
            if blood and (day % BLOOD_EVERY != 0) and day not in (-7, -4, -1):
                continue
            value = own + daily * rng.standard_normal()
            if day > 0 and name == "heart_rate":
                value = value * (1 - 0.03 * day / MISSION_DAYS)
            if day > 0 and name == "sleep_duration":
                value = value - 0.5 * day / MISSION_DAYS
            for problem in INJECTED:
                if (astronaut == problem["astronaut"] and problem["from_day"] <= day <= problem["to_day"]
                        and name in problem["change"]):
                    value = value + problem["change"][name] * daily
            rows.append({"astronaut": astronaut, "day": day, "biomarker": name, "unit": unit,
                         "value": round(value, 2), "source": "simulated"})
data = pd.DataFrame(rows)
data["phase"] = np.where(data["day"] < 0, "baseline", "flight")
print("Crew:", ", ".join(f"{a} ({'database' if (data[(data['astronaut'] == a) & data['biomarker'].isin(DAILY)]['source'] == 'database').any() else 'simulated'})" for a in CREW))


# =====================================================================
# 4. Z-SCORE AGAINST THE ASTRONAUT'S OWN BASELINE
# =====================================================================
base = (data[data["phase"] == "baseline"].groupby(["astronaut", "biomarker"])["value"]
        .agg(["mean", "std"]).rename(columns={"mean": "base_mean", "std": "base_std"}))
data = data.join(base, on=["astronaut", "biomarker"])
data["z"] = (data["value"] - data["base_mean"]) / data["base_std"]
data.round({"z": 2, "base_mean": 2, "base_std": 3}).to_csv(os.path.join(OUT_FOLDER, "biomarkers.csv"), index=False)


# =====================================================================
# 5. ALERTS: |z| >= 3 in 2 measurements in a row (in flight)
# =====================================================================
flight = data[data["phase"] == "flight"].sort_values(["astronaut", "biomarker", "day"]).copy()
flight["unusual"] = flight["z"].abs() >= Z_ALERT
flight["in_a_row"] = flight.groupby(["astronaut", "biomarker"])["unusual"].transform(
    lambda u: u.astype(int).rolling(IN_A_ROW, min_periods=1).sum())
alerts = flight[flight["in_a_row"] >= IN_A_ROW][["astronaut", "day", "biomarker", "value", "unit", "base_mean", "z"]]

# radiation dose of the crew (organ_dose.py): the same for everyone, in the cabin and in the shelter
bfo_pct = None
if os.path.exists(ORGAN_DOSES):
    with open(ORGAN_DOSES) as f:
        organ = json.load(f)
    bfo = [o for o in organ["organs"] if o["organ"] == "Blood-forming organs"][0]
    bfo_pct = bfo["pct_limit_shelter"]                 # the crew went to the shelter during the storm
alerts["priority"] = "PRIORITY (unusual + high dose)" if (bfo_pct is not None and bfo_pct >= DOSE_PRIORITY_PCT) else "medical team"
alerts.round({"z": 1, "base_mean": 2}).to_csv(os.path.join(OUT_FOLDER, "health_alerts.csv"), index=False)

# how many single |z| >= 3 come just by chance? The baseline has only 5-7 values, so its standard
# deviation is uncertain: a new value follows a Student t distribution (n - 1 degrees of freedom),
# not the normal one -> P(|z| >= 3) is ~3%, not 0.27%
checks = len(flight)
n_base = data[data["phase"] == "baseline"].groupby(["astronaut", "biomarker"]).size().rename("n_base")
flight = flight.join(n_base, on=["astronaut", "biomarker"])
flight["p_by_chance"] = 2 * stats.t.sf(Z_ALERT / np.sqrt(1 + 1 / flight["n_base"]), flight["n_base"] - 1)
expected_by_chance = flight["p_by_chance"].sum()
expected_normal = checks * 2 * stats.norm.sf(Z_ALERT)


# =====================================================================
# 6. PRINT AND THE STATUS FOR THE APP
# =====================================================================
print("Values: database where there are enough days, otherwise SIMULATED (column source)")
FLIGHT_DAYS = sorted(data.loc[data["day"] > 0, "day"].unique())
print(f"{len(CREW)} astronauts, {len(BIOMARKERS)} biomarkers, {len(FLIGHT_DAYS)} flight days: {checks} checks")
print(f"single values with |z| >= {Z_ALERT:.0f}: {int(flight['unusual'].sum())}  "
      f"(expected just by chance: ~{expected_by_chance:.0f} with a 5-7 day baseline, Student t; "
      f"~{expected_normal:.1f} if the baseline were perfectly known)")
print(f"ALERTS ({IN_A_ROW} in a row): {len(alerts)}")
if len(alerts) > 0:
    print(alerts.round({"z": 1}).to_string(index=False))
if bfo_pct is not None:
    print(f"\nradiation (organ_dose.py, {organ['storm']} storm, in the shelter): blood-forming organs {bfo_pct}% of the limit")

status = {"simulated": bool((data["source"] == "simulated").any()), "days": len(FLIGHT_DAYS), "crew": {}}
for astronaut in CREW:
    a = alerts[alerts["astronaut"] == astronaut]
    status["crew"][astronaut] = {"status": "ALERT" if len(a) > 0 else "normal",
                                 "alerts": a[["day", "biomarker", "z"]].round(1).to_dict("records")}
status["radiation_bfo_pct_limit"] = bfo_pct
with open(os.path.join(OUT_FOLDER, "health_status.json"), "w") as f:
    json.dump(status, f, indent=2)


# =====================================================================
# 7. FIGURE: z-score of every astronaut and biomarker, every flight day
# =====================================================================
grid = flight.pivot_table(index=["astronaut", "biomarker"], columns="day", values="z")
grid = grid.reindex(columns=FLIGHT_DAYS)
fig, ax = plt.subplots(figsize=(12, 11))
cmap = matplotlib.colormaps["RdBu_r"].copy()
cmap.set_bad("#d9dde2")                               # grey = no blood test that day
image = ax.imshow(np.ma.masked_invalid(grid.values), cmap=cmap, vmin=-5, vmax=5, aspect="auto")
ax.set_yticks(range(len(grid)), [f"{a}  {b}" for a, b in grid.index], fontsize=7)
ax.set_xticks(range(len(FLIGHT_DAYS)), FLIGHT_DAYS)
ax.set_xlabel("flight day (grey = no blood test that day)")
for k in range(1, len(grid)):
    if grid.index[k][0] != grid.index[k - 1][0]:          # line between two astronauts
        ax.axhline(k - 0.5, color="black", lw=0.8)
for _, r in alerts.iterrows():
    i = list(grid.index).index((r["astronaut"], r["biomarker"]))
    ax.add_patch(plt.Rectangle((FLIGHT_DAYS.index(r["day"]) - 0.5, i - 0.5), 1, 1, fill=False, color="black", lw=2))
fig.colorbar(image, ax=ax, label="z-score vs. the astronaut's own baseline", shrink=0.6)
ax.set_title(f"{'Database' if (data['source'] == 'database').all() else 'Database + SIMULATED'} biomarkers of "
             f"{len(CREW)} astronauts, {len(FLIGHT_DAYS)} flight days  ·  "
             f"black boxes = alert (|z| ≥ {Z_ALERT:.0f}, {IN_A_ROW} in a row)")
fig.tight_layout()
fig.savefig(FIGURE, dpi=140)
plt.close(fig)
print("\nSaved:", os.path.join(OUT_FOLDER, "health_alerts.csv"), os.path.join(OUT_FOLDER, "health_status.json"), FIGURE)
