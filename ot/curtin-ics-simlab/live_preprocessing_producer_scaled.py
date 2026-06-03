import json
import time
import redis
import joblib
import numpy as np
import pandas as pd
import os
from pathlib import Path
from collections import deque

#PROCESS_STREAM = "hil:telemetry"
#NETWORK_STREAM = "network:telemetry"
#OUTPUT_STREAM = "model_ready_windows"

PROCESS_WINDOW_SIZE = 50
NETWORK_WINDOW_SIZE = 120
PUBLISH_EVERY_SECONDS = 10

# Change this path if needed
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

PROCESS_STREAM = os.getenv("PROCESS_STREAM", "hil:telemetry")
NETWORK_STREAM = os.getenv("NETWORK_STREAM", "network:telemetry")
OUTPUT_STREAM = os.getenv("MODEL_READY_STREAM", "model_ready_windows")

ARTIFACTS_DIR = Path(os.getenv("ARTIFACTS_DIR", "live_artifacts"))

# Same groups used in 02_preprocess_rows.py
NETWORK_QUANTILE_TARGETS = [
    "duration", "sPackets", "rPackets", "sBytesMax", "rBytesMax",
    "sBytesMin", "rBytesMin", "sBytesAvg", "rBytesAvg",
    "sBytesTotal", "rBytesTotal", "sLoad", "rLoad",
    "sPayloadMax", "rPayloadMax", "sPayloadMin", "rPayloadMin",
    "sPayloadAvg", "rPayloadAvg", "sWin", "rWin",
    "sInterPacket", "rInterPacket"
]

NETWORK_LINEAR_TARGETS = [
    "sttl", "rttl", "sAckRate", "rAckRate", "sFinRate", "rFinRate",
    "sPshRate", "rPshRate", "sRstRate", "rRstRate",
    "sUrgRate", "rUrgRate", "sSynRate", "rSynRate",
    "sFragmentRate", "rFragmentRate"
]

PROTOCOL_COLS = [
    "proto_ARP",
    "proto_IPV4-ModbusTCP",
    "proto_IPV4-TCP",
    "proto_IPV6-OTHER",
]

PROCESS_QUANTILE_TARGETS = [
    "tank_level_value",
    "bottle_level_value",
    "bottle_distance_to_filler_value",
]

PROCESS_LINEAR_TARGETS = [
    "tank_input_flow_value",
    "tank_output_flow_value",
    "tank_input_valve_position",
    "tank_output_valve_position",
    "tank_pressure",
]

# Final Stage 1 network order from step3_windows/network/artifacts/feature_order.json
FINAL_NETWORK_FEATURES = [
    "duration", "sPackets", "rPackets", "sBytesMax", "rBytesMax",
    "sBytesMin", "rBytesMin", "sBytesAvg", "rBytesAvg",
    "sBytesTotal", "rBytesTotal", "sLoad", "rLoad",
    "sPayloadMax", "rPayloadMax", "sPayloadMin", "rPayloadMin",
    "sPayloadAvg", "rPayloadAvg", "sInterPacket", "rInterPacket",
    "sttl", "rttl", "sAckRate", "rAckRate", "sFinRate", "rFinRate",
    "sPshRate", "rPshRate", "sRstRate", "rRstRate",
    "sUrgRate", "rUrgRate", "sSynRate", "rSynRate",
    "sWin", "rWin", "sFragmentRate", "rFragmentRate",
    "proto_ARP", "proto_IPV4-ModbusTCP", "proto_IPV4-TCP", "proto_IPV6-OTHER",
]

# Final Stage 1 process order from step3_windows/process/artifacts/feature_order.json
FINAL_PROCESS_FEATURES = [
    "bottle_distance_to_filler_value",
    "bottle_level_value",
    "conveyor_belt_engine_state",
    "plc1_mode",
    "plc2_mode",
    "supply_pressure",
    "tank_input_flow_value",
    "tank_input_valve_position",
    "tank_input_valve_state",
    "tank_level_value",
    "tank_output_flow_value",
    "tank_output_valve_position",
    "tank_output_valve_state",
    "tank_pressure",
]


def to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def load_artifacts():
    return {
        "net_qt": joblib.load(ARTIFACTS_DIR / "quantile_transformer.pkl"),
        "net_mm": joblib.load(ARTIFACTS_DIR / "minmax_scaler.pkl"),
        "proc_qt": joblib.load(ARTIFACTS_DIR / "process_quantile_transformer.pkl"),
        "proc_mm": joblib.load(ARTIFACTS_DIR / "process_minmax_scaler.pkl"),
    }


def build_raw_network_dict(data):
    row = {}

    for f in NETWORK_QUANTILE_TARGETS + NETWORK_LINEAR_TARGETS:
        row[f] = to_float(data.get(f))

    protocol = data.get("protocol", "")
    for col in PROTOCOL_COLS:
        row[col] = 1.0 if col == f"proto_{protocol}" else 0.0

    return row


def scale_network_row(raw_row, artifacts):
    row = dict(raw_row)

    q_df = pd.DataFrame([[row[f] for f in NETWORK_QUANTILE_TARGETS]], columns=NETWORK_QUANTILE_TARGETS)
    l_df = pd.DataFrame([[row[f] for f in NETWORK_LINEAR_TARGETS]], columns=NETWORK_LINEAR_TARGETS)

    q_scaled = artifacts["net_qt"].transform(q_df)[0]
    l_scaled = artifacts["net_mm"].transform(l_df)[0]

    for f, v in zip(NETWORK_QUANTILE_TARGETS, q_scaled):
        row[f] = float(v)

    for f, v in zip(NETWORK_LINEAR_TARGETS, l_scaled):
        row[f] = float(v)

    return [float(row[f]) for f in FINAL_NETWORK_FEATURES]

