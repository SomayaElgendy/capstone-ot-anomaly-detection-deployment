import json
import random
from pathlib import Path
from datetime import datetime, timedelta

INPUT_FILES = [
    "all_alerts/alerts_T0838_modify_alarm_settings.json",
    "all_alerts/alerts_T0868_detect_operating_mode.json",
    "all_alerts/alerts_T0821_modify_controller_tasking.json",
    "all_alerts/alerts_T0836_modify_parameters.json",
    "all_alerts/alerts_T0858_change_operating_mode.json",
]

OUTPUT_FILE = "outputs/demo_mixed_alerts.json"

MAX_PER_ATTACK = None  # change if you want more/less alerts

all_groups = []

for file in INPUT_FILES:
    path = Path(file)
    with open(path, "r", encoding="utf-8") as f:
        alerts = json.load(f)

    random.shuffle(alerts)
    selected = alerts if MAX_PER_ATTACK is None else alerts[:MAX_PER_ATTACK]
    all_groups.append(selected)

mixed = []

# Burst-style mixing: realistic, not fully random
max_len = max(len(group) for group in all_groups)

for i in range(max_len):
    group_order = list(range(len(all_groups)))
    random.shuffle(group_order)

    for group_idx in group_order:
        if i < len(all_groups[group_idx]):
            mixed.append(all_groups[group_idx][i])

start_time = datetime.now()

for idx, alert in enumerate(mixed):
    t1 = start_time + timedelta(seconds=idx * 10)
    t2 = t1 + timedelta(seconds=10)

    alert["window_start_time"] = t1.isoformat(timespec="milliseconds")
    alert["window_end_time"] = t2.isoformat(timespec="milliseconds")
    alert["pipeline_time"] = t2.isoformat(timespec="milliseconds")

# Add demo IDs
for idx, alert in enumerate(mixed, start=1):
    alert["demo_sequence"] = idx

Path("outputs").mkdir(exist_ok=True)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(mixed, f, indent=2)

print(f"Created {OUTPUT_FILE}")
print(f"Total alerts: {len(mixed)}")