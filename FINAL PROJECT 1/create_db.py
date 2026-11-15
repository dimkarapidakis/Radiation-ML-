"""
create_db.py - builds the SQLite file from the team's database/schema.sql.

Run from the project folder:   python create_db.py
Creates database/ichor.db (empty tables). It never overwrites an existing file.
"""
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_SQL = os.path.join(HERE, "database", "schema.sql")
DB_FILE = os.path.join(HERE, "database", "ichor.db")

if not os.path.exists(SCHEMA_SQL):
    sys.exit(f"schema.sql not found at {SCHEMA_SQL}. Put it in a 'database' folder next to this file.")
if os.path.exists(DB_FILE):
    sys.exit(f"{DB_FILE} already exists - not touching it.")

with open(SCHEMA_SQL, encoding="utf-8") as f:
    sql = f.read()

con = sqlite3.connect(DB_FILE)
con.executescript(sql)
con.commit()

tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("Created", DB_FILE)
for t in tables:
    print(f"  {t}: {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} rows")
con.close()