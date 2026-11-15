# =====================================================================
# organ_dose.py
# Dose to every ORGAN of the astronauts, for a solar storm + 14 days of cosmic rays,
# compared with the NASA limits (NASA-STD-3001 Vol. 1 Rev. B, Table 3).
#
# Physics-based, no machine learning:
#   protons of the storm -> through the walls (the 400 rays of shielding/02_rays.py)
#   -> through the body down to the organ (every organ sits at its own depth)
#   -> energy left in the organ (NIST stopping power) -> Gy -> x 1.5 (RBE of protons, Table 4) -> mGy-Eq
#   Organs near the surface (skin, lens of the eye) get more than deep organs (blood-forming organs).
#
# VALIDATION: the same physics for the August 1972 storm behind 20 g/cm2 of aluminium,
# compared with NASA's phantom (NTRS 20130001648, Table 2.7, scenario C).
#
# Mission: 6 astronauts, 14 days. Two cases:
#   cabin    the crew stays in the worst crew room during the storm
#   shelter  the crew goes to the storm shelter (TEAM ASSUMPTION: 5% of the storm dose gets in)
# Every astronaut gets the same dose (nobody is tracked one by one).
#
# Input:   shielding/data/rays.csv
#          health/nasa_design_spe_oct1989.csv  (NASA-STD-3001 Table 5: the design reference storm)
#          live/data/live_log.csv              (only for STORM = "live forecast")
# Output:  health/data/organ_doses.csv, health/data/organ_doses.json (for the app)
#          health/data/validation_1972.csv
#          health/Figures/organ_doses.png
#
# Run:  python health/organ_dose.py
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAYS_FILE = os.path.join(ROOT, "shielding", "data", "rays.csv")
DESIGN_SPE = os.path.join(ROOT, "health", "nasa_design_spe_oct1989.csv")
LIVE_LOG = os.path.join(ROOT, "live", "data", "live_log.csv")
OUT_FOLDER = os.path.join(ROOT, "health", "data")
FIGURE = os.path.join(ROOT, "health", "Figures", "organ_doses.png")
os.makedirs(OUT_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(FIGURE), exist_ok=True)

# the storm:  "October 1989"  NASA design reference storm (the shelter must keep it < 250 mSv, V1 4031)
#             "August 1972"   the biggest storm of the Apollo era
#             "live forecast" the newest forecast of live/06_live.py
STORM = "October 1989"

# --- the mission ---
CREW = ["CDR", "PLT", "MS1", "MS2", "MS3", "MS4"]
MISSION_DAYS = 14
GCR_MSV_PER_DAY = 0.5        # cosmic rays, every day, about the same in every organ (TEAM ASSUMPTION)
SHELTER_LEFT = 0.05          # part of the storm dose that gets into the shelter (TEAM ASSUMPTION)
CABIN_ROOMS = ["cockpit", "seats", "galley", "exercise", "hygiene", "sleep"]

# --- the organs: depth inside the body (g/cm2 of tissue, simple average), NASA 30-day limit
#     (mGy-Eq, Table 3; None = no short-term limit), NASA phantom value for the 1972 check (mSv) ---
ORGANS = {
    "Skin":                 (0.1, 1500, 144.0),
    "Lens of the eye":      (0.3, 1000, 120.9),
    "Blood-forming organs": (5.0, 250, 42.9),
    "Heart (circulatory)":  (6.0, 250, None),
    "Brain (CNS)":          (5.0, 500, 44.8),      # NASA: calculated at the hippocampus; check: midbrain
    "Stomach":              (7.0, None, 25.5),
}
TISSUE_TO_AL = 1.3           # 1 g/cm2 of tissue stops protons like ~1.3 g/cm2 of aluminium
QUALITY = 1.5                # RBE of protons > 2 MeV (NASA-STD-3001 Table 4)
CHECK_SHIELD = 20.0          # g/cm2 aluminium around the phantom in the NASA 1972 scenario

NIST = pd.DataFrame({
    "energy": [1, 2, 5, 10, 20, 30, 50, 70, 100, 150, 200, 300, 500, 1000],
    "range_al": [0.0040, 0.0123, 0.0563, 0.170, 0.580, 1.21, 2.97, 5.40, 9.98, 19.6, 31.4, 59.5, 125, 310],
    "stopping_water": [260.8, 162.4, 79.11, 45.67, 26.07, 18.76, 12.45, 9.559, 7.289, 5.445, 4.492, 3.52, 2.743, 2.211],
})


