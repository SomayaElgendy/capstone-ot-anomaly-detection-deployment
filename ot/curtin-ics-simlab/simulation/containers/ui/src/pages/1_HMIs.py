import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app_lib import (
    setup_page,
    render_sidebar_controls,
    load_component_data,
    render_device_page,
    auto_refresh_current_page,
)

setup_page("HMIs")
render_sidebar_controls()

hmi_info, _, _, _, _ = load_component_data()
render_device_page("Human Machine Interfaces", hmi_info, num_columns=2, divider_color="orange")

auto_refresh_current_page()