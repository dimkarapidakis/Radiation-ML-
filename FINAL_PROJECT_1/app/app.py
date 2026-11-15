# =====================================================================
# app.py  -  the crew screen (Streamlit)
# Everything the models compute, told in plain words: what is happening, what to do, am I OK?
#
#   sidebar      start / stop the live system (live forecast + shielding, in the background), live or replay
#   Crew         the alert, what every astronaut must do, where everyone is (floor plans)
#   Health       is every astronaut OK? dose per organ, biomarkers (SIMULATED data)
#   Simulations  the 14-day mission with the storm of 11 November 2025, hour by hour
#   Details      the numbers behind everything (for the mission team)
#
# Run:  streamlit run app/app.py
# Needs: pip install streamlit plotly psutil
# =====================================================================


# =====================================================================
# 1. SETTINGS
# =====================================================================
import json
import math
import os
import subprocess
import sys
import time

import geopandas as gpd
import pandas as pd
import plotly.graph_objects as go
import psutil
import pyogrio
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE_SCRIPT = os.path.join(ROOT, "live", "06_live.py")
LIVE_LOG = os.path.join(ROOT, "live", "data", "live_log.csv")
LIVE_FIGURE = os.path.join(ROOT, "live", "Figures", "live.png")
PID_FILE = os.path.join(ROOT, "live", "data", "live.pid")
OUTPUT_FILE = os.path.join(ROOT, "live", "data", "live_output.txt")
ROOM_DOSES = os.path.join(ROOT, "shielding", "data", "room_doses.json")
CREW_ORDERS = os.path.join(ROOT, "shielding", "data", "crew_orders.json")
CREW_STATE = os.path.join(ROOT, "shielding", "data", "crew_live.csv")
CREW_LIVE_LOG = os.path.join(ROOT, "shielding", "data", "crew_live_log.csv")
FLOOR_PLANS = os.path.join(ROOT, "shielding", "cad", "orion_floor_plans.gpkg")
ORGAN_DOSES = os.path.join(ROOT, "health", "data", "organ_doses.json")
HEALTH_ALERTS = os.path.join(ROOT, "health", "data", "health_alerts.csv")
ANOMALY_ALERTS = os.path.join(ROOT, "health", "data", "anomaly_alerts.csv")
HEALTH_READABLE = os.path.join(ROOT, "health", "data", "health_readable.json")
MISSION_LOG = os.path.join(ROOT, "warning", "data", "crew_log.csv")
MISSION_SENSORS = os.path.join(ROOT, "warning", "data", "room_sensors_log.csv")

LIMIT_MSV = 250              # NASA 30-day allowance (blood-forming organs)
EARTH_MSV_PER_YEAR = 2.4     # natural radiation on Earth, world average (UNSCEAR)
FLOOR_GAP = 6.0              # metres between the floor plans on the map
STORM_NAMES = {0: "below storm level", 1: "S1 minor", 2: "S2 moderate", 3: "S3 strong", 4: "S4 severe",
               5: "S5 extreme"}
ROOM_NAMES = {"cockpit": "Cockpit", "seats": "Crew seats", "galley": "Galley", "exercise": "Exercise area",
              "hygiene": "Hygiene bay", "shelter": "Storm shelter", "sleep": "Sleeping area",
              "leb": "Lower equipment bay"}
BIOMARKER_WORDS = {"heart_rate": "resting heart rate", "body_temperature": "body temperature",
                   "systolic_bp": "blood pressure (upper)", "diastolic_bp": "blood pressure (lower)",
                   "sleep_duration": "sleep", "lymphocyte_count": "lymphocytes", "wbc_count": "white blood cells"}
SAFE_COLORS = {"SAFE": "#2e9e5b", "LOW": "#a3c94f", "MEDIUM": "#f0a33a", "HIGH": "#d64541"}
SAFE_WORDS = {"SAFE": "Safe", "LOW": "Low risk", "MEDIUM": "Caution", "HIGH": "Avoid"}

st.set_page_config(page_title="Orion crew radiation", page_icon="🛰️", layout="wide")


# =====================================================================
# 2. SIDEBAR: start / stop the live system
# =====================================================================
st.sidebar.title("🛰️ Mission control")
pid = int(open(PID_FILE).read()) if os.path.exists(PID_FILE) else None
running = pid is not None and psutil.pid_exists(pid)
mode = st.sidebar.radio("Data", ["replay", "live"], disabled=running,
                        captions=["an old storm (January 2026), fast", "real NOAA data now, every 5 minutes"])
