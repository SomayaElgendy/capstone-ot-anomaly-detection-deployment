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

# Network flows may be written late, so wait before searching network stream
NETWORK_DELAY_SECONDS = 70

OUT_DIR = Path("aligned_window_inspection")
OUT_DIR.mkdir(exist_ok=True)


def parse_entry(redis_id, data):
    row = {"_redis_id": redis_id}
    for k, v in data.items():
        if k == "_validation":
            row[k] = v
            continue
        try:
            row[k] = float(v)
        except Exception:
            row[k] = v
    return row


def save_csv(path, rows):
    if not rows:
        return
    keys = sorted(set().union(*(row.keys() for row in rows)))
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def filter_by_timestamp(entries, start_ms, end_ms):
    rows = []
    for redis_id, data in entries:
        row = parse_entry(redis_id, data)

        ts = row.get("timestamp_unix_ms")
        if ts is None:
            continue

        try:
            ts = int(float(ts))
        except Exception:
            continue

        if start_ms <= ts < end_ms:
            rows.append(row)

    return rows


def collect_one_window(r, window_id):
    print(f"\n=== Collecting aligned window {window_id} ===")

    start_time = time.time()
    start_ms = int(start_time * 1000)
    end_time = start_time + WINDOW_SECONDS
    end_ms = int(end_time * 1000)

    print("Window start:", datetime.fromtimestamp(start_time).isoformat(timespec="seconds"))
    print("Window end:  ", datetime.fromtimestamp(end_time).isoformat(timespec="seconds"))

    print(f"Waiting {WINDOW_SECONDS}s for process window...")
    time.sleep(WINDOW_SECONDS)

    print(f"Waiting extra {NETWORK_DELAY_SECONDS}s for delayed network flows...")
    time.sleep(NETWORK_DELAY_SECONDS)

    # Read recent entries by Redis ID range around the time window.
    # We use a wide ID range because network flows may be inserted later but contain older internal timestamps.
    process_entries = r.xrange(PROCESS_STREAM, min=f"{start_ms}-0", max=f"{end_ms}-999999", count=1000)

    # For network, read a larger recent range and filter by internal timestamp_unix_ms.
    # Count can be increased if needed.
    network_entries = r.xrevrange(NETWORK_STREAM, "+", "-", count=5000)

    process_rows = [
        parse_entry(redis_id, data)
        for redis_id, data in process_entries
    ]

    network_rows = filter_by_timestamp(network_entries, start_ms, end_ms)

    summary = {
        "window_id": window_id,
        "start_iso": datetime.fromtimestamp(start_time).isoformat(timespec="seconds"),
        "end_iso": datetime.fromtimestamp(end_time).isoformat(timespec="seconds"),
        "duration_seconds": WINDOW_SECONDS,
        "network_delay_seconds": NETWORK_DELAY_SECONDS,
        "process_rows": len(process_rows),
        "network_rows": len(network_rows),
        "process_fields": sorted(list(process_rows[0].keys())) if process_rows else [],
        "network_fields": sorted(list(network_rows[0].keys())) if network_rows else [],
        "network_protocol_counts": {},
    }

    for row in network_rows:
        proto = row.get("protocol", "UNKNOWN")
        summary["network_protocol_counts"][proto] = summary["network_protocol_counts"].get(proto, 0) + 1

    print(json.dumps(summary, indent=2))

    save_csv(OUT_DIR / f"window_{window_id}_process.csv", process_rows)
    save_csv(OUT_DIR / f"window_{window_id}_network.csv", network_rows)

    with open(OUT_DIR / f"window_{window_id}.summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    return summary


def main():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.ping()

    summaries = []

    for i in range(1, NUM_WINDOWS + 1):
        summaries.append(collect_one_window(r, i))

    with open(OUT_DIR / "all_summaries.json", "w") as f:
        json.dump(summaries, f, indent=2)

    print("\nDone. Output folder:", OUT_DIR.resolve())


if __name__ == "__main__":
    main()

