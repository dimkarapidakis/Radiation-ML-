# ICHOR · HEALTH MONITORING SYSTEM FOR ASTRONAUTS

**NASA Space Apps Challenge 2026.** Onboard health monitoring for astronauts during solar storms.

In deep space, a solar storm can deliver a month's allowed radiation dose in a few hours, and Earth is
up to 22 minutes away. ICHOR forecasts the storm, guides every astronaut to the safest place inside
Orion, and tells each one, in plain words, what the radiation is doing to **their own body**, on board
and in real time.

> Astronauts can't feel radiation until it's too late. We show each one what it's doing to their body,
> before symptoms appear.

---

## What it does

| | Question | Answer |
|---|---|---|
| 🌞 **Forecast** | How bad will the storm get? | A machine-learning model, trained on 301 solar storms, forecasts the storm from its first 30 minutes |
| 🛡 **Shielding** | Where am I safe? | The dose in every room of Orion, and each astronaut's safest room and route |
| 🚨 **Alert** | What does the crew do? | ALL CLEAR · WATCH · PREPARE · GO TO SHELTER |
| ❤️ **Health** | Am I OK? | Dose to every organ against NASA limits, vital signs against **the astronaut's own normal**, early warning signs |
| 🧠 **Mental health** | How am I coping? | A daily check-in, plus voice and breathing analysis from the microphone (live in the browser, nothing recorded) |

Tested on a 14-day mission with the real solar storm of 11 November 2025: all 6 astronauts reached the
shelter in under a minute and received **9 mSv instead of 20**.

---

## Try it

**Online:** the Streamlit app (main file `FINAL_PROJECT_1/main.py`).

**Locally** (Python 3.11 or newer):

```
cd FINAL_PROJECT_1
pip install -r requirements.txt
streamlit run main.py
```

In the app:
- **🛰 ORION · RADIATION MAP (3D):** the spacecraft with the dose in every room. **ML FORECAST** runs the live forecast with NOAA data.
- **▶ DEMO · ALL THE ALGORITHMS** (under the 3D map): one button runs every algorithm (~1 minute) and shows the results in plain words.
- **🧠 MENTAL HEALTH** (sidebar): the browser asks for the microphone; allow it and just talk.

Without the app, all the algorithms run with:

```
python run_all.py nolive      # ~1 minute
python live/06_live.py live   # the live forecast every 5 minutes (Ctrl+C to stop)
```

---

## Repository

```
FINAL_PROJECT_1/
  main.py                the ICHOR app (Streamlit)
  ichor_*.py, orion_3d.py  app panels: health, symptoms, measurements, mental health, voice, Orion 3D
  real_data.py           published reference values used by the app (NASA, HRP, REMM ...)
  database/              the team's SQLite database: astronauts, measurements, symptoms, alerts
  models/                the trained forecast model used by the app
  forecast/              ML forecast of solar storms: download, storm detection, training, prediction
  live/                  the live forecast, every 5 minutes, with NOAA data
  shielding/             Orion in 5 cm cubes, 400 rays per room, dose per room, best room per astronaut
  warning/               the crew alert and the 14-day mission with the real storm of Nov 2025
  health/                dose per organ, biomarkers, Isolation Forest, one health card per astronaut
  gis/                   floor plans and ArcGIS export
  run_all.py             runs every algorithm in order
  ALGORITHMS.md          every algorithm in detail: methods, results, outputs
  README.md              the app: setup and deployment
```

Every algorithm also writes its result in plain words (`..._readable.json`), which the app shows.

---

## How it works, in short

- **Forecast:** Ridge and logistic regression on the proton flux of the first hours. The alert always uses the **worst case** (forecast + 1.65 × model error).
- **Shielding:** proton physics (NIST) through the walls and the body to the bone marrow. The best room is found with Dijkstra on the doors, counting the dose on the way.
- **Health:** a z-score against each astronaut's own baseline, with an alert after 2 unusual measurements in a row. An Isolation Forest catches several small changes together. The organ doses are checked against NASA data (the organ ratios match within 15%).

Details: [`FINAL_PROJECT_1/ALGORITHMS.md`](FINAL_PROJECT_1/ALGORITHMS.md).

---

## Data

| Data | Source |
|---|---|
| Solar storms 1986–2017 | [GSEP catalog, Rotti et al. 2022](https://arxiv.org/abs/2204.12021) |
| Proton flux 2020–2026 (GOES-16, GOES-19) | [NOAA NCEI](https://data.ngdc.noaa.gov/platforms/solar-space-observing-satellites/goes/) |
| Live proton flux | [NOAA SWPC](https://services.swpc.noaa.gov/json/goes/primary/integral-protons-7-day.json) |
| Proton range and stopping power | [NIST PSTAR](https://physics.nist.gov/PhysRefData/Star/Text/PSTAR.html) |
| Dose limits, RBE, design storm of 1989 | [NASA-STD-3001 Vol. 1 Rev. B](https://www.nasa.gov/wp-content/uploads/2020/10/2022-01-05_nasa-std-3001_vol.1_rev._b_final_draft_with_signature_010522.pdf) |
| Organ doses of the 1972 storm (validation) | [NASA NTRS 20130001648](https://ntrs.nasa.gov/citations/20130001648) |
| Dose inside the ISS (reference) | [NASA OSDR RadLab, DOSTEL](https://visualization.osdr.nasa.gov/radlab/api/) |
| Health reference values | NASA HRP, NASA OSDR (Inspiration4), NLM REMM, published studies: see `real_data.py` |

**Honest limits:** the astronaut health data in the database are **DEMO data**. Crew movements and room
dosimeters are simulated until real sensors exist. The interior of Orion is schematic. The shelter
letting in 5% of the storm and cosmic rays of 0.5 mSv/day are team assumptions. ICHOR is screening
support, not a medical device: medication is decided by the flight surgeon.

---

## Team

| | Role |
|---|---|
| Afroditi | Mission purpose and the effects of radiation on the body |
| Theodoris | Database |
| Dimitris | Algorithms: forecast, shielding, alert, health |
| Maria | The ICHOR app |
