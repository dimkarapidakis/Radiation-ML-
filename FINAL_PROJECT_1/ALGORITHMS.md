# Dynamic Shielding Map: protecting astronauts from solar storms

**NASA Space Apps Challenge.** A solar proton storm can give an astronaut a month's radiation allowance in a
few hours. This project forecasts the storm, finds where inside Orion it is safe, tells every astronaut where
to go, and watches the health of the crew. Every algorithm also writes its result **in plain words**
(`..._readable.json`), so an astronaut can read it without knowing any physics.

```
                 NOAA / GOES-19 proton flux
                            │
                ┌───────────▼───────────┐
                │ 1. FORECAST (ML)      │  how big will the storm get, and when?
                │    forecast/, live/   │
                └───────────┬───────────┘
                            │ worst case = forecast + 1.65 × error
                ┌───────────▼───────────┐
                │ 2. SHIELDING          │  dose in every room; the best room around every astronaut
                │    shielding/         │
                └───────────┬───────────┘
                ┌───────────▼───────────┐
                │ 3. WARNING            │  ALL CLEAR / WATCH / PREPARE / GO TO SHELTER
                │    warning/           │  + a 14-day mission with a real storm
                └───────────┬───────────┘
   team database ──►┌───────▼───────────┐
   (SQLite)         │ 4. HEALTH         │  dose per organ, biomarkers, early signs, one card per astronaut
                    │    health/        │
                    └───────┬───────────┘
                            ▼
              *_readable.json  ──►  Streamlit app (app/)  ·  maps (gis/)  ·  database alerts
```

---

## Quick start

Python **3.11 or newer** (pandas 3 and scikit-learn 1.9 do not install on 3.10).

```
cd FINAL_PROJECT_1
pip install -r requirements.txt
python run_all.py nolive                     # all the algorithms, ~1 minute
streamlit run main.py                        # the ICHOR app (Streamlit Cloud: main file FINAL_PROJECT_1/main.py)
```

| Command | What it does |
|---|---|
| `python run_all.py` | everything + replay of the January 2026 storm (forecast + shielding every 5 min, ~10 minutes) |
| `python run_all.py nolive` | everything without the replay (~1 minute) |
| `python run_all.py live` | at the end: real NOAA data every 5 minutes, until Ctrl+C |
| `python run_all.py download train` | also download the newest NOAA data and train the models again (long) |
| `python run_all.py newdb` | build `database/nasaspacechallenge.db` again from `schema.sql` + `seed.sql` |
| `python run_all.py show` | show everything every script prints (otherwise it goes to `logs/`) |