fresh = st.sidebar.checkbox("Start from scratch (empty log, new crew positions)", value=True, disabled=running)
if running:
    st.sidebar.success(f"Running ({open(PID_FILE + '.mode').read() if os.path.exists(PID_FILE + '.mode') else ''})")
    if st.sidebar.button("■ Stop", use_container_width=True):
        for child in psutil.Process(pid).children(recursive=True):
            child.terminate()
        psutil.Process(pid).terminate()
        os.remove(PID_FILE)
        st.rerun()
else:
    st.sidebar.info("Stopped")
    if st.sidebar.button("▶ Start", type="primary", use_container_width=True):
        if fresh:
            for f in [LIVE_LOG, CREW_STATE, CREW_LIVE_LOG]:
                if os.path.exists(f):
                    os.remove(f)
        process = subprocess.Popen([sys.executable, "-u", LIVE_SCRIPT, mode], cwd=ROOT,
                                   stdout=open(OUTPUT_FILE, "w"), stderr=subprocess.STDOUT)
        open(PID_FILE, "w").write(str(process.pid))
        open(PID_FILE + ".mode", "w").write(mode)
        time.sleep(3)
        st.rerun()
auto = st.sidebar.toggle("Refresh every 5 seconds", value=running)


# =====================================================================
# 3. LOAD WHAT THE MODELS WROTE
# =====================================================================
now = pd.read_csv(LIVE_LOG).iloc[-1] if os.path.exists(LIVE_LOG) else None
orders = pd.DataFrame(json.load(open(CREW_ORDERS))["orders"]) if os.path.exists(CREW_ORDERS) else pd.DataFrame()
rooms = pd.DataFrame(json.load(open(ROOM_DOSES))["rooms"]).T if os.path.exists(ROOM_DOSES) else pd.DataFrame()
plans = pd.concat([gpd.read_file(FLOOR_PLANS, layer=layer) for layer in pyogrio.list_layers(FLOOR_PLANS)[:, 0]])
plans = plans[plans["floor"] >= 2]
moving = orders[orders["route"] != ""] if len(orders) > 0 else orders

tab_crew, tab_health, tab_sim, tab_details = st.tabs(["🧑‍🚀 Crew", "❤️ Health", "🎬 Simulations", "🔬 Details"])


