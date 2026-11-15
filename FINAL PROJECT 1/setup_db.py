"""
setup_db.py - builds database/nasaspacechallenge.db from database/schema.sql and database/seed_real.sql
(Theo's schema.sql + seed.sql; add --open-data to use the NASA OSDR / published-cohort seed instead). Uses Python's built-in sqlite3, no SQLite install needed.

    python setup_db.py               # seed.sql: six simulated Artemis crew members and their data
    python setup_db.py --open-data   # seed_real.sql: published cohort data + OSDR Inspiration4 crew
An existing database is preserved unless --rebuild is passed. Back it up before rebuilding.
"""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(HERE, "database")
DB_FILE = os.path.join(DB_DIR, "nasaspacechallenge.db")
SEED = "seed_real.sql" if "--open-data" in sys.argv else "seed.sql"

for name in ("schema.sql", SEED):
    if not os.path.exists(os.path.join(DB_DIR, name)):
        sys.exit(f"Missing database/{name}.")
if "--rebuild" in sys.argv and os.path.exists(DB_FILE):
    os.remove(DB_FILE)
if os.path.exists(DB_FILE):
    sys.exit(f"{DB_FILE} already exists - delete it first, or run  python setup_db.py --rebuild")

con = sqlite3.connect(DB_FILE)
for name in ("schema.sql", SEED):
    with open(os.path.join(DB_DIR, name), encoding="utf-8") as f:
        con.executescript(f.read())
con.commit()

print("Created", DB_FILE, "from", SEED)
for t in ("astronauts", "indicators", "measurements", "symptoms", "alerts", "assessment_sessions"):
    print(f"  {t}: {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} rows")
con.close()
if SEED == "seed_real.sql":
    print("\nNext: download the CBC file of OSD-569 and run  python import_osdr_cbc.py <file.csv>  to fill the Inspiration4 crew.")