import time
import redis
from collections import deque

PROCESS_STREAM = "hil:telemetry"
NETWORK_STREAM = "network:telemetry"

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


def process_row(data):
    return [to_float(data.get(feature)) for feature in PROCESS_FEATURES]


def network_row(data):
    row = {}

    for feature in NETWORK_FEATURES:
        if feature not in PROTOCOL_COLS:
            row[feature] = to_float(data.get(feature))

    protocol = data.get("protocol", "")
    for col in PROTOCOL_COLS:
        row[col] = 1.0 if col == f"proto_{protocol}" else 0.0

    return [row[feature] for feature in NETWORK_FEATURES]


def main():
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    r.ping()

    last_ids = {
        PROCESS_STREAM: "$",
        NETWORK_STREAM: "$",
    }

    process_buffer = deque(maxlen=50)
    network_buffer = deque(maxlen=120)

    print("Listening to live Redis telemetry...")
    print("Waiting until we have 50 process rows and network rows...")

    last_window_time = time.time()

    while True:
        messages = r.xread(last_ids, block=5000, count=50)

        if not messages:
            continue

        for stream_name, entries in messages:
            for msg_id, data in entries:
                last_ids[stream_name] = msg_id

                if stream_name == PROCESS_STREAM:
                    process_buffer.append(process_row(data))

                elif stream_name == NETWORK_STREAM:
                    network_buffer.append(network_row(data))

        now = time.time()

        if now - last_window_time >= 10:
            last_window_time = now

            print("\n================ LIVE WINDOW ================")
            print("Process rows:", len(process_buffer), "/ 50")
            print("Network rows:", len(network_buffer), "/ 120")

            if process_buffer:
                print("Process feature count:", len(process_buffer[-1]))

            if network_buffer:
                print("Network feature count:", len(network_buffer[-1]))

            if len(process_buffer) == 50:
                print("✅ Process window ready: (50, 14)")
            else:
                print("⏳ Process window not ready yet")

            if len(network_buffer) > 0:
                print(f"✅ Network window available: ({len(network_buffer)}, 43)")
            else:
                print("⏳ No network rows yet")

            print("============================================")


if __name__ == "__main__":
    main()
