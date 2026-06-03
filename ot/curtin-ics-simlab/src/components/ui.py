#!/usr/bin/env python3

import streamlit as st
from app_lib import (
    setup_page,
    render_top_summary,
    render_home_image,
    render_sidebar_controls,
    load_component_data,
)

setup_page("ICS Dashboard")
render_sidebar_controls()

st.title("Industrial Control System Dashboard")

hmi_info, plc_info, sensor_info, actuator_info, hil_info = load_component_data()

render_top_summary(hmi_info, plc_info, sensor_info, actuator_info)

st.divider()

render_home_image()