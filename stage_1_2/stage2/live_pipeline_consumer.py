import argparse
import json
import time
from datetime import datetime
from pathlib import Path
import os
import numpy as np
import redis
import torch

from pipeline_deploy import (
    build_model,
    build_stage2_classifier,
    score_one,
    load_json,
    load_label_names,
    trigger,
    PREDICTED_ATTACK_NAMES,
    TECHNIQUE_IDS,
)


def parse_json_array(value, name):
    try:
        return json.loads(value)
    except Exception as e:
        raise ValueError(f"Failed to parse {name}: {e}")


def publish_alert(
    r,
    stream,
    predicted_attack,
    confidence,
    network_score,
    process_score,
    technique_id,
    stage1_trigger,
    window_id,
):
    now_iso = datetime.now().isoformat(timespec="seconds")

    payload = {
        "predicted_attack": str(predicted_attack),
        "classifier_confidence": str(confidence),
        "network_anomaly_score": str(network_score),
        "process_anomaly_score": str(process_score),
        "window_start_time": now_iso,
        "window_end_time": now_iso,
        "technique_id": str(technique_id or ""),
        "stage1_trigger": str(stage1_trigger),
        "window_id": str(window_id),
        "source": "live_ot_environment",
    }

    msg_id = r.xadd(stream, payload, maxlen=1000, approximate=True)
    return msg_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--redis_host", default=os.getenv("REDIS_HOST", "localhost"))
    parser.add_argument("--redis_port", type=int, default=int(os.getenv("REDIS_PORT", "6379")))
    parser.add_argument("--input_stream", default=os.getenv("MODEL_READY_STREAM", "model_ready_windows"))
    parser.add_argument("--output_stream", default=os.getenv("AI_ALERT_STREAM", "ai_alerts"))
    parser.add_argument("--start_id", default="$")

    parser.add_argument("--network_checkpoint", default=os.getenv("NETWORK_CHECKPOINT", "models/stage1_at/network/network_at_checkpoint.pt"))
    parser.add_argument("--process_checkpoint", default=os.getenv("PROCESS_CHECKPOINT", "models/stage1_at/process/process_at_checkpoint.pt"))   
    parser.add_argument("--network_threshold_json", default=os.getenv("NETWORK_THRESHOLD_JSON", "thresholds/network_threshold.json"))
    parser.add_argument("--process_threshold_json", default=os.getenv("PROCESS_THRESHOLD_JSON", "thresholds/process_threshold.json"))
    parser.add_argument("--stage2_checkpoint_dir", default=os.getenv("STAGE2_CHECKPOINT_DIR", "models/stage2_classifier/final/itransformer_sdpa_amp_fp16_t0821_t2t2_lr8e5_ls001"))
    parser.add_argument("--label_map_path", default="data/processed/ICS/label_map.json")
    parser.add_argument("--device", default=None)

    args = parser.parse_args()

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")

    print(f"[1] Connecting to Redis {args.redis_host}:{args.redis_port}...")
    r = redis.Redis(host=args.redis_host, port=args.redis_port, decode_responses=True)
    r.ping()

    print(f"[2] Loading thresholds...")
    net_thr = float(load_json(args.network_threshold_json)["selected_threshold"])
    proc_thr = float(load_json(args.process_threshold_json)["selected_threshold"])
    
    print(f"Network threshold: {net_thr}")
    print(f"Process threshold: {proc_thr}")

    print(f"[3] Loading Stage 1 models on {device}...")
    net_model = build_model(43, 43, 120, args.network_checkpoint, device)
    proc_model = build_model(14, 14, 50, args.process_checkpoint, device)

    print("[4] Loading Stage 2 classifier...")
    stage2_model, _ = build_stage2_classifier(args.stage2_checkpoint_dir, device)

    label_names = load_label_names(args.label_map_path)

    last_id = args.start_id

    print("\nLive pipeline consumer started.")
    print(f"Input stream: {args.input_stream}")
    print(f"Output stream: {args.output_stream}")
    print("Waiting for model-ready windows...\n")

    while True:
        messages = r.xread({args.input_stream: last_id}, block=5000, count=1)

        if not messages:
            continue

        for _, entries in messages:
            for msg_id, data in entries:
                last_id = msg_id
                window_id = data.get("window_id", msg_id)

                try:
                    Xn = np.array(parse_json_array(data["network_window"], "network_window"), dtype=np.float32)
                    Xp = np.array(parse_json_array(data["process_window"], "process_window"), dtype=np.float32)
                    mn = np.array(parse_json_array(data["network_mask"], "network_mask"), dtype=np.float32)
                    mp = np.array(parse_json_array(data["process_mask"], "process_mask"), dtype=np.float32)

                    if Xn.shape != (120, 43):
                        raise ValueError(f"Expected network shape (120,43), got {Xn.shape}")
                    if Xp.shape != (50, 14):
                        raise ValueError(f"Expected process shape (50,14), got {Xp.shape}")
                    if mn.shape != (120,):
                        raise ValueError(f"Expected network mask shape (120,), got {mn.shape}")
                    if mp.shape != (50,):
                        raise ValueError(f"Expected process mask shape (50,), got {mp.shape}")

                    start = time.perf_counter()

                    ns, nr, np_ = score_one(net_model, Xn, mn, device)
                    ps, pr, pp = score_one(proc_model, Xp, mp, device)

                    na = int(ns > net_thr)
                    pa = int(ps > proc_thr)
                    stage1_anomaly = int(na or pa)
                    trig = trigger(na, pa)

                    pred_id = 0
                    pred_name = "normal"
                    confidence = 1.0
                    alert_id = None

                    if stage1_anomaly:
                        with torch.no_grad():
                            xn_t = torch.from_numpy(Xn[None]).float().to(device)
                            xp_t = torch.from_numpy(Xp[None]).float().to(device)
                            mn_t = torch.from_numpy(mn[None]).float().to(device)
                            mp_t = torch.from_numpy(mp[None]).float().to(device)

                            logits = stage2_model(xn_t, xp_t, mask_net=mn_t, mask_proc=mp_t)
                            probs = torch.softmax(logits.float(), dim=1)

                            pred_id = int(torch.argmax(probs, dim=1).item())
                            confidence = float(torch.max(probs, dim=1).values.item())

                            pred_name = label_names.get(pred_id, PREDICTED_ATTACK_NAMES.get(pred_id, str(pred_id)))
                            top_probs = probs[0].detach().cpu().numpy()
                            prob_text = " | ".join(
                                f"{label_names.get(i, str(i))}:{top_probs[i]:.3f}"
                                for i in range(len(top_probs))
                            )

                        if pred_id > 0:
                            alert_id = publish_alert(
                                r=r,
                                stream=args.output_stream,
                                predicted_attack=pred_name,
                                confidence=confidence,
                                network_score=ns,
                                process_score=ps,
                                technique_id=TECHNIQUE_IDS.get(pred_id),
                                stage1_trigger=trig,
                                window_id=window_id,
                            )

                    elapsed = time.perf_counter() - start

                    print(
                        f"[{window_id}] "
                        f"Stage1={'ANOMALY' if stage1_anomaly else 'NORMAL'} | "
                        f"trigger={trig} | "
                        f"net_score={ns:.6f} | proc_score={ps:.6f} | "
                        f"Stage2={pred_name} | conf={confidence:.4f} | probs=[{prob_text if stage1_anomaly else 'not_run'}] | "
                        f"alert_id={alert_id} | time={elapsed:.3f}s"
                    )

                except Exception as e:
                    print(f"[ERROR] Failed processing window {window_id}: {e}")


if __name__ == "__main__":
    main()
    
