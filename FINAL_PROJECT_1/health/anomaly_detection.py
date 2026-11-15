# =====================================================================
# anomaly_detection.py
# MULTIVARIATE anomaly detection on the biomarkers (biomarkers.py looks at every biomarker ALONE).
#
# Why: the start of an illness or exhaustion often moves SEVERAL biomarkers a little at the same time
# (heart rate a bit up, HRV a bit down, temperature a bit up, sleep a bit down). Every one of them can
# stay below |z| = 3, so the per-biomarker check misses it; together they are unusual.
#
# The data: health/data/biomarkers.csv (biomarkers.py): the team's database, or SIMULATED where it has too few days
#
# Method: Isolation Forest (scikit-learn), UNSUPERVISED: it needs no examples of "ill" astronauts
# (we have none). Every astronaut-day = one point with 5 values: the z-scores of the daily biomarkers
# (each against the astronaut's own baseline, so all astronauts can be put together).
# The forest splits the points at random; a point that is isolated with FEW splits is unusual.
#   UNUSUAL DAY  = among the most isolated CONTAMINATION share of all days
#   ALERT        = unusual 2 days in a row (same rule as biomarkers.py)
#
# Limits (say them in the presentation): 6 astronauts x 21 days = 126 points only; CONTAMINATION is a
# choice (we expect ~5% unusual days); an alert says "look at this astronaut", not "this is a disease".
#
# Output:  health/data/anomaly_scores.csv, health/data/anomaly_alerts.csv,
#          health/Figures/anomaly_detection.png
# Run:  python health/anomaly_detection.py      (after health/biomarkers.py)
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIOMARKERS = os.path.join(ROOT, "health", "data", "biomarkers.csv")
SINGLE_ALERTS = os.path.join(ROOT, "health", "data", "health_alerts.csv")      # per-biomarker alerts
OUT_FOLDER = os.path.join(ROOT, "health", "data")
FIGURE = os.path.join(ROOT, "health", "Figures", "anomaly_detection.png")

DAILY = ["heart_rate", "body_temperature", "systolic_bp", "diastolic_bp", "sleep_duration"]   # every day
CONTAMINATION = 0.05         # share of days we expect to be unusual (a choice)
IN_A_ROW = 2
N_TREES = 500
SEED = 0


# =====================================================================
# 2. ONE ROW PER ASTRONAUT AND DAY: the z-scores of the 5 daily biomarkers
# =====================================================================
data = pd.read_csv(BIOMARKERS)
days = data[data["biomarker"].isin(DAILY)].pivot_table(index=["astronaut", "day"], columns="biomarker",
                                                        values="z").reset_index()
X = days[DAILY].values


# =====================================================================
# 3. ISOLATION FOREST: score of every day (lower = more unusual)
# =====================================================================
forest = IsolationForest(n_estimators=N_TREES, contamination=CONTAMINATION, random_state=SEED).fit(X)
days["score"] = forest.decision_function(X)          # < 0 = unusual
days["unusual"] = forest.predict(X) == -1
days["main_reason"] = days[DAILY].abs().idxmax(axis=1)   # the biomarker furthest from normal that day

flight = days[days["day"] > 0].sort_values(["astronaut", "day"]).copy()
flight["in_a_row"] = flight.groupby("astronaut")["unusual"].transform(
    lambda u: u.astype(int).rolling(IN_A_ROW, min_periods=1).sum())
# an alert covers every day of a run of 2 or more unusual days
flight["alert"] = (flight["in_a_row"] >= IN_A_ROW) | (flight.groupby("astronaut")["in_a_row"].shift(-1) >= IN_A_ROW)
alerts = flight[flight["alert"]][["astronaut", "day", "score"] + DAILY + ["main_reason"]]

days.round(3).to_csv(os.path.join(OUT_FOLDER, "anomaly_scores.csv"), index=False)
alerts.round(2).to_csv(os.path.join(OUT_FOLDER, "anomaly_alerts.csv"), index=False)


# =====================================================================
# 4. COMPARE WITH THE PER-BIOMARKER CHECK (biomarkers.py)
# =====================================================================
single = pd.read_csv(SINGLE_ALERTS) if os.path.exists(SINGLE_ALERTS) else pd.DataFrame(columns=["astronaut", "day"])
compare = []
for astronaut in sorted(set(alerts["astronaut"]) | set(single["astronaut"])):
    compare.append({"astronaut": astronaut,
                    "days, one biomarker at a time": sorted(single.loc[single["astronaut"] == astronaut, "day"].unique().tolist()),
                    "days, all biomarkers together": sorted(alerts.loc[alerts["astronaut"] == astronaut, "day"].tolist())})
compare = pd.DataFrame(compare)

SOURCE = "SIMULATED data" if (data["source"] == "simulated").any() else "Database data"
print(f"!!! {SOURCE.upper()} !!!")
print(f"Isolation Forest on {len(days)} astronaut-days x {len(DAILY)} biomarkers, "
      f"{CONTAMINATION:.0%} expected unusual, alert = {IN_A_ROW} days in a row")
print(f"unusual flight days: {int(flight['unusual'].sum())}, alerts: {len(alerts)}")
print(alerts.round(1).to_string(index=False))
print("\nOne biomarker at a time (biomarkers.py) vs. all together (Isolation Forest):")
print(compare.to_string(index=False))


# =====================================================================
# 5. FIGURE: the score of every astronaut, every day (below the line = unusual)
# =====================================================================
threshold = 0.0
fig, axes = plt.subplots(len(days["astronaut"].unique()), 1, figsize=(11, 10), sharex=True, sharey=True)
for ax, (astronaut, g) in zip(axes, days.groupby("astronaut")):
    ax.axvspan(-7.5, 0.5, color="#eef1f4")
    ax.plot(g["day"], g["score"], color="#1f2a33", lw=1.2, marker="o", ms=3)
    ax.axhline(threshold, color="#c0392b", lw=1, ls="--")
    a = alerts[alerts["astronaut"] == astronaut]
    ax.scatter(a["day"], a["score"], color="#c0392b", s=60, zorder=3, label="alert")
    for _, r in a.iterrows():
        ax.annotate(r["main_reason"].replace("_", " "), (r["day"], r["score"]), textcoords="offset points",
                    xytext=(0, -12), ha="center", fontsize=7, color="#c0392b")
    ax.set_ylabel(astronaut, rotation=0, ha="right", va="center", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
axes[0].text(-3.5, axes[0].get_ylim()[0], "before the flight (baseline)", ha="center", va="bottom", fontsize=8,
             color="#6b7680")
axes[-1].set_xlabel("day (negative = before the flight)")
fig.suptitle(f"{SOURCE} · Isolation Forest score, all 5 daily biomarkers together\n"
             "below the red line = unusual day · red dot = alert (2 unusual days in a row)", fontsize=11)
fig.tight_layout()
fig.savefig(FIGURE, dpi=140)
plt.close(fig)
print("\nSaved:", os.path.join(OUT_FOLDER, "anomaly_alerts.csv"), FIGURE)
