from __future__ import annotations

import datetime as dt
import math
import sqlite3

import streamlit as st

import ichor_radiation as ir


def add_measurement(
    conn: sqlite3.Connection,
    astronaut_id: int,
    indicator_id: int,
    value: float,
    notes: str = "",
) -> int:
    if not math.isfinite(value):
        raise ValueError("Measurement value must be a finite number.")

    measured_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    session_notes = notes.strip() or "Manual measurement entry"
    with conn:
        if conn.execute("SELECT 1 FROM astronauts WHERE id = ?", (astronaut_id,)).fetchone() is None:
            raise ValueError(f"Astronaut {astronaut_id} does not exist.")
        if conn.execute("SELECT 1 FROM indicators WHERE id = ?", (indicator_id,)).fetchone() is None:
            raise ValueError(f"Measurement type {indicator_id} does not exist.")
        session_id = conn.execute(
            """INSERT INTO assessment_sessions
               (astronaut_id, assessment_type, started_at, completed_at, notes)
               VALUES (?, 'ad_hoc', ?, ?, ?)""",
            (astronaut_id, measured_at, measured_at, session_notes),
        ).lastrowid
        measurement_id = conn.execute(
            """INSERT INTO measurements
               (astronaut_id, indicator_id, value, measured_at, session_id)
               VALUES (?, ?, ?, ?, ?)""",
            (astronaut_id, indicator_id, value, measured_at, session_id),
        ).lastrowid

    return int(measurement_id)


def measurement_history(conn: sqlite3.Connection, astronaut_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT m.measured_at AS "Measured at (UTC)", i.name AS "Measurement",
                  m.value AS "Result", i.unit AS "Unit", COALESCE(s.notes, '') AS "Notes"
           FROM measurements m
           JOIN indicators i ON i.id = m.indicator_id
           LEFT JOIN assessment_sessions s ON s.id = m.session_id
           WHERE m.astronaut_id = ?
           ORDER BY m.measured_at DESC, m.id DESC""",
        (astronaut_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def render_measurements_panel(astronaut_label: str, real_astro: dict | None) -> None:
    st.markdown("### 🧪 MEASUREMENT LOG")
    if real_astro is None:
        st.info("Select an astronaut from the database in the sidebar to record and view measurements.")
        return

    st.caption(f"Entries are saved permanently for {astronaut_label}. Timestamps are recorded in UTC.")
    try:
        conn = ir.connect(ir.DB_PATH)
    except (FileNotFoundError, sqlite3.Error) as exc:
        st.error(f"Could not open the astronaut database: {exc}")
        return

    try:
        indicators = [
            dict(row)
            for row in conn.execute(
                "SELECT id, name, unit FROM indicators ORDER BY category, name"
            ).fetchall()
        ]
    except sqlite3.Error as exc:
        st.error(f"Could not load measurement types from the database: {exc}")
        return

    if not indicators:
        st.warning("No measurement types are configured in the database.")
        return

    with st.form("measurement_entry_form", clear_on_submit=True):
        indicator_id = st.selectbox(
            "Measurement",
            [int(row["id"]) for row in indicators],
            format_func=lambda selected_id: next(
                f'{row["name"]} ({row["unit"]})'
                for row in indicators
                if row["id"] == selected_id
            ),
        )
        value = st.number_input("Result", value=0.0, step=0.1)
        notes = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("SAVE MEASUREMENT")

    if submitted:
        try:
            add_measurement(conn, real_astro["id"], indicator_id, value, notes)
        except (ValueError, sqlite3.Error) as exc:
            st.error(f"Could not save the measurement: {exc}")
        else:
            st.success("Measurement saved.")

    st.markdown("#### Measurement history")
    try:
        history = measurement_history(conn, real_astro["id"])
    except sqlite3.Error as exc:
        st.error(f"Could not load measurement history: {exc}")
        return

    if history:
        st.dataframe(history, use_container_width=True, hide_index=True)
    else:
        st.info("No measurements have been recorded for this astronaut yet.")
