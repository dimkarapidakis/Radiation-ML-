import io
import time
from pathlib import Path

import pandas as pd
import requests


BASE = "https://visualization.osdr.nasa.gov/radlab/api/"
START = "1990-09-01"
END = "2025-10-01"
OUTPUT = Path(__file__).resolve().parent / "iss_dostel_2017-09.csv"

months = pd.date_range(START, END, freq="MS")
parts = []

for i in range(len(months) - 1):
    t0 = months[i].strftime("%Y-%m-%dT%H:%M")
    t1 = months[i + 1].strftime("%Y-%m-%dT%H:%M")
    url = (
        BASE
        + "?spacecraft=ISS&instrument=DosTel"
        + "&timestamp>=" + t0
        + "&timestamp<" + t1
        + "&absorbed_dose_rate&latitude&longitude&altitude&format=csv"
    )
    print("Κατέβασμα", t0, "έως", t1)
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    if response.text.strip():
        parts.append(pd.read_csv(io.StringIO(response.text)))
    time.sleep(2)

if not parts:
    raise RuntimeError("The NASA RadLab API returned no DOSTEL data for the requested period.")

data = pd.concat(parts, ignore_index=True)
data.to_csv(OUTPUT, index=False)
print(data.shape)
print(data.head())