# =====================================================================
# 2. THE PROTONS OF THE STORMS: energy (MeV) and number of protons per cm2
#    (all directions together, i.e. omnidirectional fluence)
# =====================================================================
spectra = {}

# August 1972 (King 1974): protons above E = 7.9e9 x exp((30 - E) / 26.5) per cm2
edges = np.logspace(np.log10(10), np.log10(1000), 2001)
above = 7.9e9 * np.exp((30 - edges) / 26.5)
spectra["August 1972"] = (np.sqrt(edges[1:] * edges[:-1]), above[:-1] - above[1:])

# October 1989 (NASA-STD-3001 Table 5): protons per cm2 per MeV -> x width of every energy step
table5 = pd.read_csv(DESIGN_SPE, comment="#")
table5 = table5[table5["energy_mev"] >= 1].reset_index(drop=True)
widths = np.gradient(table5["energy_mev"].values)
spectra["October 1989"] = (table5["energy_mev"].values, table5["fluence_per_cm2_mev"].values * widths)

# live forecast: log10 fluence per sr in 4 energy bands -> x 4 pi, spread over every band
if STORM == "live forecast":
    log = pd.read_csv(LIVE_LOG).dropna(subset=["pred_log_peak"])
    last = log.iloc[-1]
    bands = {"pred_log_fluence_10_30": (10, 30), "pred_log_fluence_30_50": (30, 50),
             "pred_log_fluence_50_100": (50, 100), "pred_log_fluence_100": (100, 500)}
    energies, protons = [], []
    for column, (low, high) in bands.items():
        energies.append(np.logspace(np.log10(low), np.log10(high), 200))
        protons.append(np.full(200, 4 * np.pi * 10 ** float(last[column]) / 200))
    spectra["live forecast"] = (np.concatenate(energies), np.concatenate(protons))
    print("Live forecast of", last["time"])


# =====================================================================
# 3. DOSE BEHIND ANY THICKNESS (walls + body), for the storm and for the 1972 check
#    a proton gets through if its range is longer than the thickness;
#    what is left of its range gives its energy, and that energy the dose it leaves
# =====================================================================
log_E = np.log(NIST["energy"].values)
log_R = np.log(NIST["range_al"].values)
log_S = np.log(NIST["stopping_water"].values)
thickness = np.concatenate([np.linspace(0, 50, 501), np.linspace(50.5, 600, 1100)])   # g/cm2 aluminium

tables = {}
for name in {STORM, "August 1972"}:
    energies, protons = spectra[name]
    proton_range = np.exp(np.interp(np.log(energies), log_E, log_R))
    table = []
    for t in thickness:
        left = proton_range - t
        through = left > NIST["range_al"].iloc[0]
        energy_after = np.exp(np.interp(np.log(left[through]), log_R, log_E))
        stopping = np.exp(np.interp(np.log(energy_after), log_E, log_S))
        table.append(1.602e-10 * (protons[through] * stopping).sum() * 1000 * QUALITY)    # mGy-Eq
    tables[name] = np.array(table)


# =====================================================================
# 4. VALIDATION: August 1972 behind 20 g/cm2 aluminium, our physics vs. NASA's phantom
# =====================================================================
check = []
for organ, (depth, limit, nasa) in ORGANS.items():
    if nasa is None:
        continue
    ours = np.interp(CHECK_SHIELD + depth * TISSUE_TO_AL, thickness, tables["August 1972"])
    check.append({"organ": organ, "ours_msv": round(ours, 1), "nasa_msv": nasa, "ours / nasa": round(ours / nasa, 2)})
check = pd.DataFrame(check)
check["ours / blood-forming"] = (check["ours_msv"] / check.loc[check["organ"] == "Blood-forming organs", "ours_msv"].iloc[0]).round(2)
check["nasa / blood-forming"] = (check["nasa_msv"] / 42.9).round(2)
check.to_csv(os.path.join(OUT_FOLDER, "validation_1972.csv"), index=False)


# =====================================================================
# 5. STORM DOSE TO EVERY ORGAN IN EVERY ROOM: average over the 400 rays of the room
# =====================================================================
rays = pd.read_csv(RAYS_FILE)
organ_room = {}
for organ, (depth, limit, nasa) in ORGANS.items():
    rays[organ] = np.interp(rays["shielding_g_cm2"] + depth * TISSUE_TO_AL, thickness, tables[STORM])
    organ_room[organ] = rays.groupby("room")[organ].mean()
