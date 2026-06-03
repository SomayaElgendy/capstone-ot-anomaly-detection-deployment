import redis

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

streams = {
    "hil:telemetry": "$",
    "network:telemetry": "$",
}

print("Listening to hil:telemetry and network:telemetry...")

while True:
    messages = r.xread(streams, block=5000, count=5)

    if not messages:
        print("No new messages...")
        continue

    for stream_name, entries in messages:
        for msg_id, data in entries:
            streams[stream_name] = msg_id

            print("\n==============================")
            print("Stream:", stream_name)
            print("Redis ID:", msg_id)
            print("Time:", data.get("timestamp_iso"))

            if stream_name == "hil:telemetry":
                print("Tank level:", data.get("tank_level_value"))
                print("Bottle level:", data.get("bottle_level_value"))
                print("PLC1 mode:", data.get("plc1_mode"))
                print("PLC2 mode:", data.get("plc2_mode"))
                print("Tank pressure:", data.get("tank_pressure"))

            elif stream_name == "network:telemetry":
                print("Sender:", data.get("sender_address"))
                print("Receiver:", data.get("receiver_address"))
                print("Protocol:", data.get("protocol"))
                print("Duration:", data.get("duration"))
                print("Total packets:", data.get("total_packets"))
                print("Total bytes:", data.get("total_bytes"))
                print("Payload bytes:", data.get("payload_bytes"))

            print("Validation:", data.get("_validation"))
