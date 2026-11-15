# =====================================================================
# health_report.py
# ONE health card per astronaut, in plain words, for the crew screen:
#
#   radiation   his own dose of the mission (warning/crew_routes.py: where he was, every 5 minutes),
#               told as % of the NASA monthly allowance and as years of natural radiation on Earth,
#               per organ with the organ ratios of organ_dose.py
#   body        biomarkers.py: which biomarker is unusual FOR HIM, in words
#   early sign  anomaly_detection.py: several small changes together
#
#   green   "Healthy"                       nothing unusual
#   yellow  "See the medical officer"       an unusual biomarker or an early sign
#   red     "See the medical officer NOW"   unusual AND a high radiation dose (bone marrow >= 15% of the allowance)
#
# The astronauts and their biomarkers come from the team's database (database/nasaspacechallenge.db);
# where it has too few days, the biomarkers are SIMULATED (see biomarkers.py).
# Every card that is not green is written into the "alerts" table of the database (warning / critical).
#
# Input:   warning/data/crew_log.csv, health/data/organ_doses.json, health/data/health_alerts.csv,
#          health/data/anomaly_alerts.csv
# Output:  health/data/health_readable.json   (for the app), and the "alerts" table of the database
# Run:     python health/health_report.py      (after organ_dose.py, biomarkers.py, anomaly_detection.py)
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import json
import os
import sqlite3

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(ROOT, "database", "nasaspacechallenge.db")      # the team's database
CREW_LOG = os.path.join(ROOT, "warning", "data", "crew_log.csv")
ORGAN_DOSES = os.path.join(ROOT, "health", "data", "organ_doses.json")
SINGLE_ALERTS = os.path.join(ROOT, "health", "data", "health_alerts.csv")
TOGETHER_ALERTS = os.path.join(ROOT, "health", "data", "anomaly_alerts.csv")
OUT = os.path.join(ROOT, "health", "data", "health_readable.json")

CREW_SIZE = 6
names = []                                                      # the astronauts from the team's database
if os.path.exists(DB_FILE):
    db = sqlite3.connect(DB_FILE)
    names = [row[0] for row in db.execute("SELECT name FROM astronauts ORDER BY id")]
    db.close()
CREW = names[:CREW_SIZE] + [f"Astronaut {i}" for i in range(len(names) + 1, CREW_SIZE + 1)]   # not in the database yet
EARTH_MSV_PER_YEAR = 2.4     # natural radiation on Earth per year (UNSCEAR)
WRITE_ALERTS = True          # write the cards that are not green into the "alerts" table of the database
TAG = "[Radiation-ML] health:"   # our alerts start with this (the old ones are replaced at every run)
PRIORITY_PCT = 15            # bone marrow above 15% of the monthly allowance + unusual biomarker -> NOW
ORGAN_WORDS = {"Blood-forming organs": "bone marrow", "Heart (circulatory)": "heart",
               "Brain (CNS)": "brain", "Lens of the eye": "eyes", "Skin": "skin"}
BIOMARKER_WORDS = {"heart_rate": "resting heart rate", "body_temperature": "body temperature",
                   "systolic_bp": "blood pressure (upper)", "diastolic_bp": "blood pressure (lower)",
                   "sleep_duration": "sleep", "lymphocyte_count": "lymphocytes (blood test)",
                   "wbc_count": "white blood cells (blood test)"}


# =====================================================================
# 2. LOAD
# =====================================================================
log = pd.read_csv(CREW_LOG, parse_dates=["time"]) if os.path.exists(CREW_LOG) else None
organ = json.load(open(ORGAN_DOSES)) if os.path.exists(ORGAN_DOSES) else None
single = pd.read_csv(SINGLE_ALERTS) if os.path.exists(SINGLE_ALERTS) else pd.DataFrame(columns=["astronaut"])
together = pd.read_csv(TOGETHER_ALERTS) if os.path.exists(TOGETHER_ALERTS) else pd.DataFrame(columns=["astronaut"])

# organ / bone marrow ratios and limits (organ_dose.py): skin and eyes get more than the bone marrow
ratio, limit = {}, {}
if organ is not None:
    organs = pd.DataFrame(organ["organs"]).set_index("organ")
    for name in ORGAN_WORDS:
        ratio[name] = organs.loc[name, "storm_cabin"] / organs.loc["Blood-forming organs", "storm_cabin"]
        limit[name] = organs.loc[name, "nasa_30day_limit"]


