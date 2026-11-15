# For our app: every result in plain words

The astronaut does not read mSv tables or z-scores. So every algorithm also writes a `..._readable.json`
in plain words, all with the **same shape**:

```json
{"module": "...", "updated": "...", "level": "green | yellow | red",
 "headline": "one sentence", "what_to_do": "what the astronaut must do",
 "why": ["the reasons, in words", "..."],
 "crew": {"CDR": {"level": "...", "message": "..."}, "...": {}}}
```

| File | Made by | What it says |
|---|---|---|
| `warning/data/alert_readable.json` | `warning/alert.py` | the alert: all clear / storm / get the shelter ready / GO TO THE SHELTER, why, how big the storm will get, when the worst comes |
| `shielding/data/shielding_readable.json` | `shielding/shielding.py` (live, every 5 min) | where every astronaut is and what he must do ("Go to the Storm shelter now: Galley -> Hygiene bay -> Storm shelter (60 seconds)") |
| `health/data/health_readable.json` | `health/health_report.py` | one health card per astronaut: radiation, body, early sign (`status`, `radiation`, `body`, `early_sign` instead of `message`) |
| `warning/data/crew_routes_readable.json` | `warning/crew_routes.py` | the story of the 14-day mission and of every astronaut |

How a dose is told: **% of the NASA monthly allowance** (250 mSv in 30 days) and **years of natural
radiation on Earth** (2.4 mSv per year), e.g. "126 mSv, 50% of your monthly allowance, like 53 years on Earth".

## Putting it in our app

`readable_view.py` shows all of them (green / yellow / red box, the reasons, one card per astronaut).
Copy its block into our Streamlit app, or try it alone:

```
streamlit run app/readable_view.py
```

`app.py` is a full example screen (crew, health, simulations, start / stop of the live system with
live or replay) that you can take parts from.