# =====================================================================
# 4. CREW: the alert, what to do, where everyone is
# =====================================================================
with tab_crew:
    if now is None:
        st.info("No data yet. Press **▶ Start** in the sidebar.")
    else:
        flux = float(now["p10_now"])
        s_now = min(int(math.log10(flux)), 5) if flux >= 10 else 0           # NOAA scale: 10 pfu = S1, 100 = S2 ...
        st.caption(f"Last update: {now['time']} UTC · protons outside: {flux:,.0f} pfu ({STORM_NAMES[s_now]})")

        # --- the one sentence ---
        if len(moving) > 0:
            worst = moving["dose_if_stays_msv"].max()
            st.error(f"## 🛑 GO TO THE STORM SHELTER NOW\n"
                     f"A solar storm is hitting the spacecraft. In the worst case, staying where you are could give "
                     f"you up to **{worst:.0f} mSv**, that is **{100 * worst / LIMIT_MSV:.0f}% of your monthly "
                     f"allowance** (= {worst / EARTH_MSV_PER_YEAR:.0f} years of natural radiation on Earth). "
                     f"In the shelter: almost nothing. Follow your route below.")
        elif now["status"] == "ALL CLEAR":
            st.success("## ✅ ALL CLEAR\nThe Sun is quiet. Normal work.")
        elif now["status"] == "STORM STARTED":
            first = pd.Timestamp(now["onset"]) + pd.Timedelta(minutes=30)
            st.warning(f"## ⚠️ A SOLAR STORM HAS STARTED\nThe first forecast comes at {first:%H:%M} UTC. "
                       f"Stay close to the storm shelter and finish what you are doing.")
        else:
            peak = 10 ** float(now["pred_log_peak"]) if not pd.isna(now["pred_log_peak"]) else flux
            s_peak = min(int(math.log10(peak)), 5) if peak >= 10 else 0
            st.warning(f"## ⚠️ SOLAR STORM ({STORM_NAMES[s_peak]}): KEEP WORKING\n"
                       f"Even in the worst case the walls keep your dose low. "
                       f"No need to move. We check again every 5 minutes.")

        # --- the storm in plain words ---
        if not pd.isna(now.get("pred_log_peak", float("nan"))):
            c1, c2, c3 = st.columns(3)
            peak = 10 ** float(now["pred_log_peak"])
            s_peak = min(int(math.log10(peak)), 5) if peak >= 10 else 0
            c1.metric("How big it will get", STORM_NAMES[s_peak], f"peak ~{peak:,.0f} pfu", delta_color="off")
            c2.metric("Storm going on for", f"{float(now['hours_since_onset']):.1f} hours")
            passed = now["prob_peak_passed"]
            c3.metric("The worst is over?", "too early to tell" if pd.isna(passed) else f"{float(passed):.0%} sure")

        # --- what every astronaut must do ---
        if len(orders) > 0:
            st.subheader("What every astronaut must do")
            columns = st.columns(3)
            for i, (_, o) in enumerate(orders.iterrows()):
                with columns[i % 3].container(border=True):
                    st.markdown(f"### {o['astronaut']}")
                    st.markdown(f"📍 **{ROOM_NAMES[o['now_in']]}** · floor {o['floor']}")
                    if o["route"]:
                        path = " → ".join(ROOM_NAMES[r] for r in o["route"].split(" -> "))
                        st.markdown(f"🛑 **Go to the {ROOM_NAMES[o['go_to']]}**  \n{path} "
                                    f"({o['minutes'] * 60:.0f} seconds)")
                        st.caption(f"Staying: up to {o['dose_if_stays_msv']:.0f} mSv · going: "
                                   f"{o['dose_if_goes_msv']:.1f} mSv · you avoid {o['saves_msv']:.0f} mSv")
                    elif o["dose_if_stays_msv"] < 0.05:
                        st.markdown("✅ **Normal work**")
                    else:
                        st.markdown("✅ **Stay where you are**")
                        st.caption(f"Worst case here: {o['dose_if_stays_msv']:.1f} mSv "
                                   f"({100 * o['dose_if_stays_msv'] / LIMIT_MSV:.1f}% of your monthly allowance), "
                                   f"too little to be worth moving")

        # --- the floor plans: rooms by risk, astronauts, routes ---
        st.subheader("Where everyone is")
        fig = go.Figure()
        for _, r in plans.iterrows():
            shift = FLOOR_GAP * (r["floor"] - 2)
            x, y = r.geometry.exterior.xy
            level = rooms["level"].get(r["room_key"], None) if r["type"] == "room" and len(rooms) > 0 else None
            color = "#8a949e" if r["type"] == "hull" else "#d5d9dd" if r["type"] == "equipment" else \
                SAFE_COLORS.get(level, "#eef1f4")
            fig.add_trace(go.Scatter(x=[a + shift for a in x], y=list(y), fill="toself", fillcolor=color,
                                     mode="lines", line={"color": "#33404d", "width": 0.6}, hoverinfo="text",
                                     text=f"{r['name']}: {SAFE_WORDS.get(level, '')}" if r["type"] == "room" else r["name"],
                                     showlegend=False))
            if r["type"] == "room":
                c = r.geometry.representative_point()
                fig.add_annotation(x=c.x + shift, y=c.y, text=r["name"], showarrow=False, font={"size": 9})
        for floor in [2, 3, 4]:
            fig.add_annotation(x=FLOOR_GAP * (floor - 2), y=2.9, text=f"<b>Floor {floor}</b>", showarrow=False)
        if len(orders) > 0:
            centre = plans[plans["type"] == "room"].set_index("room_key").geometry.representative_point()
            for _, o in moving.iterrows():
                xs = [centre[r].x + FLOOR_GAP * (int(plans.set_index("room_key").loc[r, "floor"]) - 2)
                      for r in o["route"].split(" -> ")]
                ys = [centre[r].y for r in o["route"].split(" -> ")]
                fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line={"color": "#1f5fbf", "width": 3, "dash": "dot"},
                                         hoverinfo="skip", showlegend=False))
            fig.add_trace(go.Scatter(x=orders["x"] + FLOOR_GAP * (orders["floor"] - 2), y=orders["y"],
                                     mode="markers+text", text=orders["astronaut"], textposition="top center",
                                     marker={"size": 14, "color": "#14213d", "line": {"color": "white", "width": 2}},
                                     hoverinfo="text", showlegend=False))
        for level, color in SAFE_COLORS.items():
            fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker={"size": 12, "color": color,
                                     "symbol": "square"}, name=SAFE_WORDS[level]))
        fig.update_layout(height=430, margin={"l": 0, "r": 0, "t": 10, "b": 0}, plot_bgcolor="white",
                          legend={"orientation": "h", "y": -0.05})
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False, scaleanchor="x")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Room colours = how much dose a person would get there in the worst case of this storm.")


