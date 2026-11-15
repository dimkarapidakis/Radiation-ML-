# Health: dose per organ

`organ_dose.py` computes the dose to every organ of the astronauts (6 astronauts, 14 days) for a solar
storm + cosmic rays, and compares it with the NASA 30-day limits (NASA-STD-3001 Vol. 1 Rev. B, Table 3).

Physics-based, no machine learning: protons of the storm -> through the walls (400 rays of
`shielding/02_rays.py`) -> through the body down to the organ (each organ at its own depth) ->
energy left in the organ (NIST) -> Gy x 1.5 (RBE of protons, Table 4) = mGy-Eq.

| Organ | Depth (g/cm2 tissue) | NASA 30-day limit (mGy-Eq) |
|---|---|---|
| Skin | 0.1 | 1500 |
| Lens of the eye | 0.3 | 1000 |
| Blood-forming organs | 5 | 250 |
| Heart (circulatory) | 6 | 250 |
| Brain (CNS) | 5 | 500 |
| Stomach | 7 | - |

Storms (`STORM`): **October 1989** (NASA design reference storm, Table 5 -> `nasa_design_spe_oct1989.csv`),
**August 1972**, or the **live forecast** of `live/06_live.py`.

## Validation

August 1972 storm behind 20 g/cm2 aluminium vs. NASA's phantom (NTRS 20130001648, Table 2.7, scenario C):
our model gives **~2x the NASA dose** for every organ (conservative: it has no nuclear interactions that
remove protons inside the material), but the **ratios between organs match** (lens / blood-forming organs:
2.78 ours vs 2.82 NASA; stomach: 0.64 vs 0.59; skin: 2.93 vs 3.36).

## Assumptions (team)

Cosmic rays 0.5 mSv/day in every organ; 5% of the storm dose gets into the shelter; one average depth per
organ (NASA uses full body phantoms).

```
python health/organ_dose.py
```

Output: `data/organ_doses.csv`, `data/organ_doses.json` (for the app), `data/validation_1972.csv`,
`Figures/organ_doses.png`.

# Health: biomarkers

`biomarkers.py` watches the biomarkers of every astronaut. **The data are SIMULATED** (no real astronaut
data): 6 astronauts, 7 days before the flight (baseline) + 14 flight days; every day from a wearable
(resting heart rate, HRV, SpO2, temperature, sleep), every 3 days a blood test (lymphocytes, white blood
cells, platelets). One problem is put in on purpose (MS3, fever, days 9-11) to test the detection.
Radiation does not change the biomarkers in the simulation: at the doses of the mission no measurable
signal in the blood is expected.

Statistics, no machine learning:

- z = (value - mean before the flight) / standard deviation before the flight, for **each astronaut**
- **ALERT** when |z| >= 3 in **2 measurements in a row**
- why 2 in a row: the baseline has only 5-7 values, so a new value follows a Student t distribution;
  P(|z| >= 3) is ~3%, not 0.27%. In ~500 checks ~17 single "unusual" values come just by chance
  (the run finds them) -> 2 in a row removes them all and keeps the real problem
- PRIORITY for the medical team: alert + high dose of the blood-forming organs (from `organ_dose.py`)

Two problems are put in on purpose: MS3 a clear fever (days 9-11) and MS1 a mild start of an illness
(days 5-7, every biomarker only ~2 spreads away).

## Multivariate anomaly detection

`anomaly_detection.py`: **Isolation Forest** (scikit-learn, unsupervised: needs no examples of ill
astronauts) on the 5 daily biomarkers TOGETHER (their z-scores, one point per astronaut and day).
A mild illness moves several biomarkers a little at the same time; one at a time they look normal,
together they are unusual. Unusual day = among the 5% most isolated days; alert = 2 days in a row.

Result on the simulated data: both problems found, **one day earlier** than one biomarker at a time
(MS1: day 5 instead of 6, MS3: day 9 instead of 10), no false alerts.
Limits: only 126 astronaut-days; the 5% is a choice; an alert means "look at this astronaut", not a diagnosis.

Prediction of illness from radiation is **not** done: there is not enough data for it (future work).

```
python health/organ_dose.py
python health/biomarkers.py
python health/anomaly_detection.py
```

Output: `data/biomarkers.csv`, `data/health_alerts.csv`, `data/health_status.json` (for the app),
`Figures/biomarkers.png`; `data/anomaly_scores.csv`, `data/anomaly_alerts.csv`, `Figures/anomaly_detection.png`.

## The health card of every astronaut, in plain words

`health_report.py` puts everything together in ONE card per astronaut (`data/health_readable.json`):

- **radiation**: his own dose of the mission (from `warning/crew_routes.py`: where he was every 5 minutes),
  as % of the NASA monthly allowance and as years of natural radiation on Earth; bone marrow, skin, eyes
- **body**: which biomarker is unusual for HIM, in words ("Body temperature far higher than your normal
  since day 10 (37.5 °C, your normal 36.6 °C)")
- **early sign**: several small changes together ("Often the first sign of an infection or of exhaustion")
- status: green "Healthy", yellow "See the medical officer", red "See the medical officer NOW"
  (unusual values AND bone marrow >= 15% of the allowance)

```
python health/organ_dose.py
python health/biomarkers.py
python health/anomaly_detection.py
python health/health_report.py
```