The trained model is included (`forecast/models/forecast_models.pkl`, the same as `models/forecast_models.pkl` of the app): no download is needed to forecast.
Live data work behind company or university networks too (`truststore` uses the computer's certificates).

---

## 1. Forecast: how big will the storm get? (`forecast/`)

**Machine learning.** When a storm starts (>10 MeV flux above 10 pfu, NOAA S1), the models forecast it from
the flux of the first 30 minutes to 6 hours.

| Question | Target | Model |
|---|---|---|
| How big? | peak flux >10 MeV | Ridge regression |
| How much radiation, per energy band? | fluence 10-30, 30-50, 50-100, >100 MeV | Ridge regression |
| Has the peak passed? | probability | Logistic regression |
| Peak within the next 6 h? | probability | Logistic regression |

- **Data**: 301 storms of 4 solar cycles: GSEP catalog 1986-2017 (Rotti et al. 2022) + GOES-R 2020-2026
  (storms found by `02_detect_events.py`). The GOES-R quiet level is shifted to match GSEP.
- **Features** (`features.py`, only data up to "now"): hours since onset, flux >10/30/50/100 MeV now,
  rise per hour, hardness log(>100/>10), maximum so far, drop from the maximum, background before onset.
- **Validation**: leave-one-solar-cycle-out (train on 3 cycles, test on the 4th).

| Hours after onset | 0.5 | 1 | 2 | 4 | 6 |
|---|---|---|---|---|---|
| R², fluence >100 MeV | 0.65 | 0.73 | 0.79 | 0.85 | 0.87 |
| R², peak flux | 0.33 | 0.45 | 0.58 | 0.68 | 0.72 |

"Storm will reach 100 pfu": F1 0.63-0.84 · "peak already passed": AUC 0.76-0.86 · XGBoost / LightGBM did not
beat Ridge (300 storms are too few). **Limit**: extreme storms beyond the training range are underpredicted
(S4 of January 2026); forecasts outside the training range are flagged (`outside_training`).

| Script | Step |
|---|---|
| `01_download_goesr.py` | download GOES-R proton data from NOAA |
| `02_detect_events.py` | match quiet levels to GSEP, find the storms |
| `03_build_table.py` | one row per storm and snapshot (0.5, 1, 2, 4, 6 h) |
| `04_train.py` | validate and train → `models/forecast_models.pkl`, `data/processed/results.csv` (errors) |
| `05_predict.py` | forecast on any proton-flux CSV |

### Live (`live/06_live.py`)

Runs non-stop; every 5 minutes it reads the newest flux, checks for a storm, forecasts, and then runs
`shielding/shielding.py`.

```
python live/06_live.py live      # real NOAA data (last 7 days of GOES, services.swpc.noaa.gov)
python live/06_live.py replay    # an old storm from a file, as if it were happening now (demo)
```

No storm → ALL CLEAR · first 30 min → STORM STARTED · 30 min-6 h → a new forecast every 5 min ·
after 6 h → keeps the 6 h forecast. Output: `live/data/live_log.csv`, `live/Figures/live.png`.

---

## 2. Shielding: where is it safe? (`shielding/shielding.py`)

**Physics, no ML.** One file; runs every 5 minutes from `live/06_live.py`, or `python shielding/shielding.py`.

1. **Anatomy**: Orion as a 3D grid of **5 cm cubes**, each with a material and density (heat shield,
   aluminium 4 mm + ribs, HDPE 5 cm; storm shelter HDPE 15 cm), converted to aluminium equivalent.
2. **Rays**: from the centre of every room, **400 rays** in all directions (Fibonacci sphere);
   shielding of a ray = Σ density × aluminium equivalence × length (g/cm²).
   Steps 1-2 depend only on the spacecraft: made once (`REBUILD = True` to make them again).
3. **Storm**: the **worst case** of the newest forecast = forecast + 1.65 × RMSE of the model (worse than 95%
   of storms), scaled up if the measured flux is already above it. Or `STORM = "October 1989"`, the NASA
   design reference storm (NASA-STD-3001 Table 5).
4. **Dose**: protons of every energy band → through every ray + the body (6.5 g/cm² Al to the bone marrow)
   → energy left (NIST PSTAR range and stopping power) →
   dose = 1.602·10⁻¹⁰ × Σ(protons × stopping power) × 1000 × **1.5 (RBE)** = mSv.
   Dose of a room = average of its 400 rays. The storm shelter lets in 5% of the storm (team assumption).
5. **Crew**: where everyone is (demo: they walk smoothly and at random through the doors; on a real
   spacecraft: badges) → the **best room around him**: among the rooms reachable within **1.5 minutes**,
   the one with the least **dose on the way + storm dose in the room**. The way = **Dijkstra** on the doors
   (each door weighted by minutes × dose rate). He moves only if it saves **≥ 1 mSv**, and stays until
   the storm is over. Every move order is written as a critical alert into the database.

Room levels (% of the 250 mSv limit): Safe < 5% · Low risk < 15% · Caution < 45% · Avoid.
Example (October 1989 storm): every astronaut reaches the shelter in 0.5-1 min and gets ~2 mSv instead of
104-110 mSv.

Output: `data/room_doses.json`, `data/crew_orders.json`, `data/shielding_readable.json`,
`data/room_doses_floors.gpkg`, `Figures/room_doses_floors.png`.
`Destel/`: real dose measured inside the ISS (DOSTEL, September 2017), as a reference.

---

## 3. Warning: what does the whole crew do? (`warning/`)

### The alert (`alert.py`): 6 astronauts, 14 days

| Level | When | Message |
|---|---|---|
| ALL CLEAR | no storm | Normal work |
| WATCH | storm, nothing below is true | Follow the next alerts |
| PREPARE SHELTER | worst-case forecast reaches S3 (1,000 pfu) | Get the shelter ready (~1 hour) |
| GO TO SHELTER | measured flux ≥ S3, OR worst-case cabin dose ≥ 15% of 250 mSv | **All astronauts: go to the storm shelter now** |

It never trusts the ML model alone: measured NOAA level (no model) + worst case + forecast scaled up when
exceeded + cabin dose through the rays + mission dose (cosmic rays 0.5 mSv/day × 14 days + the storm) vs.
the NASA limits. Output: `data/alert.json`, `data/alert_readable.json`, `data/alerts_log.csv`, `data/alert_map.gpkg`.

### The 14-day mission (`simulate_room_sensors.py` → `crew_routes.py`)

- **Demo dosimeters**: the REAL GOES-19 flux of 5-19 November 2025 (storm of 11 November = mission day 7),
  through the walls of every room (the rays) + cosmic rays + 5% noise, one dosimeter per room every 5 min.
- **Schedule**: sleep 23-07, meals 12:00 and 19:00, 1 hour of exercise, other hours a random work room,
  a new one every 2 hours; crew names from the database.
- **Warning**: dose rate in a crew room > 0.1 mSv/h AND > 1.5 × the rate 15 min ago (15-min average)
  → **everyone to the shelter** by the way with the least dose (Dijkstra, ladders between floors 2-3-4)
  → **all clear** after 1 hour below 0.05 mSv/h.
- **Personal dose** = dose rate of his room × 5 min, vs. the dose without the warning.

Result: warning on 11 Nov 10:35, all 6 in the shelter within 1 minute, for 42 hours;
**9 mSv each instead of 20-21 mSv** without the warning.
Output: `data/crew_log.csv`, `data/crew_routes_readable.json`, `data/crew_map.gpkg` (time slider), `Figures/crew_dose.png`.

---

## 4. Health: am I OK? (`health/`)

### Dose per organ (`organ_dose.py`)

Protons → walls (rays) → body down to every organ (own depth) → NIST → Gy × 1.5 = mGy-Eq, vs. the NASA
30-day limits (NASA-STD-3001 Vol. 1 Rev. B, Table 3).

| Organ | Depth (g/cm² tissue) | NASA 30-day limit (mGy-Eq) |
|---|---|---|
| Skin | 0.1 | 1500 |
| Lens of the eye | 0.3 | 1000 |
| Blood-forming organs | 5 | 250 |
| Heart | 6 | 250 |
| Brain (CNS) | 5 | 500 |
| Stomach | 7 | - |

**Validation**: August 1972 storm behind 20 g/cm² Al vs. NASA's phantom (NTRS 20130001648, Table 2.7):
~2× the NASA dose (conservative: no nuclear interactions), but the **ratios between organs match**
(lens / bone marrow 2.78 vs 2.82; stomach 0.64 vs 0.59; skin 2.93 vs 3.36).

### Biomarkers (`biomarkers.py`): unusual FOR THAT ASTRONAUT?

**Statistics, no ML.** From the database: every day heart rate, body temperature, blood pressure
(systolic, diastolic), sleep; blood tests lymphocytes and white blood cells.

- Baseline = the days `baseline_start`-`baseline_end` of every astronaut (table `astronauts`).
- z = (value − his baseline mean) / his baseline standard deviation.
- **Alert** when |z| ≥ 3 in **2 measurements in a row**. Why: with a short baseline a new value follows a
  Student t distribution, P(|z| ≥ 3) ≈ 3%, not 0.27%; single values come by chance, 2 in a row do not.
- An astronaut with fewer than 10 days in the database is SIMULATED (column `source`); nothing simulated
  is written into the database.

### Early signs (`anomaly_detection.py`): Isolation Forest

**Unsupervised ML** (scikit-learn, needs no examples of ill astronauts). One point per astronaut and day =
the z-scores of the 5 daily biomarkers together. A mild illness moves several biomarkers a little at the
same time: alone they look normal, together they are unusual. Unusual day = among the 5% most isolated;
alert = 2 days in a row. With the database it finds 3 astronauts on days 2-3 after the storm, earlier than
one biomarker at a time. An alert means "look at this astronaut", not a diagnosis.

### The health card (`health_report.py`)

One card per astronaut: **radiation** (his own mission dose, as % of the monthly allowance and as years
of radiation on Earth, 2.4 mSv/year), **body** (the unusual biomarkers, in words, worst day),
**early sign** (several small changes together).
Green "Healthy" · yellow "See the medical officer" · red "See the medical officer NOW"
(unusual values AND bone marrow ≥ 15% of the allowance). Every non-green card goes into the database.

---

## 5. Maps (`gis/`)

| Script | What |
|---|---|
| `layout_floor_plans.py` | the 4 floor plans at the same scale, no radiation values (PNG 300 dpi, PDF, SVG) |
| `style_floor_plans.py`, `style_floor1.py`, `style_alert.py` | run inside ArcGIS Pro: rooms by dose level, the shelter marked |
| `arcgis_export.py` | Orion in 3D for ArcGIS: OBJ, voxels (NetCDF), points |

Layers are GeoPackages (local metres): `shielding/cad/orion_floor_plans.gpkg`,
`shielding/data/room_doses_floors.gpkg`, `warning/data/alert_map.gpkg`, `warning/data/crew_map.gpkg`.

---

## 6. The team's database (`database/`, branch `database`)

SQLite, `database/nasaspacechallenge.db`, built by `run_all.py` from `schema.sql` + `seed.sql`
(6 astronauts, 24 indicators, measurements, symptoms, a simulated S3 storm; **DEMO data**, the health
responses are made bigger on purpose to show the detection).

| | Tables |
|---|---|
| **read** | `astronauts` (names, baseline period), `indicators` + `measurements` (biomarkers) |
| **written** | `alerts`: every message starts with `[Radiation-ML]`; `health:` (warning / critical) from `health_report.py`, `storm:` (critical, move now) from `shielding.py`; our old alerts are replaced at every run |

---

## 7. The crew screen (`app/`)

`streamlit run app/app.py`: an example Streamlit app that shows every result; `app/readable_view.py` shows
only the plain-words results, ready to be copied into the team's app.

Every algorithm writes the same plain-words shape, for any app:

```json
{"module": "...", "level": "green | yellow | red", "headline": "one sentence",
 "what_to_do": "...", "why": ["reason", "..."], "crew": {"name": {"level": "...", "message": "..."}}}
```

| File | Algorithm |
|---|---|
| `warning/data/alert_readable.json` | the alert for the whole crew |
| `shielding/data/shielding_readable.json` | where every astronaut goes |
| `health/data/health_readable.json` | health cards (`status`, `radiation`, `body`, `early_sign`) |
| `warning/data/crew_routes_readable.json` | the story of the 14-day mission |

---

## Team assumptions and limits

- Cosmic rays 0.5 mSv/day; the storm shelter lets in 5% of the storm; schematic interior of Orion;
  6 astronauts (Orion carries 4).
- Dose model ~2× NASA's (conservative); one average depth per organ.
- Astronaut movements and dosimeters are simulated until real badges and sensors exist.
- The database is demo data; prediction of illness from radiation is not done (not enough data).

## References

- NASA-STD-3001 Vol. 1 Rev. B: limits (Table 3), RBE (Table 4), design storm October 1989 (Table 5),
  shelter 15 g/cm² water equivalent (Table 6), one storm < 250 mSv (V1 4031), ALARA.
- NASA NTRS 20130001648: organ doses of the August 1972 storm (validation).
- NIST PSTAR: proton range and stopping power.
- NOAA GOES-R SGPS (NCEI) and SWPC real-time data; GSEP catalog, Rotti et al. (2022), ApJS.
- UNSCEAR: natural radiation on Earth, 2.4 mSv/year.
