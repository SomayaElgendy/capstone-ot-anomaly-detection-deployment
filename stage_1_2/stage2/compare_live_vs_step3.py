import json
from pathlib import Path

import numpy as np
import redis


STEP3_ROOT = Path("data/processed/Modify_Controller_Tasking_T0821/step3_windows")

NETWORK_X = STEP3_ROOT / "network/test/X_test.npy"
PROCESS_X = STEP3_ROOT / "process/test/X_test.npy"
NETWORK_MASK = STEP3_ROOT / "network/test/mask_test.npy"
PROCESS_MASK = STEP3_ROOT / "process/test/mask_test.npy"

NETWORK_FEATURES = STEP3_ROOT / "network/artifacts/feature_order.json"
PROCESS_FEATURES = STEP3_ROOT / "process/artifacts/feature_order.json"

REDIS_HOST = "localhost"
REDIS_PORT = 6379
STREAM = "model_ready_windows"


def describe(name, arr):
    arr = np.asarray(arr, dtype=np.float32)
    print(f"\n{name}")
    print("-" * len(name))
    print("shape:", arr.shape)
    print("min:", float(arr.min()))
    print("max:", float(arr.max()))
    print("mean:", float(arr.mean()))
    print("std:", float(arr.std()))


def feature_stats(name, arr, features, top_n=10):
    arr = np.asarray(arr, dtype=np.float32)
    flat = arr.reshape(-1, arr.shape[-1])

    means = flat.mean(axis=0)
    stds = flat.std(axis=0)
    mins = flat.min(axis=0)
    maxs = flat.max(axis=0)

    print(f"\n{name} feature stats sample")
    print("-" * 40)
    for i, f in enumerate(features[:top_n]):
        print(f"{i:02d} {f:30s} min={mins[i]:.4f} max={maxs[i]:.4f} mean={means[i]:.4f} std={stds[i]:.4f}")


def compare_live_to_dataset(live_arr, dataset_arr, features, name):
    live_flat = live_arr.reshape(-1, live_arr.shape[-1])
    data_flat = dataset_arr.reshape(-1, dataset_arr.shape[-1])

    live_mean = live_flat.mean(axis=0)
    data_mean = data_flat.mean(axis=0)
    live_std = live_flat.std(axis=0)
    data_std = data_flat.std(axis=0)

    diff = np.abs(live_mean - data_mean)
    worst = np.argsort(diff)[::-1][:10]

    print(f"\nTop mean differences: {name}")
    print("-" * 50)
    for idx in worst:
        print(
            f"{features[idx]:30s} "
            f"live_mean={live_mean[idx]:.4f} "
            f"step3_mean={data_mean[idx]:.4f} "
            f"diff={diff[idx]:.4f} "
            f"live_std={live_std[idx]:.4f} "
            f"step3_std={data_std[idx]:.4f}"
        )


def protocol_report(arr, features, name):
    proto_cols = [f for f in features if f.startswith("proto_")]
    if not proto_cols:
        return

    print(f"\n{name} protocol columns")
    print("-" * 40)
    flat = arr.reshape(-1, arr.shape[-1])
    for col in proto_cols:
        idx = features.index(col)
        print(f"{col:25s} sum={flat[:, idx].sum():.2f} mean={flat[:, idx].mean():.5f}")


def main():
    print("Loading step3 dataset windows...")
    Xn_step3 = np.load(NETWORK_X)
    Xp_step3 = np.load(PROCESS_X)
    Mn_step3 = np.load(NETWORK_MASK)
    Mp_step3 = np.load(PROCESS_MASK)

    net_features = json.loads(NETWORK_FEATURES.read_text())
    proc_features = json.loads(PROCESS_FEATURES.read_text())

    describe("STEP3 network X_test", Xn_step3)
    describe("STEP3 process X_test", Xp_step3)
    describe("STEP3 network mask_test", Mn_step3)
    describe("STEP3 process mask_test", Mp_step3)

    print("\nSTEP3 mask real rows:")
    print("network mask sum min/max/mean:", Mn_step3.sum(axis=1).min(), Mn_step3.sum(axis=1).max(), Mn_step3.sum(axis=1).mean())
    print("process mask sum min/max/mean:", Mp_step3.sum(axis=1).min(), Mp_step3.sum(axis=1).max(), Mp_step3.sum(axis=1).mean())

    print("\nReading latest 2 live windows from Redis...")
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    entries = r.xrevrange(STREAM, "+", "-", count=2)

    if not entries:
        print("No live windows found in Redis stream:", STREAM)
        return

    for live_idx, (msg_id, data) in enumerate(entries, start=1):
        print("\n" + "=" * 80)
        print(f"LIVE WINDOW {live_idx} | Redis ID: {msg_id} | window_id: {data.get('window_id')}")
        print("=" * 80)

        Xn_live = np.array(json.loads(data["network_window"]), dtype=np.float32)
        Xp_live = np.array(json.loads(data["process_window"]), dtype=np.float32)
        Mn_live = np.array(json.loads(data["network_mask"]), dtype=np.float32)
        Mp_live = np.array(json.loads(data["process_mask"]), dtype=np.float32)

        describe("LIVE network window", Xn_live)
        describe("LIVE process window", Xp_live)
        describe("LIVE network mask", Mn_live)
        describe("LIVE process mask", Mp_live)

        print("\nLIVE mask real rows:")
        print("network real rows:", int(Mn_live.sum()))
        print("process real rows:", int(Mp_live.sum()))

        protocol_report(Xn_live[None, :, :], net_features, "LIVE network")
        protocol_report(Xn_step3, net_features, "STEP3 network dataset")

        compare_live_to_dataset(Xn_live[None, :, :], Xn_step3, net_features, "network")
        compare_live_to_dataset(Xp_live[None, :, :], Xp_step3, proc_features, "process")

        feature_stats("LIVE network", Xn_live[None, :, :], net_features, top_n=15)
        feature_stats("LIVE process", Xp_live[None, :, :], proc_features, top_n=14)


if __name__ == "__main__":
    main()