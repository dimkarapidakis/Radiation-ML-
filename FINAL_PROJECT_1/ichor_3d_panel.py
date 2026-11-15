"""
ichor_3d_panel.py - 3D radiation / solar-storm panel driven by the ICHOR SQLite database.

Usage inside ichor_dashboard.py:
    from ichor_3d_panel import render_radiation_panel
    render_radiation_panel(view_angle=view_angle, show_body=show_body)
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import ichor_radiation as ir

COL = {"ok": "#00ff66", "warn": "#ffb300", "crit": "#ff2d55"}
SEV_COL = {"none": "#00ff66", "info": "#6fe89a", "warning": "#ffb300", "critical": "#ff2d55"}
SEV_TXT = {"none": "NOMINAL", "info": "INFO", "warning": "WARNING", "critical": "CRITICAL"}
BODY_COLOR = "#6fe89a"

# x = left/right, y = front/back, z = height   (same geometry as the existing organ scan)
ORGAN_GEOM = {
    "Brain":      ((0.0, 0.0, 8.0),  (1.5, 1.2, 1.2), 140),
    "Heart":      ((0.0, 0.3, 3.5),  (0.6, 0.7, 0.8), 80),
    "Left Lung":  ((-1.7, 0.0, 3.8), (0.8, 1.0, 1.8), 110),
    "Right Lung": ((1.7, 0.0, 3.8),  (0.8, 1.0, 1.8), 110),
    "Liver":      ((-1.2, 0.2, 1.2), (1.1, 0.9, 0.8), 90),
    "Stomach":    ((1.1, 0.2, 1.0),  (1.0, 0.8, 0.8), 90),
}

REFERENCE_ORGAN_POINTS = {
    "Testis": (0.0, 0.0, 0.3), "Bladder": (0.0, 0.0, 0.8),
    "Esophagus": (0.0, -0.1, 4.5), "Liver": (-0.8, 0.2, 1.7),
    "Thyroid": (0.0, -0.1, 5.9), "Brain": (0.0, 0.0, 8.0),
    "Salivary gland": (0.0, -0.2, 6.4), "Skin": (0.0, -1.45, 3.8),
    "Adrenal": (-0.3, 0.1, 1.7), "ET region": (0.0, -0.1, 6.0),
    "Gallbladder": (-0.6, 0.1, 1.5), "Heart": (0.0, 0.3, 3.5),
    "Kidney": (0.6, 0.1, 1.4), "Muscle": (1.3, 0.0, 2.0),
    "Oral mucosa": (0.0, -0.3, 6.6), "Pancreas": (0.0, 0.1, 1.6),
    "Prostate": (0.0, 0.0, 0.5), "Small intestine": (0.0, 0.1, 1.2),
    "Spleen": (-0.6, 0.1, 1.8), "Thymus": (0.0, 0.0, 2.8),
    "Stomach": (1.1, 0.2, 1.0), "Colon": (0.0, 0.1, 0.9),
    "Lungs": (0.0, 0.0, 3.9), "Thorax": (0.0, -0.3, 3.8),
    "Gonads": (0.0, 0.0, 0.3), "Anterior brain": (0.0, -0.1, 8.35),
    "Midbrain": (0.0, 0.0, 8.0), "Posterior brain": (0.0, 0.1, 7.65),
    "Eye lens": (0.35, -0.4, 7.7), "Bone marrow (BFO)": (0.0, 0.0, 3.1),
}

NASA_ORGAN_REFERENCE_SCENARIOS = {
    "SPE Aug 1972 · 10 g/cm² shelter": {
        "kind": "reported",
        "context": "Male phantom; solar-storm shelter; exposure duration and units are not stated in the document.",
        "source": "https://ntrs.nasa.gov/api/citations/20110008183/downloads/20110008183.pdf",
        "data": {
            "Testis": 0.39, "Bladder": 0.10, "Esophagus": 0.11, "Liver": 0.14,
            "Thyroid": 0.32, "Brain": 0.32, "Salivary gland": 0.41, "Skin": 0.94,
            "Adrenal": 0.10, "ET region": 0.37, "Gallbladder": 0.09, "Heart": 0.14,
            "Kidney": 0.16, "Muscle": 0.40, "Oral mucosa": 0.24, "Pancreas": 0.09,
            "Prostate": 0.10, "Small intestine": 0.15, "Spleen": 0.18, "Thymus": 0.16,
        },
    },
    "ISS GCR · 2001 (mGy/day)": {
        "kind": "daily",
        "context": "ISS Increment 2; July–August 2001; male torso phantom; experimental and NASA model values.",
        "source": "https://ntrs.nasa.gov/api/citations/20110007210/downloads/20110007210.pdf",
        "data": {
            "Brain": (0.076, 0.077), "Thyroid": (0.074, 0.077),
            "Heart": (0.075, 0.076), "Stomach": (0.076, 0.077),
            "Colon": (0.073, 0.076),
        },
    },
    "Annual GCR · 5 g/cm² Al": {
        "kind": "dose_pair",
        "context": "Solar minimum (1977 model); male phantom; one-year exposure; 5 g/cm² aluminum.",
        "source": "https://ntrs.nasa.gov/citations/20130001648",
        "data": {
            "Skin": (198.8, 832.3), "Bone marrow (BFO)": (185.7, 614.0),
            "Stomach": (182.2, 547.6), "Colon": (185.6, 606.2),
            "Liver": (183.1, 566.6), "Lungs": (184.5, 590.9),
            "Esophagus": (184.0, 584.4), "Bladder": (181.6, 540.8),
            "Thyroid": (186.8, 632.7), "Thorax": (194.1, 770.2),
            "Gonads": (186.5, 640.9), "Anterior brain": (190.6, 696.9),
            "Midbrain": (187.7, 640.2), "Posterior brain": (190.5, 695.2),
            "Eye lens": (196.2, 806.3), "Gallbladder": (181.6, 540.8),
        },
    },
    "Annual GCR · 20 g/cm² Al": {
        "kind": "dose_pair",
        "context": "Solar minimum (1977 model); male phantom; one-year exposure; 20 g/cm² aluminum.",
        "source": "https://ntrs.nasa.gov/citations/20130001648",
        "data": {
            "Skin": (193.5, 599.8), "Bone marrow (BFO)": (182.0, 494.2),
            "Stomach": (179.1, 465.5), "Colon": (181.9, 491.3),
            "Liver": (179.8, 473.6), "Lungs": (180.9, 484.4),
            "Esophagus": (180.5, 481.4), "Bladder": (178.6, 462.2),
            "Thyroid": (182.9, 502.5), "Thorax": (189.0, 558.7),
            "Gonads": (182.5, 503.3), "Anterior brain": (186.1, 530.5),
            "Midbrain": (183.7, 506.9), "Posterior brain": (186.0, 529.8),
            "Eye lens": (190.8, 574.0), "Gallbladder": (178.6, 462.2),
        },
    },
    "SPE Aug 1972 · 20 g/cm² Al": {
        "kind": "dose_pair",
        "context": "Solar particle event; male phantom; August 1972; total event dose; 20 g/cm² aluminum.",
        "source": "https://ntrs.nasa.gov/citations/20130001648",
        "data": {
            "Skin": (87.8, 144.0), "Bone marrow (BFO)": (23.4, 42.9),
            "Stomach": (12.1, 25.5), "Colon": (21.0, 39.4),
            "Liver": (15.6, 30.7), "Lungs": (18.3, 35.2),
            "Esophagus": (17.5, 34.0), "Bladder": (12.0, 25.0),
            "Thyroid": (25.7, 46.5), "Thorax": (67.2, 107.0),
            "Gonads": (37.5, 62.5), "Anterior brain": (37.6, 64.8),
            "Midbrain": (24.0, 44.8), "Posterior brain": (37.0, 64.0),
            "Eye lens": (76.7, 120.9), "Gallbladder": (12.0, 25.0),
        },
    },
}


def H(markup: str):
    st.markdown(" ".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def _reference_scenario_select(key: str, default_scenario: str | None = None) -> str | None:
    options = ["No literature overlay", *NASA_ORGAN_REFERENCE_SCENARIOS]
    index = options.index(default_scenario) if default_scenario in options else 0
    selected = st.selectbox("NASA organ-dose reference", options, index=index, key=key)
    if selected == options[0]:
        return None
    scenario = NASA_ORGAN_REFERENCE_SCENARIOS[selected]
    st.caption(
        f"{scenario['context']} [NASA source]({scenario['source']}). "
        "Cyan diamonds mark reported reference values; their positions are schematic. "
        "These are not measurements for the selected astronaut."
    )
    return selected


def _reference_text(organ: str, scenario_name: str) -> str:
    scenario = NASA_ORGAN_REFERENCE_SCENARIOS[scenario_name]
    value = scenario["data"][organ]
    if scenario["kind"] == "reported":
        return f"{value:.2f} (unit not stated)"
    if scenario["kind"] == "daily":
        experimental, nasa_model = value
        return f"Experimental: {experimental:.3f} mGy/day<br>NASA model: {nasa_model:.3f} mGy/day"
    absorbed, equivalent = value
    return f"Absorbed: {absorbed:.1f} mGy<br>Equivalent: {equivalent:.1f} mSv"


def _add_reference_organs(fig: go.Figure, scenario_name: str | None) -> None:
    if scenario_name is None:
        return
    values = NASA_ORGAN_REFERENCE_SCENARIOS[scenario_name]["data"]
    organs = [organ for organ in values if organ in REFERENCE_ORGAN_POINTS]
    points = [REFERENCE_ORGAN_POINTS[organ] for organ in organs]
    fig.add_trace(go.Scatter3d(
        x=[point[0] for point in points],
        y=[point[1] for point in points],
        z=[point[2] for point in points],
        mode="markers",
        text=[f"<b>{organ}</b><br>{_reference_text(organ, scenario_name)}" for organ in organs],
        hoverinfo="text",
        showlegend=False,
        marker=dict(size=9, color="#43d5ff", symbol="diamond", opacity=1, line=dict(width=1, color="white")),
    ))


def _render_reference_table(scenario_name: str | None) -> None:
    if scenario_name is None:
        return
    scenario = NASA_ORGAN_REFERENCE_SCENARIOS[scenario_name]
    st.markdown(f"#### Literature reference · {scenario_name}")
    st.dataframe(
        [{"Organ": organ, "Reported values": _reference_text(organ, scenario_name).replace("<br>", " · ")}
         for organ in scenario["data"]],
        use_container_width=True,
        hide_index=True,
    )


@st.cache_resource
def _conn(path: str):
    # keyed by the path, so a changed DB file is never served from an old cached connection
    return ir.connect(path)


@st.cache_data
def _cells():
    rng = np.random.default_rng(42)
    out = {}
    for name, (c, r, n) in ORGAN_GEOM.items():
        d = rng.normal(size=(n, 3))
        d /= np.linalg.norm(d, axis=1, keepdims=True)
        rad = rng.random(n) ** (1 / 3)
        pts = d * rad[:, None] * np.array(r) + np.array(c)
        out[name] = {"pts": pts, "tol": rng.uniform(-6, 6, n)}
    return out


def _spow(v, e):
    return np.sign(v) * np.abs(v) ** e


def _shell(fig, center, radii, e1, e2, n=40):
    u, v = np.meshgrid(np.linspace(-np.pi / 2, np.pi / 2, n), np.linspace(-np.pi, np.pi, n))
    x = center[0] + radii[0] * _spow(np.cos(u), e1) * _spow(np.cos(v), e2)
    y = center[1] + radii[1] * _spow(np.cos(u), e1) * _spow(np.sin(v), e2)
    z = center[2] + radii[2] * _spow(np.sin(u), e1)
    fig.add_trace(go.Surface(x=x, y=y, z=z, colorscale=[[0, BODY_COLOR], [1, BODY_COLOR]],
                             showscale=False, opacity=0.12, hoverinfo="skip", showlegend=False))


def build_body_figure(a: ir.Assessment, angle: int, body: bool,
                      reference_scenario: str | None = None) -> go.Figure:
    fig = go.Figure()
    if body:
        _shell(fig, (0, 0, 8.0), (2.0, 1.6, 1.5), 1.0, 1.0)
        _shell(fig, (0, 0, 2.5), (3.5, 1.8, 4.0), 0.35, 0.6)

    pct = {o["organ"]: o for o in a.organs}
    xs, ys, zs, cs, txt = [], [], [], [], []
    for name, d in _cells().items():
        o = pct[name]
        p = np.clip(o["pct"] + d["tol"] * (o["pct"] > 0), 0, 100)      # per-cell spread (team assumption)
        xs += d["pts"][:, 0].tolist(); ys += d["pts"][:, 1].tolist(); zs += d["pts"][:, 2].tolist()
        cs += p.tolist()
        txt += [f"{ir.ORGAN_NAME[name]}<br>Risk: {o['pct']:.0f}%<br>Organ dose: {o['dose_msv']:.1f} mSv"] * len(p)
    fig.add_trace(go.Scatter3d(
        x=xs, y=ys, z=zs, mode="markers", text=txt, hoverinfo="text", showlegend=False,
        marker=dict(size=5, color=cs, cmin=0, cmax=100, opacity=0.95, line=dict(width=1, color="white"),
                    colorscale=[[0, "#00ff66"], [0.25, "#b6ff5c"], [0.45, "#ffb300"], [0.65, "#ff2d55"], [1, "#ff2d55"]],
                    colorbar=dict(title=dict(text="Risk %", font=dict(color="#d4ffe2")),
                                  tickfont=dict(color="#d4ffe2"), len=0.6, thickness=12)),
    ))
    # floating labels with the % per organ
    lab = {n: ORGAN_GEOM[n][0] for n in ORGAN_GEOM}
    fig.add_trace(go.Scatter3d(
        x=[lab[n][0] for n in lab], y=[lab[n][1] - 1.4 for n in lab], z=[lab[n][2] for n in lab],
        mode="text", hoverinfo="skip", showlegend=False,
        text=[f"{pct[n]['pct']:.0f}%" for n in lab], textfont=dict(color="#ffffff", size=13)))
    _add_reference_organs(fig, reference_scenario)

    a_rad = np.deg2rad(angle)
    hidden = dict(visible=False)
    fig.update_layout(
        height=560, paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=0, b=0),
        uirevision=f"view-{angle}",
        scene=dict(xaxis=hidden, yaxis=hidden, zaxis=hidden, bgcolor="rgba(0,0,0,0)", aspectmode="data",
                   camera=dict(eye=dict(x=2.2 * np.sin(a_rad), y=-2.2 * np.cos(a_rad), z=0.5),
                               up=dict(x=0, y=0, z=1))))
    return fig


def build_timeline(a: ir.Assessment) -> go.Figure:
    t = [p[0] for p in a.series]
    v = [p[1] for p in a.series]
    fig = go.Figure(go.Scatter(x=t, y=v, mode="lines", line=dict(color="#00ff66", width=2), name="Dose rate"))
    if a.event:
        e = a.event
        fig.add_vrect(x0=e["start"], x1=e["end"], fillcolor="#ff2d55", opacity=0.18, line_width=0)
        fig.add_hline(y=e["baseline_usv_h"], line=dict(color="#6fe89a", dash="dot"))
        fig.add_hline(y=e["baseline_usv_h"] * ir.ELEVATED_RATIO, line=dict(color="#ffb300", dash="dash"))
        fig.add_hline(y=e["baseline_usv_h"] * ir.SPIKE_RATIO, line=dict(color="#ff2d55", dash="dash"))
    fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,18,8,.6)", font=dict(color="#d4ffe2"), showlegend=False,
                      yaxis=dict(title="µSv/h (log)", type="log", gridcolor="rgba(0,255,102,.12)"),
                      xaxis=dict(gridcolor="rgba(0,255,102,.12)"))
    return fig


def _tile(label, value, color):
    return (f'<div class="hud" style="text-align:center"><div class="p-title">{label}</div>'
            f'<div style="font-family:Orbitron;font-weight:800;font-size:1.7rem;color:{color};'
            f'text-shadow:0 0 12px {color}">{value}</div></div>')


def get_real_astronauts() -> list:
    """Astronauts stored in the real database (empty list if the DB is missing / unreadable)."""
    try:
        return [dict(r) for r in ir.list_astronauts(_conn(ir.DB_PATH))]
    except Exception:
        return []


def _seed(storm: bool):
    ir.seed_demo(_conn(ir.DB_PATH), storm=storm)


def render_radiation_panel(view_angle: int = 0, show_body: bool = True, astronaut_id: int | None = None):
    try:
        conn = _conn(ir.DB_PATH)
    except Exception as exc:                          # wrong DB_PATH, not a SQLite file, ...
        st.error(f"Could not open the database: {exc}")
        return
    st.caption(f"Data source: {ir.DB_PATH}")

    # the DB must contain the dose-rate indicator; otherwise show what it does contain
    try:
        missing = ir.missing_slugs(conn)
    except Exception as exc:
        st.error(f"The database does not have the expected schema (indicators table): {exc}")
        return
    if missing:
        # no radiation indicator in this database (e.g. the team's heart rate / sleep data): show the real health data instead
        render_health_panel(conn, view_angle, show_body, astronaut_id)
        return
    st.markdown("### ☢ RADIATION & SOLAR-STORM DETECTION (DATABASE)")
    reference_scenario = _reference_scenario_select("radiation_organ_reference")

    astros = [dict(r) for r in ir.list_astronauts(conn)]   # plain dicts: st.selectbox deep-copies its options
    if not astros:
        st.info("The astronauts table is empty." + ("" if not ir.DEMO_MODE else " Load demo data:"))
        if ir.DEMO_MODE:
            st.button("Create demo with a solar storm", on_click=_seed, args=(True,), key="seed_empty")
        return

    c1, c2 = st.columns([2, 1])
    with c1:
        if astronaut_id is not None:
            sel = next((a for a in astros if a["id"] == astronaut_id), astros[0])
        else:
            sel = st.selectbox("Astronaut", astros, format_func=lambda r: f"{r['name']} · {r['mission_name']}",
                               key="rad_astro")
    with c2:
        shelter = st.toggle("What if sheltered (×0.5 dose)", value=False, key="rad_shelter")

    try:
        a = ir.assess(conn, sel["id"], shielding=0.5 if shelter else 1.0)
    except (KeyError, ValueError) as exc:             # e.g. unsupported unit text in indicators.unit
        st.error(str(exc))
        return
    if not a.series:
        st.warning("No dose-rate measurements for this astronaut in the measurements table.")
    if not shelter:                                   # alerts are only issued for the real (unshielded) reading
        new_id = ir.issue_alert(conn, a)
        if new_id:
            st.toast(f"New alert #{new_id} ({a.severity})", icon="🚨")

    # ---- status banner ----
    if a.event is None:
        H(f'<div class="banner ok">🟢 NO EVENT DETECTED<br><small>Dose rate of {a.astronaut_name} is within the baseline level.</small></div>')
    else:
        e = a.event
        kind = "SOLAR STORM" if e["kind"] == "SOLAR_STORM" else "ELEVATED RADIATION"
        state = "ONGOING" if e["ongoing"] else "COMPLETED"
        H(f'<div class="banner bad">🚨 {kind} · {state} · {SEV_TXT[a.severity]}<br>'
          f'<small>{" · ".join(a.reasons)}</small></div>')

    # ---- tiles ----
    ev = a.event
    ev_dose = ev["dose_msv"] * a.shielding if ev else 0.0
    t = st.columns(4)
    sc = SEV_COL[a.severity]
    with t[0]:
        H(_tile("RISK", f"{a.risk_score}/100", sc))
    with t[1]:
        H(_tile("EVENT DOSE", f"{ev_dose:.0f} mSv", sc))
    with t[2]:
        H(_tile("PEAK", f"×{ev['peak_ratio']:.1f}" if ev else "—", sc))
    with t[3]:
        H(_tile("CUMULATIVE DOSE", f"{a.cumulative_msv:.0f}/{ir.CAREER_LIMIT_MSV:.0f}", sc))

    # ---- 3D body + organ bars ----
    left, right = st.columns([2, 1])
    with left:
        st.caption("Each organ is coloured by its risk percentage. Drag to rotate 360°, scroll to zoom.")
        st.plotly_chart(build_body_figure(a, view_angle, show_body, reference_scenario),
                        use_container_width=True, key="rad_3d")
    with right:
        bars = ""
        for o in a.organs:
            col = COL[o["level"]]
            extra = f" +{o['symptom_bonus']:.0f} symptoms" if o["symptom_bonus"] else ""
            bars += (f'<div style="margin:9px 0"><div style="display:flex;justify-content:space-between;'
                     f'font-family:Share Tech Mono;font-size:.78rem"><span>{ir.ORGAN_NAME[o["organ"]].upper()}</span>'
                     f'<span style="color:{col}">{o["pct"]:.0f}%</span></div>'
                     f'<div class="track"><div class="fill" style="width:{o["pct"]:.0f}%;background:{col};'
                     f'box-shadow:0 0 8px {col}"></div></div>'
                     f'<div style="font-family:Share Tech Mono;font-size:.66rem;color:#3b9a60">'
                     f'{o["dose_msv"]:.1f} mSv in the organ{extra}</div></div>')
        H(f'<div class="hud"><div class="p-title">◉ IMPACT BY ORGAN</div>{bars}</div>')
        if a.symptoms:
            rows = "".join(f"<div>• {s['name']} (severity {s['severity']}/5)</div>" for s in a.symptoms)
            H(f'<div class="hud"><div class="p-title">◉ SYMPTOMS AFTER THE EVENT</div>'
              f'<div style="font-family:Share Tech Mono;font-size:.8rem">{rows}</div></div>')
    _render_reference_table(reference_scenario)

    # ---- timeline ----
    st.markdown("#### Dose rate over time")
    st.plotly_chart(build_timeline(a), use_container_width=True, key="rad_timeline")
    st.caption("Green dotted: baseline · orange: ×1.5 (elevated) · red: ×3 (solar storm) · red band: detected event.")

    # ---- alerts from the `alerts` table ----
    st.markdown("#### Alerts")
    alerts = ir.get_alerts(conn, sel["id"])
    if not alerts:
        st.caption("No alerts.")
    for al in alerts[:10]:
        sev = al["severity"]
        col = SEV_COL[sev]
        done = "✔ acknowledged" if al["acknowledged"] else "NEW"
        H(f'<div class="hud" style="border-color:{col};padding:8px 12px"><span style="color:{col};'
          f'font-family:Orbitron;font-size:.7rem;letter-spacing:.12em">[{sev.upper()}] #{al["id"]} · {al["created_at"]} · {done}</span>'
          f'<div style="font-size:.98rem;margin-top:4px">{al["message"]}</div></div>')
        if not al["acknowledged"]:
            st.button(f"Acknowledge alert #{al['id']}", key=f"ack_{al['id']}",
                      on_click=ir.acknowledge_from_path, args=(ir.DB_PATH, al["id"]))

    with st.expander("Data mapping (which indicators the algorithm reads)"):
        st.caption(f"Database: {ir.DB_PATH} · dose rate: {ir.SLUG_RATE} · cumulative dose: {ir.SLUG_CUM} · lymphocytes: {ir.SLUG_ALC}. "
                   "Change them at the top of ichor_radiation.py.")
        st.dataframe(ir.list_indicators(conn), use_container_width=True)

    if ir.DEMO_MODE:
        with st.expander("Demo tools (test data)"):
            st.button("Add an astronaut with a solar storm", on_click=_seed, args=(True,), key="seed_storm")
            st.button("Add an astronaut with a calm profile", on_click=_seed, args=(False,), key="seed_calm")


# =============================================================================
#  HEALTH VIEW - driven by the real indicators / symptoms / alerts in the database
# =============================================================================
import ichor_health as ih

GREY = "#5b6b63"


def build_health_figure(res: dict, angle: int, body: bool,
                        reference_scenario: str | None = None) -> go.Figure:
    fig = go.Figure()
    if body:
        _shell(fig, (0, 0, 8.0), (2.0, 1.6, 1.5), 1.0, 1.0)
        _shell(fig, (0, 0, 2.5), (3.5, 1.8, 4.0), 0.35, 0.6)
    byname = {o["organ"]: o for o in res["organs"]}
    xs, ys, zs, cs, txt = [], [], [], [], []
    gx, gy, gz, gt = [], [], [], []
    for name, d in _cells().items():
        o = byname[name]
        pts = d["pts"]
        if not o["has_data"]:                                   # no data for this organ -> grey, never green
            gx += pts[:, 0].tolist(); gy += pts[:, 1].tolist(); gz += pts[:, 2].tolist()
            gt += [f"{ir.ORGAN_NAME[name]}<br>No data in the database"] * len(pts)
            continue
        p = np.clip(o["pct"] + d["tol"] * (o["pct"] > 0) * 0.4, 0, 100)
        xs += pts[:, 0].tolist(); ys += pts[:, 1].tolist(); zs += pts[:, 2].tolist(); cs += p.tolist()
        why = o["worst"] or ("Symptoms: " + ", ".join(o["symptoms"]) if o["symptoms"] else "Within normal limits")
        txt += [f"{ir.ORGAN_NAME[name]}<br>Load: {o['pct']:.0f}%<br>{why}"] * len(pts)
    if gx:
        fig.add_trace(go.Scatter3d(x=gx, y=gy, z=gz, mode="markers", text=gt, hoverinfo="text", showlegend=False,
                                   marker=dict(size=5, color=GREY, opacity=0.55)))
    if xs:
        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs, mode="markers", text=txt, hoverinfo="text", showlegend=False,
            marker=dict(size=5, color=cs, cmin=0, cmax=100, opacity=0.95, line=dict(width=1, color="white"),
                        colorscale=[[0, "#00ff66"], [0.25, "#b6ff5c"], [0.45, "#ffb300"], [0.65, "#ff2d55"], [1, "#ff2d55"]],
                        colorbar=dict(title=dict(text="Load %", font=dict(color="#d4ffe2")),
                                      tickfont=dict(color="#d4ffe2"), len=0.6, thickness=12))))
    lab = {n: ORGAN_GEOM[n][0] for n in ORGAN_GEOM}
    fig.add_trace(go.Scatter3d(
        x=[lab[n][0] for n in lab], y=[lab[n][1] - 1.4 for n in lab], z=[lab[n][2] for n in lab],
        mode="text", hoverinfo="skip", showlegend=False,
        text=[f"{byname[n]['pct']:.0f}%" if byname[n]["has_data"] else "—" for n in lab],
        textfont=dict(color="#ffffff", size=13)))
    _add_reference_organs(fig, reference_scenario)
    a_rad = np.deg2rad(angle)
    hidden = dict(visible=False)
    fig.update_layout(
        height=560, paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=0, r=0, t=0, b=0), uirevision=f"hview-{angle}",
        scene=dict(xaxis=hidden, yaxis=hidden, zaxis=hidden, bgcolor="rgba(0,0,0,0)", aspectmode="data",
                   camera=dict(eye=dict(x=2.2 * np.sin(a_rad), y=-2.2 * np.cos(a_rad), z=0.5), up=dict(x=0, y=0, z=1))))
    return fig


def render_health_panel(conn, view_angle: int = 0, show_body: bool = True, astronaut_id: int | None = None):
    st.markdown("### 🩺 VITAL SIGNS · 3D BODY MODEL (FROM THE DATABASE)")
    st.info("The database has no radiation measurements (no slug '" + ir.SLUG_RATE + "'), so solar-storm detection "
            "cannot run on this data. The real health data stored in the database is shown below.")
    reference_scenario = _reference_scenario_select("health_organ_reference")
    astros = [dict(r) for r in ir.list_astronauts(conn)]
    if not astros:
        st.warning("The astronauts table is empty.")
        return
    if astronaut_id is not None:
        sel = next((a for a in astros if a["id"] == astronaut_id), astros[0])
    else:
        sel = st.selectbox("Astronaut", astros, format_func=lambda r: f"{r['name']} · {r['mission_name']} · day {r['mission_day']}",
                           key="health_astro")
    res = ih.assess_health(conn, sel["id"])
    if res["ref"] is None:
        st.warning("No measurements or symptoms for this astronaut.")
        return
    new_ids = ih.issue_alerts(conn, sel["id"], res)
    if new_ids:
        st.toast(f"New alert #{new_ids[0]}", icon="🚨")

    sev = res["severity"]
    col = SEV_COL[sev]
    if sev == "none":
        H(f'<div class="banner ok">🟢 NO ORGAN UNDER LOAD<br><small>Latest record: {res["ref"]:%Y-%m-%d %H:%M}</small></div>')
    else:
        worst = max((o for o in res["organs"] if o["has_data"]), key=lambda o: o["pct"])
        H(f'<div class="banner bad">{"🚨" if sev == "critical" else "⚠"} {SEV_TXT[sev]} · {ir.ORGAN_NAME[worst["organ"]]} {worst["pct"]:.0f}%<br>'
          f'<small>Latest record: {res["ref"]:%Y-%m-%d %H:%M}</small></div>')

    t = st.columns(4)
    lat = {f["slug"]: f for f in res["findings"]}
    hr, sbp, dbp, sl = lat.get("heart_rate"), lat.get("systolic_bp"), lat.get("diastolic_bp"), lat.get("sleep_duration")
    with t[0]:
        H(_tile("LOAD", f"{res['score']}/100", col))
    with t[1]:
        H(_tile("HEART RATE", f"{hr['value']:.0f} bpm" if hr else "—", COL[hr["level"]] if hr else GREY))
    with t[2]:
        H(_tile("BLOOD PRESSURE", f"{sbp['value']:.0f}/{dbp['value']:.0f}" if sbp and dbp else "—",
                COL[max((sbp, dbp), key=lambda f: f["pct"])["level"]] if sbp and dbp else GREY))
    with t[3]:
        H(_tile("SLEEP", f"{sl['value']:g} h" if sl else "—", COL[sl["level"]] if sl else GREY))

    # ---- diagram: how the astronaut is doing over time (same rules as the 3D body) ----
    hist = ih.history(conn, sel["id"])
    if len(hist) >= 1:
        tr, delta = ih.trend(hist)
        tcol = {"improving": "#00ff66", "stable": "#ffb300", "declining": "#ff2d55"}[tr]
        arrow = {"improving": "▼", "stable": "►", "declining": "▲"}[tr]
        H(f'<div class="hud"><div class="p-title">◉ HOW {sel["name"].upper()} IS DOING</div>'
          f'<span style="font-family:Orbitron;font-size:1.3rem;color:{tcol};text-shadow:0 0 10px {tcol}">{arrow} {tr.upper()}</span>'
          f'<span style="font-family:Share Tech Mono;font-size:.8rem;color:#6fe89a"> &nbsp; load {hist[0]["score"]:.0f}% → {hist[-1]["score"]:.0f}% '
          f'({delta:+.0f} points over {len(hist)} day(s) with data) · lower is better</span></div>')
        x = [str(hh["day"]) for hh in hist]
        fig = go.Figure()
        fig.add_hrect(y0=0, y1=25, fillcolor="#00ff66", opacity=0.07, line_width=0)
        fig.add_hrect(y0=25, y1=60, fillcolor="#ffb300", opacity=0.08, line_width=0)
        fig.add_hrect(y0=60, y1=100, fillcolor="#ff2d55", opacity=0.08, line_width=0)
        for organ in ih.ORGAN_LIST:
            ys = [hh["organs"].get(organ) for hh in hist]
            if any(v is not None for v in ys):
                fig.add_trace(go.Scatter(x=x, y=ys, mode="lines+markers", name=ir.ORGAN_NAME[organ], connectgaps=True,
                                         line=dict(width=1.5, dash="dot"), marker=dict(size=6), opacity=0.8))
        fig.add_trace(go.Scatter(x=x, y=[hh["score"] for hh in hist], mode="lines+markers", name="OVERALL LOAD",
                                 line=dict(color="#ffffff", width=3), marker=dict(size=9, color=tcol, line=dict(width=1, color="white"))))
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,18,8,.6)",
                          font=dict(color="#d4ffe2"), legend=dict(orientation="h", y=-0.2),
                          yaxis=dict(title="Organ load % (0 = normal)", range=[0, 100], gridcolor="rgba(0,255,102,.12)"),
                          xaxis=dict(type="category", gridcolor="rgba(0,255,102,.12)"))
        st.plotly_chart(fig, use_container_width=True, key="health_trend")
        st.caption("Green band = within limits (<25%), amber = warning (25-60%), red = critical (≥60%). Each day uses the latest value of every indicator up to that day plus symptoms of the last 3 days.")

    left, right = st.columns([2, 1])
    with left:
        st.caption("Colour = organ load computed from the database. Grey = no data for this organ in the database.")
        st.plotly_chart(build_health_figure(res, view_angle, show_body, reference_scenario),
                        use_container_width=True, key="health_3d")
    with right:
        bars = ""
        for o in sorted(res["organs"], key=lambda o: (not o["has_data"], -o["pct"])):
            if not o["has_data"]:
                bars += (f'<div style="margin:9px 0;font-family:Share Tech Mono;font-size:.78rem;color:{GREY}">'
                         f'{ir.ORGAN_NAME[o["organ"]].upper()} · no data</div>')
                continue
            c = COL[o["level"]]
            sub = ("Symptoms: " + ", ".join(o["symptoms"])) if o["symptoms"] else (o["worst"] or "Within limits")
            bars += (f'<div style="margin:9px 0"><div style="display:flex;justify-content:space-between;font-family:Share Tech Mono;'
                     f'font-size:.78rem"><span>{ir.ORGAN_NAME[o["organ"]].upper()}</span><span style="color:{c}">{o["pct"]:.0f}%</span></div>'
                     f'<div class="track"><div class="fill" style="width:{o["pct"]:.0f}%;background:{c};box-shadow:0 0 8px {c}"></div></div>'
                     f'<div style="font-family:Share Tech Mono;font-size:.66rem;color:#3b9a60">{sub}</div></div>')
        H(f'<div class="hud"><div class="p-title">◉ LOAD BY ORGAN</div>{bars}</div>')
    _render_reference_table(reference_scenario)

    st.markdown("#### Latest measurements")
    st.dataframe([{"Indicator": f["label"], "Value": f"{f['value']:g} {f['unit']}", "Normal range": f["normal"],
                   "Status": {"ok": "within limits", "warn": "caution", "crit": "critical"}[f["level"]],
                   "Time": f"{f['measured_at']:%Y-%m-%d %H:%M}"} for f in res["findings"]], use_container_width=True)

    inds = ih.indicators_with_data(conn, sel["id"])
    if inds:
        pick = st.selectbox("Indicator over time", inds, format_func=lambda r: f"{r['name']} ({r['unit']}) · {r['n']} measurements",
                            key="health_ind")
        s = ih.series(conn, sel["id"], pick["slug"])
        fig = go.Figure(go.Scatter(x=[p[0] for p in s], y=[p[1] for p in s], mode="lines+markers",
                                   line=dict(color="#00ff66", width=2), marker=dict(size=8)))
        fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,18,8,.6)", font=dict(color="#d4ffe2"), showlegend=False,
                          yaxis=dict(title=pick["unit"], gridcolor="rgba(0,255,102,.12)"), xaxis=dict(gridcolor="rgba(0,255,102,.12)"))
        st.plotly_chart(fig, use_container_width=True, key="health_series")

    if res["symptoms"]:
        rows = "".join(f"<div>• {s['reported_at'][:16]} · {s['name']} (severity {s['severity']}/5)"
                       f"{' · ' + s['notes'] if s['notes'] else ''}</div>" for s in reversed(res["symptoms"]))
        H(f'<div class="hud"><div class="p-title">◉ SYMPTOMS (last {ih.SYMPTOM_WINDOW_DAYS} days)</div>'
          f'<div style="font-family:Share Tech Mono;font-size:.8rem">{rows}</div></div>')

    st.markdown("#### Alerts")
    alerts = ir.get_alerts(conn, sel["id"])
    if not alerts:
        st.caption("No alerts.")
    for al in alerts[:12]:
        c = SEV_COL[al["severity"]]
        done = "✔ acknowledged" if al["acknowledged"] else "NEW"
        H(f'<div class="hud" style="border-color:{c};padding:8px 12px"><span style="color:{c};font-family:Orbitron;font-size:.7rem;'
          f'letter-spacing:.12em">[{al["severity"].upper()}] #{al["id"]} · {al["created_at"]} · {done}</span>'
          f'<div style="font-size:.98rem;margin-top:4px">{al["message"]}</div></div>')
        if not al["acknowledged"]:
            st.button(f"Acknowledge alert #{al['id']}", key=f"hack_{al['id']}",
                      on_click=ir.acknowledge_from_path, args=(ir.DB_PATH, al["id"]))


# =============================================================================
#  COMPACT 3D BODY for the MONITORING screen: one model per astronaut, from the database
# =============================================================================
def render_body_compact(astronaut_name: str, view_angle: int = 0, show_body: bool = True):
    """3D body + organ bars + key vitals of the astronaut called `astronaut_name`, read from the database (Theo's data)."""
    import ichor_health as _ih
    st.markdown("### 🩺 VITAL SIGNS · 3D BODY MODEL (DATABASE)")
    try:
        conn = _conn(ir.DB_PATH)
        astros = [dict(r) for r in ir.list_astronauts(conn)]
    except Exception as exc:
        st.error(f"The 3D body model needs the database ({exc}). Run  python setup_db.py  and reload.")
        return
    sel = next((a for a in astros if a["name"] == astronaut_name), None)
    if sel is None:
        st.warning(f"No astronaut called '{astronaut_name}' in the database. Pick one of: " + ", ".join(a["name"] for a in astros))
        return
    res = _ih.assess_health(conn, sel["id"])
    if res["ref"] is None:
        st.warning("No measurements or symptoms for this astronaut in the database.")
        return
    lat = {f["slug"]: f for f in res["findings"]}
    hr, sbp, dbp, sl = lat.get("heart_rate"), lat.get("systolic_bp"), lat.get("diastolic_bp"), lat.get("sleep_duration")
    sev_col = SEV_COL[res["severity"]]
    t = st.columns(4)
    with t[0]:
        H(_tile("LOAD", f"{res['score']}/100", sev_col))
    with t[1]:
        H(_tile("HEART RATE", f"{hr['value']:.0f} bpm" if hr else "—", COL[hr["level"]] if hr else GREY))
    with t[2]:
        H(_tile("BLOOD PRESSURE", f"{sbp['value']:.0f}/{dbp['value']:.0f}" if sbp and dbp else "—",
                COL[max((sbp, dbp), key=lambda f: f["pct"])["level"]] if sbp and dbp else GREY))
    with t[3]:
        H(_tile("SLEEP", f"{sl['value']:g} h" if sl else "—", COL[sl["level"]] if sl else GREY))
    left, right = st.columns([3, 2])
    with left:
        fig = build_health_figure(res, view_angle, show_body)
        fig.update_layout(height=470)
        st.plotly_chart(fig, use_container_width=True, key=f"compact_3d_{sel['id']}")
        st.caption(f"{sel['name']} · data of {res['ref']:%Y-%m-%d %H:%M}. Colour = organ load from the database; grey = no data.")
    with right:
        bars = ""
        for o in sorted(res["organs"], key=lambda o: (not o["has_data"], -o["pct"])):
            if not o["has_data"]:
                bars += (f'<div style="margin:9px 0;font-family:Share Tech Mono;font-size:.78rem;color:{GREY}">'
                         f'{ir.ORGAN_NAME[o["organ"]].upper()} · no data</div>')
                continue
            c = COL[o["level"]]
            sub = ("Symptoms: " + ", ".join(o["symptoms"])) if o["symptoms"] else (o["worst"] or "Within limits")
            bars += (f'<div style="margin:9px 0"><div style="display:flex;justify-content:space-between;font-family:Share Tech Mono;'
                     f'font-size:.78rem"><span>{ir.ORGAN_NAME[o["organ"]].upper()}</span><span style="color:{c}">{o["pct"]:.0f}%</span></div>'
                     f'<div class="track"><div class="fill" style="width:{o["pct"]:.0f}%;background:{c};box-shadow:0 0 8px {c}"></div></div>'
                     f'<div style="font-family:Share Tech Mono;font-size:.66rem;color:#3b9a60">{sub}</div></div>')
        H(f'<div class="hud"><div class="p-title">◉ LOAD BY ORGAN · {sel["name"].upper()}</div>{bars}</div>')



# =============================================================================
#  CHOOSE RADIATION: pick a NASA-sourced radiation environment / event -> organ effects in %
# =============================================================================
# (label, dose, unit, source, note). unit "day" = dose rate in mSv per day (multiplied by the chosen duration), "event" = total dose.
RADIATION_CHOICES = [
    ("ISS / low-Earth orbit", 0.5, "day", "NASA OCHMO Radiation Protection Technical Brief (NASA-STD-3001): ~0.5 mSv/day on ISS", "Published average"),
    ("Deep space transit (Mars mission planning value)", 1.5, "day", "Same NASA brief: 1.5 mSv/day used for Mars transit", "Published planning value"),
    ("Moon surface (lunar stay)", 1.37, "day", "Chang'E-4 lander dosimetry, Zhang et al., Science Advances 2020 (about 1.37 mSv/day) - please verify before citing", "Measured on the lunar far side"),
    ("Mars surface", 0.64, "day", "Curiosity RAD, Hassler et al., Science 2014 (about 0.64 mSv/day) - please verify before citing", "Measured on Mars"),
    ("Mars round trip (about 180 days each way)", 660.0, "event", "Curiosity RAD cruise measurement, Zeitlin et al., Science 2013 (about 0.66 Sv round trip) - please verify before citing", "Total dose of the whole trip"),
    ("Solar storm · mild (50% of the NASA per-event limit)", 125.0, "event", "NASA-STD-3001 limit is 250 mSv per solar particle event; 50% is a team scenario", "Team scenario"),
    ("Solar storm · at the NASA limit (250 mSv)", 250.0, "event", "NASA-STD-3001: 250 mSv per solar particle event", "NASA limit"),
    ("Solar storm · severe (2 × the NASA limit)", 500.0, "event", "Team scenario: twice the NASA per-event limit", "Team scenario"),
]
ORGAN_SYMPTOMS = {"Brain": "headache, dizziness, confusion", "Heart": "chest discomfort, palpitations", "Left Lung": "cough, shortness of breath",
                  "Right Lung": "cough, shortness of breath", "Liver": "abdominal pain, jaundice", "Stomach": "nausea, vomiting"}


def _toggle_rad():
    st.session_state["show_rad_choose"] = not st.session_state.get("show_rad_choose", False)


def render_radiation_chooser(astronaut_name: str, view_angle: int = 0, show_body: bool = True):
    """Button 'CHOOSE RADIATION' -> hazard picker -> % effect per organ (3D body + table). Organ model: ichor_radiation.ORGANS (team assumption)."""
    from types import SimpleNamespace
    import ichor_health as _ih
    opened = st.session_state.get("show_rad_choose", False)
    st.button("☢ CHOOSE RADIATION ▾" if opened else "☢ CHOOSE RADIATION ▸", on_click=_toggle_rad, key="rad_choose_btn")
    if not opened:
        return
    st.markdown("### ☢ RADIATION HAZARD · EFFECT ON THE ORGANS")
    reference_scenario = _reference_scenario_select(
        "rad_choice_organ_reference", "SPE Aug 1972 · 20 g/cm² Al")
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        labels = [c[0] for c in RADIATION_CHOICES]
        choice = RADIATION_CHOICES[labels.index(st.selectbox("Radiation type / event", labels, key="rad_choice"))]
    with c2:
        days = st.slider("Duration (days)", 1, 365, 30, key="rad_days") if choice[2] == "day" else None
        if choice[2] == "event":
            st.caption("Single event / whole trip: duration does not apply.")
    with c3:
        shelter = st.toggle("Storm shelter (×0.5 dose)", value=False, key="rad_choice_shelter")
        add_health = st.toggle("Add to the astronaut's current load", value=True, key="rad_add_health")
    dose = choice[1] * (days if days else 1) * (0.5 if shelter else 1.0)
    ref_limit = ir.EVENT_LIMIT_MSV if choice[2] == "event" else ir.CAREER_LIMIT_MSV
    ref_name = f"{ir.EVENT_LIMIT_MSV:.0f} mSv per-event limit" if choice[2] == "event" else f"{ir.CAREER_LIMIT_MSV:.0f} mSv career limit"

    # current (Theo's data) load of the selected astronaut, per organ
    base = {}
    if add_health:
        try:
            conn = _conn(ir.DB_PATH)
            a = next((x for x in [dict(r) for r in ir.list_astronauts(conn)] if x["name"] == astronaut_name), None)
            if a:
                base = {o["organ"]: o["pct"] for o in _ih.assess_health(conn, a["id"])["organs"] if o["has_data"]}
        except Exception:
            base = {}
    organs = []
    for name, cfg in ir.ORGANS.items():
        d = dose * cfg["depth"]
        rad_pct = min(100.0, d / cfg["limit"] * 100)
        pct = min(100.0, rad_pct + base.get(name, 0.0))
        organs.append({"organ": name, "dose_msv": round(d, 1), "pct": round(pct, 1), "rad_pct": round(rad_pct, 1), "base": base.get(name, 0.0),
                       "level": ir._level(pct)})
    organs.sort(key=lambda o: o["pct"], reverse=True)
    worst = organs[0]
    sev = "critical" if worst["pct"] >= 60 else "warning" if worst["pct"] >= 25 else "none"

    t = st.columns(3)
    with t[0]:
        H(_tile("DOSE", f"{dose:,.1f} mSv", SEV_COL[sev]))
    with t[1]:
        H(_tile("OF " + ("EVENT LIMIT" if choice[2] == "event" else "CAREER LIMIT"), f"{dose / ref_limit * 100:.0f}%", SEV_COL[sev]))
    with t[2]:
        H(_tile("MOST AFFECTED", f"{ir.ORGAN_NAME[worst['organ']]} {worst['pct']:.0f}%", SEV_COL[sev]))
    if sev != "none":
        H(f'<div class="banner bad">{"🚨" if sev == "critical" else "⚠"} {SEV_TXT[sev]} · {ir.ORGAN_NAME[worst["organ"]]} {worst["pct"]:.0f}%<br>'
          f'<small>{choice[0]}: {dose:,.1f} mSv. Reference: {ref_name}.</small></div>')
    else:
        H(f'<div class="banner ok">🟢 NO ORGAN IN THE WARNING RANGE<br><small>{choice[0]}: {dose:,.1f} mSv. Reference: {ref_name}.</small></div>')

    left, right = st.columns([2, 1])
    with left:
        fig = build_body_figure(SimpleNamespace(organs=organs), view_angle, show_body, reference_scenario)
        fig.update_layout(height=470)
        st.plotly_chart(fig, use_container_width=True, key="rad_choose_3d")
        st.caption("Organ colour = radiation effect" + (" plus the current load from the database" if base else "") +
                   ". Cyan diamonds = NASA reference data; hover to inspect. Drag to rotate, scroll to zoom.")
    with right:
        bars = ""
        for o in organs:
            c = COL[o["level"]]
            extra = f" (radiation {o['rad_pct']:.0f}% + current {o['base']:.0f}%)" if base else ""
            watch = ORGAN_SYMPTOMS[o["organ"]] if o["pct"] >= 25 else "no expected effect"
            bars += (f'<div style="margin:9px 0"><div style="display:flex;justify-content:space-between;font-family:Share Tech Mono;'
                     f'font-size:.78rem"><span>{ir.ORGAN_NAME[o["organ"]].upper()}</span><span style="color:{c}">{o["pct"]:.0f}%</span></div>'
                     f'<div class="track"><div class="fill" style="width:{o["pct"]:.0f}%;background:{c};box-shadow:0 0 8px {c}"></div></div>'
                     f'<div style="font-family:Share Tech Mono;font-size:.66rem;color:#3b9a60">{o["dose_msv"]:.1f} mSv in the organ{extra}<br>watch for: {watch}</div></div>')
        H(f'<div class="hud"><div class="p-title">◉ EFFECT BY ORGAN · {astronaut_name.upper()}</div>{bars}</div>')
    _render_reference_table(reference_scenario)
    st.caption(f"Source of the dose: {choice[3]}. {choice[4]}. The organ percentages use the team's organ model "
               "(depth attenuation and organ limits in ichor_radiation.py): a team assumption, not an official NASA organ limit. Not medical advice.")