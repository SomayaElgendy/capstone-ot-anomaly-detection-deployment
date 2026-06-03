import json
import os
import sqlite3
import sys

import altair as alt
import pandas as pd
import requests
import streamlit as st
import time

REQUEST_TIMEOUT = 2
PHYSICAL_CHART_LIMIT = 100
AUTO_REFRESH_SECONDS = 1

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DB_PATH = os.path.join(BASE_DIR, "physical_interactions.db")
IMAGE_PATH = os.path.join(BASE_DIR, "ics_system.png")


def auto_refresh_current_page():
    if st.session_state.get("auto_refresh_enabled", True):
        time.sleep(AUTO_REFRESH_SECONDS)
        st.rerun()

def setup_page(page_title):
    st.set_page_config(
        page_title=page_title,
        page_icon="🛠️",
        layout="wide",
    )
    
def setup_page(page_title):
    st.set_page_config(
        page_title=page_title,
        page_icon="🛠️",
        layout="wide",
    )

    st.markdown(
        """
        <style>
            :root {
                --bg1: #060b18;
                --bg2: #0a1430;
                --glass: rgba(255,255,255,0.06);
                --glass2: rgba(255,255,255,0.08);
                --stroke: rgba(255,255,255,0.10);
                --blue: #3b82f6;
                --blue2: #2563eb;
                --text: #e8eefc;
                --muted: rgba(232,238,252,0.72);
            }

            html, body, [class*="css"] {
                color: var(--text);
            }

            .stApp,
            .stAppViewContainer,
            .main {
                background:
                    radial-gradient(circle at top left, rgba(59,130,246,0.10), transparent 30%),
                    linear-gradient(135deg, var(--bg1), var(--bg2)) !important;
                color: var(--text);
            }

            .block-container {
                padding-top: 1.2rem;
                padding-bottom: 1.2rem;
                max-width: 1500px;
            }

            /* Top Streamlit chrome/header */
            header[data-testid="stHeader"] {
                background: linear-gradient(180deg, #0a1430, #060b18) !important;
                border-bottom: 1px solid rgba(255,255,255,0.08) !important;
            }

            [data-testid="stToolbar"] {
                background: transparent !important;
            }

            [data-testid="stToolbar"] button,
            [data-testid="stToolbar"] a,
            [data-testid="stToolbar"] svg {
                color: #e8eefc !important;
                fill: #e8eefc !important;
            }

            [data-testid="stDecoration"] {
                background: transparent !important;
            }

            /* Sidebar */
            section[data-testid="stSidebar"] {
                background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.03));
                border-right: 1px solid var(--stroke);
            }

            section[data-testid="stSidebar"] * {
                color: var(--text) !important;
            }

            [data-testid="stSidebarNav"] {
                margin-top: 0.5rem;
            }

            [data-testid="stSidebarNav"] a {
                border-radius: 12px;
                margin-bottom: 0.2rem;
                color: var(--text) !important;
                font-size: 17px !important;
            }

            [data-testid="stSidebarNav"] a:hover {
                background: rgba(255,255,255,0.08);
            }

            [data-testid="stSidebarNav"] a[aria-current="page"] {
                background: rgba(255,255,255,0.12);
                font-weight: 700;
            }

            /* Headings */
            h1, h2, h3 {
                color: var(--text) !important;
                font-weight: 800 !important;
                letter-spacing: -0.02em;
            }

            h1 {
                font-size: 3.2rem !important;
            }

            h2 {
                font-size: 2rem !important;
            }

            h3 {
                font-size: 1.45rem !important;
            }

            /* Text */
            div[data-testid="stMarkdownContainer"] p {
                color: var(--text);
                font-size: 17px;
            }

            .muted-text {
                color: var(--muted) !important;
                font-size: 15px;
            }

            /* Metric cards */
            div[data-testid="stMetric"] {
                border: 1px solid var(--stroke);
                border-radius: 18px;
                padding: 0.8rem 0.9rem;
                background: linear-gradient(135deg, rgba(59,130,246,0.20), rgba(255,255,255,0.04));
                box-shadow: 0 14px 40px rgba(0,0,0,0.45);
            }

            div[data-testid="stMetricLabel"] {
                opacity: 0.82;
                font-size: 15px;
                letter-spacing: 0.2px;
            }

            div[data-testid="stMetricValue"] {
                font-size: 2.5rem;
                font-weight: 800;
            }

            /* Containers / panels */
            div[data-testid="stVerticalBlock"] div[data-testid="stContainer"] {
                border-radius: 18px;
            }

            div[data-testid="stHorizontalBlock"] > div div[data-testid="stContainer"],
            div[data-testid="stVerticalBlock"] div[data-testid="stContainer"][data-border="true"] {
                border: 1px solid var(--stroke) !important;
                background: rgba(255,255,255,0.05) !important;
                box-shadow: 0 14px 40px rgba(0,0,0,0.45);
                border-radius: 18px !important;
                padding: 0.35rem 0.45rem;
            }

            .section-panel {
                border: 1px solid var(--stroke);
                background: rgba(255,255,255,0.05);
                border-radius: 18px;
                padding: 16px;
                box-shadow: 0 14px 40px rgba(0,0,0,0.45);
            }

            .panel-title {
                font-size: 20px;
                font-weight: 800;
                margin-bottom: 4px;
            }

            .panel-subtitle {
                color: var(--muted);
                font-size: 15px;
                margin-bottom: 12px;
            }

            /* Dataframes / tables */
            .stDataFrame, div[data-testid="stDataFrame"] {
                border-radius: 14px !important;
                overflow: hidden;
                border: 1px solid rgba(255,255,255,0.08);
                background: rgba(0,0,0,0.25);
            }

            .stDataFrame * {
                color: var(--text) !important;
            }

            /* Inputs / buttons */
            div[data-baseweb="select"] > div,
            div[data-baseweb="input"] > div,
            .stTextInput input,
            .stSelectbox div[data-baseweb="select"] > div {
                background: rgba(255,255,255,0.06) !important;
                border: 1px solid rgba(255,255,255,0.12) !important;
                color: var(--text) !important;
                border-radius: 10px !important;
            }

            .stButton > button,
            .stDownloadButton > button {
                border-radius: 12px !important;
                border: 1px solid rgba(255,255,255,0.12) !important;
                background: rgba(255,255,255,0.06) !important;
                color: var(--text) !important;
                font-size: 16px !important;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover {
                border-color: rgba(59,130,246,0.35) !important;
                background: rgba(59,130,246,0.12) !important;
            }

            .stToggle label, .stToggle div {
                color: var(--text) !important;
                font-size: 16px !important;
            }

            .streamlit-expanderHeader {
                color: var(--text) !important;
                font-size: 16px !important;
            }

            .streamlit-expanderContent {
                background: rgba(255,255,255,0.04);
                border-radius: 14px;
            }

            hr {
                border-color: rgba(255,255,255,0.08) !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_controls():
    st.sidebar.title("ICS Dashboard")
    st.sidebar.caption("Native multi-page navigation")

    if "auto_refresh_enabled" not in st.session_state:
        st.session_state["auto_refresh_enabled"] = True

    st.sidebar.toggle(
        "Live refresh",
        key="auto_refresh_enabled",
    )


def retrieve_configs(filename):
    with open(filename, "r") as f:
        return json.loads(f.read())


def get_component_info(configs):
    hmi_info = {}
    plc_info = {}
    sensor_info = {}
    actuator_info = {}
    hil_info = {}

    if "hmis" in configs:
        for hmi in configs["hmis"]:
            hmi_info[hmi["name"]] = {"ip": hmi["network"]["ip"]}

    if "plcs" in configs:
        for plc in configs["plcs"]:
            plc_info[plc["name"]] = {"ip": plc["network"]["ip"]}

    if "sensors" in configs:
        for sensor in configs["sensors"]:
            sensor_info[sensor["name"]] = {"ip": sensor["network"]["ip"]}

    if "actuators" in configs:
        for actuator in configs["actuators"]:
            actuator_info[actuator["name"]] = {"ip": actuator["network"]["ip"]}

    if "hils" in configs:
        for hil in configs["hils"]:
            physical_values = [pv["name"] for pv in hil["physical_values"]]
            hil_info[hil["name"]] = {"values": physical_values}

    return hmi_info, plc_info, sensor_info, actuator_info, hil_info


@st.cache_data(show_spinner=False)
def load_component_data():
    configs = retrieve_configs(CONFIG_PATH)
    return get_component_info(configs)


def create_register_table_rows(type_list, address, count, value, response):
    for register in response.values():
        type_list.append(register["type"])
        address.append(register["address"])
        count.append(register["count"])
        value.append(register["value"])


def create_register_table(response):
    type_list, address, count, value = [], [], [], []
    create_register_table_rows(type_list, address, count, value, response)
    return pd.DataFrame(
        {"type": type_list, "address": address, "count": count, "value": value}
    ).astype(str)


def fetch_registers(ip):
    try:
        response = requests.get(f"http://{ip}:1111/registers", timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return create_register_table(response.json()), None
    except Exception as e:
        return None, str(e)


def render_top_summary(hmi_info, plc_info, sensor_info, actuator_info):
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("HMIs", len(hmi_info))
    k2.metric("PLCs", len(plc_info))
    k3.metric("Sensors", len(sensor_info))
    k4.metric("Actuators", len(actuator_info))


def render_home_image():
    if os.path.exists(IMAGE_PATH):
        col1, col2, col3 = st.columns([1, 1.8, 1])
        with col2:
            st.image(IMAGE_PATH)
    else:
        st.info("Environment image not found — place ics_system.png alongside ui.py.")

def render_device_page(page_title, info_dict, num_columns=2, divider_color="orange"):
    st.title("Industrial Control System Dashboard")

    hmi_info, plc_info, sensor_info, actuator_info, _ = load_component_data()
    render_top_summary(hmi_info, plc_info, sensor_info, actuator_info)

    st.divider()
    st.markdown(
        f'''
        <div class="section-panel">
            <div class="panel-title">{page_title}</div>
            <div class="panel-subtitle">Live device registers with continuous refresh.</div>
        </div>
        ''',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    if not info_dict:
        st.info("No devices found in config.")
        return

    cols = st.columns(num_columns)
    col_index = 0

    for name, info in info_dict.items():
        with cols[col_index]:
            with st.container(border=True):
                st.markdown(f"##### {name}")
                df, error = fetch_registers(info["ip"])
                if error:
                    st.error(f"Could not reach {name}: {error}")
                elif df is None or df.empty:
                    st.info("No register data available.")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)

        col_index = (col_index + 1) % num_columns


def get_db_connection():
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH)


def get_latest_physical_value(conn, table_name):
    try:
        df = pd.read_sql_query(
            f'SELECT value FROM "{table_name}" ORDER BY timestamp DESC LIMIT 1',
            conn,
        )
        if df.empty:
            return pd.DataFrame(columns=["physical_value", "value"])
        df["physical_value"] = table_name
        return df[["physical_value", "value"]]
    except Exception:
        return pd.DataFrame(columns=["physical_value", "value"])


def get_physical_timeseries(conn, table_name, limit=PHYSICAL_CHART_LIMIT):
    try:
        df = pd.read_sql_query(
            f'SELECT timestamp, value FROM "{table_name}" ORDER BY timestamp DESC LIMIT {limit}',
            conn,
        )
        if df.empty:
            return pd.DataFrame(columns=["timestamp", "value"])

        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["timestamp", "value"])
        return df.groupby("timestamp")[["value"]].mean().reset_index()
    except Exception:
        return pd.DataFrame(columns=["timestamp", "value"])


def render_physical_page(hil_info):
    st.title("Industrial Control System Dashboard")

    hmi_info, plc_info, sensor_info, actuator_info, _ = load_component_data()
    render_top_summary(hmi_info, plc_info, sensor_info, actuator_info)

    st.divider()
    st.markdown(
        """
        <div class="section-panel">
            <div class="panel-title">Hardware-in-the-Loops</div>
            <div class="panel-subtitle">Latest physical values and live trends from the OT process.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    conn = get_db_connection()
    if conn is None:
        st.error("physical_interactions.db not found.")
        return

    physical_values = []
    for hil in hil_info.values():
        physical_values.extend(hil["values"])

    if not physical_values:
        st.info("No physical values found in config.")
        conn.close()
        return

    cols = st.columns(3)
    col_index = 0

    for physical_value in physical_values:
        with cols[col_index]:
            with st.container(border=True):
                st.markdown(f"##### {physical_value}")

                latest_df = get_latest_physical_value(conn, physical_value)
                if latest_df.empty:
                    st.info("No latest value available.")
                else:
                    st.dataframe(latest_df, use_container_width=True, hide_index=True)

                ts_df = get_physical_timeseries(conn, physical_value)
                if ts_df.empty:
                    st.info("No time-series data available.")
                else:
                    chart = (
                        alt.Chart(ts_df, height=325)
                        .mark_line()
                        .encode(
                            x=alt.X("timestamp:T", title="Time", axis=alt.Axis(format="%M:%S")),
                            y=alt.Y("value:Q", title="Value"),
                        )
                    )
                    st.altair_chart(chart, use_container_width=True)

        col_index = (col_index + 1) % 3

    conn.close()