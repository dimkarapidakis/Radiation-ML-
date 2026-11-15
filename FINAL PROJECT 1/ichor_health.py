"""
ichor_health.py - organ-level health assessment from the team's REAL database
(heart_rate, blood pressure, sleep, fatigue, symptoms ...). No UI imports: pure logic.

What is real and what is an assumption
--------------------------------------
REAL: every value comes from the measurements / symptoms / alerts tables of the database.
ASSUMPTION (team design, not medical advice): the normal ranges below, the mapping
indicator -> organ, and the symptom bonus. Ranges follow common clinical references
(resting heart rate 60-100, blood pressure < 130/80, SpO2 >= 95 %, sleep 7-9 h ...).
"""
from __future__ import annotations

import datetime as dt
import sqlite3

import ichor_radiation as ir

ORGAN_LIST = ["Brain", "Heart", "Left Lung", "Right Lung", "Liver", "Stomach"]
LUNGS = ["Left Lung", "Right Lung"]

# slug, organs, label (EL), lo_ok, hi_ok, lo_crit, hi_crit  -> 0 % inside [lo_ok, hi_ok], 100 % at a crit bound
RULES = [
    ("heart_rate",        ["Heart"], "Heart rate",   60, 100, 40, 140),
    ("systolic_bp",       ["Heart"], "Systolic pressure",     90, 129, 70, 180),
    ("diastolic_bp",      ["Heart"], "Diastolic pressure",    60,  84, 40, 120),
    ("respiratory_rate",  LUNGS,     "Respiratory rate", 12,  20,  8,  30),
    ("oxygen_saturation", LUNGS,     "Oxygen saturation",   95, 100, 85, 100),
    ("body_temperature",  [],        "Body temperature", 36.1, 37.5, 34, 40),
    ("sleep_duration",    ["Brain"], "Sleep duration",       7,   9,  4,  12),
    ("sleep_quality",     ["Brain"], "Sleep quality",      3.5,  5,  1,   5),
    ("mood",              ["Brain"], "Mood",             3.5,  5,  1,   5),
    ("fatigue",           ["Brain"], "Fatigue",                1,  2,  1,   5),
    ("hydration_status",  ["Stomach"], "Hydration",         3.5,  5,  1,   5),
    # --- slugs of the team's newer schema.sql / seed.sql (score 1-5: 5 = best, except fatigue) ---
    ("hydration_self_assessment", ["Stomach"], "Hydration",  3.5,  5,  1,   5),
    ("appetite",          ["Stomach"], "Appetite",           3.5,  5,  1,   5),                # TEAM ASSUMPTION: appetite -> stomach
    ("lymphocyte_count",  [],        "Lymphocytes",          1.0,  4.8,  0.5, 8.0),            # 10^9/L (= 1,000-4,800 cells/uL)
    ("wbc_count",         [],        "White blood cells",    4.0, 11.0,  2.0, 20.0),           # 10^9/L
    # --- blood counts (NASA OSDR Inspiration4, OSD-569). Normal adult ranges; organ mapping is a TEAM ASSUMPTION ---
    ("hemoglobin",        LUNGS,     "Hemoglobin",          12.0, 17.5,  8.0, 21.0),   # g/dL, oxygen transport
    ("hematocrit",        LUNGS,     "Hematocrit",          36.0, 50.0, 24.0, 60.0),   # %
    ("lymphocytes",       [],        "Lymphocytes",         1000, 4800,  500, 8000),   # cells/uL (NHLBI: <1,000 = lymphocytopenia)
    ("white_blood_cells", [],        "White blood cells",    4.0, 11.0,  2.0, 20.0),   # 10^3/uL
    ("platelets",         [],        "Platelets",            150,  400,   50,  700),   # 10^3/uL
]

SYMPTOM_MAP = {**ir.SYMPTOM_ORGANS, "appetite": ["Stomach"], "flash": ["Brain"], "headache": ["Brain"], "dizz": ["Brain"], "fatigue": ["Brain"],
               "sleep": ["Brain"], "mood": ["Brain"], "cough": LUNGS, "breath": LUNGS, "chest": ["Heart"]}
SYMPTOM_WINDOW_DAYS = 3        # symptoms reported within 3 days of the newest record
SYMPTOM_PTS_PER_LEVEL = 4.0    # +4 percentage points per severity level
SYMPTOM_CAP = 25.0

SEV_FROM_PCT = (60.0, 25.0)    # >= 60 critical, >= 25 warning