# =====================================================================
# 5. HEALTH: is every astronaut OK?
# =====================================================================
with tab_health:
    st.info("The health data are **SIMULATED** (6 astronauts, 14 days). Every value is compared with "
            "the astronaut's OWN normal values from before the flight.")
    single = pd.read_csv(HEALTH_ALERTS) if os.path.exists(HEALTH_ALERTS) else pd.DataFrame(columns=["astronaut"])
    together = pd.read_csv(ANOMALY_ALERTS) if os.path.exists(ANOMALY_ALERTS) else pd.DataFrame(columns=["astronaut"])
    columns = st.columns(3)
    crew_names = list(json.load(open(HEALTH_READABLE))["crew"]) if os.path.exists(HEALTH_READABLE) else []
    for i, astronaut in enumerate(crew_names):
        a1 = single[single["astronaut"] == astronaut]
        a2 = together[together["astronaut"] == astronaut]
        with columns[i % 3].container(border=True):
            st.markdown(f"### {astronaut}")
            if len(a1) == 0 and len(a2) == 0:
                st.markdown("✅ **All normal**")
            else:
                st.markdown("🩺 **See the medical officer**")
                if len(a2) > 0:
                    st.markdown(f"Several small changes together since day {a2['day'].min()} "
                                f"(an early sign, e.g. of an infection or exhaustion).")
                for _, a in a1.drop_duplicates("biomarker").iterrows():
                    word = "higher" if a["z"] > 0 else "lower"
                    st.markdown(f"- {BIOMARKER_WORDS[a['biomarker']].capitalize()} {word} than your normal "
                                f"(day {a['day']}: {a['value']:.1f} {a['unit']}, your normal {a['base_mean']:.1f})")

    if os.path.exists(ORGAN_DOSES):
        organ = json.load(open(ORGAN_DOSES))
        o = pd.DataFrame(organ["organs"]).dropna(subset=["pct_limit_cabin"])
        st.subheader(f"Radiation per organ: {organ['storm']} storm + {organ['days']} days in space")
        st.markdown(f"The organ that limits you is the **{o.loc[o['pct_limit_cabin'].idxmax(), 'organ'].lower()}**: "
                    f"without the shelter it would use **{o['pct_limit_cabin'].max():.0f}%** of its monthly allowance, "
                    f"with the shelter only **{o.loc[o['pct_limit_cabin'].idxmax(), 'pct_limit_shelter']:.0f}%**.")
        fig = go.Figure()
        fig.add_trace(go.Bar(y=o["organ"], x=o["pct_limit_cabin"], orientation="h", name="no shelter",
                             marker_color="#d64541"))
        fig.add_trace(go.Bar(y=o["organ"], x=o["pct_limit_shelter"], orientation="h", name="in the shelter",
                             marker_color="#2e9e5b"))
        fig.add_vline(x=100, line_dash="dash", annotation_text="NASA monthly allowance")
        fig.update_layout(height=320, barmode="group", xaxis_title="% of the monthly allowance",
                          margin={"l": 0, "r": 0, "t": 10, "b": 0}, legend={"orientation": "h"})
        st.plotly_chart(fig, use_container_width=True)


