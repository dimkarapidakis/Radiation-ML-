"""
ichor_radiation.py - radiation / solar-storm detection for Project ICHOR (SQLite).

Pipeline
--------
1. Read the dose-rate series (indicator slug `radiation_dose_rate`, uSv/h) of one astronaut.
2. Estimate the calm baseline and detect an event: >= MIN_RUN consecutive readings at
   >= ELEVATED_RATIO x baseline. Peak >= SPIKE_RATIO x baseline => SOLAR_STORM.
3. Integrate the dose over the event (trapezoid rule) and compare it with the real NASA
   limits (250 mSv per solar particle event, 600 mSv career - NASA-STD-3001).
4. Estimate the dose and % of the limit for each organ (depth attenuation + organ limit,
   both TEAM ASSUMPTIONS, not official values) and add a bonus from reported symptoms.
5. Derive severity (info / warning / critical, matching the `alerts` CHECK constraint)
   and write ONE alert per event (and one more if the severity escalates).

Educational prototype - not for real medical use.
"""
from __future__ import annotations

import datetime as dt
import random
import sqlite3
import statistics
from dataclasses import dataclass, field

# ======================= CONFIG: point this at YOUR database =====================
import glob
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_found = sorted(glob.glob(os.path.join(_HERE, "database", "*.db")),
                key=lambda p: (os.path.basename(p) != "nasaspacechallenge.db", p))   # Theo's file first
# first .db file in the "database" folder next to this file; otherwise set the full path yourself:
# DB_PATH = "/Users/you/OtherProject/database/yourfile.db"
DB_PATH = _found[0] if _found else os.path.join(_HERE, "database", "YOURFILE.db")
DEMO_MODE = False        # True = create ichor.db with fake demo data; False = read-only use of your DB

# indicators.slug values in YOUR database that the algorithm reads.
# Units are read from indicators.unit and converted automatically (see UNIT tables below).
SLUG_RATE = "radiation_dose_rate"        # dose RATE: uSv/h, mSv/h, uSv/day or mSv/day
SLUG_CUM = "radiation_cumulative"        # cumulative dose: mSv, uSv or Sv (optional)
SLUG_ALC = "lymphocytes"                 # cells/uL (optional)

# unit text (lower case, "µ" written as "u", spaces removed) -> multiplier
RATE_TO_USV_H = {"usv/h": 1.0, "usv/hr": 1.0, "msv/h": 1000.0, "msv/hr": 1000.0,
                 "usv/day": 1 / 24, "usv/d": 1 / 24, "msv/day": 1000 / 24, "msv/d": 1000 / 24}
CUM_TO_MSV = {"msv": 1.0, "usv": 0.001, "sv": 1000.0}

# ---- real reference values (NASA-STD-3001, NASA OCHMO brief) ---------------
EVENT_LIMIT_MSV = 250.0                  # per solar particle event
CAREER_LIMIT_MSV = 600.0
BASELINE_USV_H = 1.5 / 24 * 1000         # 1.5 mSv/day deep space = 62.5 uSv/h (fallback)

# ---- TEAM detection parameters (not official) ------------------------------
ELEVATED_RATIO = 1.5                     # >= 1.5 x baseline counts as elevated
SPIKE_RATIO = 3.0                        # peak >= 3 x baseline = solar storm
MIN_RUN = 2                              # consecutive readings needed (noise filter)

# ---- TEAM organ model (assumptions) ----------------------------------------
# depth  = share of the event dose that reaches the organ (deeper = more shielded by the body)
# limit  = dose (mSv) at which the organ risk index reads 100 %
ORGANS = {
    "Brain":      {"depth": 0.40, "limit": 500.0},
    "Heart":      {"depth": 0.50, "limit": 500.0},
    "Left Lung":  {"depth": 0.60, "limit": 300.0},
    "Right Lung": {"depth": 0.60, "limit": 300.0},
    "Liver":      {"depth": 0.45, "limit": 400.0},
    "Stomach":    {"depth": 0.50, "limit": 250.0},
}
ORGAN_GR = {"Brain": "Εγκέφαλος", "Heart": "Καρδιά", "Left Lung": "Αριστερός πνεύμονας",
            "Right Lung": "Δεξιός πνεύμονας", "Liver": "Ήπαρ", "Stomach": "Στομάχι"}

