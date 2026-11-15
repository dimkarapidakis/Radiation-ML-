import math
import random
import time
import datetime
import json

import streamlit as st
import streamlit.components.v1 as components

import numpy as np
import pandas as pd

# Sourced reference values, thresholds, simulation, playbooks (see real_data.py)
from real_data import (
    NASA_THRESHOLDS,
    PROFILES,
    SCENARIOS,
    PLAYBOOKS,
    SOURCES_MD,
    simulate_scenario,
    assess,
    build_raw_alerts,
    crew_integrity,
)

# Database-driven radiation / solar-storm detection panel (ichor_radiation.py + ichor_3d_panel.py)
from ichor_3d_panel import render_radiation_panel, render_body_compact, render_radiation_chooser, get_real_astronauts
from orion_3d import render_orion, radiation_input
from ichor_mind import render_mind_panel
from ichor_search import render_search_panel
from ichor_measurements import render_measurements_panel
import ichor_radiation as _ir

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:  # app still runs; the 3D panel shows an install hint
    HAS_PLOTLY = False

# =====================================================================
#  PROJECT ICHOR
#  Autonomous Onboard Health Monitoring System  |  Edge Intelligence
#  Run:  streamlit run main.py
#  NOTE: database values come from open datasets (see DATA_SOURCES.md); the scenario simulator is SIMULATED around real published numbers.
#        Educational prototype - not for real medical use.
# =====================================================================

st.set_page_config(
    page_title="Project ICHOR · Astronaut Health Monitoring",
    page_icon="🛸",
    layout="wide",
    initial_sidebar_state="expanded",
)

COL = {"ok": "#00ff66", "warn": "#ffb300", "crit": "#ff2d55"}
STATE_TXT = {"ok": "NOMINAL", "warn": "WARNING", "crit": "CRITICAL"}

# =====================================================================
#  HUD THEME (CSS)
# =====================================================================
HUD_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;800&family=Rajdhani:wght@400;500;700&family=Share+Tech+Mono&display=swap');

:root { --cyan:#00ff66; --gold:#ffb300; --red:#ff2d55; --bg:#020d05; }

#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"], [data-testid="stDecoration"] { visibility: hidden; }
/* keep the sidebar open/close arrow visible and on-theme */
[data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"],
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] { visibility: visible !important; }
[data-testid="stSidebarCollapsedControl"] button, [data-testid="collapsedControl"] button,
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] button { color: #00ff66 !important; }
.block-container { padding-top: 1.2rem; max-width: 1500px; }

.stApp {
    background:
        radial-gradient(ellipse at 20% 0%, rgba(0,160,70,.28) 0%, transparent 55%),
        radial-gradient(ellipse at 90% 100%, rgba(120,0,40,.18) 0%, transparent 50%),
        linear-gradient(rgba(0,255,102,.045) 1px, transparent 1px) 0 0 / 46px 46px,
        linear-gradient(90deg, rgba(0,255,102,.045) 1px, transparent 1px) 0 0 / 46px 46px,
        var(--bg);
    color: #d4ffe2;
    font-family: 'Rajdhani', sans-serif;
}
.stApp::after {
    content: ""; position: fixed; left: 0; right: 0; top: 0; height: 2px;
    background: linear-gradient(90deg, transparent, rgba(0,255,102,.45), transparent);
    animation: scan 7s linear infinite; pointer-events: none; z-index: 9999;
}
@keyframes scan { from { top: -2px; } to { top: 100%; } }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 0%,100% { opacity: .75; transform: scale(.94); } 50% { opacity: 1; transform: scale(1.04); } }
@keyframes blink { 50% { opacity: 0; } }
@keyframes alarm { 0%,100% { box-shadow: 0 0 8px rgba(255,45,85,.4), inset 0 0 18px rgba(255,45,85,.12); }
                   50% { box-shadow: 0 0 28px rgba(255,45,85,.9), inset 0 0 28px rgba(255,45,85,.3); } }

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #031c0d 0%, #02120a 100%);
    border-right: 1px solid rgba(0,255,102,.35);
}
section[data-testid="stSidebar"] * { font-family: 'Rajdhani', sans-serif; }
h1, h2, h3, h4 { font-family: 'Orbitron', sans-serif !important; letter-spacing: .08em; color: var(--cyan); }

