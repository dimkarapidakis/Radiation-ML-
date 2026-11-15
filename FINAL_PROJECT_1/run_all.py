# =====================================================================
# run_all.py
# Runs ALL the algorithms of the project, in the right order, and at the end
# tells the story in plain words.
#
#   0. DATABASE              build database/nasaspacechallenge.db from schema.sql + seed.sql if it is missing
#                            (the team's database: the astronauts and their health measurements)
#   1. DOWNLOAD  (optional)  the newest proton data of GOES-19 from NOAA       forecast/01_download_goesr.py
#   2. TRAIN     (optional)  find the storms and train the forecast again      forecast/02, 03, 04, 05
#   3. MISSION               14 days, 6 astronauts, the real storm of Nov 2025 warning/simulate_room_sensors.py
#                            dosimeters every 5 min -> everyone to the shelter warning/crew_routes.py
#   4. HEALTH                dose per organ, biomarkers, early signs, cards    health/organ_dose.py ... health_report.py
#   5. LIVE                  forecast every 5 min + shielding (where to go)    live/06_live.py  (calls shielding.py)
#                            -> the alert for the whole crew                   warning/alert.py
#   6. MAPS                  the 4 floor plans for the presentation            gis/layout_floor_plans.py
#   7. STREAMLIT             copies of the results into streamlit/data/, only if the folder streamlit/ exists
#
# Run:   python run_all.py                     (no download, no training, replay of the January 2026 storm)
#        python run_all.py download            also download the newest data (takes long)
#        python run_all.py download train      also train the models again
#        python run_all.py live                live NOAA data at the end (never stops: Ctrl+C)
#        python run_all.py nolive              skip the live / replay (shielding runs once instead)
#        python run_all.py show                show everything every script prints (warnings too)
#        python run_all.py newdb               build the database again from schema.sql + seed.sql
#
# Every script writes what it prints into logs/<script>.log; on the screen you see one line per step.
# If a step fails, the end of its log is shown.
# Or change the settings below.
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

DOWNLOAD = "download" in sys.argv     # True = download the newest GOES-19 data from NOAA (takes long)
TRAIN = "train" in sys.argv           # True = find the storms and train the forecast models again
SHOW = "show" in sys.argv             # True = show everything every script prints, warnings too
LIVE = "live" if "live" in sys.argv else None if "nolive" in sys.argv else "replay"
                                      # "replay" = the storm of January 2026 (~10 minutes, then it stops)
                                      # "live"   = real NOAA data now, runs until Ctrl+C
                                      # None     = no live, shielding runs once with the last forecast

DATABASE = os.path.join(ROOT, "database")
DB_FILE = os.path.join(DATABASE, "nasaspacechallenge.db")
NEW_DB = "newdb" in sys.argv          # True = build the database again (our alerts in it are lost)

STEPS = []
if DOWNLOAD:
    STEPS += [("Download the newest GOES-19 proton data (NOAA)", "forecast/01_download_goesr.py", [])]
if TRAIN:
    STEPS += [("Find the storms in the GOES-R data", "forecast/02_detect_events.py", []),
              ("Build the training table", "forecast/03_build_table.py", []),
              ("Train the forecast models (ML)", "forecast/04_train.py", []),
              ("Forecast figures of recent storms", "forecast/05_predict.py", [])]
STEPS += [("Mission: dosimeters and crew schedule (14 days, real storm of Nov 2025)", "warning/simulate_room_sensors.py", []),
          ("Mission: warning and route to the shelter, personal dose", "warning/crew_routes.py", []),
          ("Health: dose per organ (NASA limits)", "health/organ_dose.py", []),
          ("Health: biomarkers vs. each astronaut's normal", "health/biomarkers.py", []),
          ("Health: several small changes together (Isolation Forest)", "health/anomaly_detection.py", []),
          ("Health: one card per astronaut", "health/health_report.py", []),
          ("Maps: the 4 floor plans", "gis/layout_floor_plans.py", [])]