def _t(s) -> dt.datetime:
    return dt.datetime.fromisoformat(str(s).replace("T", " ")[:19])


def band_pct(v: float, lo_ok: float, hi_ok: float, lo_crit: float, hi_crit: float) -> float:
    if lo_ok <= v <= hi_ok:
        return 0.0
    if v > hi_ok:
        span = hi_crit - hi_ok
        return 100.0 if span <= 0 else min(100.0, (v - hi_ok) / span * 100)
    span = lo_ok - lo_crit
    return 100.0 if span <= 0 else min(100.0, (lo_ok - v) / span * 100)


def level(pct: float) -> str:
    return "crit" if pct >= SEV_FROM_PCT[0] else "warn" if pct >= SEV_FROM_PCT[1] else "ok"


def latest_values(conn, astronaut_id: int) -> dict:
    """slug -> dict(value, unit, name, measured_at) using the newest measurement of each indicator."""
    rows = conn.execute(
        """SELECT i.slug, i.name, i.unit, m.value, m.measured_at FROM measurements m
           JOIN indicators i ON i.id = m.indicator_id
           WHERE m.astronaut_id = ? ORDER BY m.measured_at, m.id""", (astronaut_id,)).fetchall()
    out = {}
    for r in rows:                                   # later rows overwrite earlier ones
        out[r["slug"]] = {"value": float(r["value"]), "unit": r["unit"], "name": r["name"],
                          "measured_at": _t(r["measured_at"])}
    return out


def series(conn, astronaut_id: int, slug: str) -> list[tuple[dt.datetime, float]]:
    rows = conn.execute(
        """SELECT m.measured_at, m.value FROM measurements m JOIN indicators i ON i.id = m.indicator_id
           WHERE m.astronaut_id = ? AND i.slug = ? ORDER BY m.measured_at, m.id""",
        (astronaut_id, slug)).fetchall()
    return [(_t(r["measured_at"]), float(r["value"])) for r in rows]