# keyword (lower case, English or Greek) -> organs it points to
SYMPTOM_ORGANS = {
    "nausea": ["Stomach"], "vomit": ["Stomach"], "ναυτία": ["Stomach"], "έμετ": ["Stomach"],
    "abdominal": ["Stomach", "Liver"], "κοιλιακ": ["Stomach", "Liver"], "jaundice": ["Liver"],
    "headache": ["Brain"], "κεφαλαλγ": ["Brain"], "πονοκέφαλ": ["Brain"],
    "dizz": ["Brain"], "ζάλη": ["Brain"], "confus": ["Brain"], "σύγχυση": ["Brain"],
    "cough": ["Left Lung", "Right Lung"], "βήχας": ["Left Lung", "Right Lung"],
    "breath": ["Left Lung", "Right Lung"], "δύσπνοια": ["Left Lung", "Right Lung"],
    "chest": ["Heart"], "palpit": ["Heart"], "στήθος": ["Heart"], "παλμ": ["Heart"],
}
SYMPTOM_PTS_PER_LEVEL = 2.0              # +2 percentage points per severity level (max +10)

SEV_RANK = {"none": 0, "info": 1, "warning": 2, "critical": 3}

SCHEMA = """
CREATE TABLE IF NOT EXISTS astronauts (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, mission_name TEXT NOT NULL,
    mission_day INTEGER NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS indicators (
    id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
    category TEXT NOT NULL, unit TEXT NOT NULL,
    instructions TEXT, equipment TEXT, preparation TEXT, frequency TEXT);
CREATE TABLE IF NOT EXISTS assessment_sessions (
    id INTEGER PRIMARY KEY, astronaut_id INTEGER NOT NULL, assessment_type TEXT NOT NULL,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP, completed_at TEXT, notes TEXT,
    FOREIGN KEY (astronaut_id) REFERENCES astronauts(id));
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY, astronaut_id INTEGER NOT NULL, indicator_id INTEGER NOT NULL,
    value REAL NOT NULL, measured_at TEXT DEFAULT CURRENT_TIMESTAMP,
    session_id INTEGER REFERENCES assessment_sessions(id),
    FOREIGN KEY (astronaut_id) REFERENCES astronauts(id),
    FOREIGN KEY (indicator_id) REFERENCES indicators(id));
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY, astronaut_id INTEGER NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info','warning','critical')),
    message TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    acknowledged INTEGER NOT NULL DEFAULT 0 CHECK (acknowledged IN (0,1)),
    FOREIGN KEY (astronaut_id) REFERENCES astronauts(id));
CREATE TABLE IF NOT EXISTS symptoms (
    id INTEGER PRIMARY KEY, astronaut_id INTEGER NOT NULL, name TEXT NOT NULL,
    severity INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 5), notes TEXT,
    reported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    session_id INTEGER REFERENCES assessment_sessions(id),
    FOREIGN KEY (astronaut_id) REFERENCES astronauts(id));
CREATE INDEX IF NOT EXISTS idx_measurements_astronaut ON measurements(astronaut_id);
CREATE INDEX IF NOT EXISTS idx_measurements_indicator ON measurements(indicator_id);
CREATE INDEX IF NOT EXISTS idx_measurements_date ON measurements(measured_at);
CREATE INDEX IF NOT EXISTS idx_alerts_astronaut ON alerts(astronaut_id);
"""

INDICATORS = [
    (SLUG_RATE, "Radiation dose rate", "radiation", "uSv/h"),
    (SLUG_CUM, "Cumulative radiation dose", "radiation", "mSv"),
    (SLUG_ALC, "Lymphocyte count", "immune", "cells/uL"),
]


# ============================================================ database helpers
def connect(path: str = DB_PATH) -> sqlite3.Connection:
    import os
    if not DEMO_MODE and path != ":memory:" and not os.path.exists(path):
        raise FileNotFoundError(
            f"Database not found: {path!r}. Set DB_PATH at the top of ichor_radiation.py "
            f"to your .db file (or DEMO_MODE = True for fake demo data).")
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if DEMO_MODE or path == ":memory:":     # never modify a real database
        conn.executescript(SCHEMA)
        ensure_indicators(conn)
    return conn


def list_indicators(conn) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT slug, name, category, unit FROM indicators ORDER BY category, slug")]


def missing_slugs(conn) -> list[str]:
    have = {r["slug"] for r in conn.execute("SELECT slug FROM indicators")}
    return [s for s in (SLUG_RATE,) if s not in have]       # only the dose rate is mandatory


def _unit_factor(conn, slug: str, table: dict, default: float | None) -> float:
    row = conn.execute("SELECT unit FROM indicators WHERE slug = ?", (slug,)).fetchone()
    if row is None:
        raise KeyError(f"Indicator slug {slug!r} not found in the indicators table.")
    key = (row["unit"] or "").lower().replace("µ", "u").replace("μ", "u").replace(" ", "")
    if key in table:
        return table[key]
    if default is not None and not key:
        return default
    raise ValueError(f"Unsupported unit {row['unit']!r} for {slug!r}. Add it to RATE_TO_USV_H / CUM_TO_MSV.")