if LIVE == "replay":
    STEPS += [("Live: replay of the January 2026 storm (forecast + shielding every 5 min)", "live/06_live.py", ["replay"]),
              ("Alert for the whole crew", "warning/alert.py", [])]
elif LIVE is None:
    STEPS += [("Shielding: dose per room and where every astronaut goes", "shielding/shielding.py", []),
              ("Alert for the whole crew", "warning/alert.py", [])]

LOGS = os.path.join(ROOT, "logs")
os.makedirs(LOGS, exist_ok=True)
QUIET = dict(os.environ, PYTHONWARNINGS="ignore")       # no warnings from the libraries (pandas, sklearn, ...)

READABLE = {"ALERT": "warning/data/alert_readable.json",
            "WHERE TO GO": "shielding/data/shielding_readable.json",
            "HEALTH": "health/data/health_readable.json",
            "THE 14-DAY MISSION": "warning/data/crew_routes_readable.json"}

STREAMLIT_DATA = os.path.join(ROOT, "streamlit", "data")      # the Streamlit app reads only this folder
FOR_STREAMLIT = ["shielding/cad/orion_floor_plans.gpkg", "shielding/data/room_doses.json",
                 "shielding/data/crew_orders.json", "shielding/data/shielding_readable.json",
                 "warning/data/alert_readable.json", "warning/data/crew_routes_readable.json",
                 "warning/data/crew_log.csv", "warning/data/room_sensors_log.csv",
                 "health/data/health_readable.json"]


# =====================================================================
# 2. THE DATABASE (the astronauts and their health): build it if it is missing
#    one statement at a time, so one bad line of seed.sql does not stop the rest
# =====================================================================
if os.path.exists(os.path.join(DATABASE, "schema.sql")):
    if NEW_DB and os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    if not os.path.exists(DB_FILE):
        db = sqlite3.connect(DB_FILE)
        db.executescript(open(os.path.join(DATABASE, "schema.sql"), encoding="utf-8").read())
        ok, failed = 0, 0
        for statement in open(os.path.join(DATABASE, "seed.sql"), encoding="utf-8").read().split(";\n"):
            if statement.strip():
                try:
                    db.execute(statement)
                    ok += 1
                except sqlite3.Error:
                    failed += 1
        db.commit()
        db.close()
        print(f"Database built: {DB_FILE} ({ok} rows from seed.sql, {failed} could not be read)")
    db = sqlite3.connect(DB_FILE)
    people = db.execute("SELECT COUNT(*) FROM astronauts").fetchone()[0]
    values = db.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    db.close()
    print(f"Database: {people} astronauts, {values} measurements\n")
else:
    print("No database/ folder: the astronauts and their health are SIMULATED.\n"
          "To use the team's database:  git checkout origin/database -- database\n")

# =====================================================================
# 3. NO LIVE FORECAST YET (new copy of the project, without the live): start the live log with the
#    last measurement of GOES-19 that we have, so shielding and alert have something to read.
#    live/06_live.py adds the real rows when it runs.
# =====================================================================
LIVE_LOG = os.path.join(ROOT, "live", "data", "live_log.csv")
GOES_FILE = os.path.join(ROOT, "forecast", "data", "processed", "GOESR", "goesr_goes19_2025-04-01_2026-12-01.csv")
if LIVE is None and not os.path.exists(LIVE_LOG) and os.path.exists(GOES_FILE):
    import pandas as pd
    last = pd.read_csv(GOES_FILE).dropna().iloc[-1]
    os.makedirs(os.path.dirname(LIVE_LOG), exist_ok=True)
    with open(LIVE_LOG, "w") as f:
        f.write("time,status,p10_now,onset,hours_since_onset,pred_log_peak,pred_log_fluence_10_30,"
                "pred_log_fluence_30_50,pred_log_fluence_50_100,pred_log_fluence_100,prob_peak_passed,"
                "prob_peak_within_6h,outside_training\n")
        f.write(f"{last['time_tag']},{'STORM STARTED' if last['flux_gt10MeV'] >= 10 else 'ALL CLEAR'},"
                f"{last['flux_gt10MeV']},,,,,,,,,,\n")
    print(f"No live forecast yet: {LIVE_LOG} starts with the last GOES-19 value ({last['time_tag']}).\n"
          f"For the real live forecast:  python live/06_live.py live\n")


