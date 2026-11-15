# =====================================================================
# pages/run_demo.py  -  a page of the Streamlit app: one button runs ALL the algorithms
#
#   the button runs  python run_all.py nolive  (~1 minute): the 14-day mission, health, maps,
#   shielding and the alert; then the page shows every result in plain words.
#
# Streamlit puts every file of the folder pages/ next to main.py in the menu on the left,
# so main.py does not change.
# =====================================================================
import json
import os
import subprocess
import sys

import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # FINAL_PROJECT_1
RESULTS = {"🚨 Alert": os.path.join(ROOT, "warning", "data", "alert_readable.json"),
           "🧭 Where to go": os.path.join(ROOT, "shielding", "data", "shielding_readable.json"),
           "❤️ Health": os.path.join(ROOT, "health", "data", "health_readable.json"),
           "🎬 The 14-day mission": os.path.join(ROOT, "warning", "data", "crew_routes_readable.json")}
BOX = {"green": st.success, "yellow": st.warning, "red": st.error}
ICON = {"green": "✅", "yellow": "⚠️", "red": "🛑"}

st.set_page_config(page_title="Run the demo", page_icon="▶️", layout="wide")
st.title("▶️ Run all the algorithms")
st.write("Forecast → shielding → warning → health, with the real solar storm of 11 November 2025 "
         "and the astronauts of the team's database. It takes about 1 minute.")

if st.button("▶️ Run the demo  (run_all.py nolive)", type="primary"):
    with st.spinner("Running the 9 steps ..."):
        result = subprocess.run([sys.executable, os.path.join(ROOT, "run_all.py"), "nolive"], cwd=ROOT,
                                capture_output=True, text=True, env=dict(os.environ, PYTHONWARNINGS="ignore"))
    if result.returncode == 0 and "FAILED" not in result.stdout:
        st.success("Done: every step OK.")
    else:
        st.error("A step failed: see the output below.")
    with st.expander("What run_all.py printed"):
        st.code(result.stdout + result.stderr)

# --- the results in plain words (the last run) ---
for title, path in RESULTS.items():
    if not os.path.exists(path):
        continue
    r = json.load(open(path, encoding="utf-8"))
    st.subheader(title)
    BOX[r["level"]](f"**{r['headline']}**  \n{r['what_to_do']}")
    for line in r["why"]:
        st.markdown("- " + line)
    columns = st.columns(3)
    for i, (astronaut, c) in enumerate(r.get("crew", {}).items()):
        with columns[i % 3].container(border=True):
            st.markdown(f"**{ICON[c['level']]} {astronaut}**")
            if "message" in c:                                   # alert, where to go, mission
                st.write(c["message"])
            else:                                                # health card
                st.markdown(f"**{c['status']}**")
                if c["radiation"]:
                    st.caption("☢️ " + c["radiation"])
                for b in c["body"]:
                    st.write("🌡️ " + b)
                if c["early_sign"]:
                    st.write("🔎 " + c["early_sign"])
