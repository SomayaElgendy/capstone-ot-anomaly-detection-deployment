import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from app_lib import (
    setup_page,
    render_sidebar_controls,
    load_component_data,
    render_physical_page,
    auto_refresh_current_page,
)

setup_page("Physical")
render_sidebar_controls()

_, _, _, _, hil_info = load_component_data()
render_physical_page(hil_info)

auto_refresh_current_page()