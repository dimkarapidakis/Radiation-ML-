from pathlib import Path

import pandas as pd


DATA_DIR = Path(__file__).resolve().parent
FULL_DATA = DATA_DIR / "iss_dostel_2017-09.csv"
SAMPLE_DATA = DATA_DIR / "dostel_2017-09-01_20.csv"
DATA_FILE = FULL_DATA if FULL_DATA.exists() else SAMPLE_DATA

if not DATA_FILE.exists():
    raise FileNotFoundError(
        f"No DOSTEL CSV found in {DATA_DIR}. Run dostel.py to download the full dataset."
    )

df = pd.read_csv(DATA_FILE)
print(df.columns)