# =====================================================================
# 3. ONE CARD PER ASTRONAUT
# =====================================================================
report = {"module": "health", "crew": {}}
for astronaut in CREW:
    card = {"level": "green", "status": "Healthy", "radiation": "", "body": [], "early_sign": ""}

    # --- radiation: his own dose ---
    marrow_pct = 0.0
    if log is not None and astronaut in set(log["astronaut"]):      # his dose of the mission
        mine = log[log["astronaut"] == astronaut]
        dose = mine["dose_msv"].iloc[-1]
        no_warning = mine["dose_if_no_warning_msv"].iloc[-1]
        days = (mine["time"].iloc[-1] - mine["time"].iloc[0]).total_seconds() / 86400
        marrow_pct = 100 * dose / limit.get("Blood-forming organs", 250)
        text = (f"{dose:.0f} mSv in {days:.0f} days, like {dose / EARTH_MSV_PER_YEAR:.0f} years on Earth. "
                f"Bone marrow (the organ that matters most): {marrow_pct:.0f}% of the monthly allowance.")
        if ratio:
            worst = max(ORGAN_WORDS, key=lambda o: dose * ratio[o] / limit[o])
            if worst != "Blood-forming organs":
                text += (f" Most loaded organ: {ORGAN_WORDS[worst]}, {100 * dose * ratio[worst] / limit[worst]:.0f}% "
                         f"of its allowance.")
            text += (f" Skin and eyes: {100 * dose * ratio['Skin'] / limit['Skin']:.0f}% and "
                     f"{100 * dose * ratio['Lens of the eye'] / limit['Lens of the eye']:.0f}% of their allowances.")
        if no_warning - dose >= 1:
            text += f" The storm shelter saved you {no_warning - dose:.0f} mSv."
        card["radiation"] = text

    # --- body: unusual biomarkers, in words ---
    mine = single[single["astronaut"] == astronaut].copy()
    mine["size"] = mine["z"].abs()
    for _, a in mine.sort_values("size", ascending=False).drop_duplicates("biomarker").iterrows():   # its worst day
        how = "far" if abs(a["z"]) >= 5 else "clearly"
        word = "higher" if a["z"] > 0 else "lower"
        card["body"].append(f"{BIOMARKER_WORDS[a['biomarker']].capitalize()} {how} {word} than your normal "
                            f"(day {a['day']}: {a['value']:.1f} {a['unit']}, your normal "
                            f"{a['base_mean']:.1f} {a['unit']}).")

    # --- early sign: several small changes together ---
    mine = together[together["astronaut"] == astronaut]
    if len(mine) > 0:
        first = mine.sort_values("day").iloc[0]
        changed = first[list(BIOMARKER_WORDS)[:5]].abs().sort_values(ascending=False).index[:3]
        card["early_sign"] = (f"Since day {first['day']}: several small changes at the same time "
                              f"({', '.join(BIOMARKER_WORDS[c] for c in changed)}). Often the first sign of an "
                              f"infection or of exhaustion.")

    # --- the status ---
    if card["body"] or card["early_sign"]:
        card["level"] = "yellow"
        card["status"] = "See the medical officer"
        if marrow_pct >= PRIORITY_PCT:
            card["level"] = "red"
            card["status"] = "See the medical officer NOW (unusual values and a high radiation dose)"
    report["crew"][astronaut] = card

# --- the whole crew in one sentence ---
check = [a for a, c in report["crew"].items() if c["level"] != "green"]
report["level"] = "red" if any(c["level"] == "red" for c in report["crew"].values()) else "yellow" if check else "green"
report["headline"] = ("All astronauts healthy" if not check else
                      f"{len(CREW) - len(check)} of {len(CREW)} astronauts healthy. "
                      f"{' and '.join(check)}: see the medical officer")
report["what_to_do"] = "Nothing to do." if not check else "The medical officer checks them today."
single_all = pd.read_csv(os.path.join(ROOT, "health", "data", "biomarkers.csv")) if os.path.exists(
    os.path.join(ROOT, "health", "data", "biomarkers.csv")) else pd.DataFrame(columns=["source"])
report["why"] = ["Every value is compared with the astronaut's OWN normal values from before the flight.",
                 "Radiation does not show in these measurements at mission doses: it is watched with the dosimeters."]
report["simulated_biomarkers"] = bool((single_all["source"] == "simulated").any())
if report["simulated_biomarkers"]:
    report["why"].append("Some values are SIMULATED, until the database has enough days for every astronaut.")
if (single_all["source"] == "database").any():
    report["why"].append("The values come from the team's database: DEMO data, the health responses are made bigger "
                         "on purpose to show the detection.")
with open(OUT, "w") as f:
    json.dump(report, f, indent=2)


# =====================================================================
# 4. INTO THE DATABASE: every card that is not green -> table "alerts"
#    (only astronauts that are in the database; our old alerts are replaced, the others are not touched)
# =====================================================================
written = 0
if WRITE_ALERTS and os.path.exists(DB_FILE):
    db = sqlite3.connect(DB_FILE)
    ids = dict(db.execute("SELECT name, id FROM astronauts"))
    db.execute("DELETE FROM alerts WHERE message LIKE ?", (TAG + "%",))
    for astronaut, c in report["crew"].items():
        if c["level"] == "green" or astronaut not in ids:
            continue
        text = " ".join([TAG, c["status"] + "."] + c["body"] + ([c["early_sign"]] if c["early_sign"] else []))
        db.execute("INSERT INTO alerts (astronaut_id, severity, message, created_at, acknowledged) "
                   "VALUES (?, ?, ?, datetime('now'), 0)",
                   (ids[astronaut], "critical" if c["level"] == "red" else "warning", text))
        written += 1
    db.commit()
    db.close()


# =====================================================================
# 5. PRINT
# =====================================================================
print(report["headline"].upper())
for astronaut, c in report["crew"].items():
    print(f"\n{astronaut}: {c['status']}")
    print("  radiation :", c["radiation"])
    for b in c["body"]:
        print("  body      :", b)
    if c["early_sign"]:
        print("  early sign:", c["early_sign"])
print("\nSaved:", OUT, f"| {written} alerts written into the database" if os.path.exists(DB_FILE) else "")