organ_room = pd.DataFrame(organ_room)
worst_room = organ_room.loc[CABIN_ROOMS, "Blood-forming organs"].idxmax()


# =====================================================================
# 6. MISSION DOSE: 14 days of cosmic rays + the storm, in the cabin or in the shelter
# =====================================================================
gcr = GCR_MSV_PER_DAY * MISSION_DAYS
rows = []
for organ, (depth, limit, nasa) in ORGANS.items():
    storm_cabin = organ_room.loc[worst_room, organ]
    row = {"organ": organ, "depth_g_cm2": depth, "nasa_30day_limit": limit, "gcr_14_days": gcr,
           "storm_cabin": storm_cabin, "storm_shelter": storm_cabin * SHELTER_LEFT,
           "total_cabin": gcr + storm_cabin, "total_shelter": gcr + storm_cabin * SHELTER_LEFT}
    row["pct_limit_cabin"] = None if limit is None else 100 * row["total_cabin"] / limit
    row["pct_limit_shelter"] = None if limit is None else 100 * row["total_shelter"] / limit
    rows.append(row)
mission = pd.DataFrame(rows).round(1)
mission.to_csv(os.path.join(OUT_FOLDER, "organ_doses.csv"), index=False)

with open(os.path.join(OUT_FOLDER, "organ_doses.json"), "w") as f:
    json.dump({"storm": STORM, "crew": CREW, "days": MISSION_DAYS, "worst_cabin_room": worst_room,
               "assumptions": {"gcr_msv_per_day": GCR_MSV_PER_DAY, "shelter_left": SHELTER_LEFT},
               "organs": mission.to_dict("records")}, f, indent=2)


# =====================================================================
# 7. PRINT
# =====================================================================
pd.set_option("display.width", 200)
print("VALIDATION: August 1972, 20 g/cm2 aluminium, our physics vs. NASA phantom (mSv)")
print(check.to_string(index=False))
print(f"\nStorm: {STORM} | mission: {len(CREW)} astronauts, {MISSION_DAYS} days | worst cabin room: {worst_room}")
print(mission[["organ", "nasa_30day_limit", "gcr_14_days", "storm_cabin", "total_cabin", "pct_limit_cabin",
               "total_shelter", "pct_limit_shelter"]].to_string(index=False))
over = mission[mission["pct_limit_cabin"] >= 100]["organ"].tolist()
print("\nOver the NASA 30-day limit if they stay in the cabin:", ", ".join(over) if over else "none")
print("Over the limit in the shelter:", ", ".join(mission[mission["pct_limit_shelter"] >= 100]["organ"]) or "none")


# =====================================================================
# 8. FIGURE: validation (left), % of the NASA limit per organ (right)
# =====================================================================
fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
x = np.arange(len(check))
axes[0].bar(x - 0.2, check["nasa_msv"], 0.4, label="NASA phantom", color="#9aa5b1")
axes[0].bar(x + 0.2, check["ours_msv"], 0.4, label="our model", color="#1f5fbf")
axes[0].set_xticks(x, check["organ"], rotation=20, ha="right", fontsize=9)
axes[0].set_ylabel("mSv")
axes[0].set_title("Validation: August 1972 storm behind 20 g/cm² aluminium")
axes[0].legend(frameon=False)

limited = mission.dropna(subset=["pct_limit_cabin"])
x = np.arange(len(limited))
axes[1].bar(x - 0.2, limited["pct_limit_cabin"], 0.4, label=f"stay in the cabin ({worst_room})", color="#d6453d")
axes[1].bar(x + 0.2, limited["pct_limit_shelter"], 0.4, label="go to the shelter", color="#2e7d32")
axes[1].axhline(100, color="black", lw=1, ls="--")
axes[1].text(len(limited) - 0.5, 102, "NASA 30-day limit", ha="right", va="bottom", fontsize=9)
axes[1].set_xticks(x, limited["organ"], rotation=20, ha="right", fontsize=9)
axes[1].set_ylabel("% of the NASA 30-day limit")
axes[1].set_title(f"{STORM} storm + {MISSION_DAYS} days of cosmic rays, {len(CREW)} astronauts")
axes[1].legend(frameon=False)
for ax in axes:
    ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(FIGURE, dpi=150)
plt.close(fig)
print("\nSaved:", os.path.join(OUT_FOLDER, "organ_doses.csv"), os.path.join(OUT_FOLDER, "validation_1972.csv"), FIGURE)