# =====================================================================
# 6. SIMULATIONS: the 14-day mission, hour by hour
# =====================================================================
with tab_sim:
    if not os.path.exists(MISSION_LOG):
        st.info("Run warning/simulate_room_sensors.py and warning/crew_routes.py first.")
    else:
        log = pd.read_csv(MISSION_LOG, parse_dates=["time"])
        sensors = pd.read_csv(MISSION_SENSORS, parse_dates=["time"]).pivot_table(
            index="time", columns="room", values="dose_rate_msv_h")
        last = log[log["time"] == log["time"].max()]
        sheltered = log[log["room"] == "shelter"]
        st.markdown(f"### 14 days, 6 astronauts, one real solar storm\n"
                    f"On **11 November 2025** (day 7) a real solar storm hit (measured by NOAA's GOES-19). "
                    f"The dosimeters saw the dose rising, and in **1 minute** everyone was in the storm shelter. "
                    f"They stayed **{(sheltered['time'].max() - sheltered['time'].min()).total_seconds() / 3600:.0f} hours**. "
                    f"Result: **{last['dose_msv'].mean():.0f} mSv** each instead of "
                    f"**{last['dose_if_no_warning_msv'].mean():.0f} mSv** without the warning.")

        hours = sorted(log["time"].dt.floor("h").unique())
        pick = st.select_slider("Move through the mission", options=hours, value=hours[len(hours) // 2],
                                format_func=lambda t: pd.Timestamp(t).strftime("day %d %b, %H:%M"))
        at = log[log["time"] == pick]
        rate_now = sensors.loc[pick]
        fig = go.Figure()
        for _, r in plans.iterrows():
            shift = FLOOR_GAP * (r["floor"] - 2)
            x, y = r.geometry.exterior.xy
            value = rate_now.get(r["room_key"], 0) if r["type"] == "room" else 0
            color = "#8a949e" if r["type"] == "hull" else "#d5d9dd" if r["type"] == "equipment" else \
                "#2e9e5b" if value < 0.05 else "#f0a33a" if value < 0.3 else "#d64541"
            fig.add_trace(go.Scatter(x=[a + shift for a in x], y=list(y), fill="toself", fillcolor=color,
                                     mode="lines", line={"color": "#33404d", "width": 0.6}, hoverinfo="text",
                                     text=f"{r['name']}: {value:.2f} mSv/h" if r["type"] == "room" else r["name"],
                                     showlegend=False))
        for floor in [2, 3, 4]:
            fig.add_annotation(x=FLOOR_GAP * (floor - 2), y=2.9, text=f"<b>Floor {floor}</b>", showarrow=False)
        fig.add_trace(go.Scatter(x=at["x"] + FLOOR_GAP * (at["floor"] - 2), y=at["y"], mode="markers+text",
                                 text=at["astronaut"], textposition="top center", showlegend=False,
                                 marker={"size": 14, "color": "#14213d", "line": {"color": "white", "width": 2}}))
        fig.update_layout(height=380, margin={"l": 0, "r": 0, "t": 10, "b": 0}, plot_bgcolor="white")
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False, scaleanchor="x")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Green = quiet · orange = storm · red = strong storm in that room")

        dose = log.groupby("time")[["dose_msv", "dose_if_no_warning_msv"]].mean()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dose.index, y=dose["dose_if_no_warning_msv"], name="without the warning",
                                 line={"color": "#d64541", "dash": "dash"}))
        fig.add_trace(go.Scatter(x=dose.index, y=dose["dose_msv"], name="with the warning (shelter)",
                                 line={"color": "#2e9e5b", "width": 3}))
        fig.add_vline(x=pick, line_color="#14213d")
        fig.update_layout(height=300, yaxis_title="dose of one astronaut (mSv)", margin={"l": 0, "r": 0, "t": 10, "b": 0},
                          legend={"orientation": "h"})
        st.plotly_chart(fig, use_container_width=True)


# =====================================================================
# 7. DETAILS: the numbers (for the mission team)
# =====================================================================
with tab_details:
    if len(rooms) > 0:
        st.subheader("Worst-case storm dose per room")
        st.dataframe(rooms, use_container_width=True)
    if len(orders) > 0:
        st.subheader("Orders")
        st.dataframe(orders, use_container_width=True)
    if os.path.exists(LIVE_LOG):
        st.subheader("Forecast log (last 10)")
        st.dataframe(pd.read_csv(LIVE_LOG).tail(10), use_container_width=True)
    if os.path.exists(LIVE_FIGURE):
        st.image(LIVE_FIGURE)
    if os.path.exists(OUTPUT_FILE):
        st.subheader("Output of the live system")
        st.code("".join(open(OUTPUT_FILE).readlines()[-25:]))

if auto:
    time.sleep(5)
    st.rerun()