# =====================================================================
# 4. RUN EVERY STEP (stop at the first one that fails)
# =====================================================================
done = []
start_all = time.time()
print(f"Running {len(STEPS)} steps. What every script prints goes to the folder logs/ "
      f"(python run_all.py show to see it here).\n")
for k, (name, script, args) in enumerate(STEPS, start=1):
    log_file = os.path.join(LOGS, os.path.basename(script).replace(".py", ".log"))
    print(f"[{k}/{len(STEPS)}] {name} ...", end=" ", flush=True)
    if "06_live.py" in script:
        print("(about 10 minutes)", end=" ", flush=True)
    start = time.time()
    if SHOW:
        print()
        result = subprocess.run([sys.executable, os.path.join(ROOT, script)] + args, cwd=ROOT)
    else:
        with open(log_file, "w", encoding="utf-8") as out:
            result = subprocess.run([sys.executable, os.path.join(ROOT, script)] + args, cwd=ROOT,
                                    stdout=out, stderr=subprocess.STDOUT, env=QUIET)
    seconds = time.time() - start
    done.append((name, "OK" if result.returncode == 0 else "FAILED", seconds))
    print(f"{'OK' if result.returncode == 0 else 'FAILED'} ({seconds:.0f} s)")
    if result.returncode != 0:
        print(f"\nFAILED: python {script} {' '.join(args)}")
        if not SHOW:
            print(f"The end of {log_file}:\n" + "-" * 70)
            print("".join(open(log_file, encoding="utf-8", errors="replace").readlines()[-25:]))
            print("-" * 70)
        print("The next steps need it, so we stop here.")
        break


# =====================================================================
# 5. SUMMARY AND THE STORY IN PLAIN WORDS
# =====================================================================
print("\n" + "=" * 70)
print(f"SUMMARY ({(time.time() - start_all) / 60:.1f} minutes)")
print("=" * 70)
for name, status, seconds in done:
    print(f"  {status:<7}{seconds:>7.0f} s   {name}")

if all(status == "OK" for _, status, _ in done):
    for title, path in READABLE.items():
        if not os.path.exists(os.path.join(ROOT, path)):
            continue
        r = json.load(open(os.path.join(ROOT, path), encoding="utf-8"))
        print(f"\n--- {title} [{r['level'].upper()}] ---")
        print(f"  {r['headline']}. {r['what_to_do']}")
        for line in r["why"]:
            print("   - " + line)
        for astronaut, c in r.get("crew", {}).items():
            print(f"   {astronaut}: {c.get('message', c.get('status', ''))}")
    print("\nFor the app: the *_readable.json files above (app/readable_view.py shows them).")

    # the Streamlit app (folder streamlit/, if it is there) gets a copy of everything it shows
    if os.path.isdir(os.path.dirname(STREAMLIT_DATA)):
        os.makedirs(STREAMLIT_DATA, exist_ok=True)
        for path in FOR_STREAMLIT:
            if os.path.exists(os.path.join(ROOT, path)):
                shutil.copyfile(os.path.join(ROOT, path), os.path.join(STREAMLIT_DATA, os.path.basename(path)))
        print(f"Copied for the Streamlit app: {STREAMLIT_DATA}   (cd streamlit, then streamlit run app.py)")

if LIVE == "live" and all(status == "OK" for _, status, _ in done):
    print("\n" + "=" * 70)
    print("LIVE: real NOAA data, forecast + shielding every 5 minutes (stop with Ctrl+C)")
    print("=" * 70, flush=True)
    subprocess.run([sys.executable, os.path.join(ROOT, "live", "06_live.py"), "live"], cwd=ROOT,
                   env=None if SHOW else QUIET)
