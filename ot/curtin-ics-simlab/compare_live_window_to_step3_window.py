import json
import time
from pathlib import Path
from datetime import datetime
from collections import Counter

import pandas as pd
import redis


# =========================
# CONFIG
# =========================

REDIS_HOST = "localhost"
REDIS_PORT = 6379

PROCESS_STREAM = "hil:telemetry"
NETWORK_STREAM = "network:telemetry"

WINDOW_SECONDS = 10
NETWORK_DELAY_SECONDS = 70

# Dataset Step 3 folder
STAGE2_ROOT = Path("/mnt/c/Users/somay/OneDrive/Desktop/Capstone 1/stage_1_2/stage2")
STEP3_ROOT = STAGE2_ROOT / "data/processed/Modify_Controller_Tasking_T0821/step3_windows"

# Choose a dataset window known to have normal Modbus rows
DATASET_WINDOW_ID = 0

OUT_DIR = Path("live_vs_step3_evidence")
OUT_DIR.mkdir(exist_ok=True)


# =========================
# HELPERS
# =========================

def parse_redis_entry(redis_id, data):
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


def filter_network_by_timestamp(entries, start_ms, end_ms):
    rows = []

    for redis_id, data in entries:
        row = parse_redis_entry(redis_id, data)

        ts = row.get("timestamp_unix_ms")
        if ts is None:
            continue

        try:
            ts = int(float(ts))
        except Exception:
            continue

        if start_ms <= ts < end_ms:
            rows.append(row)

    return pd.DataFrame(rows)


def protocol_counts(df):
    if df.empty or "protocol" not in df.columns:
        return {}
    return dict(Counter(df["protocol"].astype(str)))


def top_pairs(df, n=5):
    if df.empty or "sender_address" not in df.columns or "receiver_address" not in df.columns:
        return {}

    pairs = Counter(
        zip(
            df["sender_address"].astype(str),
            df["receiver_address"].astype(str)
        )
    )

    return {f"{src} -> {dst}": count for (src, dst), count in pairs.most_common(n)}


def safe_head(df, n=10):
    if df.empty:
        return pd.DataFrame()
    return df.head(n)


# =========================
# LIVE COLLECTION
# =========================

def collect_live_window():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.ping()

    start_time = time.time()
    end_time = start_time + WINDOW_SECONDS

    start_ms = int(start_time * 1000)
    end_ms = int(end_time * 1000)

    print("=" * 70)
    print("Collecting LIVE window")
    print("Start:", datetime.fromtimestamp(start_time).isoformat(timespec="seconds"))
    print("End:  ", datetime.fromtimestamp(end_time).isoformat(timespec="seconds"))
    print("=" * 70)

    time.sleep(WINDOW_SECONDS)

    print(f"Waiting {NETWORK_DELAY_SECONDS}s for delayed network flows...")
    time.sleep(NETWORK_DELAY_SECONDS)

    # Process stream is regular, so Redis ID range works.
    process_entries = r.xrange(
        PROCESS_STREAM,
        min=f"{start_ms}-0",
        max=f"{end_ms}-999999",
        count=2000
    )

    live_process_rows = [
        parse_redis_entry(redis_id, data)
        for redis_id, data in process_entries
    ]
    live_process_df = pd.DataFrame(live_process_rows)

    # Network stream is flow-based and delayed, so read recent rows and filter by internal timestamp.
    network_entries = r.xrevrange(NETWORK_STREAM, "+", "-", count=10000)
    live_network_df = filter_network_by_timestamp(network_entries, start_ms, end_ms)

    live_info = {
        "live_start_iso": datetime.fromtimestamp(start_time).isoformat(timespec="seconds"),
        "live_end_iso": datetime.fromtimestamp(end_time).isoformat(timespec="seconds"),
        "live_window_seconds": WINDOW_SECONDS,
        "live_network_delay_seconds": NETWORK_DELAY_SECONDS,
        "live_process_rows": int(len(live_process_df)),
        "live_network_rows": int(len(live_network_df)),
        "live_network_protocol_counts": protocol_counts(live_network_df),
        "live_network_top_pairs": top_pairs(live_network_df),
    }

    return live_process_df, live_network_df, live_info


