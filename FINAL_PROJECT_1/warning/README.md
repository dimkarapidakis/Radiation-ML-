# Warning

`alert.py` turns the newest forecast of `live/06_live.py` into one decision for the crew
(mission: **6 astronauts, 14 days**):

| Level | When | Message |
|---|---|---|
| ALL CLEAR | no storm | Normal work |
| WATCH | storm, but nothing below is true | Follow the next alerts |
| PREPARE SHELTER | the worst-case forecast reaches S3 (1,000 pfu) | Get the storm shelter ready (~1 hour) |
| GO TO SHELTER | measured flux S3 or more, OR worst-case storm dose in the cabin >= 15% of the 250 mSv limit | **All 6 astronauts: go to the storm shelter now** |

The storm shelter is THE safe place: many layers of shielding (HDPE, water, stowage bags) that
lower the dose to almost nothing (team assumption: 5% of the storm dose gets in).

It never trusts the ML model alone:

1. **Measured level**: the flux now on the NOAA S-scale (no model).
2. **Worst case**: forecast + 1.65 x RMSE of the model (`forecast/data/processed/results.csv`).
3. **Forecast exceeded**: flux now above the forecast peak -> the forecast is scaled up to the measurement.
4. **Dose in the cabin**: worst-case fluence through the rays of `shielding/02_rays.py`, in the worst crew
   room (we do not know where every astronaut is).
5. **Mission dose**: cosmic rays (assumption 0.5 mSv/day x 14 days) + the storm, in the cabin vs. in the
   shelter, compared with the NASA limits (NASA-STD-3001 Vol. 1 Rev. B: 250 mGy-Eq in 30 days for the
   blood-forming organs, Table 3; 250 mSv for one storm, V1 4031; RBE of protons 1.5, Table 4).

```
python warning/alert.py
```

Output: `data/alert.json` (numbers), `data/alert_readable.json` (the same in plain words, for the app), one row per run in
`data/alerts_log.csv`, and `data/alert_map.gpkg` (rooms coloured by worst-case dose, the shelter marked
as the place to go; styled in ArcGIS by `gis/style_alert.py`).

## 2. Where everyone is, and where they go: `crew_routes.py`

Every 5 minutes, for 6 astronauts and 14 days:

1. **Where is everyone**: the crew schedule (`data/crew_schedule.csv`, every hour: room, floor, x, y),
   unless they are sheltering.
2. **Warning**: the dose rate in a crew room is > 0.1 mSv/h (~5 x the cosmic rays) AND > 1.5 x the rate
   15 minutes ago (on the 15-minute average of the dosimeters).
3. **Everyone goes to the storm shelter**, by the way with the least dose: Dijkstra on the doors between
   the rooms (ladders between floors 2-3-4), every door weighted by minutes x the dose rate of its rooms now.
4. They stay until the **all clear** (1 hour below 0.05 mSv/h), then follow the schedule again.
5. **Personal dose** = dose rate of the room where the astronaut is x 5 minutes, compared with the dose
   if there had been no warning (they had followed the schedule).

Input: `data/room_sensors_log.csv` (one dosimeter per room, every 5 min), `data/crew_schedule.csv`.
Output: `data/crew_log.csv`, `data/crew_routes.csv`, `data/crew_status.json`, `data/crew_routes_readable.json` (the story in plain words, for the app),
`data/crew_map.gpkg` (floors side by side, layers with time for the ArcGIS time slider),
`Figures/crew_dose.png`.

**Demo** (`simulate_room_sensors.py`, until the real sensors exist): the REAL proton flux measured by
GOES-19 for 5-19 November 2025 (the storm of 11 November = mission day 7) -> dose rate inside every room
through its walls (rays of `shielding/02_rays.py`) + cosmic rays 0.5 mSv/day + 5% noise; the shelter lets
in 5% of the storm (team assumption). The schedule: sleep 23-07 (floor 4), meals 12:00 and 19:00 (galley),
1 hour of exercise, the other hours a random work room on any crew floor, a new one every 2 hours.

Result: warning on 11 Nov 10:35, all 6 in the shelter within 1 minute, until 13 Nov 04:10;
14-day dose 9 mSv each instead of 20-21 mSv without the warning.

```
python warning/simulate_room_sensors.py
python warning/crew_routes.py
```
