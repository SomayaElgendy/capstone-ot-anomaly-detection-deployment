import json
import time
import redis
from collections import deque

PROCESS_STREAM = "hil:telemetry"
NETWORK_STREAM = "network:telemetry"
OUTPUT_STREAM = "model_ready_windows"

PROCESS_WINDOW_SIZE = 50
NETWORK_WINDOW_SIZE = 120
PUBLISH_EVERY_SECONDS = 10

PROCESS_FEATURES = [
    "tank_level_value",
    "bottle_level_value",
    "bottle_distance_to_filler_value",
    "tank_input_flow_value",
    "tank_output_flow_value",
    "tank_input_valve_position",
    "tank_output_valve_position",
    "tank_pressure",
    "tank_input_valve_state",
    "tank_output_valve_state",
    "conveyor_belt_engine_state",
    "plc1_mode",
    "plc2_mode",
    "supply_pressure",
]

NETWORK_FEATURES = [
    "duration",
    "sPackets",
    "rPackets",
    "sBytesMax",
    "rBytesMax",
    "sBytesMin",
    "rBytesMin",
    "sBytesAvg",
    "rBytesAvg",
    "sBytesTotal",
    "rBytesTotal",
    "sLoad",
    "rLoad",
    "sPayloadMax",
    "rPayloadMax",
    "sPayloadMin",
    "rPayloadMin",
    "sPayloadAvg",
    "rPayloadAvg",
    "sInterPacket",
    "rInterPacket",
    "sttl",
    "rttl",
    "sAckRate",
    "rAckRate",
    "sFinRate",
    "rFinRate",
    "sPshRate",
    "rPshRate",
    "sRstRate",
    "rRstRate",
    "sUrgRate",
    "rUrgRate",
    "sSynRate",
    "rSynRate",
    "sWin",
    "rWin",
    "sFragmentRate",
    "rFragmentRate",
    "proto_ARP",
    "proto_IPV4-ModbusTCP",
    "proto_IPV4-TCP",
    "proto_IPV6-OTHER",
]

PROTOCOL_COLS = [
    "proto_ARP",
    "proto_IPV4-ModbusTCP",
    "proto_IPV4-TCP",
    "proto_IPV6-OTHER",
]


def to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def build_process_row(data):
    return [to_float(data.get(feature)) for feature in PROCESS_FEATURES]


def build_network_row(data):
    row = {}

    for feature in NETWORK_FEATURES:
        if feature not in PROTOCOL_COLS:
            row[feature] = to_float(data.get(feature))

    protocol = data.get("protocol", "")
    for col in PROTOCOL_COLS:
        row[col] = 1.0 if col == f"proto_{protocol}" else 0.0

    return [row[feature] for feature in NETWORK_FEATURES]


def pad_network_window(network_rows):
    rows = list(network_rows)[-NETWORK_WINDOW_SIZE:]

    if len(rows) < NETWORK_WINDOW_SIZE:
        zero_row = [0.0] * len(NETWORK_FEATURES)
        padding = [zero_row for _ in range(NETWORK_WINDOW_SIZE - len(rows))]
        rows = padding + rows

    return rows


def main():
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()

    last_ids = {
        PROCESS_STREAM: "$",
        NETWORK_STREAM: "$",
    }

    process_buffer = deque(maxlen=PROCESS_WINDOW_SIZE)
    network_buffer = deque(maxlen=NETWORK_WINDOW_SIZE)

    last_publish_time = time.time()
    window_counter = 0

    print("Live preprocessing producer started.")
    print(f"Input streams: {PROCESS_STREAM}, {NETWORK_STREAM}")
    print(f"Output stream: {OUTPUT_STREAM}")

    while True:
        messages = r.xread(last_ids, block=5000, count=100)

        if messages:
            for stream_name, entries in messages:
                for msg_id, data in entries:
                    last_ids[stream_name] = msg_id

                    if stream_name == PROCESS_STREAM:
                        process_buffer.append(build_process_row(data))

                    elif stream_name == NETWORK_STREAM:
                        network_buffer.append(build_network_row(data))

        now = time.time()

        if now - last_publish_time >= PUBLISH_EVERY_SECONDS:
            last_publish_time = now

            if len(process_buffer) < PROCESS_WINDOW_SIZE:
                print(f"Waiting for process window: {len(process_buffer)}/{PROCESS_WINDOW_SIZE}")
                continue

            process_window = list(process_buffer)
            network_window = pad_network_window(network_buffer)

            window_counter += 1
            window_id = f"live_window_{window_counter}"

            payload = {
                "window_id": window_id,
                "source": "live_ot_environment",
                "created_at_unix": str(time.time()),
                "process_shape": json.dumps([PROCESS_WINDOW_SIZE, len(PROCESS_FEATURES)]),
                "network_shape": json.dumps([NETWORK_WINDOW_SIZE, len(NETWORK_FEATURES)]),
                "process_features": json.dumps(PROCESS_FEATURES),
                "network_features": json.dumps(NETWORK_FEATURES),
                "process_window": json.dumps(process_window),
                "network_window": json.dumps(network_window),
                "raw_process_rows_available": str(len(process_buffer)),
                "raw_network_rows_available": str(len(network_buffer)),
            }

            msg_id = r.xadd(OUTPUT_STREAM, payload, maxlen=1000, approximate=True)

            print(
                f"Published {window_id} → {OUTPUT_STREAM} | "
                f"Redis ID={msg_id} | "
                f"process=(50,14), network=(120,43), "
                f"raw_network_rows={len(network_buffer)}"
            )


if __name__ == "__main__":
    main()