/* ---------- Header ---------- */
.top { display: flex; align-items: center; gap: 22px; margin-bottom: 8px; }
.reactor { position: relative; width: 96px; height: 96px; flex: none; }
.reactor div { position: absolute; border-radius: 50%; }
.r1 { inset: 0; border: 3px dashed rgba(0,255,102,.7); animation: spin 14s linear infinite; }
.r2 { inset: 12px; border: 2px solid rgba(0,255,102,.95); border-top-color: transparent; border-bottom-color: transparent; animation: spin 5s linear infinite reverse; }
.r3 { inset: 24px; border: 2px dotted #8bffb0; animation: spin 9s linear infinite; }
.core { inset: 36px; background: radial-gradient(circle, #fff 0%, #8bffb0 35%, #00c853 70%, transparent 100%);
        box-shadow: 0 0 26px 8px rgba(0,255,102,.8); animation: pulse 2.2s ease-in-out infinite; }
.ttl { font-family: 'Orbitron', sans-serif; font-weight: 800; font-size: 2.1rem; letter-spacing: .18em; color: #eafff1;
       text-shadow: 0 0 14px rgba(0,255,102,.9); line-height: 1.1; }
.sub { font-family: 'Share Tech Mono', monospace; color: #6fe89a; letter-spacing: .12em; font-size: .85rem; margin-top: 4px; }
.spacer { flex: 1; }
.big { text-align: right; font-family: 'Orbitron', sans-serif; }
.big .v { font-size: 2.3rem; font-weight: 800; }
.big .l { font-size: .62rem; letter-spacing: .25em; color: #6fe89a; }

/* ---------- Panels ---------- */
.hud { position: relative; border: 1px solid rgba(0,255,102,.32); background: rgba(0,38,18,.62);
       padding: 14px 16px; margin-bottom: 14px; box-shadow: inset 0 0 22px rgba(0,255,102,.07), 0 0 14px rgba(0,255,102,.08); }
.hud::before, .hud::after { content: ""; position: absolute; width: 14px; height: 14px; border: 2px solid var(--cyan); }
.hud::before { top: -2px; left: -2px; border-right: none; border-bottom: none; }
.hud::after { bottom: -2px; right: -2px; border-left: none; border-top: none; }
.p-title { font-family: 'Orbitron', sans-serif; font-size: .72rem; letter-spacing: .28em; color: #6fe89a; margin-bottom: 10px; }

/* ---------- Banner ---------- */
.banner { font-family: 'Orbitron', sans-serif; letter-spacing: .12em; padding: 12px 18px; margin: 6px 0 14px 0; border: 1px solid; }
.banner.ok { border-color: rgba(0,255,102,.6); color: #8bffb0; background: rgba(0,255,102,.07); }
.banner.bad { border-color: var(--red); color: #ff7b94; background: rgba(255,45,85,.09); animation: alarm 1.4s infinite; }
.banner small { font-family: 'Rajdhani', sans-serif; letter-spacing: .04em; font-size: 1rem; color: #d4ffe2; }

/* ---------- Data provenance strip ---------- */
.prov { font-family: 'Share Tech Mono', monospace; font-size: .74rem; letter-spacing: .05em; color: #6fe89a;
        border: 1px dashed rgba(0,255,102,.35); padding: 6px 12px; margin: 0 0 14px 0; background: rgba(0,255,102,.03); }
.prov b { color: #eafff1; }

/* ---------- Mission bar ---------- */
.mission { display: flex; align-items: center; gap: 14px; font-family: 'Share Tech Mono', monospace; font-size: .8rem; color: #6fe89a; }
.track { position: relative; flex: 1; height: 6px; background: rgba(0,255,102,.14); border-radius: 3px; }
.fill { height: 6px; border-radius: 3px; background: linear-gradient(90deg, #00803a, #00ff66); box-shadow: 0 0 10px #00ff66; }
.ship { position: absolute; top: -13px; font-size: 1.2rem; transform: translateX(-50%); filter: drop-shadow(0 0 6px #00ff66); }

/* ---------- Gauges ---------- */
.gauge { text-align: center; padding: 10px 8px 12px 8px; }
.gauge svg { width: 100%; max-width: 160px; }
.g-label { font-family: 'Orbitron', sans-serif; font-size: .66rem; letter-spacing: .22em; color: #6fe89a; }
.g-dots { fill: none; stroke: rgba(0,255,102,.4); stroke-width: 1.5; stroke-dasharray: 2 7;
          transform-box: fill-box; transform-origin: center; animation: spin 40s linear infinite; }
.g-bg { fill: none; stroke: #0a3b1f; stroke-width: 9; }
.g-fg { fill: none; stroke-width: 9; stroke-linecap: round; }
.g-val { font-family: 'Orbitron', sans-serif; font-weight: 800; font-size: 20px; }
.g-unit { font-family: 'Share Tech Mono', monospace; font-size: 9px; fill: #6fe89a; letter-spacing: .1em; }
.g-note { font-family: 'Share Tech Mono', monospace; font-size: .7rem; letter-spacing: .06em; margin-top: 2px; }

/* ---------- Live vitals ---------- */
.ecg { width: 100%; height: 130px; background:
        linear-gradient(rgba(0,255,102,.08) 1px, transparent 1px) 0 0 / 100% 26px,
        linear-gradient(90deg, rgba(0,255,102,.08) 1px, transparent 1px) 0 0 / 40px 100%, rgba(0,18,8,.7);
       border: 1px solid rgba(0,255,102,.2); }
.vit { display: flex; gap: 12px; margin-top: 10px; }
.vit div { flex: 1; text-align: center; border: 1px solid rgba(0,255,102,.2); padding: 6px 2px; background: rgba(0,255,102,.04); }
.vit b { display: block; font-family: 'Orbitron', sans-serif; font-size: 1.35rem; color: #eafff1; text-shadow: 0 0 10px rgba(0,255,102,.8); }
.vit span { font-family: 'Share Tech Mono', monospace; font-size: .68rem; color: #6fe89a; letter-spacing: .1em; }

/* ---------- Console ---------- */
.console { font-family: 'Share Tech Mono', monospace; font-size: .86rem; line-height: 1.55; max-height: 285px; overflow-y: auto; }
.console .t { color: #3b9a60; }
.console .tag { display: inline-block; min-width: 62px; font-weight: bold; }
.console .ICHOR { color: #00ff66; } .console .USER { color: #eafff1; }
.console .WARN { color: #ffb300; } .console .ALERT { color: #ff2d55; } .console .SYS { color: #b6ff5c; }
.cursor { display: inline-block; width: 8px; height: 14px; background: #00ff66; animation: blink 1s steps(1) infinite; vertical-align: middle; }

/* ---------- Playbook cards ---------- */
.pb-head h3 { margin: 0 0 4px 0; font-size: 1.05rem; }
.pb-head .reason { font-family: 'Share Tech Mono', monospace; font-size: .8rem; color: #ffd4dc; }
.med .row { margin: 6px 0; font-size: 1.02rem; }
.med .row b { color: #6fe89a; font-family: 'Orbitron', sans-serif; font-size: .68rem; letter-spacing: .15em; display: block; }
.med code { color: #b6ff5c; background: rgba(0,0,0,.4); padding: 2px 6px; font-family: 'Share Tech Mono', monospace; }
.med .src { font-family: 'Share Tech Mono', monospace; font-size: .8rem; color: #b6ff5c; }
.step { display: flex; gap: 12px; padding: 7px 0; border-bottom: 1px dashed rgba(0,255,102,.18); font-size: 1.04rem; }
.step .n { font-family: 'Orbitron', sans-serif; font-size: .8rem; color: #00ff66; text-shadow: 0 0 8px #00ff66; padding-top: 3px; }

/* ---------- Secure comms chat ---------- */
.chat-lock { font-family: 'Share Tech Mono', monospace; color: #6fe89a; font-size: .78rem; letter-spacing: .06em; }
.chat-msg { padding: 7px 11px; margin: 5px 0; border: 1px solid rgba(0,255,102,.22); background: rgba(0,255,102,.035);
            font-family: 'Share Tech Mono', monospace; font-size: .86rem; line-height: 1.4; }
.chat-msg.me { border-color: rgba(0,255,102,.6); background: rgba(0,255,102,.08); box-shadow: 0 0 10px rgba(0,255,102,.12); }
.chat-msg .who { display: block; color: #6fe89a; font-family: 'Orbitron', sans-serif; font-size: .62rem; letter-spacing: .14em; margin-bottom: 3px; }
.chat-msg.me .who { color: #00ff66; text-shadow: 0 0 6px rgba(0,255,102,.6); }

/* ---------- Streamlit widgets ---------- */
.stButton > button, .stFormSubmitButton > button {
    background: rgba(0,255,102,.06); color: #00ff66; border: 1px solid #00ff66; border-radius: 0;
    font-family: 'Orbitron', sans-serif; letter-spacing: .12em; font-size: .72rem; text-transform: uppercase;
    transition: all .2s; }
.stButton > button:hover, .stFormSubmitButton > button:hover {
    background: #00ff66; color: #001a0a; box-shadow: 0 0 18px rgba(0,255,102,.9); }
.stTextInput input { background: rgba(0,18,8,.8) !important; color: #eafff1 !important; border: 1px solid rgba(0,255,102,.5) !important;
    border-radius: 0 !important; font-family: 'Share Tech Mono', monospace !important; }
div[data-baseweb="select"] > div { background: rgba(0,18,8,.8) !important; border-radius: 0 !important; border-color: rgba(0,255,102,.5) !important; }
[data-testid="stChatInput"] textarea { background: rgba(0,18,8,.8) !important; color: #eafff1 !important;
    border: 1px solid rgba(0,255,102,.5) !important; border-radius: 0 !important; font-family: 'Share Tech Mono', monospace !important; }
[data-testid="stChatInput"] { border-top: 1px solid rgba(0,255,102,.25) !important; }
[data-testid="stExpander"] { border: 1px solid rgba(0,255,102,.32) !important; border-radius: 0 !important; background: rgba(0,38,18,.45); }
[data-testid="stExpander"] table { font-size: .85rem; }
/* ---------- Tab switch (MONITORING / SYMPTOM SEARCH) ---------- */
[data-testid="stMain"] [data-testid="stRadio"] [role="radiogroup"] { gap: 0 !important; }
[data-testid="stMain"] [data-testid="stRadio"] label { border: 1px solid rgba(0,255,102,.4); padding: 7px 22px; margin: 0 -1px 0 0;
    background: rgba(0,255,102,.05); font-family: 'Orbitron', sans-serif; letter-spacing: .14em; font-size: .72rem; }
[data-testid="stMain"] [data-testid="stRadio"] label:has(input:checked) { background: rgba(0,255,102,.2); box-shadow: 0 0 14px rgba(0,255,102,.5); border-color: #00ff66; }
[data-testid="stMain"] [data-testid="stRadio"] label > div:first-child { display: none; }
.chip { display: inline-block; font-family: 'Share Tech Mono', monospace; font-size: .8rem; letter-spacing: .06em; color: #eafff1;
    border: 1px solid #00ff66; background: rgba(0,255,102,.1); padding: 3px 10px; margin: 3px 6px 3px 0; }
.chip.red { border-color: #ff2d55; background: rgba(255,45,85,.12); color: #ff9db0; }
.chip.amber { border-color: #ffb300; background: rgba(255,179,0,.1); color: #ffd98a; }
.matchbar { height: 6px; background: rgba(0,255,102,.14); border-radius: 3px; margin: 4px 0 8px 0; }
.matchbar > div { height: 6px; border-radius: 3px; background: linear-gradient(90deg, #00803a, #00ff66); box-shadow: 0 0 8px #00ff66; }
.foot { text-align: center; font-family: 'Share Tech Mono', monospace; font-size: .7rem; color: #3b9a60; letter-spacing: .15em; margin-top: 20px; }
</style>
"""
st.markdown(HUD_CSS, unsafe_allow_html=True)


def H(markup: str):
    """Render HTML collapsed to one line (avoids Markdown code-block quirks)."""
    st.markdown(" ".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def ts(offset=0):
    return (now_utc() + datetime.timedelta(seconds=offset)).strftime("%H:%M:%S")


# =====================================================================
#  SESSION STATE
# =====================================================================
if "events" not in st.session_state:
    st.session_state.events = []
if "pending_cmd" not in st.session_state:
    st.session_state.pending_cmd = None
if "speak" not in st.session_state:
    st.session_state.speak = None

# -- Secure comms channel state --
if "chat_user" not in st.session_state:
    st.session_state.chat_user = ""
if "chat_room" not in st.session_state:
    st.session_state.chat_room = ""
if "show_comms" not in st.session_state:
    st.session_state.show_comms = False
if "show_rocket" not in st.session_state:
    st.session_state.show_rocket = False
if "show_fictional" not in st.session_state:
    st.session_state.show_fictional = False


@st.cache_resource
def get_comm_channels():
    """Shared, server-wide in-RAM store for the Secure Comms Channel.
    Structure: {"room_code": [{"user": ..., "text": ..., "time": ...}, ...]}"""
    return {}


comm_channels = get_comm_channels()


def queue_command():
    cmd = st.session_state.get("cmd_input", "").strip()
    if cmd:
        st.session_state.pending_cmd = cmd


def log_dose(playbook_id):
    st.session_state.events.append((ts(), "SYS", f"Protocol {playbook_id} applied / confirmed by crew. Logged to medical record."))
    st.toast(f"Protocol {playbook_id} application logged successfully!", icon="💊")


def chat_login():
    u = st.session_state.get("chat_user_input", "").strip()
    r = st.session_state.get("chat_room_input", "").strip()
    if u and r:
        st.session_state.chat_user = u
        st.session_state.chat_room = r
        if r not in comm_channels:
            comm_channels[r] = []
    else:
        st.session_state.chat_login_error = True


def chat_logout():
    st.session_state.chat_user = ""
    st.session_state.chat_room = ""


def toggle_comms():
    st.session_state.show_comms = not st.session_state.show_comms


def toggle_rocket():
    st.session_state.show_rocket = not st.session_state.show_rocket


def toggle_fictional():
    st.session_state.show_fictional = not st.session_state.show_fictional


def chat_send():
    msg = st.session_state.get("chat_box", "")
    if msg and msg.strip():
        comm_channels.setdefault(st.session_state.chat_room, []).append(
            {"user": st.session_state.chat_user, "text": msg.strip(), "time": ts()}
        )


# =====================================================================
#  SIDEBAR : MISSION CONTROL
# =====================================================================
st.sidebar.markdown("## ⬡ ICHOR CONTROL")
st.sidebar.caption("ICHOR MISSION INTERFACE v3.2")
st.sidebar.markdown("---")

st.sidebar.markdown("---")

# Real open-data subjects stored in the database + published cohort profiles used by the scenario simulator
_real_list = get_real_astronauts()
_real_map = {a['name']: a for a in _real_list}
_astro_options = list(_real_map) + [p for p in PROFILES if p not in _real_map]
astronaut = st.sidebar.selectbox("Astronaut / Cohort Profile", _astro_options, index=0)
REAL_ASTRO = _real_map.get(astronaut)       # dict from the database, or None for the simulated crew
REAL = REAL_ASTRO is not None
DASH = True      # the gauges / live vitals / console / playbooks are shown for EVERY astronaut (database ones included)
mission_day = st.sidebar.slider("Mission Day (Mars Transit)", 1, 180, 45)

st.sidebar.markdown("### 🛰️ Telemetry Override")
scenario = st.sidebar.radio("Select Mission Scenario:", SCENARIOS)
st.sidebar.markdown("---")
voice_on = st.sidebar.toggle("🔊 ICHOR Voice", value=False)
live_feed = st.sidebar.toggle("📡 Live vitals feed", value=True)
briefing_btn = st.sidebar.button("Voice briefing")

st.sidebar.markdown("---")
st.sidebar.markdown("### ☢️ 3D Organ Scan")
link_rad = st.sidebar.toggle("Link to mission radiation", value=True,
                             help="ON: exposure follows the cumulative radiation of the selected scenario (as a share of the 600 mSv career limit). OFF: use the manual slider.")
manual_rad = st.sidebar.slider("Manual exposure (%)", 0, 100, 0, disabled=link_rad)
view_angle = st.sidebar.slider("Viewing angle (°)", 0, 360, 0, step=15)
show_body = st.sidebar.checkbox("Show body outline", value=True)

# --- Secure comms category toggle (click to show/hide the panel) ---
st.sidebar.markdown("---")
st.sidebar.markdown("### 🔒 Categories")
comms_label = "📡 COMMUNICATIONS ▾" if st.session_state.show_comms else "📡 COMMUNICATIONS ▸"
st.sidebar.button(comms_label, on_click=toggle_comms, key="toggle_comms_btn", use_container_width=True)
rocket_label = "🧠 MENTAL HEALTH & 🚀 ROCKET ▾" if st.session_state.show_rocket else "🧠 MENTAL HEALTH & 🚀 ROCKET ▸"
st.sidebar.button(rocket_label, on_click=toggle_rocket, key="toggle_rocket_btn", use_container_width=True)
fict_label = "☢ FICTIONAL RADIATION DATA ▾" if st.session_state.show_fictional else "☢ FICTIONAL RADIATION DATA ▸"
st.sidebar.button(fict_label, on_click=toggle_fictional, key="toggle_fict_btn", use_container_width=True)
if st.session_state.chat_user and st.session_state.chat_room:
    st.sidebar.caption(f"ONLINE · {st.session_state.chat_user} · CHANNEL `******`")
    st.sidebar.button("Disconnect channel", on_click=chat_logout, key="sb_chat_logout")
else:
    st.sidebar.caption("OFFLINE · Press COMMUNICATIONS to connect.")


# =====================================================================
#  TABS: MONITORING dashboard  |  SYMPTOM SEARCH
#  (a radio styled as tabs; the search view stops the script before the dashboard renders)
# =====================================================================
_VIEWS = ["📊 MONITORING", "🔎 SYMPTOM SEARCH", "🧪 MEASUREMENTS"]
view = st.radio("View", _VIEWS, horizontal=True, label_visibility="collapsed", key="main_view")
if view == _VIEWS[1]:
    H(f"""
    <div class="top">
      <div class="reactor"><div class="r1"></div><div class="r2"></div><div class="r3"></div><div class="core"></div></div>
      <div>
        <div class="ttl">ICHOR</div>
        <div class="sub">SYMPTOM SEARCH · NASA MEDICAL KIT 3.001 DECISION SUPPORT · CREW: {astronaut.upper()}</div>
      </div>
    </div>
    """)
    render_search_panel(astronaut, REAL_ASTRO)
    H("""<div class="foot">PROJECT ICHOR · EDUCATIONAL DECISION SUPPORT — NOT A DIAGNOSIS · NOT FOR REAL MEDICAL USE</div>""")
    st.stop()
if view == _VIEWS[2]:
    H(f"""
    <div class="top">
      <div class="reactor"><div class="r1"></div><div class="r2"></div><div class="r3"></div><div class="core"></div></div>
      <div>
        <div class="ttl">ICHOR</div>
        <div class="sub">MEASUREMENT LOG · CREW: {astronaut.upper()}</div>
      </div>
    </div>
    """)
    render_measurements_panel(astronaut, REAL_ASTRO)
    H("""<div class="foot">PROJECT ICHOR · MEASUREMENTS ARE STORED IN THE CREW DATABASE</div>""")
    st.stop()

# =====================================================================
#  SCENARIO DATA (real_data.py: simulation around real published reference values)
# =====================================================================
T = NASA_THRESHOLDS
sim = simulate_scenario(astronaut, mission_day, scenario)
states = assess(sim)

rad_cum = sim["rad_msv"]       # mSv cumulative (incl. any solar particle event)
event_msv = sim["event_msv"]   # mSv from the current solar particle event
alc = sim["alc"]               # lymphocytes per microlitre
ocular = sim["iop"]            # intraocular pressure, mmHg
bmd_pct = sim["bmd_pct"]       # bone density change vs baseline, %
sleep_h = sim["sleep_h"]       # hours of sleep per night

rad_state = states["radiation"]
imm_state = states["immune"]
ocu_state = states["ocular"]
bmd_state = states["bone"]
slp_state = states["sleep"]

# Sleep deficit vs the 7 h lower bound of the recommendation (drives the vitals simulation)
sleep_deficit = max(0.0, T["sleep_rec_low_h"] - sleep_h)

telemetry = {
    "metadata": {"astronaut": astronaut, "day": mission_day, "time": now_utc().strftime("%H:%M:%S UTC")},
    "biometrics": {"rad": rad_cum, "alc": alc, "bmd_pct": bmd_pct, "ocular": ocular},
    "behavioral": {"sleep_h": sleep_h, "sentiment": "STRESSED/FATIGUED" if sleep_h < T["sleep_crit_h"] else "OPTIMAL"},
}


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


# --- Alerts (merged per playbook) ---
raw_alerts = build_raw_alerts(states, sim)

merged = {}
for sev, name, pid in raw_alerts:
    if pid not in merged:
        merged[pid] = {"severity": sev, "reasons": [name]}
    else:
        merged[pid]["reasons"].append(name)
        if sev == "CRITICAL":
            merged[pid]["severity"] = "CRITICAL"
alerts = sorted(merged.items(), key=lambda kv: 0 if kv[1]["severity"] == "CRITICAL" else 1)

# --- Crew Integrity Index (0-100, team-defined, NOT a clinical score) ---
integrity = crew_integrity(sim)
integ_state = "ok" if integrity >= 80 else "warn" if integrity >= 60 else "crit"

# =====================================================================
#  ICHOR BRAIN
# =====================================================================
def briefing():
    base = f"{astronaut}, mission day {mission_day}. Crew integrity stands at {integrity} percent. "
    if not alerts:
        return base + "All biometric parameters are within the reference limits. All systems nominal."
    reasons = "; ".join(r for _, d in alerts for r in d["reasons"])
    return base + f"I have detected {len(alerts)} active protocol{'s' if len(alerts) > 1 else ''}: {reasons}. Onboard playbooks are ready."


def ichor_reply(cmd: str) -> str:
    c = cmd.lower()
    if any(k in c for k in ("help", "commands", "what can")):
        return "Try: status, briefing, radiation, immune, eyes, bone, sleep, protocol, sources."
    if any(k in c for k in ("source", "real data", "reference")):
        return "Reference limits come from NASA STD-3001, the NASA Human Research Program and NLM REMM. Crew values are simulated. Open the data sources panel for details."
    if any(k in c for k in ("status", "brief", "report", "summary")):
        return briefing()
    if "radi" in c:
        extra = f" The current solar particle event dose is {event_msv:.0f} millisieverts against a {T['spe_limit_msv']:.0f} limit." if event_msv else ""
        return (f"Cumulative radiation is {rad_cum} millisieverts against a {T['max_cumulative_radiation_msv']:.0f} career limit."
                f"{extra} Status {STATE_TXT[rad_state].lower()}.")
    if "immun" in c or "lymph" in c:
        return (f"Lymphocyte count is {alc:,} per microlitre. Normal range is {T['alc_normal_low']:,.0f} to {T['alc_normal_high']:,.0f}; "
                f"early warning below {T['alc_warn']:,.0f}. Status {STATE_TXT[imm_state].lower()}.")
    if any(k in c for k in ("eye", "ocular", "sans", "pressure")):
        return f"Intraocular pressure reads {ocular} millimetres of mercury. Upper normal limit is {T['iop_normal_high']:.0f}. Status {STATE_TXT[ocu_state].lower()}."
    if any(k in c for k in ("bone", "bmd", "density")):
        return f"Bone density is {bmd_pct:+.1f} percent versus baseline. Warning at {T['bmd_warn_pct']:.0f} percent, critical at {T['bmd_crit_pct']:.0f}. Status {STATE_TXT[bmd_state].lower()}."
    if any(k in c for k in ("stress", "fatigue", "mental", "sleep", "cognitive")):
        return (f"Sleep is {sleep_h} hours per night against the {T['sleep_rec_low_h']:.0f} to {T['sleep_rec_high_h']:.0f} hour recommendation, "
                f"sentiment {telemetry['behavioral']['sentiment'].lower()}. Status {STATE_TXT[slp_state].lower()}.")
    if any(k in c for k in ("protocol", "playbook", "medic", "drug", "treat")):
        if not alerts:
            return "No clinical protocols are active, sir. Everything is quiet."
        return "Active protocols: " + ", ".join(PLAYBOOKS[p]["title"].split(" ")[1] + " " + p.replace("ASCLEPIUS_", "") for p, _ in alerts) + ". Scroll down for steps and reference doses. A flight surgeon decides on medication."
    return "I'm afraid I didn't catch that. Say 'help' for available queries."


# --- Process the pending command (if any) ---
if st.session_state.pending_cmd:
    cmd = st.session_state.pending_cmd
    reply = ichor_reply(cmd)
    st.session_state.events.append((ts(), "USER", f"> {cmd}"))
    st.session_state.events.append((ts(), "ICHOR", reply))
    st.session_state.speak = reply
    st.session_state.pending_cmd = None

if briefing_btn:
    st.session_state.events.append((ts(), "ICHOR", briefing()))
    st.session_state.speak = briefing()

# =====================================================================
#  HEADER
# =====================================================================
if DASH:
    ic = COL[integ_state]
    H(f"""
    <div class="top">
      <div class="reactor"><div class="r1"></div><div class="r2"></div><div class="r3"></div><div class="core"></div></div>
      <div>
        <div class="ttl">ICHOR</div>
        <div class="sub">AUTONOMOUS ONBOARD HEALTH MONITORING · EDGE INTELLIGENCE · CREW: {astronaut.upper()}</div>
      </div>
      <div class="spacer"></div>
      <div class="big"><div class="v" style="color:{ic};text-shadow:0 0 16px {ic}">{integrity}%</div><div class="l">CREW INTEGRITY INDEX · TEAM-DEFINED</div></div>
    </div>
    """)

    if not alerts:
        H(f"""<div class="banner ok">🟢 STATUS: NOMINAL<br><small>All biometric parameters of {astronaut} are within the reference limits.</small></div>""")
    else:
        H(f"""<div class="banner bad">🚨 STATUS: ANOMALY DETECTED<br><small>{len(alerts)} active protocol(s) detected. Protective measures start immediately without waiting for Earth; medication is decided only by the flight surgeon.</small></div>""")

    H("""<div class="prov"><b>DATA PROVENANCE</b> · Limits and reference values: <b>real, published</b> (NASA-STD-3001, NASA HRP, NLM REMM, NHLBI) ·
    Baseline sleep of the selected cohort: <b>real</b> (Barger et al. 2014) · Day-by-day scenario values: <b>simulated</b> around these numbers · Early-warning limits and Crew Integrity Index: <b>team-defined</b> (not official NASA limits).
    See the "DATA SOURCES" panel at the bottom for links.</div>""")

    pct = mission_day / 180 * 100
    H(f"""
    <div class="hud"><div class="mission">
      <span>🌍 EARTH</span>
      <div class="track"><div class="fill" style="width:{pct:.1f}%"></div><div class="ship" style="left:{pct:.1f}%">🚀</div></div>
      <span>MARS 🔴</span>
      <span style="color:#eafff1">DAY {mission_day}/180 &nbsp;·&nbsp; T-{180 - mission_day}d TO ORBIT INSERTION</span>
    </div></div>
    """)
else:
    H(f"""
    <div class="top">
      <div class="reactor"><div class="r1"></div><div class="r2"></div><div class="r3"></div><div class="core"></div></div>
      <div>
        <div class="ttl">ICHOR</div>
        <div class="sub">AUTONOMOUS ONBOARD HEALTH MONITORING · REAL DATABASE · CREW: {astronaut.upper()}</div>
      </div>
    </div>
    """)


# =====================================================================
#  GAUGES
# =====================================================================
def gauge(label, big, unit, frac, state, note):
    frac = clamp(frac, 0.03, 1.0)
    col = COL[state]
    C = 2 * math.pi * 52
    return f"""
    <div class="hud gauge">
      <div class="g-label">{label}</div>
      <svg viewBox="0 0 140 140">
        <circle cx="70" cy="70" r="65" class="g-dots"/>
        <circle cx="70" cy="70" r="52" class="g-bg"/>
        <circle cx="70" cy="70" r="52" class="g-fg" transform="rotate(-90 70 70)"
                style="stroke:{col};stroke-dasharray:{frac * C:.1f} {C:.1f};filter:drop-shadow(0 0 6px {col})"/>
        <text x="70" y="72" text-anchor="middle" class="g-val" style="fill:{col}">{big}</text>
        <text x="70" y="90" text-anchor="middle" class="g-unit">{unit}</text>
      </svg>
      <div class="g-note" style="color:{col}">{STATE_TXT[state]} · {note}</div>
    </div>"""


rad_frac = max(rad_cum / T["max_cumulative_radiation_msv"], event_msv / T["spe_limit_msv"])
rad_note = f"SPE {event_msv:.0f}/{T['spe_limit_msv']:.0f}" if event_msv else f"LIM {T['max_cumulative_radiation_msv']:.0f}"

if DASH:
    g = st.columns(5)
    with g[0]:
        H(gauge("RADIATION", f"{rad_cum}", "mSv CUMULATIVE", rad_frac, rad_state, rad_note))
    with g[1]:
        H(gauge("LYMPHOCYTES", f"{alc:,}", "CELLS / µL", alc / T["alc_normal_high"], imm_state, f"MIN {T['alc_normal_low']:,.0f}"))
    with g[2]:
        H(gauge("OCULAR · SANS", f"{ocular}", "mmHg", (ocular - 10) / 20, ocu_state, f"LIM {T['iop_normal_high']:.0f}"))
    with g[3]:
        H(gauge("BONE DENSITY", f"{bmd_pct:+.1f}%", "BMD VS BASELINE", abs(bmd_pct) / abs(T["bmd_crit_pct"]), bmd_state, f"CRIT {T['bmd_crit_pct']:.0f}%"))
    with g[4]:
        H(gauge("SLEEP", f"{sleep_h}", "HOURS / NIGHT", sleep_h / T["sleep_rec_high_h"], slp_state, f"REC {T['sleep_rec_low_h']:.0f}-{T['sleep_rec_high_h']:.0f} h"))


# ---- 3D body model of the selected astronaut (Theo's database), right under the gauges ----
render_body_compact(astronaut, view_angle=view_angle, show_body=show_body)
render_radiation_chooser(astronaut, view_angle=view_angle, show_body=show_body)

# =====================================================================
#  LIVE VITALS (auto-refresh fragment) + ICHOR CONSOLE
#  (heart rate / SpO2 / resp / HRV are a purely cosmetic simulated stream)
# =====================================================================
def ecg_points(hr, n=300, w=600, h=130):
    beats = hr / 60 * 6.0
    period = n / beats
    offset = (time.time() * n / 6.0) % period
    pts = []
    for i in range(n):
        p = ((i + offset) % period) / period
        y = 0.0
        if 0.10 < p < 0.16:
            y = 0.15 * math.sin((p - 0.10) / 0.06 * math.pi)
        elif 0.20 < p < 0.22:
            y = -0.15
        elif 0.22 < p < 0.26:
            y = 1.0 - abs((p - 0.24) / 0.02)
        elif 0.26 < p < 0.28:
            y = -0.25
        elif 0.38 < p < 0.50:
            y = 0.30 * math.sin((p - 0.38) / 0.12 * math.pi)
        yy = h / 2 + 8 - y * h * 0.42 + random.uniform(-0.7, 0.7)
        pts.append(f"{i * w / (n - 1):.1f},{yy:.1f}")
    return " ".join(pts)


def live_vitals():
    storm = scenario.startswith("Solar")
    hr = int(66 + sleep_deficit * 11 + (14 if storm else 0) + random.uniform(-2, 2))
    spo2 = random.choice([98, 98, 99, 97]) - (1 if storm else 0)
    resp = random.randint(13, 18) + (3 if sleep_h < T["sleep_crit_h"] else 0)
    hrv = int(62 - sleep_deficit * 15 + random.uniform(-3, 3))
    col = "#ff2d55" if hr > 100 else "#00ff66"
    H(f"""
    <div class="hud"><div class="p-title">◉ LIVE BIOMETRIC STREAM (SIMULATED) · {astronaut.upper()} · {now_utc().strftime('%H:%M:%S')} UTC</div>
    <svg class="ecg" viewBox="0 0 600 130" preserveAspectRatio="none">
      <polyline points="{ecg_points(hr)}" fill="none" stroke="{col}" stroke-width="2"
                style="filter:drop-shadow(0 0 5px {col})"/>
    </svg>
    <div class="vit">
      <div><b>{hr}</b><span>HEART RATE · BPM</span></div>
      <div><b>{spo2}%</b><span>SpO₂</span></div>
      <div><b>{resp}</b><span>RESP · /MIN</span></div>
      <div><b>{hrv}</b><span>HRV · ms</span></div>
    </div></div>
    """)


if DASH:
    live_vitals = st.fragment(run_every=2 if live_feed else None)(live_vitals) if hasattr(st, "fragment") else live_vitals

    left, right = st.columns([3, 2])

    with left:
        live_vitals()

    with right:
        boot = [
            (ts(-9), "SYS", "ICHOR core online. Neural link established."),
            (ts(-8), "ICHOR", f"Biometric uplink synchronized: {astronaut}."),
            (ts(-7), "SYS", "Reference limits loaded (NASA-STD-3001 / HRP). Crew values simulated. Earth comms latency up to 22 min."),
            (ts(-6), "ICHOR", "Autonomous clinical mode engaged. Good to see you, sir."),
        ]
        sev_tag = {"CRITICAL": "ALERT", "WARNING": "WARN"}
        alert_rows = [(ts(-3), sev_tag[d["severity"]], f"{d['severity']}: " + " + ".join(d["reasons"])) for _, d in alerts]
        rows = boot + alert_rows + st.session_state.events
        rows = rows[-14:]
        lines = "".join(
            f'<div><span class="t">[{t}]</span> <span class="tag {tag}">{tag}</span> {msg}</div>' for t, tag, msg in rows
        )
        H(f"""<div class="hud"><div class="p-title">◉ ICHOR CONSOLE</div>
             <div class="console">{lines}<div><span class="cursor"></span></div></div></div>""")

        with st.form("cmd_form", clear_on_submit=True):
            st.text_input("Voice / text command", key="cmd_input", placeholder="status · radiation · immune · eyes · bone · sleep · protocol · sources · help")
            st.form_submit_button("⏎ TRANSMIT", on_click=queue_command)

# =====================================================================
#  VITAL SIGNS · 3D BODY MODEL + HEALTH TREND for the selected astronaut (Theo's database)
#  Shown for EVERY astronaut (Alex Morgan, Sarah Chen, James Wilson ...), right under the live vitals.
# =====================================================================
if not _real_list:
    st.error("Database not found or empty, so the 3D body model cannot be drawn. Put schema.sql and seed.sql in the 'database' folder, "
             "run  python setup_db.py  (delete an old database/nasaspacechallenge.db first) and reload this page.")
else:
    _sel_astro = REAL_ASTRO or next((a for a in _real_list if a["name"] == astronaut), _real_list[0])
    render_radiation_panel(view_angle=view_angle, show_body=show_body, astronaut_id=_sel_astro["id"])

# =====================================================================
#  SECURE COMMS CHANNEL (code-locked, shared crew-to-crew chat)
#  Only rendered while the "📡 COMMUNICATIONS" category is toggled open.
# =====================================================================
if st.session_state.show_comms:
    st.markdown("### 🔒 SECURE COMMS CHANNEL")

    if not st.session_state.chat_user or not st.session_state.chat_room:
        st.markdown('<div class="hud">', unsafe_allow_html=True)
        H("""<div class="p-title">◉ CHANNEL AUTHENTICATION REQUIRED</div>
             <div class="chat-lock">Enter a callsign and a channel code. Everyone who uses the same code shares the same encrypted channel.</div>""")
        with st.form("chat_login_form"):
            lc1, lc2 = st.columns(2)
            with lc1:
                st.text_input("Callsign", key="chat_user_input", placeholder="e.g. CDR Alpha")
            with lc2:
                st.text_input("Channel code", key="chat_room_input", type="password", placeholder="shared channel code")
            st.form_submit_button("🔓 DECRYPT CHANNEL", on_click=chat_login)
        if st.session_state.pop("chat_login_error", False):
            st.warning("Both fields are required.")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        def render_chat():
            room = st.session_state.chat_room
            msgs = comm_channels.get(room, [])
            H(f'<div class="p-title">◉ CHANNEL ONLINE · {st.session_state.chat_user.upper()} · LOCK `******` · {len(msgs)} MSG</div>')
            if not msgs:
                H('<div class="chat-lock">Channel active. Waiting for incoming crew messages...</div>')
            else:
                rows = "".join(
                    f'<div class="chat-msg {"me" if m["user"] == st.session_state.chat_user else ""}">'
                    f'<span class="who">[{m["time"]}] {m["user"]}</span>{m["text"]}</div>'
                    for m in msgs[-50:]
                )
                H(f'<div class="console">{rows}</div>')

        render_chat = st.fragment(run_every=2)(render_chat) if hasattr(st, "fragment") else render_chat

        st.markdown('<div class="hud">', unsafe_allow_html=True)
        render_chat()
        st.markdown("</div>", unsafe_allow_html=True)

        cc1, cc2 = st.columns([6, 1])
        with cc1:
            st.text_input("Message", key="chat_box", placeholder="Write an encrypted message to the channel...", label_visibility="collapsed", on_change=chat_send)
        with cc2:
            st.button("EXIT", on_click=chat_logout, key="main_chat_logout")

# ---- Rocket panel renders further down (toggled via the 🚀 ROCKET category) ----

# =====================================================================
#  ROCKET · ORBITAL DEFENSE (spaceship vs. alien ships)
#  Blended look: ICHOR's HUD chrome (Orbitron/Share Tech Mono, green
#  scanlines + grid + corner brackets + glow) wraps a NASA-insignia
#  colored interceptor and alien craft (blue #0B3D91 / red #FC3D21 /
#  white), with thin cyan rim accents tying the ships into the rest
#  of the dashboard. Rendering stays flat (no per-frame shadowBlur)
#  and star/enemy/particle counts are trimmed for smooth performance.
#  100% original canvas drawing + vanilla JS + WebAudio beeps.
#  No external game libraries, images, or copyrighted assets.
# =====================================================================
ROCKET_HTML = """
<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@600;800&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
  :root{ --cyan:#00ff66; --blue:#0B3D91; --red:#FC3D21; --white:#FFFFFF; --ink:#020d05; }
  *{box-sizing:border-box;}
  html,body{margin:0;height:100%;background:var(--ink);overflow:hidden;
    font-family:'Share Tech Mono',ui-monospace,Consolas,monospace;color:#d4ffe2;}
  .frame{position:relative;width:100%;height:100%;}
  .hudbar{display:flex;justify-content:space-between;padding:8px 14px;
    font-family:'Orbitron',sans-serif;font-size:11px;letter-spacing:.14em;color:#6fe89a;
    border-bottom:1px solid rgba(0,255,102,.35);background:rgba(0,30,15,.65);}
  .hudbar b{color:var(--white);font-size:13px;text-shadow:0 0 6px var(--cyan);}
  #stage{position:relative;width:100%;height:calc(100% - 38px);
    background:
      radial-gradient(ellipse at 50% 0%, rgba(0,255,102,.07), transparent 60%),
      linear-gradient(rgba(0,255,102,.05) 1px, transparent 1px) 0 0/100% 30px,
      linear-gradient(90deg, rgba(0,255,102,.05) 1px, transparent 1px) 0 0/30px 100%,
      var(--ink);}
  canvas{display:block;width:100%;height:100%;}
  .scan{position:absolute;inset:0;pointer-events:none;
    background:repeating-linear-gradient(rgba(0,0,0,0) 0 2px, rgba(0,0,0,.2) 3px 4px);
    mix-blend-mode:multiply;}
  .vign{position:absolute;inset:0;pointer-events:none;box-shadow:inset 0 0 70px rgba(0,0,0,.8);}
  .corner{position:absolute;width:13px;height:13px;border:2px solid var(--cyan);pointer-events:none;opacity:.8;}
  .c-tl{top:4px;left:4px;border-right:none;border-bottom:none;}
  .c-br{bottom:4px;right:4px;border-left:none;border-top:none;}
  .ov{position:absolute;inset:38px 0 0 0;display:flex;flex-direction:column;align-items:center;
    justify-content:center;gap:12px;background:rgba(2,13,5,.9);text-align:center;padding:16px;}
  .ov h1{font-family:'Orbitron',sans-serif;font-size:clamp(14px,4vw,20px);color:var(--cyan);
    text-shadow:0 0 10px var(--cyan);margin:0;letter-spacing:.14em;text-transform:uppercase;
    padding-bottom:8px;border-bottom:3px solid transparent;
    border-image:linear-gradient(90deg,var(--blue),var(--red)) 1;}
  .ov p{font-size:9px;line-height:1.9;color:#8fe8af;margin:0;max-width:380px;letter-spacing:.04em;}
  button.go{font-family:'Orbitron',sans-serif;font-size:10px;letter-spacing:.14em;padding:11px 22px;
    text-transform:uppercase;background:rgba(0,255,102,.08);color:var(--cyan);
    border:1px solid var(--cyan);cursor:pointer;box-shadow:0 0 14px rgba(0,255,102,.45);}
  button.go:hover{background:var(--cyan);color:#001a0a;}
  .hidden{display:none !important;}
  .touch{position:absolute;left:0;right:0;bottom:8px;display:flex;justify-content:center;gap:10px;}
  .tbtn{font-family:'Orbitron',sans-serif;font-size:13px;width:48px;height:42px;
    border:1px solid var(--cyan);background:rgba(0,255,102,.08);color:var(--cyan);}
  .tbtn:active{background:rgba(0,255,102,.3);}
  .fire{width:74px;border-color:var(--red);color:var(--red);background:rgba(252,61,33,.08);}
  .fire:active{background:rgba(252,61,33,.3);}
</style></head>
<body>
<div class="frame">
  <div class="hudbar">
    <span>SCORE <b id="score">0</b></span>
    <span>WAVE <b id="wave">1</b></span>
    <span>HULL <b id="lives">III</b></span>
  </div>
  <div id="stage">
    <canvas id="c"></canvas>
    <div class="scan"></div><div class="vign"></div>
    <div class="corner c-tl"></div><div class="corner c-br"></div>
    <div class="ov" id="ov">
      <h1>◉ Orbital Defense Grid</h1>
      <p>Alien craft are closing on the station. Launch the interceptor and hold the line.<br>
      ◀ ▶ / A D to steer · SPACE to fire</p>
      <button class="go" id="start">Engage</button>
    </div>
  </div>
  <div class="touch">
    <button class="tbtn" id="bL">◀</button>
    <button class="tbtn fire" id="bF">FIRE</button>
    <button class="tbtn" id="bR">▶</button>
  </div>
</div>
<script>
(function(){
var cv=document.getElementById('c'), ctx=cv.getContext('2d', {alpha:false}), stage=document.getElementById('stage');
var ov=document.getElementById('ov'), startBtn=document.getElementById('start');
var scoreEl=document.getElementById('score'), waveEl=document.getElementById('wave'), livesEl=document.getElementById('lives');
var W=640,H=420,DPR=1;
function resize(){
  var r=stage.getBoundingClientRect();
  DPR=Math.min(window.devicePixelRatio||1,1.5);
  W=r.width; H=r.height;
  cv.width=Math.round(W*DPR); cv.height=Math.round(H*DPR);
  ctx.setTransform(DPR,0,0,DPR,0,0);
}
window.addEventListener('resize', resize);

/* light WebAudio beeps, created once and reused (no asset loading) */
var actx;
function beep(freq,dur,type,gain){
  try{
    actx = actx || new (window.AudioContext||window.webkitAudioContext)();
    var o=actx.createOscillator(), g=actx.createGain();
    o.type=type||'square'; o.frequency.value=freq; g.gain.value=gain||0.04;
    o.connect(g); g.connect(actx.destination);
    o.start(); g.gain.exponentialRampToValueAtTime(0.0001, actx.currentTime+dur);
    o.stop(actx.currentTime+dur);
  }catch(e){}
}

var keys={}, running=false, score=0, wave=1, lives=3;
var player, bullets, enemies, ebullets, stars, particles, dir=1, dropTimer=0;

function initStars(){
  stars=[];
  for(var i=0;i<34;i++) stars.push({x:Math.random()*W,y:Math.random()*H,s:Math.random()*1.6+0.6,v:Math.random()*16+6});
}

function spawnWave(){
  enemies=[];
  var cols=5, rows=3, gx=64, gy=46, ox=60, oy=40;
  for(var r=0;r<rows;r++){
    for(var c=0;c<cols;c++){
      enemies.push({x:ox+c*gx, y:oy+r*gy, w:30, h:18, alive:true,
        type:r===0?2:(r===1?1:0), phase:Math.random()*Math.PI*2});
    }
  }
  dir=1; dropTimer=0;
}

function resetGame(){
  player={x:W/2-16, y:H-44, w:32, h:26, speed:230, cool:0};
  bullets=[]; ebullets=[]; particles=[];
  score=0; wave=1; lives=3;
  initStars(); spawnWave(); updateHud();
}

function romanLives(n){
  var map=['', 'I', 'II', 'III', 'IIII', 'IIIII'];
  return n>0 ? (map[n]||String(n)) : '—';
}
function updateHud(){
  scoreEl.textContent=score; waveEl.textContent=wave;
  livesEl.textContent=romanLives(lives);
}

window.addEventListener('keydown', function(e){
  keys[e.key.toLowerCase()]=true;
  if(e.key===' ') e.preventDefault();
});
window.addEventListener('keyup', function(e){ keys[e.key.toLowerCase()]=false; });

function bindHold(id,key){
  var el=document.getElementById(id);
  var on=function(e){ e.preventDefault(); keys[key]=true; };
  var off=function(e){ e.preventDefault(); keys[key]=false; };
  el.addEventListener('touchstart',on,{passive:false});
  el.addEventListener('touchend',off);
  el.addEventListener('mousedown',on);
  el.addEventListener('mouseup',off);
  el.addEventListener('mouseleave',off);
}
bindHold('bL','arrowleft'); bindHold('bR','arrowright'); bindHold('bF',' ');

startBtn.addEventListener('click', function(){
  ov.classList.add('hidden');
  resetGame(); running=true; last=performance.now();
  requestAnimationFrame(loop);
});

function fire(){
  if(player.cool>0) return;
  bullets.push({x:player.x+player.w/2-2, y:player.y-4, w:4, h:12, vy:-440});
  player.cool=0.26; beep(680,0.06,'square',0.035);
}
function enemyFire(){
  enemies.forEach(function(e){
    if(e.alive && Math.random()<0.012) ebullets.push({x:e.x+e.w/2-3, y:e.y+e.h, w:6, h:6, vy:220});
  });
}
function explode(x,y,col){
  for(var i=0;i<6;i++){
    var a=Math.random()*Math.PI*2, sp=Math.random()*110+40;
    particles.push({x:x,y:y,vx:Math.cos(a)*sp,vy:Math.sin(a)*sp,life:0.4,col:col});
  }
  beep(150,0.12,'sawtooth',0.04);
}
function gameOver(win){
  running=false;
  ov.classList.remove('hidden');
  ov.innerHTML='<h1 style="color:'+(win?'#00ff66':'#FC3D21')+';text-shadow:0 0 10px '+(win?'#00ff66':'#FC3D21')+'">'+(win?'Sector Cleared':'Hull Breached')+
    '</h1><p>Final score '+score+'<br>'+(win?'Reinforcements inbound...':'The alien wing broke through the line.')+
    '</p><button class="go" id="again">Relaunch</button>';
  document.getElementById('again').addEventListener('click', function(){
    ov.classList.add('hidden'); resetGame(); running=true; last=performance.now();
    requestAnimationFrame(loop);
  });
}

var last=0;
function loop(now){
  if(!running) return;
  var dt=Math.min((now-last)/1000,0.05); last=now;
  update(dt); draw();
  requestAnimationFrame(loop);
}

function update(dt){
  if(keys['arrowleft']||keys['a']) player.x -= player.speed*dt;
  if(keys['arrowright']||keys['d']) player.x += player.speed*dt;
  player.x=Math.max(4, Math.min(W-player.w-4, player.x));
  player.cool=Math.max(0, player.cool-dt);
  if(keys[' ']||keys['spacebar']) fire();

  for(var i=bullets.length-1;i>=0;i--){ bullets[i].y+=bullets[i].vy*dt; if(bullets[i].y+bullets[i].h<0) bullets.splice(i,1); }
  for(var j=ebullets.length-1;j>=0;j--){ ebullets[j].y+=ebullets[j].vy*dt; if(ebullets[j].y>H) ebullets.splice(j,1); }

  var minX=Infinity, maxX=-Infinity, liveCount=0;
  enemies.forEach(function(e){ if(e.alive){ minX=Math.min(minX,e.x); maxX=Math.max(maxX,e.x+e.w); liveCount++; } });
  var speed=26+wave*7+(15-liveCount)*1.1;
  if(minX<=10 || maxX>=W-10){
    if(dropTimer<=0){ enemies.forEach(function(e){ e.y+=14; }); dir*=-1; dropTimer=0.4; }
  }
  dropTimer=Math.max(0, dropTimer-dt);
  enemies.forEach(function(e){ if(e.alive){ e.x+=dir*speed*dt; e.phase+=dt*3; } });
  enemyFire();

  bullets.forEach(function(b){
    enemies.forEach(function(e){
      if(e.alive && b.x<e.x+e.w && b.x+b.w>e.x && b.y<e.y+e.h && b.y+b.h>e.y){
        e.alive=false; b.y=-999; score+=(e.type+1)*10;
        explode(e.x+e.w/2, e.y+e.h/2, e.type===2?'#FC3D21':e.type===1?'#0B3D91':'#00ff66');
        updateHud();
      }
    });
  });
  ebullets.forEach(function(b){
    if(b.x<player.x+player.w && b.x+b.w>player.x && b.y<player.y+player.h && b.y+b.h>player.y){
      b.y=9999; lives-=1; updateHud();
      explode(player.x+player.w/2, player.y+player.h/2, '#FC3D21');
      if(lives<=0) gameOver(false);
    }
  });
  for(var k=0;k<enemies.length;k++){ if(enemies[k].alive && enemies[k].y+enemies[k].h>=player.y){ gameOver(false); break; } }

  for(var p=particles.length-1;p>=0;p--){ var pt=particles[p]; pt.x+=pt.vx*dt; pt.y+=pt.vy*dt; pt.life-=dt; if(pt.life<=0) particles.splice(p,1); }
  stars.forEach(function(s){ s.y+=s.v*dt; if(s.y>H){ s.y=0; s.x=Math.random()*W; } });

  if(liveCount===0 && running){
    wave+=1; updateHud(); bullets=[]; ebullets=[]; spawnWave();
  }
}

/* NASA-colored craft, ICHOR-style thin cyan rim accents; flat fills only
   (no per-frame shadowBlur) so it stays cheap to render every frame. */
function drawPlayerShip(x,y,w,h){
  ctx.save(); ctx.translate(x,y);
  var flameLen=7+Math.random()*6;
  ctx.fillStyle='#FC3D21';
  ctx.beginPath();
  ctx.moveTo(w*0.34,h); ctx.lineTo(w*0.5,h+flameLen); ctx.lineTo(w*0.66,h);
  ctx.closePath(); ctx.fill();
  ctx.fillStyle='#FFFFFF';
  ctx.beginPath();
  ctx.moveTo(w/2,0); ctx.lineTo(w*0.85,h*0.78); ctx.lineTo(w*0.65,h);
  ctx.lineTo(w*0.35,h); ctx.lineTo(w*0.15,h*0.78);
  ctx.closePath(); ctx.fill();
  ctx.strokeStyle='#00ff66'; ctx.lineWidth=1; ctx.globalAlpha=.8; ctx.stroke(); ctx.globalAlpha=1;
  ctx.fillStyle='#0B3D91';
  ctx.fillRect(1,h*0.55,5,h*0.32); ctx.fillRect(w-6,h*0.55,5,h*0.32);
  ctx.fillStyle='#0B3D91';
  ctx.beginPath(); ctx.ellipse(w/2,h*0.38,3.5,5,0,0,Math.PI*2); ctx.fill();
  ctx.restore();
}

function drawAlienShip(e){
  if(!e.alive) return;
  var col = e.type===2?'#FC3D21':e.type===1?'#0B3D91':'#C9D2DC';
  var bob=Math.sin(e.phase)*2.2;
  ctx.save(); ctx.translate(e.x+e.w/2, e.y+e.h/2+bob);
  ctx.strokeStyle='#00ff66'; ctx.globalAlpha=.4; ctx.lineWidth=1;
  ctx.beginPath(); ctx.ellipse(0,4,e.w/2+3,7,0,0,Math.PI*2); ctx.stroke();
  ctx.globalAlpha=1;
  ctx.fillStyle=col;
  ctx.beginPath(); ctx.ellipse(0,4,e.w/2,6,0,0,Math.PI*2); ctx.fill();
  ctx.beginPath(); ctx.arc(0,-1,7,Math.PI,0); ctx.fill();
  ctx.fillStyle='#020d05';
  ctx.beginPath(); ctx.arc(0,-1,3.5,Math.PI,0); ctx.fill();
  ctx.restore();
}

function draw(){
  ctx.fillStyle='#020d05'; ctx.fillRect(0,0,W,H);
  ctx.fillStyle='#6fe89a';
  stars.forEach(function(s){ ctx.fillRect(s.x,s.y,s.s,s.s); });

  drawPlayerShip(player.x, player.y, player.w, player.h);

  ctx.fillStyle='#00e5ff';
  bullets.forEach(function(b){ ctx.fillRect(b.x,b.y,b.w,b.h); });
  ctx.fillStyle='#FC3D21';
  ebullets.forEach(function(b){ ctx.beginPath(); ctx.arc(b.x+3,b.y+3,3.5,0,Math.PI*2); ctx.fill(); });

  enemies.forEach(drawAlienShip);

  particles.forEach(function(p){ ctx.globalAlpha=Math.max(p.life,0)/0.4; ctx.fillStyle=p.col; ctx.fillRect(p.x,p.y,3,3); });
  ctx.globalAlpha=1;
}

resize(); initStars(); draw();
})();
</script>
</body></html>
"""

# =====================================================================
#  3D ORGAN RADIATION SCAN
# =====================================================================
STATUS_ORDER = ["Normal", "Exposed", "Critical Stage"]
STATUS_COLORS_3D = {"Normal": "#00ff66", "Exposed": "#ffb300", "Critical Stage": "#ff2d55"}
BODY_COLOR = "#6fe89a"


# x = left/right, y = front/back (depth), z = height
@st.cache_data
def generate_organ_cells():
    r = np.random.default_rng(42)
    organs = {
        "Brain":      {"c": (0.0, 0.0, 8.0),  "r": (1.5, 1.2, 1.2), "count": 140},
        "Heart":      {"c": (0.0, 0.3, 3.5),  "r": (0.6, 0.7, 0.8), "count": 80},
        "Left Lung":  {"c": (-1.7, 0.0, 3.8), "r": (0.8, 1.0, 1.8), "count": 110},
        "Right Lung": {"c": (1.7, 0.0, 3.8),  "r": (0.8, 1.0, 1.8), "count": 110},
        "Liver":      {"c": (-1.2, 0.2, 1.2), "r": (1.1, 0.9, 0.8), "count": 90},
        "Stomach":    {"c": (1.1, 0.2, 1.0),  "r": (1.0, 0.8, 0.8), "count": 90},
    }
    frames = []
    for name, cfg in organs.items():
        n = cfg["count"]
        direction = r.normal(size=(n, 3))
        direction /= np.linalg.norm(direction, axis=1, keepdims=True)
        radius = r.random(n) ** (1 / 3)
        pts = direction * radius[:, None] * np.array(cfg["r"]) + np.array(cfg["c"])
        frames.append(pd.DataFrame({
            "Organ": name,
            "x": pts[:, 0], "y": pts[:, 1], "z": pts[:, 2],
            "Tolerance": r.uniform(-8, 8, n),  # individual cellular tolerance
        }))
    return pd.concat(frames, ignore_index=True)


def spow(v, e):
    return np.sign(v) * np.abs(v) ** e


def superellipsoid(center, radii, e1, e2, n=40):
    u = np.linspace(-np.pi / 2, np.pi / 2, n)
    v = np.linspace(-np.pi, np.pi, n)
    u, v = np.meshgrid(u, v)
    x = center[0] + radii[0] * spow(np.cos(u), e1) * spow(np.cos(v), e2)
    y = center[1] + radii[1] * spow(np.cos(u), e1) * spow(np.sin(v), e2)
    z = center[2] + radii[2] * spow(np.sin(u), e1)
    return x, y, z


def add_body_shell(fig, center, radii, e1, e2):
    x, y, z = superellipsoid(center, radii, e1, e2)
    fig.add_trace(go.Surface(
        x=x, y=y, z=z, colorscale=[[0, BODY_COLOR], [1, BODY_COLOR]],
        showscale=False, opacity=0.12, hoverinfo="skip", showlegend=False,
    ))


def build_organ_figure(cells, angle, body):
    fig = go.Figure()
    if body:
        add_body_shell(fig, (0, 0, 8.0), (2.0, 1.6, 1.5), 1.0, 1.0)   # Head
        add_body_shell(fig, (0, 0, 2.5), (3.5, 1.8, 4.0), 0.35, 0.6)  # Torso
    for status in STATUS_ORDER:
        grp = cells[cells["Status"] == status]
        if grp.empty:
            continue
        fig.add_trace(go.Scatter3d(
            x=grp["x"], y=grp["y"], z=grp["z"], mode="markers", name=status,
            marker=dict(color=STATUS_COLORS_3D[status], size=5, opacity=0.95, line=dict(width=1, color="white")),
            text=[f"Organ: {o}<br>Exposure: {e:.1f}%<br>Condition: {status}"
                  for o, e in zip(grp["Organ"], grp["Exposure_Pct"])],
            hoverinfo="text",
        ))
    a = np.deg2rad(angle)
    eye = dict(x=2.2 * np.sin(a), y=-2.2 * np.cos(a), z=0.5)
    hidden = dict(visible=False)
    fig.update_layout(
        height=560, paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=0, b=0),
        legend=dict(font=dict(color="#d4ffe2")),
        uirevision=f"view-{angle}",  # slider resets the camera, other changes keep your drag
        scene=dict(xaxis=hidden, yaxis=hidden, zaxis=hidden, bgcolor="rgba(0,0,0,0)",
                   aspectmode="data", camera=dict(eye=eye, up=dict(x=0, y=0, z=1))),
    )
    return fig



# ---- ORION spacecraft 3D (outside / inside, radiation colors per room) ----
st.markdown("### 🛰 ORION · RADIATION MAP (3D)")
_orion_dose, _orion_src = radiation_input(REAL_ASTRO, event_msv, scenario)
render_orion(_orion_dose, _orion_src, height=800)
st.caption("Orion geometry: public NASA / ESA / Lockheed Martin / Airbus figures. Interior layout is schematic and the per-room "
           "shielding factors are team assumptions. Needs internet in the browser (three.js).")

# ---- DEMO: run ALL the algorithms once (python run_all.py nolive, ~1 minute) and show the results in plain words ----
#      forecast -> shielding -> alert -> health, the 14-day mission with the real solar storm of 11 November 2025
st.markdown("### ▶ DEMO · ALL THE ALGORITHMS")
st.caption("Forecast → shielding → alert → health: the 14-day mission with the real solar storm of 11 November 2025 "
           "and the astronauts of the database. About 1 minute.")
if st.button("▶ RUN THE DEMO (run_all.py nolive)", key="run_all_demo_btn"):
    import os
    import subprocess
    import sys
    _here = os.path.dirname(os.path.abspath(__file__))
    with st.spinner("Running all the algorithms (about 1 minute)..."):
        _run = subprocess.run([sys.executable, os.path.join(_here, "run_all.py"), "nolive"], cwd=_here,
                              capture_output=True, text=True, env=dict(os.environ, PYTHONWARNINGS="ignore"))
    if _run.returncode == 0 and "FAILED" not in _run.stdout:
        st.success("Done: every step OK.")
    else:
        st.error("A step failed: see what run_all.py printed.")
    with st.expander("What run_all.py printed"):
        st.code(_run.stdout + _run.stderr)
    _box = {"green": st.success, "yellow": st.warning, "red": st.error}
    for _title, _path in {"🚨 Alert": ("warning", "alert_readable.json"),
                          "🧭 Where to go": ("shielding", "shielding_readable.json"),
                          "❤️ Health": ("health", "health_readable.json"),
                          "🎬 The 14-day mission": ("warning", "crew_routes_readable.json")}.items():
        _file = os.path.join(_here, _path[0], "data", _path[1])
        if not os.path.exists(_file):
            continue
        _r = json.load(open(_file, encoding="utf-8"))
        st.markdown(f"#### {_title}")
        _box[_r["level"]](f"**{_r['headline']}**  \n{_r['what_to_do']}")
        for _line in _r["why"]:
            st.markdown("- " + _line)
        for _name, _c in _r.get("crew", {}).items():
            if "message" in _c:                              # alert, where to go, mission
                st.markdown(f"**{_name}**: {_c['message']}")
            else:                                            # health card
                st.markdown(f"**{_name}**: {_c['status']}")
                for _b in ([_c["radiation"]] if _c["radiation"] else []) + _c["body"] + ([_c["early_sign"]] if _c["early_sign"] else []):
                    st.caption(_b)

# ---- category MENTAL HEALTH & ROCKET (sidebar button) ----
if st.session_state.show_rocket:
    render_mind_panel(REAL_ASTRO["name"] if REAL_ASTRO else astronaut,
                      real_db_path=_ir.DB_PATH if REAL_ASTRO else None,
                      astronaut_id=REAL_ASTRO["id"] if REAL_ASTRO else None)


    st.markdown("### 🚀 ROCKET · ORBITAL DEFENSE GRID")
    st.markdown('<div class="hud" style="padding:0;overflow:hidden">', unsafe_allow_html=True)
    components.html(ROCKET_HTML, height=520, scrolling=False)
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption("Click inside the viewport first so keyboard controls register. ICHOR HUD chrome with a NASA-colored interceptor; flat shapes keep it smooth on low-power devices.")


# ---- FICTIONAL data: only shown after pressing the sidebar category "FICTIONAL RADIATION DATA" ----
if st.session_state.show_fictional:
    st.markdown("### ☢ FICTIONAL RADIATION DATA · 3D ORGAN RADIATION SCAN (SIMULATED, NOT REAL)")
    if not HAS_PLOTLY:
        st.warning("The 3D scan needs Plotly. Run:  pip install plotly numpy pandas")
    else:
        # Exposure % = share of the real 600 mSv career limit (or of the 250 mSv per-event limit, whichever is higher)
        global_rad = min(100.0, rad_frac * 100) if link_rad else float(manual_rad)

        cells = generate_organ_cells().copy()
        cells["Exposure_Pct"] = (global_rad + cells["Tolerance"]).clip(0, 100)
        cells["Status"] = np.select(
            [cells["Exposure_Pct"] <= 0, cells["Exposure_Pct"] <= 65],
            ["Normal", "Exposed"], default="Critical Stage",
        )
        counts = cells["Status"].value_counts()

        c3d_left, c3d_right = st.columns([2, 1])
        with c3d_left:
            st.caption("Drag to rotate 360°, scroll to zoom, hover a dot for exact exposure. Per-organ spread is a team assumption, not measured data.")
            st.plotly_chart(build_organ_figure(cells, view_angle, show_body), use_container_width=True, key="organ_3d")

        with c3d_right:
            tiles = "".join(
                f'<div style="flex:1;text-align:center"><b style="font-family:Orbitron;font-size:1.5rem;'
                f'color:{STATUS_COLORS_3D[s]};text-shadow:0 0 10px {STATUS_COLORS_3D[s]}">{int(counts.get(s, 0))}</b>'
                f'<br><span style="font-family:Share Tech Mono;font-size:.68rem;color:#6fe89a;letter-spacing:.1em">{s.upper()}</span></div>'
                for s in STATUS_ORDER
            )
            H(f"""<div class="hud"><div class="p-title">◉ CELL DIAGNOSTICS · EXPOSURE {global_rad:.0f}%</div>
                 <div style="display:flex;gap:8px">{tiles}</div></div>""")

            bars = ""
            for organ, grp in cells.groupby("Organ", sort=False):
                mean = float(grp["Exposure_Pct"].mean())
                col = COL["ok"] if mean < 15 else COL["warn"] if mean <= 65 else COL["crit"]
                bars += (
                    f'<div style="margin:9px 0"><div style="display:flex;justify-content:space-between;'
                    f'font-family:Share Tech Mono;font-size:.78rem"><span>{organ.upper()}</span>'
                    f'<span style="color:{col}">{mean:.0f}%</span></div>'
                    f'<div class="track"><div class="fill" style="width:{mean:.0f}%;background:{col};box-shadow:0 0 8px {col}"></div></div></div>'
                )
            H(f"""<div class="hud"><div class="p-title">◉ MEAN EXPOSURE BY ORGAN</div>{bars}</div>""")

# =====================================================================
#  ASCLEPIUS PLAYBOOKS
#  Doses are REFERENCE INFORMATION from public sources; a flight surgeon decides.
# =====================================================================
if alerts and DASH:
    st.markdown("### 🎬 ASCLEPIUS ONBOARD CLINICAL PLAYBOOKS")
    st.caption("Offline guidance based on public sources. Protective measures do not wait for Earth (latency); drugs and doses are reference information and are decided by the flight surgeon.")

    for playbook_id, info in alerts:
        pb = PLAYBOOKS[playbook_id]
        color = COL["crit"] if info["severity"] == "CRITICAL" else COL["warn"]
        reasons = " + ".join(info["reasons"])

        H(f"""
        <div class="hud" style="border-color:{color};box-shadow:0 0 16px {color}55, inset 0 0 20px {color}18">
          <div class="pb-head">
            <h3 style="color:{color};text-shadow:0 0 10px {color}">⚠ [{info['severity']}] {pb['title']}</h3>
            <div class="reason">TRIGGER: {reasons}</div>
            <div style="margin-top:6px"><b style="color:#6fe89a;font-family:Orbitron;font-size:.68rem;letter-spacing:.15em">CONDITION</b><br>{pb['condition']}</div>
          </div>
        </div>
        """)

        lc, rc = st.columns(2)
        with lc:
            m = pb["medication"]
            H(f"""
            <div class="hud med">
              <div class="p-title">💊 DRUG REFERENCE INFORMATION</div>
              <div class="row"><b>DRUG / DECISION</b>{m['name']}</div>
              <div class="row"><b>DOSAGE (REFERENCE)</b>{m['dosage']}</div>
              <div class="row"><b>SOURCE</b><span class="src">{m['source']}</span></div>
            </div>
            """)
        with rc:
            steps_html = "".join(f'<div class="step"><span class="n">{i:02d}</span><span>{s}</span></div>' for i, s in enumerate(pb["steps"], 1))
            H(f"""<div class="hud"><div class="p-title">🏃 IMMEDIATE ACTIONS</div>{steps_html}</div>""")

        st.button(
            f"Log application of protocol {playbook_id}",
            key=playbook_id,
            on_click=log_dose,
            args=(playbook_id,),
        )

# =====================================================================
#  DATA SOURCES (what is real, what is simulated)
# =====================================================================
st.markdown("### 📚 DATA SOURCES")
with st.expander("What is real, what is simulated · references", expanded=False):
    st.markdown(SOURCES_MD)

H("""<div class="foot">PROJECT ICHOR · OPEN-DATA CREW RECORDS + SIMULATED SCENARIOS AROUND REAL NASA REFERENCE NUMBERS — NOT FOR REAL MEDICAL USE</div>""")

# =====================================================================
#  VOICE (browser speech synthesis, best-effort)
# =====================================================================
if voice_on and st.session_state.speak:
    msg = json.dumps(st.session_state.speak)
    components.html(
        f"<script>const u=new SpeechSynthesisUtterance({msg});u.lang='en-GB';u.rate=0.95;u.pitch=0.8;"
        "window.speechSynthesis.cancel();window.speechSynthesis.speak(u);</script>",
        height=0,
    )
st.session_state.speak = None