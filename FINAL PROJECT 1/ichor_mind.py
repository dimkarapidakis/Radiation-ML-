"""
ichor_mind.py - mental-health module for Project ICHOR.

 * Daily check-in with published short screening scales (PHQ-2, GAD-2, PSS-4) + sleep + energy
 * Overall health index per day = mental (check-ins) + physical (the team's REAL database), trend, 7-day prognosis
 * Daily and monthly diagram: improved / stable / declined
 * Analysis of a recorded WAV (breathing rate + voice stress) with the same rules as the live browser monitor
 * Recommendations ("what to do")

HONEST LIMITS
 - PHQ-2 / GAD-2 / PSS-4 are SCREENING tools, not diagnoses. Their cut-offs (>= 3) were validated for a 2-week recall
   period; here they are asked about "today", so a positive result means "worth a conversation", nothing more.
 - The index weights, trend thresholds and prognosis are TEAM ASSUMPTIONS. The prognosis is a straight-line trend
   extrapolation, not a clinical prediction.
 - Voice / breathing analysis is a heuristic, not validated.
 - Own data only: stored in database/ichor_mind.db (separate file; the team's database is only READ).
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import sqlite3
import wave

import numpy as np

import ichor_health as ih
from ichor_voice_monitor import (HEAVY_RATE, IRREGULAR_CV, PANIC_RATE, STRESS_SCORE)

_HERE = os.path.dirname(os.path.abspath(__file__))
MIND_DB = os.path.join(_HERE, "database", "ichor_mind.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS checkins(
  id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, day TEXT NOT NULL, answers TEXT NOT NULL,
  phq2 INTEGER, gad2 INTEGER, pss4 INTEGER, sleep INTEGER, energy INTEGER, mental_score REAL,
  simulated INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(subject, day));
CREATE TABLE IF NOT EXISTS voice_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, ts TEXT NOT NULL, kind TEXT NOT NULL,
  breath_rate REAL, stress REAL, note TEXT, simulated INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS voice_baseline(
  subject TEXT PRIMARY KEY, f0 REAL, sd REAL, db REAL, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""


def mconn(path: str | None = None) -> sqlite3.Connection:
    path = path or MIND_DB
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


# =====================================================================================================
# questionnaire
# =====================================================================================================
FOUR = [(0, "Not at all"), (1, "A little"), (2, "Quite a bit"), (3, "Very much")]
PSS = [(0, "Never"), (1, "Almost never"), (2, "Sometimes"), (3, "Fairly often"), (4, "Very often")]
FIVE = [(1, "1"), (2, "2"), (3, "3"), (4, "4"), (5, "5")]

# key, text, options, scale, reversed
QUESTIONS = [
    ("phq1", "Today I had little interest or pleasure in doing things.", FOUR, "PHQ-2", False),
    ("phq2", "Today I felt down, depressed or hopeless.", FOUR, "PHQ-2", False),
    ("gad1", "Today I felt nervous, anxious or on edge.", FOUR, "GAD-2", False),
    ("gad2", "Today I was not able to stop or control worrying.", FOUR, "GAD-2", False),
    ("pss1", "Today I felt unable to control the important things in my life.", PSS, "PSS-4", False),
    ("pss2", "Today I felt confident about my ability to handle my personal problems.", PSS, "PSS-4", True),
    ("pss3", "Today I felt that things were going my way.", PSS, "PSS-4", True),
    ("pss4", "Today I felt that difficulties were piling up so high that I could not overcome them.", PSS, "PSS-4", False),
    ("sleep", "How well did you sleep last night? (1 = very badly, 5 = very well)", FIVE, "Sleep", False),
    ("energy", "How is your energy today? (1 = exhausted, 5 = very energetic)", FIVE, "Energy", False),
]
SCALE_REFS = (
    "PHQ-2 (Kroenke 2003, Med Care 41:1284) and GAD-2 (Kroenke 2007, Ann Intern Med 146:317): 2-item screens, "
    "score 0-6, >= 3 = positive screen. PSS-4 (Cohen 1983, J Health Soc Behav 24:385): 4 items, 0-16, items 2 and 3 "
    "reverse-scored, higher = more perceived stress.")

PHQ_CUT, GAD_CUT, PSS_HIGH = 3, 3, 10     # PSS-4 has no official cut-off: 10 is a TEAM threshold


def score_checkin(a: dict) -> dict:
    phq = a["phq1"] + a["phq2"]
    gad = a["gad1"] + a["gad2"]
    pss = a["pss1"] + (4 - a["pss2"]) + (4 - a["pss3"]) + a["pss4"]
    burden = (0.25 * phq / 6 + 0.25 * gad / 6 + 0.25 * pss / 16
              + 0.125 * (5 - a["sleep"]) / 4 + 0.125 * (5 - a["energy"]) / 4)          # TEAM weights
    return {"phq2": phq, "gad2": gad, "pss4": pss, "sleep": a["sleep"], "energy": a["energy"],
            "mental_score": round(100 * (1 - burden), 1),
            "flag_depr": phq >= PHQ_CUT, "flag_anx": gad >= GAD_CUT, "flag_stress": pss >= PSS_HIGH}


def save_checkin(conn, subject: str, day: str, answers: dict, simulated: bool = False) -> dict:
    s = score_checkin(answers)
    conn.execute("""INSERT INTO checkins(subject,day,answers,phq2,gad2,pss4,sleep,energy,mental_score,simulated)
                    VALUES(?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(subject,day) DO UPDATE SET answers=excluded.answers, phq2=excluded.phq2,
                    gad2=excluded.gad2, pss4=excluded.pss4, sleep=excluded.sleep, energy=excluded.energy,
                    mental_score=excluded.mental_score, simulated=excluded.simulated""",
                 (subject, day, json.dumps(answers), s["phq2"], s["gad2"], s["pss4"], s["sleep"], s["energy"],
                  s["mental_score"], int(simulated)))
    conn.commit()
    return s


def get_checkins(conn, subject: str) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM checkins WHERE subject=? ORDER BY day", (subject,))]


# =====================================================================================================
# physical index from the REAL database + overall series
# =====================================================================================================
def physical_daily(real_conn, astronaut_id: int) -> dict[str, float]:
    """day -> physical score (100 = every indicator inside its normal range). Uses the daily mean of each indicator."""
    rules = {r[0]: r for r in ih.RULES}
    rows = real_conn.execute(
        """SELECT i.slug AS slug, substr(m.measured_at,1,10) AS d, AVG(m.value) AS v
           FROM measurements m JOIN indicators i ON i.id = m.indicator_id
           WHERE m.astronaut_id = ? GROUP BY i.slug, d""", (astronaut_id,)).fetchall()
    burden: dict[str, float] = {}
    for r in rows:
        rule = rules.get(r["slug"])
        if not rule:
            continue
        _, _, _, lo_ok, hi_ok, lo_c, hi_c = rule
        burden[r["d"]] = max(burden.get(r["d"], 0.0), ih.band_pct(float(r["v"]), lo_ok, hi_ok, lo_c, hi_c))
    return {d: round(100 - b, 1) for d, b in burden.items()}


def build_series(checkins: list[dict], physical: dict[str, float] | None) -> list[dict]:
    physical = physical or {}
    mental = {c["day"]: c["mental_score"] for c in checkins}
    out = []
    for d in sorted(set(mental) | set(physical)):
        m, p = mental.get(d), physical.get(d)
        vals = [v for v in (m, p) if v is not None]
        out.append({"day": d, "mental": m, "physical": p, "overall": round(sum(vals) / len(vals), 1)})
    return out


def _slope(ys: list[float]) -> float:
    if len(ys) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(ys)), ys, 1)[0])


STABLE_BAND = 0.5          # points per day
MIN_DAYS = 3


def prognosis(series: list[dict], window: int = 14, horizon: int = 7) -> dict:
    ys = [s["overall"] for s in series][-window:]
    if len(ys) < MIN_DAYS:
        return {"status": "insufficient", "n": len(ys), "text": f"Need at least {MIN_DAYS} days of data (have {len(ys)})."}
    slope = _slope(ys)
    last7, prev7 = ys[-7:], ys[-14:-7]
    delta = (float(np.mean(last7)) - float(np.mean(prev7))) if prev7 else None
    status = "improving" if slope >= STABLE_BAND else "declining" if slope <= -STABLE_BAND else "stable"
    fit_last = float(np.polyval(np.polyfit(np.arange(len(ys)), ys, 1), len(ys) - 1))
    proj = max(0.0, min(100.0, fit_last + slope * horizon))
    word = {"improving": "improving", "declining": "declining", "stable": "stable"}[status]
    text = (f"Overall health is {word} ({slope:+.2f} points/day over the last {len(ys)} days). "
            f"If the trend continues, the index would be about {proj:.0f}/100 in {horizon} days.")
    return {"status": status, "slope": slope, "n": len(ys), "projected": proj, "delta7": delta, "text": text,
            "latest": ys[-1]}


def monthly(series: list[dict]) -> list[dict]:
    by: dict[str, list[float]] = {}
    for s in series:
        by.setdefault(s["day"][:7], []).append(s["overall"])
    months = sorted(by)
    out, prev = [], None
    for m in months:
        mean = float(np.mean(by[m]))
        d = None if prev is None else mean - prev
        st = "first month" if d is None else "improved" if d >= 2 else "declined" if d <= -2 else "about the same"
        out.append({"month": m, "mean": round(mean, 1), "days": len(by[m]), "delta": d, "status": st})
        prev = mean
    return out


def period_change(series: list[dict], days: int = 7) -> dict | None:
    ys = [s["overall"] for s in series]
    if len(ys) < days + 1:
        return None
    cur = float(np.mean(ys[-days:]))
    prv = float(np.mean(ys[-2 * days:-days])) if len(ys) >= 2 * days else float(np.mean(ys[:-days]))
    d = cur - prv
    return {"current": cur, "previous": prv, "delta": d,
            "status": "improved" if d >= 2 else "declined" if d <= -2 else "about the same"}


# =====================================================================================================
# flags + recommendations
# =====================================================================================================
def flags(checkins: list[dict], events: list[dict], today: str | None = None) -> dict:
    today = today or dt.date.today().isoformat()
    last = checkins[-1] if checkins else None
    recent = [c for c in checkins if c["day"] >= (dt.date.fromisoformat(today) - dt.timedelta(days=2)).isoformat()]
    pos3 = len(recent) >= 3 and all(c["phq2"] >= PHQ_CUT or c["gad2"] >= GAD_CUT for c in recent)
    since = (dt.datetime.fromisoformat(today) - dt.timedelta(days=1)).isoformat()
    ev24 = [e for e in events if e["ts"] >= since and e["kind"] != "NORMAL"]
    return {"last": last, "depr": bool(last and last["phq2"] >= PHQ_CUT), "anx": bool(last and last["gad2"] >= GAD_CUT),
            "stress": bool(last and last["pss4"] >= PSS_HIGH), "sleep": bool(last and last["sleep"] <= 2),
            "energy": bool(last and last["energy"] <= 2), "persistent": pos3,
            "panic24": any(e["kind"] == "PANIC" for e in ev24), "events24": ev24,
            "checked_today": bool(last and last["day"] == today)}


def recommendations(f: dict, prog: dict) -> list[tuple[str, str]]:
    """(priority, text). Generic, evidence-informed self-care advice; not treatment."""
    r: list[tuple[str, str]] = []
    if f["persistent"] or f["panic24"]:
        r.append(("high", "Talk to the flight surgeon / behavioral-health support today (private psychological conference). "
                          "Several positive screens in a row or a panic-like episode deserve a human assessment."))
    if f["anx"] or f["stress"] or f["panic24"] or any(e["kind"] != "PANIC" for e in f["events24"]):
        r.append(("med", "Paced breathing 10 min, 6 breaths/min (4 s in, 6 s out) with the relaxing music; repeat twice a day (Lehrer & Gevirtz 2014)."))
        r.append(("med", "Grounding exercise: name 5 things you see, 4 you can touch, 3 you hear, 2 you smell, 1 you taste."))
    if f["depr"]:
        r.append(("med", "Schedule a video call with family or friends and one pleasant activity today; low mood improves with contact and activity (behavioral activation)."))
    if f["sleep"] or f["energy"]:
        r.append(("med", "Protect the sleep window: fixed schedule, dim light before sleep, no screens 1 h before, limit caffeine after midday."))
    r.append(("low", "Keep the exercise protocol (about 30 min/day): it supports mood, sleep and bone/muscle health in microgravity."))
    r.append(("low", "Keep a regular routine: meals, work blocks, short breaks, daily time for a personal hobby."))
    if prog.get("status") == "declining":
        r.insert(0, ("high", "The overall trend is declining: review workload, sleep and social contact with the crew commander / support team this week."))
    if not f["checked_today"]:
        r.append(("low", "Complete today's check-in: it takes about a minute."))
    return r


# =====================================================================================================
# WAV analysis (same rules as the live browser monitor)
# =====================================================================================================
def classify(rate, stress) -> str:
    s = stress or 0
    kind = "NORMAL"
    if s >= STRESS_SCORE:
        kind = "STRESS"
    if rate is not None and rate >= HEAVY_RATE:
        kind = "HEAVY_BREATHING"
    if rate is not None and (rate >= PANIC_RATE or (rate >= HEAVY_RATE and s >= STRESS_SCORE)):
        kind = "PANIC"
    return kind


def _f0_frames(x: np.ndarray, sr: int):
    n, hop = int(0.04 * sr), int(0.02 * sr)
    lo, hi = int(sr / 400), int(sr / 75)
    rms_all, f0s, dbs = [], [], []
    frames = [x[i:i + n] for i in range(0, len(x) - n, hop)]
    rms = np.array([np.sqrt(np.mean(f ** 2)) for f in frames]) if frames else np.array([])
    thr = max(0.015, 0.3 * np.percentile(rms, 90)) if len(rms) else 1.0
    voiced = np.zeros(len(frames), bool)
    for k, f in enumerate(frames):
        if rms[k] < thr:
            continue
        s = f - f.mean()
        ac = np.fft.irfft(np.abs(np.fft.rfft(s, 2 * n)) ** 2)[:n]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0] * (n / (n - np.arange(n)))
        seg = ac[lo:hi + 1]
        best = seg.max()
        if best < 0.5:
            continue
        cand = [l for l in range(lo + 1, hi) if ac[l] >= 0.9 * best and ac[l] >= ac[l - 1] and ac[l] >= ac[l + 1]]
        if not cand:
            continue
        voiced[k] = True
        f0s.append(sr / cand[0])
        dbs.append(20 * np.log10(rms[k]))
    return np.array(f0s), np.array(dbs), float(voiced.mean()) if len(voiced) else 0.0, voiced


def _breathing(x: np.ndarray, sr: int, voiced: np.ndarray):
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    spec[(freqs < 300) | (freqs > 2500)] = 0
    band = np.fft.irfft(spec, len(x))
    hop = int(0.05 * sr)
    env = np.array([np.sqrt(np.mean(band[i:i + hop] ** 2)) for i in range(0, len(band) - hop, hop)])
    hz = 20
    if len(env) < hz * 15:
        return None, None, "short"
    k = max(3, hz // 2)
    sm = np.convolve(env, np.ones(k) / k, mode="same")
    amp = sm.max() - sm.min()
    if amp < 0.0008:
        return None, None, "no-signal"
    thr = sm.min() + 0.4 * amp
    gap, pk = hz, []
    for i in range(1, len(sm) - 1):
        if sm[i] > thr and sm[i] >= sm[i - 1] and sm[i] > sm[i + 1]:
            if pk and i - pk[-1] < gap:
                if sm[i] > sm[pk[-1]]:
                    pk[-1] = i
            else:
                pk.append(i)
    if len(pk) < 3:
        return None, None, "few-peaks"
    iv = np.diff(pk) / hz
    return float(60 / np.median(iv)), float(iv.std() / iv.mean()), "ok"


def analyze_wav(data: bytes, baseline: dict | None = None) -> dict:
    with wave.open(io.BytesIO(data)) as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        if sw != 2:
            raise ValueError("Please upload a 16-bit PCM WAV file.")
        raw = w.readframes(min(n, sr * 120))
    x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    f0s, dbs, vfrac, voiced = _f0_frames(x, sr)
    rate, cv, why = (None, None, "speaking") if vfrac > 0.3 else _breathing(x, sr, voiced)
    feat = None
    if len(f0s) >= 15:
        st = 12 * np.log2(f0s)
        feat = {"f0": float(f0s.mean()), "sd": float(st.std()), "db": float(dbs.mean())}
    stress = None
    if feat and baseline:
        df = (feat["f0"] - baseline["f0"]) / baseline["f0"] * 100
        sdr = feat["sd"] / max(baseline["sd"], 0.3)
        dd = feat["db"] - baseline["db"]
        c = lambda v, a, b: max(a, min(b, v))
        stress = round(40 * c(df / 15, 0, 1) + 30 * c((sdr - 1) / 0.5, 0, 1) + 30 * c(dd / 6, 0, 1))
    return {"seconds": len(x) / sr, "breath_rate": rate, "cv": cv, "breath_status": why, "voiced_fraction": vfrac,
            "voice": feat, "stress": stress, "kind": classify(rate, stress)}


def save_event(conn, subject, kind, rate=None, stress=None, note="", simulated=False, ts=None):
    conn.execute("INSERT INTO voice_events(subject,ts,kind,breath_rate,stress,note,simulated) VALUES(?,?,?,?,?,?,?)",
                 (subject, ts or dt.datetime.now().isoformat(timespec="seconds"), kind, rate, stress, note, int(simulated)))
    conn.commit()


def get_events(conn, subject) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM voice_events WHERE subject=? ORDER BY ts", (subject,))]


def get_baseline(conn, subject):
    r = conn.execute("SELECT f0,sd,db FROM voice_baseline WHERE subject=?", (subject,)).fetchone()
    return dict(r) if r else None


def set_baseline(conn, subject, feat):
    conn.execute("""INSERT INTO voice_baseline(subject,f0,sd,db) VALUES(?,?,?,?)
                    ON CONFLICT(subject) DO UPDATE SET f0=excluded.f0, sd=excluded.sd, db=excluded.db,
                    updated_at=CURRENT_TIMESTAMP""", (subject, feat["f0"], feat["sd"], feat["db"]))
    conn.commit()


# =====================================================================================================
# SIMULATED history (clearly labelled) so the diagrams can be demonstrated
# =====================================================================================================
def seed_simulated(conn, subject: str, days: int = 75, seed: int = 7) -> int:
    rng = np.random.default_rng(seed)
    today = dt.date.today()
    n = 0
    for k in range(days):
        d = today - dt.timedelta(days=days - 1 - k)
        t = k / (days - 1)
        load = 0.55 - 0.25 * np.sin(np.pi * min(1, t * 1.25)) + (0.0 if t < 0.8 else -0.18 * (t - 0.8) / 0.2)
        load = float(np.clip(load + rng.normal(0, 0.06), 0.02, 0.95))          # 0 = fine, 1 = bad
        def q(top, bias=1.0):
            return int(np.clip(round(top * load * bias + rng.normal(0, 0.35)), 0, top))
        a = {"phq1": q(3), "phq2": q(3, 0.9), "gad1": q(3), "gad2": q(3, 0.9),
             "pss1": q(4), "pss2": 4 - q(4, 0.9), "pss3": 4 - q(4, 0.9), "pss4": q(4, 0.8),
             "sleep": int(np.clip(round(5 - 4 * load + rng.normal(0, 0.5)), 1, 5)),
             "energy": int(np.clip(round(5 - 4 * load + rng.normal(0, 0.5)), 1, 5))}
        save_checkin(conn, subject, d.isoformat(), a, simulated=True)
        n += 1
    return n


def clear_simulated(conn, subject: str):
    conn.execute("DELETE FROM checkins WHERE subject=? AND simulated=1", (subject,))
    conn.execute("DELETE FROM voice_events WHERE subject=? AND simulated=1", (subject,))
    conn.commit()


# =====================================================================================================
# Streamlit panel
# =====================================================================================================
def _figs(series, prog):
    import plotly.graph_objects as go
    days = [s["day"] for s in series]
    layout = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(2,18,10,.6)", font=dict(color="#d4ffe2", family="monospace"),
                  margin=dict(l=40, r=20, t=40, b=40), yaxis=dict(range=[0, 100], title="health index (100 = best)", gridcolor="#12402a"),
                  xaxis=dict(gridcolor="#12402a"), legend=dict(orientation="h", y=-0.2), height=360)
    d = go.Figure(layout=layout)
    d.add_trace(go.Scatter(x=days, y=[s["overall"] for s in series], name="Overall", mode="lines+markers", line=dict(color="#00ff66", width=3)))
    if any(s["mental"] is not None for s in series):
        d.add_trace(go.Scatter(x=days, y=[s["mental"] for s in series], name="Mental", mode="lines", line=dict(color="#4aa3ff", width=1.5), connectgaps=True))
    if any(s["physical"] is not None for s in series):
        d.add_trace(go.Scatter(x=days, y=[s["physical"] for s in series], name="Physical (real DB)", mode="lines+markers", line=dict(color="#ffd60a", width=1.5), connectgaps=True))
    ys = [s["overall"] for s in series][-14:]
    if len(ys) >= MIN_DAYS:
        p = np.polyfit(np.arange(len(ys)), ys, 1)
        d.add_trace(go.Scatter(x=days[-len(ys):], y=list(np.polyval(p, np.arange(len(ys)))), name="14-day trend",
                               mode="lines", line=dict(color="#ff8a00", dash="dash", width=2)))
    d.add_hrect(y0=0, y1=40, fillcolor="#ff2d55", opacity=0.07, line_width=0)
    d.update_layout(title="DAILY overall health index")
    mons = monthly(series)
    colors = ["#00ff66" if m["status"] == "improved" else "#ff2d55" if m["status"] == "declined" else "#ffd60a" for m in mons]
    mf = go.Figure(layout={**layout, "height": 320})
    mf.add_trace(go.Bar(x=[m["month"] for m in mons], y=[m["mean"] for m in mons], marker_color=colors,
                        text=[("" if m["delta"] is None else f"{m['delta']:+.1f} · ") + m["status"] for m in mons], textposition="outside"))
    mf.update_layout(title="MONTHLY average (green = improved, yellow = about the same, red = declined)", showlegend=False)
    return d, mf


def render_mind_panel(subject: str, real_db_path: str | None = None, astronaut_id: int | None = None) -> None:
    import streamlit as st
    from ichor_voice_monitor import MUSIC_PARAMS, MUSIC_REFERENCES, render_voice_monitor

    st.markdown("### 🧠 MENTAL HEALTH · VOICE & BREATHING · PROGNOSIS")
    st.caption(f"Crew member: {subject} · own data in database/ichor_mind.db · screening support, not a diagnosis.")
    conn = mconn()
    today = dt.date.today().isoformat()
    t1, t2, t3 = st.tabs(["📝 Daily check-in", "🎙 Voice & breathing", "📈 Prognosis & trends"])

    # ---------------------------------------------------------------- check-in
    with t1:
        existing = {c["day"]: c for c in get_checkins(conn, subject)}.get(today)
        prev = json.loads(existing["answers"]) if existing else {}
        if existing:
            st.success("Today's check-in is saved. You can change the answers and save again.")
        with st.form(f"mind_form_{subject}"):
            ans = {}
            for key, text, opts, scale, _rev in QUESTIONS:
                labels = {v: l for v, l in opts}
                default = prev.get(key, opts[0][0] if scale not in ("Sleep", "Energy") else 3)
                ans[key] = st.radio(f"{text}  ·  {scale}", [v for v, _ in opts], index=[v for v, _ in opts].index(default),
                                    format_func=lambda v, labels=labels: labels[v], horizontal=True, key=f"q_{subject}_{key}")
            ok = st.form_submit_button("SAVE TODAY'S CHECK-IN")
        if ok:
            res = save_checkin(conn, subject, today, ans)
            st.success(f"Saved. Mental index today: {res['mental_score']:.0f}/100 · PHQ-2 {res['phq2']}/6 · GAD-2 {res['gad2']}/6 · PSS-4 {res['pss4']}/16")
            if res["flag_depr"] or res["flag_anx"] or res["flag_stress"]:
                st.warning("A screen is positive today. This is not a diagnosis; see the recommendations in the 'Prognosis & trends' tab.")
        st.caption(SCALE_REFS)

    # ---------------------------------------------------------------- voice
    with t2:
        render_voice_monitor(660)
        with st.expander("Relaxing-music design and scientific basis"):
            st.write(MUSIC_PARAMS)
            for r in MUSIC_REFERENCES:
                st.markdown(f"- {r}")
            st.caption("Please verify the references before quoting them in the project report. The music is generated live in the browser (no copyrighted tracks).")
        with st.expander("Analyse a recorded WAV file (saves the result to the daily diagram)"):
            base = get_baseline(conn, subject)
            st.caption("Calm baseline: " + (f"F0 {base['f0']:.0f} Hz, sd {base['sd']:.1f} st" if base else "none yet (voice stress cannot be scored without one)"))
            up = st.file_uploader("16-bit PCM .wav, at least 20 s for breathing", type=["wav"], key=f"wav_{subject}")
            c1, c2 = st.columns(2)
            if up is not None:
                try:
                    res = analyze_wav(up.getvalue(), base)
                    st.json(res)
                    if c1.button("Save as an event", key=f"sev_{subject}"):
                        save_event(conn, subject, res["kind"], res["breath_rate"], res["stress"], "wav upload")
                        st.success("Saved.")
                    if res["voice"] and c2.button("Use as my CALM baseline", key=f"sbase_{subject}"):
                        set_baseline(conn, subject, res["voice"])
                        st.success("Baseline saved.")
                except Exception as e:
                    st.error(f"Could not analyse the file: {e}")

    # ---------------------------------------------------------------- trends
    with t3:
        phys = None
        if real_db_path and astronaut_id is not None:
            try:
                import ichor_3d_panel as p3
                phys = physical_daily(p3._conn(real_db_path), astronaut_id)
            except Exception:
                phys = None
        checkins = get_checkins(conn, subject)
        events = get_events(conn, subject)
        series = build_series(checkins, phys)
        sim_n = sum(c["simulated"] for c in checkins)
        if sim_n:
            st.warning(f"{sim_n} of the check-ins are SIMULATED demo data (not real). Delete them below before real use.")
        if not series:
            st.info("No data yet. Fill in today's check-in, or load the labelled simulated history to see the diagrams.")
        else:
            prog = prognosis(series)
            f = flags(checkins, events)
            icon = {"improving": "🟢 IMPROVING", "stable": "🟡 STABLE", "declining": "🔴 DECLINING", "insufficient": "⚪ NOT ENOUGH DATA"}[prog["status"]]
            a, b, c, d = st.columns(4)
            a.metric("Overall status", icon)
            a.caption(prog["text"])
            b.metric("Latest index", f"{series[-1]['overall']:.0f}/100")
            pc = period_change(series, 7)
            c.metric("Last 7 days vs previous 7", "–" if not pc else f"{pc['current']:.0f}", None if not pc else f"{pc['delta']:+.1f} ({pc['status']})")
            mons = monthly(series)
            d.metric("This month vs last", f"{mons[-1]['mean']:.0f}", None if mons[-1]["delta"] is None else f"{mons[-1]['delta']:+.1f} ({mons[-1]['status']})")
            try:
                import plotly  # noqa: F401
                fd, fm = _figs(series, prog)
                st.plotly_chart(fd, use_container_width=True)
                st.plotly_chart(fm, use_container_width=True)
            except Exception:
                import pandas as pd
                st.line_chart(pd.DataFrame(series).set_index("day")[["overall"]])
            st.markdown("**What to do**")
            for pr, txt in recommendations(f, prog):
                st.markdown(f"{'🔴' if pr == 'high' else '🟠' if pr == 'med' else '🟢'} {txt}")
            if events:
                st.markdown("**Voice / breathing events**")
                st.dataframe(events[-20:][::-1], use_container_width=True)
            st.caption("Index = mean of the mental score (check-ins) and, when the real database has data for that day, the physical score "
                       "(100 minus the worst indicator deviation). Weights, the ±0.5 points/day 'stable' band and the 7-day projection are team assumptions; "
                       "the projection is a straight-line extrapolation, not a clinical prediction.")
        c1, c2 = st.columns(2)
        if c1.button("Load 75 days of SIMULATED history (demo)", key=f"seed_{subject}"):
            seed_simulated(conn, subject)
            st.rerun()
        if sim_n and c2.button("Delete all simulated data", key=f"clr_{subject}"):
            clear_simulated(conn, subject)
            st.rerun()
    conn.close()