def build_raw_process_dict(data):
    row = {}

    needed = set(FINAL_PROCESS_FEATURES + PROCESS_QUANTILE_TARGETS + PROCESS_LINEAR_TARGETS)

    for f in needed:
        row[f] = to_float(data.get(f))

    return row


def scale_process_row(raw_row, artifacts):
    row = dict(raw_row)

    q_df = pd.DataFrame([[row[f] for f in PROCESS_QUANTILE_TARGETS]], columns=PROCESS_QUANTILE_TARGETS)
    l_df = pd.DataFrame([[row[f] for f in PROCESS_LINEAR_TARGETS]], columns=PROCESS_LINEAR_TARGETS)

    q_scaled = artifacts["proc_qt"].transform(q_df)[0]
    l_scaled = artifacts["proc_mm"].transform(l_df)[0]

    for f, v in zip(PROCESS_QUANTILE_TARGETS, q_scaled):
        row[f] = float(v)

    for f, v in zip(PROCESS_LINEAR_TARGETS, l_scaled):
        row[f] = float(v)

    return [float(row[f]) for f in FINAL_PROCESS_FEATURES]

def pad_network_window(network_rows):
    rows = list(network_rows)[-NETWORK_WINDOW_SIZE:]
    real_count = len(rows)

    if real_count < NETWORK_WINDOW_SIZE:
        zero_row = [0.0] * len(FINAL_NETWORK_FEATURES)
        pad_count = NETWORK_WINDOW_SIZE - real_count
        rows = [zero_row for _ in range(pad_count)] + rows
        mask = [0] * pad_count + [1] * real_count
    else:
        mask = [1] * NETWORK_WINDOW_SIZE

    return rows, mask

def main():
    print("Loading scaler artifacts...")
    artifacts = load_artifacts()
    print("Scaler artifacts loaded.")

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.ping()

    last_ids = {
        PROCESS_STREAM: "$",
        NETWORK_STREAM: "$",
    }

    process_buffer = deque(maxlen=PROCESS_WINDOW_SIZE)
    network_buffer = []
    last_publish_time = time.time()
    window_counter = 0

    print("Scaled live preprocessing producer started.")
    print(f"Input streams: {PROCESS_STREAM}, {NETWORK_STREAM}")
    print(f"Output stream: {OUTPUT_STREAM}")

    while True:
        messages = r.xread(last_ids, block=5000, count=100)

        if messages:
            for stream_name, entries in messages:
                for msg_id, data in entries:
                    last_ids[stream_name] = msg_id

                    if stream_name == PROCESS_STREAM:
                        raw = build_raw_process_dict(data)
                        process_buffer.append(scale_process_row(raw, artifacts))

                    elif stream_name == NETWORK_STREAM:
                        raw = build_raw_network_dict(data)
                        network_buffer.append(scale_network_row(raw, artifacts))

        now = time.time()

        if now - last_publish_time >= PUBLISH_EVERY_SECONDS:
            last_publish_time = now

            if len(process_buffer) < PROCESS_WINDOW_SIZE:
                print(f"Waiting for process window: {len(process_buffer)}/{PROCESS_WINDOW_SIZE}")
                continue

            process_window = list(process_buffer)
            network_window, network_mask = pad_network_window(network_buffer)
            process_mask = [1] * PROCESS_WINDOW_SIZE
            window_counter += 1
            window_id = f"live_scaled_window_{window_counter}"

            payload = {
                "window_id": window_id,
                "source": "live_ot_environment_scaled",
                "created_at_unix": str(time.time()),
                "process_shape": json.dumps([PROCESS_WINDOW_SIZE, len(FINAL_PROCESS_FEATURES)]),
                "network_shape": json.dumps([NETWORK_WINDOW_SIZE, len(FINAL_NETWORK_FEATURES)]),
                "process_features": json.dumps(FINAL_PROCESS_FEATURES),
                "network_features": json.dumps(FINAL_NETWORK_FEATURES),
                "process_window": json.dumps(process_window),
                "network_window": json.dumps(network_window),
                "raw_process_rows_available": str(len(process_buffer)),
                "raw_network_rows_available": str(len(network_buffer)),
                "scaled": "true",
                "process_mask": json.dumps(process_mask),
                "network_mask": json.dumps(network_mask),
            }

            msg_id = r.xadd(OUTPUT_STREAM, payload, maxlen=1000, approximate=True)

            p_arr = np.array(process_window, dtype=np.float32)
            n_arr = np.array(network_window, dtype=np.float32)

            print(
                f"Published {window_id} → {OUTPUT_STREAM} | Redis ID={msg_id} | "
                f"process={p_arr.shape}, range=({p_arr.min():.4f}, {p_arr.max():.4f}) | "
                f"network={n_arr.shape}, range=({n_arr.min():.4f}, {n_arr.max():.4f}) | "
                f"raw_network_rows={len(network_buffer)}"
            )
            network_buffer.clear()

if __name__ == "__main__":
    main()