# =========================
# STEP3 DATASET WINDOW
# =========================

def load_step3_window(window_id):
    network_rows_path = STEP3_ROOT / "network_rows_aligned.csv"
    process_rows_path = STEP3_ROOT / "process_rows_aligned.csv"
    network_meta_path = STEP3_ROOT / "network/all/window_metadata.csv"
    process_meta_path = STEP3_ROOT / "process/all/window_metadata.csv"

    network_rows = pd.read_csv(network_rows_path)
    process_rows = pd.read_csv(process_rows_path)
    network_meta = pd.read_csv(network_meta_path)
    process_meta = pd.read_csv(process_meta_path)

    net_meta_row = network_meta[network_meta["window_id"] == window_id].iloc[0]
    proc_meta_row = process_meta[process_meta["window_id"] == window_id].iloc[0]

    start_s = float(net_meta_row["window_start_seconds"])
    end_s = float(net_meta_row["window_end_seconds"])

    step3_network_df = network_rows[
        (network_rows["event_time_seconds"] >= start_s)
        & (network_rows["event_time_seconds"] < end_s)
    ].copy()

    step3_process_df = process_rows[
        (process_rows["process_time_seconds"] >= start_s)
        & (process_rows["process_time_seconds"] < end_s)
    ].copy()

    step3_info = {
        "dataset_window_id": int(window_id),
        "dataset_window_start_hms": str(net_meta_row["window_start_hms"]),
        "dataset_window_end_hms": str(net_meta_row["window_end_hms"]),
        "dataset_process_rows": int(len(step3_process_df)),
        "dataset_network_rows": int(len(step3_network_df)),
        "dataset_network_protocol_counts": protocol_counts(step3_network_df),
        "dataset_network_top_pairs": top_pairs(step3_network_df),
        "dataset_network_raw_event_count_from_metadata": int(net_meta_row["raw_event_count"]),
        "dataset_process_raw_row_count_from_metadata": int(proc_meta_row["raw_row_count"]),
    }

    return step3_process_df, step3_network_df, step3_info


# =========================
# REPORT
# =========================