def indicators_with_data(conn, astronaut_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT i.slug, i.name, i.unit, COUNT(*) AS n FROM measurements m JOIN indicators i ON i.id = m.indicator_id
           WHERE m.astronaut_id = ? GROUP BY i.id ORDER BY i.category, i.name""", (astronaut_id,))]


def assess_health(conn, astronaut_id: int) -> dict:
    ast = ir.get_astronaut(conn, astronaut_id)
    latest = latest_values(conn, astronaut_id)
    sym_rows = ir.symptom_rows(conn, astronaut_id)

    stamps = [v["measured_at"] for v in latest.values()] + [_t(s["reported_at"]) for s in sym_rows]
    ref = max(stamps) if stamps else None

    findings = []                                    # one per rule that has data
    for slug, organs, label, lo_ok, hi_ok, lo_crit, hi_crit in RULES:
        if slug not in latest:
            continue
        v = latest[slug]
        pct = band_pct(v["value"], lo_ok, hi_ok, lo_crit, hi_crit)
        findings.append({"slug": slug, "label": label, "value": v["value"], "unit": v["unit"],
                         "measured_at": v["measured_at"], "organs": organs, "pct": round(pct, 1),
                         "level": level(pct), "normal": f"{lo_ok:g}–{hi_ok:g}"})

    window_start = ref - dt.timedelta(days=SYMPTOM_WINDOW_DAYS) if ref else None
    symptoms = [s for s in sym_rows if ref and _t(s["reported_at"]) >= window_start]
    bonus = {o: 0.0 for o in ORGAN_LIST}
    sym_for = {o: [] for o in ORGAN_LIST}
    for s in symptoms:
        key = s["name"].lower()
        hit = {o for kw, organs in SYMPTOM_MAP.items() if kw in key for o in organs}
        for o in hit:
            bonus[o] = min(SYMPTOM_CAP, bonus[o] + SYMPTOM_PTS_PER_LEVEL * s["severity"])
            sym_for[o].append(f"{s['name']} ({s['severity']}/5)")

    organs = []
    for name in ORGAN_LIST:
        mine = [f for f in findings if name in f["organs"]]
        has_data = bool(mine) or bonus[name] > 0
        base = max([f["pct"] for f in mine], default=0.0)
        pct = min(100.0, base + bonus[name])
        worst = max(mine, key=lambda f: f["pct"], default=None)
        organs.append({"organ": name, "pct": round(pct, 1), "level": level(pct), "has_data": has_data,
                       "symptom_bonus": bonus[name], "symptoms": sym_for[name],
                       "worst": f"{worst['label']} {worst['value']:g} {worst['unit']}" if worst and worst["pct"] > 0 else None,
                       "indicators": [f["label"] for f in mine]})
    top = max((o["pct"] for o in organs if o["has_data"]), default=0.0)
    severity = "critical" if top >= SEV_FROM_PCT[0] else "warning" if top >= SEV_FROM_PCT[1] else "none"
    return {"astronaut": dict(ast) if ast else {}, "findings": findings, "organs": organs, "symptoms": symptoms,
            "severity": severity, "score": round(top), "ref": ref}


def issue_alerts(conn, astronaut_id: int, result: dict) -> list[int]:
    """One alert per (organ, day, severity) for organs at warning/critical. The only thing written to the DB."""
    new_ids = []
    if not result["ref"]:
        return new_ids
    for o in result["organs"]:
        if not o["has_data"] or o["pct"] < SEV_FROM_PCT[1]:
            continue
        sev = "critical" if o["pct"] >= SEV_FROM_PCT[0] else "warning"
        tag = f"[AUTO {o['organ']} {result['ref']:%Y-%m-%d}:{sev}]"
        if conn.execute("SELECT 1 FROM alerts WHERE astronaut_id = ? AND message LIKE ?",
                        (astronaut_id, tag + "%")).fetchone():
            continue
        why = "; ".join(filter(None, [o["worst"], ("Symptoms: " + ", ".join(o["symptoms"])) if o["symptoms"] else None]))
        msg = f"{tag} {ir.ORGAN_NAME[o['organ']]}: load index {o['pct']:.0f}% · {why}"
        new_ids.append(ir.insert_alert(conn, astronaut_id, sev, msg))
    conn.commit()
    return new_ids


def history(conn, astronaut_id: int) -> list[dict]:
    """Load index per calendar day (values as of the end of that day) -> data for the 'how is the astronaut doing' diagram.

    Each row: {day, score, organs: {organ: pct}}. Uses the same RULES / symptom bonus as assess_health(), so the
    diagram and the 3D body model always agree.
    """
    rows = conn.execute(
        """SELECT i.slug, m.measured_at, m.value FROM measurements m JOIN indicators i ON i.id = m.indicator_id
           WHERE m.astronaut_id = ? ORDER BY m.measured_at, m.id""", (astronaut_id,)).fetchall()
    sym = [(_t(r["reported_at"]), r["name"].lower(), r["severity"]) for r in ir.symptom_rows(conn, astronaut_id)]
    if not rows:
        return []
    days = sorted({_t(r["measured_at"]).date() for r in rows} | {t.date() for t, _, _ in sym})
    out = []
    for d in days:
        end = dt.datetime.combine(d, dt.time(23, 59, 59))
        cur = {}
        for r in rows:
            if _t(r["measured_at"]) <= end:
                cur[r["slug"]] = float(r["value"])
        per = {o: 0.0 for o in ORGAN_LIST}
        has = {o: False for o in ORGAN_LIST}
        for slug, organs, _label, lo_ok, hi_ok, lo_crit, hi_crit in RULES:
            if slug in cur:
                p = band_pct(cur[slug], lo_ok, hi_ok, lo_crit, hi_crit)
                for o in organs:
                    per[o] = max(per[o], p)
                    has[o] = True
        bonus = {o: 0.0 for o in ORGAN_LIST}
        for t, key, sev in sym:
            if end - dt.timedelta(days=SYMPTOM_WINDOW_DAYS) <= t <= end:
                for o in {o for kw, organs in SYMPTOM_MAP.items() if kw in key for o in organs}:
                    bonus[o] = min(SYMPTOM_CAP, bonus[o] + SYMPTOM_PTS_PER_LEVEL * sev)
                    has[o] = True
        organs_pct = {o: round(min(100.0, per[o] + bonus[o]), 1) for o in ORGAN_LIST if has[o]}
        out.append({"day": d, "score": round(max(organs_pct.values(), default=0.0), 1), "organs": organs_pct})
    return out


def trend(hist: list[dict]) -> tuple[str, float]:
    """('improving' | 'stable' | 'declining', change in load points between the first and the last day)."""
    if len(hist) < 2:
        return "stable", 0.0
    delta = hist[-1]["score"] - hist[0]["score"]
    return ("declining" if delta >= 10 else "improving" if delta <= -10 else "stable"), round(delta, 1)