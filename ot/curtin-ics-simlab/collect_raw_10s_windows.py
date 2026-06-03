import time
import json
import csv
from pathlib import Path
from datetime import datetime

import redis


REDIS_HOST = "localhost"
REDIS_PORT = 6379

PROCESS_STREAM = "hil:telemetry"
NETWORK_STREAM = "network:telemetry"

WINDOW_SECONDS = 10
NUM_WINDOWS = 2

OUT_DIR = Path("raw_window_inspection")
OUT_DIR.mkdir(exist_ok=True)


def parse_entry(data):
    parsed = {}
    for k, v in data.items():
        if k == "_validation":
            parsed[k] = v
            continue
        try:
            parsed[k] = float(v)
        except:
            parsed[k] = v
    return parsed


def save_csv(path, rows):
    if not rows:
        return

    keys = sorted(set().union(*(row.keys() for row in rows)))

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def collect_window(r, window_id):
    print(f"\nCollecting window {window_id} for {WINDOW_SECONDS} seconds...")

    start_time = time.time()
    start_ms = int(start_time * 1000)
    end_time = start_time + WINDOW_SECONDS

    process_rows = []
    network_rows = []

    last_process_id = "$"
    last_network_id = "$"

    while time.time() < end_time:
        messages = r.xread(
            {
                PROCESS_STREAM: last_process_id,
                NETWORK_STREAM: last_network_id,
            },
            block=1000,
            count=100,
        )

        for stream_name, entries in messages:
            for msg_id, data in entries:
                if stream_name == PROCESS_STREAM:
                    last_process_id = msg_id
                    row = parse_entry(data)
                    row["_redis_id"] = msg_id
                    process_rows.append(row)

                elif stream_name == NETWORK_STREAM:
                    last_network_id = msg_id
                    row = parse_entry(data)
                    row["_redis_id"] = msg_id
                    network_rows.append(row)

    end_ms = int(time.time() * 1000)

    summary = {
        "window_id": window_id,
        "start_iso": datetime.fromtimestamp(start_time).isoformat(timespec="seconds"),
        "duration_seconds": WINDOW_SECONDS,
        "process_rows": len(process_rows),
        "network_rows": len(network_rows),
        "process_fields": sorted(list(process_rows[0].keys())) if process_rows else [],
        "network_fields": sorted(list(network_rows[0].keys())) if network_rows else [],
    }

    print("\nSummary:")
    print(json.dumps(summary, indent=2))

    base = OUT_DIR / f"window_{window_id}"

    with open(base.with_suffix(".summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    with open(OUT_DIR / f"window_{window_id}_process.json", "w") as f:
        json.dump(process_rows, f, indent=2)

    with open(OUT_DIR / f"window_{window_id}_network.json", "w") as f:
        json.dump(network_rows, f, indent=2)

    save_csv(OUT_DIR / f"window_{window_id}_process.csv", process_rows)
    save_csv(OUT_DIR / f"window_{window_id}_network.csv", network_rows)

    return summary


def main():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.ping()

    print("Connected to Redis.")
    print(f"Collecting {NUM_WINDOWS} windows x {WINDOW_SECONDS}s each")
    print(f"Output folder: {OUT_DIR.resolve()}")

    all_summaries = []

    for i in range(1, NUM_WINDOWS + 1):
        summary = collect_window(r, i)
        all_summaries.append(summary)

    with open(OUT_DIR / "all_summaries.json", "w") as f:
        json.dump(all_summaries, f, indent=2)

    print("\nDone. Files saved in:", OUT_DIR.resolve())


if __name__ == "__main__":
    main()