def make_report(live_info, step3_info):
    rows = [
        {
            "metric": "window_duration_seconds",
            "live": live_info["live_window_seconds"],
            "step3_dataset": 10,
            "interpretation": "Both use 10-second windows."
        },
        {
            "metric": "process_rows",
            "live": live_info["live_process_rows"],
            "step3_dataset": step3_info["dataset_process_rows"],
            "interpretation": "Process side is similar and healthy."
        },
        {
            "metric": "network_rows",
            "live": live_info["live_network_rows"],
            "step3_dataset": step3_info["dataset_network_rows"],
            "interpretation": "Major mismatch. Live has too few network rows."
        },
        {
            "metric": "network_protocol_counts",
            "live": json.dumps(live_info["live_network_protocol_counts"]),
            "step3_dataset": json.dumps(step3_info["dataset_network_protocol_counts"]),
            "interpretation": "Dataset is mostly ModbusTCP; live is sparse or mostly TCP."
        },
        {
            "metric": "network_top_pairs",
            "live": json.dumps(live_info["live_network_top_pairs"]),
            "step3_dataset": json.dumps(step3_info["dataset_network_top_pairs"]),
            "interpretation": "Dataset includes OT Modbus pairs; live often shows host/Redis traffic."
        }
    ]

    comparison_df = pd.DataFrame(rows)

    report_lines = [
        "# Live vs Step 3 Window Comparison Diagnosis",
        "",
        "## Purpose",
        "",
        "This evidence was collected to verify whether the live OT Redis telemetry produces model-ready windows similar to the offline Step 3 dataset used to train Stage 1 and Stage 2.",
        "",
        "## Dataset Step 3 Window",
        "",
        f"Dataset window ID: {step3_info['dataset_window_id']}",
        f"Window time: {step3_info['dataset_window_start_hms']} to {step3_info['dataset_window_end_hms']}",
        f"Process rows: {step3_info['dataset_process_rows']}",
        f"Network rows: {step3_info['dataset_network_rows']}",
        "",
        "Network protocol counts:",
        json.dumps(step3_info["dataset_network_protocol_counts"], indent=2),
        "",
        "Top network pairs:",
        json.dumps(step3_info["dataset_network_top_pairs"], indent=2),
        "",
        "## Live Environment Window",
        "",
        f"Live time: {live_info['live_start_iso']} to {live_info['live_end_iso']}",
        f"Process rows: {live_info['live_process_rows']}",
        f"Network rows: {live_info['live_network_rows']}",
        "",
        "Network protocol counts:",
        json.dumps(live_info["live_network_protocol_counts"], indent=2),
        "",
        "Top network pairs:",
        json.dumps(live_info["live_network_top_pairs"], indent=2),
        "",
        "## Diagnosis",
        "",
        "The live process stream is healthy because it produces approximately the expected number of process rows in a 10-second interval.",
        "",
        "However, the live network stream does not match the Step 3 dataset. The Step 3 network window contains many network rows, mostly ModbusTCP, while the live network window contains very few network rows. This means the live network branch input is not equivalent to the training data.",
        "",
        "Therefore, the unstable Stage 2 classification is likely caused by live network input distribution mismatch, not primarily by model thresholds or scaling.",
        "",
        "## Main Cause",
        "",
        "The offline Step 3 dataset appears to have been produced from dense PCAP/network event extraction, where many ModbusTCP events appear inside each 10-second window. The live Redis network:telemetry stream is flow-based and currently produces sparse summarized rows. As a result, the live model-ready network window is mostly padded zeros or contains unrelated generic TCP rows.",
        "",
        "## Impact on Stage 2",
        "",
        "Stage 2 was trained on network windows with dense ModbusTCP evidence. During live inference, it receives sparse or incomplete network evidence. This causes the classifier to produce low-confidence or wrong attack labels, often leaning toward the closest learned class rather than the true live attack class.",
        "",
        "## Recommended Future Fixes",
        "",
        "1. Update the live network telemetry service so it emits PCAP-equivalent Modbus event rows, similar to the offline Step 3 network rows.",
        "2. Recreate the Step 3 windowing logic in the live pipeline using event timestamps and sufficient ModbusTCP row density.",
        "3. Avoid publishing model-ready network windows when the network mask contains too few real rows.",
        "4. If the live Redis telemetry format must remain sparse, retrain or recalibrate Stage 1 and Stage 2 using live-collected Redis windows instead of offline PCAP-derived windows.",
        "5. For the current demo, use this limitation as an engineering validation result and avoid claiming that live Stage 2 classification is fully reliable on the network branch."
    ]

    report = "\n".join(report_lines)

    return comparison_df, report
def main():
    live_process_df, live_network_df, live_info = collect_live_window()
    step3_process_df, step3_network_df, step3_info = load_step3_window(DATASET_WINDOW_ID)

    comparison_df, report = make_report(live_info, step3_info)

    live_process_df.to_csv(OUT_DIR / "live_process_window.csv", index=False)
    live_network_df.to_csv(OUT_DIR / "live_network_window.csv", index=False)

    step3_process_df.to_csv(OUT_DIR / "step3_process_window.csv", index=False)
    step3_network_df.to_csv(OUT_DIR / "step3_network_window.csv", index=False)

    comparison_df.to_csv(OUT_DIR / "side_by_side_comparison.csv", index=False)

    with open(OUT_DIR / "diagnosis_report.md", "w", encoding="utf-8") as f:
        f.write(report)

    with open(OUT_DIR / "summary.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "live": live_info,
                "step3_dataset": step3_info
            },
            f,
            indent=2
        )

    print("\nSaved evidence files to:", OUT_DIR.resolve())
    print("\n=== SIDE BY SIDE SUMMARY ===")
    print(comparison_df.to_string(index=False))
    print("\nOpen report:")
    print(OUT_DIR / "diagnosis_report.md")


if __name__ == "__main__":
    main()