def ensure_indicators(conn: sqlite3.Connection) -> None:
    for slug, name, cat, unit in INDICATORS:
        conn.execute("INSERT OR IGNORE INTO indicators (slug, name, category, unit) VALUES (?,?,?,?)",
                     (slug, name, cat, unit))
    conn.commit()


def _t(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(str(s).replace("T", " ")[:19])


def _series(conn, astronaut_id: int, slug: str) -> list[tuple[dt.datetime, float]]:
    rows = conn.execute(
        """SELECT m.measured_at, m.value FROM measurements m
           JOIN indicators i ON i.id = m.indicator_id
           WHERE m.astronaut_id = ? AND i.slug = ? ORDER BY m.measured_at""",
        (astronaut_id, slug)).fetchall()
    return [(_t(r["measured_at"]), float(r["value"])) for r in rows]


def list_astronauts(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM astronauts ORDER BY name").fetchall()


# ================================================================== detection
def estimate_baseline(values: list[float]) -> float:
    """Calm level = median of the lowest half of the readings (robust to a long storm)."""
    if not values:
        return BASELINE_USV_H
    lower = sorted(values)[: max(3, len(values) // 2)]
    return statistics.median(lower)


def detect_event(series: list[tuple[dt.datetime, float]]) -> dict | None:
    """Latest run of elevated dose-rate readings, or None."""
    if len(series) < 3:
        return None
    vals = [v for _, v in series]
    base = estimate_baseline(vals)
    flags = [v / base >= ELEVATED_RATIO for v in vals]

    runs, i = [], 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j + 1 < len(flags) and flags[j + 1]:
                j += 1
            if j - i + 1 >= MIN_RUN:
                runs.append((i, j))
            i = j + 1
        else:
            i += 1
    if not runs:
        return None

    i, j = runs[-1]
    a, b = max(i - 1, 0), min(j + 1, len(series) - 1)      # include the edge points for integration
    dose_usv = 0.0
    for k in range(a, b):
        (t1, v1), (t2, v2) = series[k], series[k + 1]
        dose_usv += (v1 + v2) / 2 * (t2 - t1).total_seconds() / 3600
    peak = max(vals[i:j + 1])
    peak_ratio = peak / base
    return {
        "kind": "SOLAR_STORM" if peak_ratio >= SPIKE_RATIO else "ELEVATED_RADIATION",
        "start": series[i][0], "end": series[j][0],
        "baseline_usv_h": base, "peak_usv_h": peak, "peak_ratio": peak_ratio,
        "dose_msv": dose_usv / 1000.0,
        "duration_h": (series[j][0] - series[i][0]).total_seconds() / 3600,
        "ongoing": j == len(series) - 1,
    }


# ================================================================ assessment
@dataclass
class Assessment:
    astronaut_id: int
    astronaut_name: str
    event: dict | None
    cumulative_msv: float
    alc: float | None
    symptoms: list = field(default_factory=list)
    organs: list = field(default_factory=list)      # [{organ, dose_msv, pct, level}]
    severity: str = "none"
    risk_score: int = 0
    reasons: list = field(default_factory=list)
    shielding: float = 1.0
    series: list = field(default_factory=list)


def _level(pct: float) -> str:
    return "crit" if pct >= 60 else "warn" if pct >= 25 else "ok"


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def assess(conn, astronaut_id: int, shielding: float = 1.0) -> Assessment:
    """shielding: 1.0 = no shelter, 0.5 = storm shelter halves the dose reaching the crew."""
    ast = conn.execute("SELECT * FROM astronauts WHERE id = ?", (astronaut_id,)).fetchone()
    k_rate = _unit_factor(conn, SLUG_RATE, RATE_TO_USV_H, None)
    series = [(t, v * k_rate) for t, v in _series(conn, astronaut_id, SLUG_RATE)]
    event = detect_event(series)

    have = {r["slug"] for r in conn.execute("SELECT slug FROM indicators")}
    k_cum = _unit_factor(conn, SLUG_CUM, CUM_TO_MSV, 1.0) if SLUG_CUM in have else 1.0
    cum_s = [(t, v * k_cum) for t, v in _series(conn, astronaut_id, SLUG_CUM)] if SLUG_CUM in have else []
    alc_s = _series(conn, astronaut_id, SLUG_ALC) if SLUG_ALC in have else []
    event_msv = event["dose_msv"] * shielding if event else 0.0
    if cum_s:
        cumulative = cum_s[-1][1]
    else:
        cumulative = (ast["mission_day"] * 1.5 if ast else 0.0) + event_msv
    alc = alc_s[-1][1] if alc_s else None

    # symptoms since the event started (or in the last 24 h if there is no event)
    since = event["start"] if event else dt.datetime.utcnow() - dt.timedelta(hours=24)
    sym_rows = conn.execute(
        "SELECT name, severity, reported_at FROM symptoms WHERE astronaut_id = ? ORDER BY reported_at",
        (astronaut_id,)).fetchall()
    symptoms = [dict(r) for r in sym_rows if _t(r["reported_at"]) >= since]

    bonus = {o: 0.0 for o in ORGANS}
    for s in symptoms:
        name = s["name"].lower()
        for kw, organs in SYMPTOM_ORGANS.items():
            if kw in name:
                for o in organs:
                    bonus[o] = min(10.0, bonus[o] + SYMPTOM_PTS_PER_LEVEL * s["severity"])

    organs = []
    for name, cfg in ORGANS.items():
        dose = event_msv * cfg["depth"]
        pct = _clamp((dose / cfg["limit"]) * 100 + bonus[name], 0, 100)
        organs.append({"organ": name, "dose_msv": round(dose, 1), "pct": round(pct, 1),
                       "level": _level(pct), "symptom_bonus": bonus[name]})
    organs.sort(key=lambda o: o["pct"], reverse=True)

    # ---- severity: explainable rules, strongest finding wins ----
    event_frac = event_msv / EVENT_LIMIT_MSV
    career_frac = cumulative / CAREER_LIMIT_MSV
    sev, reasons = "none", []

    def raise_to(level, why):
        nonlocal sev
        reasons.append(why)
        if SEV_RANK[level] > SEV_RANK[sev]:
            sev = level

    if event:
        label = "Ηλιακή καταιγίδα" if event["kind"] == "SOLAR_STORM" else "Αυξημένη ακτινοβολία"
        raise_to("info", f"{label}: κορύφωση ×{event['peak_ratio']:.1f} του βασικού επιπέδου")
        if event_frac >= 1:
            raise_to("critical", f"Δόση συμβάντος {event_msv:.0f} mSv ≥ όριο {EVENT_LIMIT_MSV:.0f} mSv")
        elif event_frac >= 0.5:
            raise_to("warning", f"Δόση συμβάντος {event_msv:.0f} mSv ≥ 50% του ορίου")
        elif event["peak_ratio"] >= SPIKE_RATIO:
            raise_to("warning", "Απότομη αύξηση ρυθμού δόσης (ηλιακή καταιγίδα)")
    if career_frac >= 1:
        raise_to("critical", f"Σωρευτική δόση {cumulative:.0f} mSv ≥ όριο καριέρας {CAREER_LIMIT_MSV:.0f} mSv")
    elif career_frac >= 0.8:
        raise_to("warning", f"Σωρευτική δόση στο {career_frac * 100:.0f}% του ορίου καριέρας")
    if alc is not None and event:
        if alc < 1000:
            raise_to("critical", f"Λεμφοκυτταροπενία: {alc:.0f} κύτταρα/µL")
        elif alc < 1500:
            raise_to("warning", f"Πτώση λεμφοκυττάρων: {alc:.0f} κύτταρα/µL")
    if organs and organs[0]["pct"] >= 60:
        raise_to("critical", f"{ORGAN_GR[organs[0]['organ']]} σε {organs[0]['pct']:.0f}% κινδύνου")

    alc_factor = _clamp((1500 - alc) / 500) if (alc is not None and event) else 0.0
    spike_factor = _clamp(event["peak_ratio"] / 10) * 0.4 if event else 0.0
    risk = round(100 * _clamp(max(event_frac, career_frac, alc_factor, spike_factor,
                                  (organs[0]["pct"] / 100) if event else 0.0)))

    return Assessment(astronaut_id, ast["name"] if ast else "?", event, round(cumulative, 1), alc,
                      symptoms, organs, sev, risk, reasons, shielding, series)


# ====================================================================== alerts
def alert_message(a: Assessment) -> str:
    e = a.event
    head = "🚨 ΗΛΙΑΚΗ ΚΑΤΑΙΓΙΔΑ" if e["kind"] == "SOLAR_STORM" else "⚠ ΑΥΞΗΜΕΝΗ ΑΚΤΙΝΟΒΟΛΙΑ"
    top = ", ".join(f"{ORGAN_GR[o['organ']]} {o['pct']:.0f}%" for o in a.organs[:4] if o["pct"] > 0)
    state = "σε εξέλιξη" if e["ongoing"] else "ολοκληρώθηκε"
    return (f"[EVT {e['start']:%Y-%m-%d %H:%M}:{a.severity}] {head} ({state}) · "
            f"{a.astronaut_name} · δόση {a.event['dose_msv'] * a.shielding:.0f} mSv "
            f"({a.event['dose_msv'] * a.shielding / EVENT_LIMIT_MSV * 100:.0f}% του ορίου {EVENT_LIMIT_MSV:.0f}) · "
            f"κορύφωση ×{e['peak_ratio']:.1f} · κίνδυνος {a.risk_score}/100 · Όργανα: {top}")


def issue_alert(conn, a: Assessment) -> int | None:
    """Insert one alert per (event, severity). Returns the new id, or None if nothing to report/duplicate."""
    if a.event is None or a.severity == "none":
        return None
    tag = f"[EVT {a.event['start']:%Y-%m-%d %H:%M}:{a.severity}]"
    dup = conn.execute("SELECT 1 FROM alerts WHERE astronaut_id = ? AND message LIKE ?",
                       (a.astronaut_id, tag + "%")).fetchone()
    if dup:
        return None
    cur = conn.execute("INSERT INTO alerts (astronaut_id, severity, message) VALUES (?,?,?)",
                       (a.astronaut_id, a.severity, alert_message(a)))
    conn.commit()
    return cur.lastrowid


def acknowledge(conn, alert_id: int) -> None:
    conn.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
    conn.commit()


def get_alerts(conn, astronaut_id: int | None = None, only_open: bool = False) -> list[sqlite3.Row]:
    q, args = "SELECT * FROM alerts WHERE 1=1", []
    if astronaut_id is not None:
        q += " AND astronaut_id = ?"; args.append(astronaut_id)
    if only_open:
        q += " AND acknowledged = 0"
    return conn.execute(q + " ORDER BY created_at DESC, id DESC", args).fetchall()


# ================================================================== demo data
def seed_demo(conn, storm: bool = True) -> int:
    """Creates a demo astronaut with 48 h of dose-rate data (15 min steps). Returns astronaut id."""
    if not DEMO_MODE and conn.execute("PRAGMA database_list").fetchone()["file"]:
        raise RuntimeError("seed_demo only runs with DEMO_MODE = True (it would write fake data into your database).")
    conn.executescript(SCHEMA)
    ensure_indicators(conn)
    r = random.Random(7)
    cur = conn.execute("INSERT INTO astronauts (name, mission_name, mission_day) VALUES (?,?,?)",
                       ("CDR M. Rodriguez", "ARES-1 Mars Transit", 45))
    aid = cur.lastrowid
    ids = {s: conn.execute("SELECT id FROM indicators WHERE slug=?", (s,)).fetchone()["id"]
           for s, *_ in INDICATORS}
    now = dt.datetime.utcnow().replace(microsecond=0)
    step, n = dt.timedelta(minutes=15), 192
    storm_start, storm_len, peak = 120, 32, 65000.0          # 8 h triangular storm, ~260 mSv
    for k in range(n):
        t = now - (n - 1 - k) * step
        rate = BASELINE_USV_H + r.uniform(-5, 5)
        if storm and storm_start <= k < storm_start + storm_len:
            x = (k - storm_start) / storm_len
            rate += peak * (1 - abs(2 * x - 1))
        conn.execute("INSERT INTO measurements (astronaut_id, indicator_id, value, measured_at) VALUES (?,?,?,?)",
                     (aid, ids[SLUG_RATE], round(rate, 1), t.isoformat(sep=" ")))
    conn.execute("INSERT INTO measurements (astronaut_id, indicator_id, value, measured_at) VALUES (?,?,?,?)",
                 (aid, ids[SLUG_CUM], 330.0 if storm else 67.5, now.isoformat(sep=" ")))
    conn.execute("INSERT INTO measurements (astronaut_id, indicator_id, value, measured_at) VALUES (?,?,?,?)",
                 (aid, ids[SLUG_ALC], 1300.0 if storm else 2450.0, now.isoformat(sep=" ")))
    if storm:
        t_sym = (now - dt.timedelta(hours=2)).isoformat(sep=" ")
        conn.execute("INSERT INTO symptoms (astronaut_id, name, severity, reported_at) VALUES (?,?,?,?)",
                     (aid, "Nausea", 3, t_sym))
        conn.execute("INSERT INTO symptoms (astronaut_id, name, severity, reported_at) VALUES (?,?,?,?)",
                     (aid, "Headache", 2, t_sym))
    conn.commit()
    return aid