# ============================================================
# V5 FULL STREAMLIT SIMULATION APP (COMPLETE BUILD)
# - Bravo simulation logic
# - Oxygen unlock gate
# - SVOD unlock gate
# - Class code cohort isolation
# - SQLite backend
# - Leaderboard + exports
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
from datetime import datetime
import plotly.express as px
import io

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(page_title="Media Simulation V5", layout="wide")

st.title("📺 Media Strategy Simulation (V5)")
st.markdown("Class-based simulation with Bravo → Oxygen → SVOD progression")

# ============================================================
# DATABASE SETUP
# ============================================================
conn = sqlite3.connect("simulations.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_code TEXT,
    timestamp TEXT,
    student TEXT,
    team TEXT,
    year INTEGER,
    ocf REAL,
    roi REAL,
    hitrate REAL,
    oxygen INTEGER,
    svod INTEGER
)
""")

conn.commit()

# ============================================================
# SESSION STATE INIT
# ============================================================
if "year" not in st.session_state:
    st.session_state.year = 1

if "bravo_completed" not in st.session_state:
    st.session_state.bravo_completed = False

if "oxygen_unlocked" not in st.session_state:
    st.session_state.oxygen_unlocked = False

if "svod_unlocked" not in st.session_state:
    st.session_state.svod_unlocked = False

# ============================================================
# CLASS CODE (COHORT ISOLATION)
# ============================================================
st.sidebar.header("🏫 Class Code")

st.sidebar.markdown("""
### Suggested formats:
- DARDEN_2026_BRAND
- WHARTON_2025_MKTG
- KELLOGG_2026_MEDIA
- INSEAD_2026_STRATEGY
""")

class_code = st.sidebar.text_input(
    "Enter Class Code",
    value="DARDEN_2026_BRAND"
)

# ============================================================
# STUDENT INPUTS
# ============================================================
st.sidebar.header("👥 Student Info")

student_name = st.sidebar.text_input("Student Name", "Anonymous")
team_name = st.sidebar.text_input("Team Name", "Team A")

# ============================================================
# SIMULATION DATA (PLACEHOLDER MODEL)
# ============================================================
np.random.seed(42)

shows = pd.DataFrame({
    "Show": [f"Show {i}" for i in range(1, 11)],
    "Revenue": np.random.randint(80, 200, 10),
    "Total_Cost": np.random.randint(50, 150, 10)
})

# Core metrics
ocf = (shows["Revenue"] - shows["Total_Cost"]).sum()
roi = ocf / shows["Total_Cost"].sum()

# ============================================================
# BRAVO SIMULATION
# ============================================================
st.subheader("🎬 Bravo Simulation")

st.dataframe(shows, use_container_width=True)

if st.button("Run Bravo Simulation"):

    st.session_state.bravo_completed = True

    st.success("Bravo simulation completed.")

    # Unlock Oxygen condition
    if roi > 0.25:
        st.session_state.oxygen_unlocked = True
        st.info("🔓 Oxygen Channel Unlocked!")
    else:
        st.warning("Oxygen not unlocked. Improve ROI > 25%.")

# ============================================================
# OXYGEN SIMULATION (GATED)
# ============================================================
st.subheader("🧪 Oxygen Channel")

if st.session_state.oxygen_unlocked:

    oxygen_shows = shows.copy()
    oxygen_shows["Revenue"] *= np.random.uniform(1.1, 1.4)

    st.dataframe(oxygen_shows, use_container_width=True)

    if st.button("Run Oxygen Simulation"):

        oxygen_roi = (
            oxygen_shows["Revenue"].sum() - oxygen_shows["Total_Cost"].sum()
        ) / oxygen_shows["Total_Cost"].sum()

        if oxygen_roi > 0.30:
            st.session_state.svod_unlocked = True
            st.success("🔓 SVOD Unlocked!")
        else:
            st.warning("SVOD not unlocked yet. Target ROI > 30%.")

else:
    st.info("Complete Bravo with sufficient performance to unlock Oxygen.")

# ============================================================
# SVOD SIMULATION (GATED)
# ============================================================
st.subheader("📡 SVOD Platform")

if st.session_state.svod_unlocked:
    st.success("SVOD Access Granted")
else:
    st.info("SVOD locked. Complete Oxygen performance threshold.")

# ============================================================
# SUBMISSION LOGIC
# ============================================================
st.divider()
st.subheader("📥 Submit Results")

if st.button("Submit Simulation"):

    hitrate = (shows["Revenue"] > shows["Total_Cost"]).mean()

    cursor.execute("""
        INSERT INTO submissions (
            class_code, timestamp, student, team, year,
            ocf, roi, hitrate, oxygen, svod
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        class_code,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        student_name,
        team_name,
        st.session_state.year,
        ocf,
        roi,
        hitrate,
        int(st.session_state.oxygen_unlocked),
        int(st.session_state.svod_unlocked)
    ))

    conn.commit()

    st.success("Submission saved to class database.")

    # Move simulation forward
    st.session_state.year += 1

# ============================================================
# CLASS LEADERBOARD (FILTERED BY CLASS CODE)
# ============================================================
st.divider()
st.subheader(f"🏆 Leaderboard: {class_code}")

df = pd.read_sql_query(
    "SELECT * FROM submissions WHERE class_code = ?",
    conn,
    params=(class_code,)
)

if len(df) > 0:

    col1, col2 = st.columns(2)

    with col1:
        st.dataframe(
            df.sort_values("roi", ascending=False),
            use_container_width=True
        )

    with col2:
        fig = px.bar(
            df.groupby("team")["roi"].mean().reset_index(),
            x="team",
            y="roi",
            title="Average ROI by Team"
        )
        st.plotly_chart(fig, use_container_width=True)

else:
    st.info("No submissions yet for this class.")

# ============================================================
# CLASS EXPORT
# ============================================================
st.divider()
st.subheader("📄 Export Class Report")

if st.button("Download Class Report"):

    df_export = pd.read_sql_query(
        "SELECT * FROM submissions WHERE class_code = ?",
        conn,
        params=(class_code,)
    )

    buffer = io.StringIO()

    buffer.write(f"CLASS REPORT: {class_code}\n\n")
    buffer.write(f"Total Submissions: {len(df_export)}\n\n")

    buffer.write("TEAM PERFORMANCE SUMMARY\n")
    buffer.write(
        df_export.groupby("team")[["roi", "ocf", "hitrate"]]
        .mean()
        .to_string()
    )

    buffer.write("\n\nFULL DATA\n")
    buffer.write(df_export.to_string(index=False))

    st.download_button(
        label="Download Report (.txt)",
        data=buffer.getvalue(),
        file_name=f"{class_code}_report.txt",
        mime="text/plain"
    )