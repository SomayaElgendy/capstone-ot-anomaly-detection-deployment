import redis
from datetime import datetime
from collections import defaultdict, Counter

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

entries = r.xrevrange("network:telemetry", "+", "-", count=5000)

bins = defaultdict(list)

for msg_id, data in entries:
    ts = data.get("timestamp_unix_ms")
    if ts is None:
        continue

    ts_ms = int(float(ts))
    ts_sec = ts_ms // 1000
    bin_start = (ts_sec // 10) * 10

    bins[bin_start].append({
        "id": msg_id,
        "protocol": data.get("protocol", "UNKNOWN"),
        "sender": data.get("sender_address", ""),
        "receiver": data.get("receiver_address", ""),
        "timestamp_iso": data.get("timestamp_iso", ""),
    })

print("Last 20 non-empty 10-second network bins:")
for b in sorted(bins.keys())[-20:]:
    rows = bins[b]
    protocols = Counter(row["protocol"] for row in rows)
    pairs = Counter((row["sender"], row["receiver"]) for row in rows)

    print("\nBIN:", datetime.fromtimestamp(b).strftime("%Y-%m-%d %H:%M:%S"))
    print("row_count:", len(rows))
    print("protocols:", dict(protocols))
    print("top_pairs:", pairs.most_common(5))

