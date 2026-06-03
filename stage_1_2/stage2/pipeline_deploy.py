import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
import torch.nn.functional as F
import torch
import time
import matplotlib.pyplot as plt
from src.stage1_at.model.AnomalyTransformer import AnomalyTransformer
from src.stage2_classifier.model.itransformer_classifier import Stage2ITransformerClassifier, Stage2ModelConfig

BG = "#F8F9FA"

PREDICTED_ATTACK_NAMES = {
    0: "normal",
    1: "detect_operating_mode",
    2: "modify_alarm_settings",
    3: "modify_controller_tasking",
    4: "modify_parameters",
    5: "change_operating_mode",
}

TECHNIQUE_IDS = {
    1: "T0868",
    2: "T0838",
    3: "T0821",
    4: "T0836",
    5: "T0858",
}

def ensure_dir(path): Path(path).mkdir(parents=True, exist_ok=True)
def load_json(path): return json.loads(Path(path).read_text())
def load_label_names(path):
    p = Path(path)
    if not p.exists(): return {0: "normal"}
    m = json.loads(p.read_text())
    return {int(v): str(k) for k, v in m.items()}

def my_kl_loss(p, q):
    return torch.mean(torch.sum(p * (torch.log(p + 0.0001) - torch.log(q + 0.0001)), dim=-1), dim=1)

def batch_prior_score(series_list, prior_list, mask):
    total = None
    for series, prior in zip(series_list, prior_list):
        p_norm = prior / (torch.sum(prior, dim=-1, keepdim=True) + 1e-8)
        layer = my_kl_loss(p_norm, series.detach()) + my_kl_loss(series.detach(), p_norm)
        layer = torch.sum(layer * mask, dim=1) / (torch.sum(mask, dim=1) + 1e-8)
        total = layer if total is None else total + layer
    return total / max(len(prior_list), 1)

def build_model(input_c, output_c, win_size, checkpoint_path, device):
    model = AnomalyTransformer(win_size=win_size, enc_in=input_c, c_out=output_c, d_model=512, n_heads=8, e_layers=3, d_ff=512, dropout=0.0, activation="gelu", output_attention=True).to(device)
    model.load_state_dict(torch.load(checkpoint_path, map_location=device, weights_only=True))
    model.eval()
    return model

def load_branch(root_dir, branch, dataset_name, split="test"):
    branch_dir = Path(root_dir) / branch / split
    x_name, y_name, m_name = ("X_test.npy", "y_test.npy", "mask_test.npy") if split == "test" else ("X_all.npy", "y_all.npy", "mask_all.npy")
    X, y, mask = np.load(branch_dir / x_name).astype(np.float32), np.load(branch_dir / y_name).astype(np.int64), np.load(branch_dir / m_name).astype(np.float32)
    meta_path = branch_dir / "window_metadata.csv"
    meta = pd.read_csv(meta_path) if meta_path.exists() else pd.DataFrame(index=np.arange(len(y)))
    meta = meta.reset_index(drop=True)
    meta["dataset"] = dataset_name
    meta["window_index"] = np.arange(len(y))
    return X, y, mask, meta

def score_one(model, x_np, m_np, device):
    with torch.no_grad():
        x = torch.from_numpy(x_np[None]).float().to(device)
        m = torch.from_numpy(m_np[None]).float().to(device)
        out, series, prior, _ = model(x, padding_mask=m)
        rec = torch.sum(((out - x) ** 2) * m.unsqueeze(-1), dim=(1, 2)) / (torch.sum(m, dim=1) * x.shape[-1] + 1e-8)
        prior_s = batch_prior_score(series, prior, m)
        score = rec * prior_s
    return float(score.item()), float(rec.item()), float(prior_s.item())

def parse_attack_args(items):
    out = []
    for item in items:
        name, path = item.split("=", 1)
        out.append((name, path))
    return out

def choose_final_label(n, p): return int(n) if int(n) > 0 else int(p)

def decision(flag): return "ANOMALY" if flag else "NORMAL"
def trigger(n, p): return "both" if n and p else "network" if n else "process" if p else "none"

def compute_summary(df, net_thr, proc_thr):
    y = (df["final_label_id"].to_numpy() > 0).astype(int)
    pred = df["stage1_anomaly"].to_numpy().astype(int)
    tn = int(((pred == 0) & (y == 0)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum()); tp = int(((pred == 1) & (y == 1)).sum())
    total = len(df)
    return {
        "network_threshold": float(net_thr), "process_threshold": float(proc_thr), "total_windows": int(total),
        "passed_to_stage2": int(pred.sum()), "blocked": int((pred == 0).sum()),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "accuracy": float((tp + tn) / (total + 1e-9)),
        "recall": float(tp / (tp + fn + 1e-9)),
        "precision": float(tp / (tp + fp + 1e-9)),
        "f1": float((2 * tp) / (2 * tp + fp + fn + 1e-9)),
        "fpr": float(fp / (fp + tn + 1e-9))
    }

def plot_passed_blocked(df, out_dir):
    counts = {"Blocked": int((df.stage1_anomaly == 0).sum()), "Passed to Stage 2": int((df.stage1_anomaly == 1).sum())}
    fig, ax = plt.subplots(figsize=(8, 6)); fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.pie(counts.values(), labels=[f"{k}\n({v})" for k, v in counts.items()], autopct="%1.1f%%", startangle=140, colors=["#2E86DE", "#F39C12"], wedgeprops=dict(edgecolor="white", linewidth=2))
    ax.set_title("Stage 1 Fusion — Passed vs Blocked", fontsize=13, fontweight="bold", color="#1E3A5F")
    plt.tight_layout(); plt.savefig(Path(out_dir) / "stage1_fusion_passed_vs_blocked.png", dpi=160, bbox_inches="tight", facecolor=BG); plt.close()

def plot_filtering_summary(df, out_dir):
    y = (df.final_label_id > 0).astype(int); pred = df.stage1_anomaly.astype(int)
    counts = {
        "Normal Blocked": int(((pred == 0) & (y == 0)).sum()),
        "Normal Passed": int(((pred == 1) & (y == 0)).sum()),
        "Attack Passed": int(((pred == 1) & (y == 1)).sum()),
        "Attack Missed": int(((pred == 0) & (y == 1)).sum())
    }
    fig, ax = plt.subplots(figsize=(8, 6)); fig.patch.set_facecolor(BG); ax.set_facecolor(BG)
    ax.pie(counts.values(), labels=[f"{k}\n({v})" for k, v in counts.items()], autopct="%1.1f%%", startangle=90, colors=["#2E86DE", "#F39C12", "#2CA02C", "#D62728"], wedgeprops=dict(edgecolor="white", linewidth=2))
    ax.set_title("Stage 1 Fusion Filtering Summary", fontsize=13, fontweight="bold", color="#1E3A5F")
    plt.tight_layout(); plt.savefig(Path(out_dir) / "stage1_fusion_filtering_summary.png", dpi=160, bbox_inches="tight", facecolor=BG); plt.close()

def plot_full_pipeline_metrics(df, out_dir):
    y_true = df["final_label_id"].to_numpy()
    y_pred = df["stage2_pred_id"].to_numpy()

    acc = (y_true == y_pred).mean()
    attack_mask = y_true > 0
    attack_acc = (y_true[attack_mask] == y_pred[attack_mask]).mean() if attack_mask.any() else 0

    metrics = {
        "Overall Accuracy": acc * 100,
        "Attack Accuracy": attack_acc * 100,
        "Stage 1 Recall": compute_summary(df, df["network_threshold"].iloc[0], df["process_threshold"].iloc[0])["recall"] * 100,
    }

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    bars = ax.bar(metrics.keys(), metrics.values())
    ax.set_ylim(0, 100)
    ax.set_ylabel("Score (%)")
    ax.set_title("Full Pipeline Deployment Metrics", fontsize=13, fontweight="bold", color="#1E3A5F")

    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 1, f"{h:.2f}%", ha="center", fontweight="bold")

    plt.tight_layout()
    plt.savefig(Path(out_dir) / "full_pipeline_metric_summary.png", dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close()


def plot_stage2_confusion(df, out_dir, label_names):
    from sklearn.metrics import confusion_matrix

    y_true = df["final_label_id"].to_numpy()
    y_pred = df["stage2_pred_id"].to_numpy()
    labels = sorted(label_names.keys())
    names = [label_names[i] for i in labels]

    cm = confusion_matrix(y_true, y_pred, labels=labels)

    fig, ax = plt.subplots(figsize=(9, 7))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    im = ax.imshow(cm, cmap="Blues")
    plt.colorbar(im, ax=ax)

    ax.set_xticks(range(len(names)))
    ax.set_yticks(range(len(names)))
    ax.set_xticklabels(names, rotation=35, ha="right")
    ax.set_yticklabels(names)

    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, str(cm[i, j]), ha="center", va="center", fontweight="bold")

    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Full Pipeline Confusion Matrix", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(Path(out_dir) / "full_pipeline_confusion_matrix.png", dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close()


def plot_inference_time(df, out_dir):
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    ax.hist(df["inference_time_sec"], bins=20)
    ax.set_xlabel("Inference Time per Window (seconds)")
    ax.set_ylabel("Window Count")
    ax.set_title("Full Pipeline Inference Time", fontsize=13, fontweight="bold", color="#1E3A5F")

    plt.tight_layout()
    plt.savefig(Path(out_dir) / "full_pipeline_inference_time.png", dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close()

def plot_stage2_confusion_percent(df, out_dir, label_names):
    from sklearn.metrics import confusion_matrix
    import numpy as np

    y_true = df["final_label_id"].to_numpy()
    y_pred = df["stage2_pred_id"].to_numpy()
    labels = sorted(label_names.keys())
    names = [label_names[i] for i in labels]

    cm = confusion_matrix(y_true, y_pred, labels=labels)
    row_sums = cm.sum(axis=1, keepdims=True)
    cm_pct = np.divide(cm, row_sums, out=np.zeros_like(cm, dtype=float), where=row_sums != 0) * 100

    fig, ax = plt.subplots(figsize=(9, 7))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    im = ax.imshow(cm_pct, cmap="Blues", vmin=0, vmax=100)
    plt.colorbar(im, ax=ax)

    ax.set_xticks(range(len(names)))
    ax.set_yticks(range(len(names)))
    ax.set_xticklabels(names, rotation=35, ha="right")
    ax.set_yticklabels(names)

    for i in range(cm_pct.shape[0]):
        for j in range(cm_pct.shape[1]):
            ax.text(j, i, f"{cm_pct[i, j]:.1f}%", ha="center", va="center", fontweight="bold")

    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Full Pipeline Confusion Matrix (%)", fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(Path(out_dir) / "full_pipeline_confusion_matrix_percent.png", dpi=160, bbox_inches="tight", facecolor=BG)
    plt.close()

def get_meta_value(row, candidates, default=None):
    for c in candidates:
        if c in row and pd.notna(row[c]):
            return row[c]
    return default


def as_iso_time(value, fallback_seconds=None):
    if value is not None:
        s = str(value)
        if "T" in s:
            return s
        if len(s.split(":")) >= 2:
            return f"2022-01-01T{s}"

    if fallback_seconds is not None:
        seconds = float(fallback_seconds)
        h = int(seconds // 3600) % 24
        m = int((seconds % 3600) // 60)
        sec = int(seconds % 60)
        return f"2022-01-01T{h:02d}:{m:02d}:{sec:02d}"

    return "2022-01-01T00:00:00"

def save_stage2_ready(out_dir, passed, tensors):
    d = Path(out_dir) / "stage2_ready"; ensure_dir(d)
    if len(passed):
        np.save(d / "X_network_stage2.npy", np.stack([tensors[r.dataset]["Xn"][int(r.window_index)] for r in passed.itertuples()]).astype(np.float32))
        np.save(d / "X_process_stage2.npy", np.stack([tensors[r.dataset]["Xp"][int(r.window_index)] for r in passed.itertuples()]).astype(np.float32))
        np.save(d / "mask_network_stage2.npy", np.stack([tensors[r.dataset]["mn"][int(r.window_index)] for r in passed.itertuples()]).astype(np.float32))
        np.save(d / "mask_process_stage2.npy", np.stack([tensors[r.dataset]["mp"][int(r.window_index)] for r in passed.itertuples()]).astype(np.float32))
        np.save(d / "y_network_stage2.npy", np.array([tensors[r.dataset]["yn"][int(r.window_index)] for r in passed.itertuples()], dtype=np.int64))
        np.save(d / "y_process_stage2.npy", np.array([tensors[r.dataset]["yp"][int(r.window_index)] for r in passed.itertuples()], dtype=np.int64))
        np.save(d / "y_stage2.npy", passed.final_label_id.to_numpy(dtype=np.int64))
    passed.to_csv(d / "stage2_metadata.csv", index=False)
    return d

def build_stage2_classifier(checkpoint_dir, device):
    checkpoint_dir = Path(checkpoint_dir)
    cfg_dict = json.loads((checkpoint_dir / "config.json").read_text())

    allowed = Stage2ModelConfig.__dataclass_fields__.keys()
    cfg_clean = {k: v for k, v in cfg_dict.items() if k in allowed}
    cfg = Stage2ModelConfig(**cfg_clean)

    model = Stage2ITransformerClassifier(cfg).to(device)

    ckpt = torch.load(checkpoint_dir / "checkpoint.pt", map_location=device, weights_only=True)
    state = ckpt["model_state_dict"] if isinstance(ckpt, dict) and "model_state_dict" in ckpt else ckpt

    model.load_state_dict(state)
    model.eval()
    return model, cfg_dict

def export_deployment_alerts_json(df, out_dir):
    alerts = []
    rows = []

    for _, row in df.iterrows():
        pred = int(row["stage2_pred_id"])

        full_row = {
            "true_label": int(row["final_label_id"]),
            "predicted_label": pred,
            "predicted_attack": PREDICTED_ATTACK_NAMES.get(pred, str(pred)),
            "classifier_confidence": float(row.get("classifier_confidence", 0.0)),
            "network_anomaly_score": float(row.get("network_score", 0.0)),
            "process_anomaly_score": float(row.get("process_score", 0.0)),
            "window_start_time": as_iso_time(
                get_meta_value(row, ["window_start_time", "window_start_hms"], None),
                get_meta_value(row, ["window_start_seconds"], None),
            ),
            "window_end_time": as_iso_time(
                get_meta_value(row, ["window_end_time", "window_end_hms"], None),
                get_meta_value(row, ["window_end_seconds"], None),
            ),
            "technique_id": TECHNIQUE_IDS.get(pred),
            "dataset": row.get("dataset"),
            "window_index": int(row.get("window_index", -1)),
            "stage1_trigger": row.get("fusion_trigger"),
            "result_text": row.get("result_text"),
        }

        rows.append(full_row)

        if pred > 0:
            alerts.append({
                "predicted_attack": full_row["predicted_attack"],
                "classifier_confidence": full_row["classifier_confidence"],
                "network_anomaly_score": full_row["network_anomaly_score"],
                "process_anomaly_score": full_row["process_anomaly_score"],
                "window_start_time": full_row["window_start_time"],
                "window_end_time": full_row["window_end_time"],
                "technique_id": full_row["technique_id"],
            })

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "alerts.json", "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2)

    pd.DataFrame(rows).to_csv(out_dir / "stage2_all_predictions.csv", index=False)

    stage2_default = Path("outputs") / "stage2"
    stage2_default.mkdir(parents=True, exist_ok=True)

    with open(stage2_default / "alerts.json", "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2)

    pd.DataFrame(rows).to_csv(stage2_default / "deployment_stage2_all_predictions.csv", index=False)

    return alerts

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--normal_root", required=True); p.add_argument("--attack", nargs="+", required=True)
    p.add_argument("--network_checkpoint", required=True); p.add_argument("--process_checkpoint", required=True)
    p.add_argument("--network_threshold_json", required=True); p.add_argument("--process_threshold_json", required=True)
    p.add_argument("--output_dir", required=True); p.add_argument("--label_map_path", default="data/processed/ICS/label_map.json")
    p.add_argument("--split", choices=["test", "all"], default="test"); p.add_argument("--device", default=None)
    p.add_argument("--stage2_checkpoint_dir", required=True)
    args = p.parse_args()

    out_dir = Path(args.output_dir); ensure_dir(out_dir)
    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    label_names = load_label_names(args.label_map_path)
    net_thr = float(load_json(args.network_threshold_json)["selected_threshold"])
    proc_thr = float(load_json(args.process_threshold_json)["selected_threshold"])

    print(f"[1] Loading models on {device}...")
    net_model = build_model(43, 43, 120, args.network_checkpoint, device)
    proc_model = build_model(14, 14, 50, args.process_checkpoint, device)

    print("[2] Loading Stage 2 classifier...")
    stage2_model, stage2_cfg = build_stage2_classifier(args.stage2_checkpoint_dir, device)

    print("WINDOW | GT | STAGE1 | STAGE2 | NETWORK | PROCESS | NET_SCORE | PROC_SCORE | TRIGGER | RESULT | TIME")
    rows, tensors = [], {}
    for dataset, root in [("normal_validation", args.normal_root)] + parse_attack_args(args.attack):
        print(f"========== {dataset} ==========")
        Xn, yn, mn, meta_n = load_branch(root, "network", dataset, args.split)
        Xp, yp, mp, meta_p = load_branch(root, "process", dataset, args.split)
        if len(Xn) != len(Xp): raise ValueError(f"{dataset}: network/process window count mismatch.")
        tensors[dataset] = {"Xn": Xn, "Xp": Xp, "mn": mn, "mp": mp, "yn": yn, "yp": yp}

        for i in range(len(Xn)):
            ns, nr, np_ = score_one(net_model, Xn[i], mn[i], device)
            ps, pr, pp = score_one(proc_model, Xp[i], mp[i], device)
            na, pa = int(ns > net_thr), int(ps > proc_thr)
            fa, trig = int(na or pa), trigger(na, pa)
            start_t = time.perf_counter()
            stage2_pred = "BLOCKED"
            pred_id = 0
            classifier_confidence = 1.0
            if fa:
                with torch.no_grad():
                    xn = torch.from_numpy(Xn[i][None]).float().to(device)
                    xp = torch.from_numpy(Xp[i][None]).float().to(device)
                    mn_t = torch.from_numpy(mn[i][None]).float().to(device)
                    mp_t = torch.from_numpy(mp[i][None]).float().to(device)
                    logits = stage2_model(xn, xp,mask_net=mn_t,mask_proc=mp_t)
                    probs = torch.softmax(logits.float(), dim=1)
                    pred_id = int(torch.argmax(probs, dim=1).item())
                    classifier_confidence = float(torch.max(probs, dim=1).values.item())
                    stage2_pred = label_names.get(pred_id, str(pred_id))
            flabel = choose_final_label(yn[i], yp[i])
            gt_name = label_names.get(flabel, str(flabel))
            is_correct = ((fa == 0 and flabel == 0) or (fa == 1 and stage2_pred == gt_name))
            row = meta_n.iloc[i].to_dict()
            elapsed = time.perf_counter() - start_t
            pred_id = 0 if not fa else pred_id
            stage2_pred_id = int(pred_id)
            result_text = "CORRECT" if is_correct else "WRONG"
            row.update({"dataset": dataset, "window_index": i, "network_label_id": int(yn[i]), "process_label_id": int(yp[i]), "network_score": ns, "process_score": ps, "network_reconstruction_score": nr, "process_reconstruction_score": pr, "network_prior_score": np_, "process_prior_score": pp, "network_threshold": net_thr, "process_threshold": proc_thr, "network_anomaly": na, "process_anomaly": pa, "stage1_anomaly": fa, "fusion_trigger": trig, "network_trigger_flag": na, "process_trigger_flag": pa, "final_label_id": flabel, "final_label_name": label_names.get(flabel, str(flabel)), "is_true_attack": int(flabel > 0), "stage2_pred_id": stage2_pred_id,"stage2_prediction": stage2_pred,"is_correct": int(is_correct),"result_text": result_text,"inference_time_sec": elapsed, "classifier_confidence": classifier_confidence})
            rows.append(row)
            net_mark = "✓" if na else "-"
            proc_mark = "✓" if pa else "-"
            print(
                f"[{i:04d}] | "
                f"{gt_name:32s} | "
                f"{decision(fa):8s} | "
                f"{stage2_pred:32s} | "
                f"{net_mark:^7s} | "
                f"{proc_mark:^7s} | "
                f"{ns:.4f} | "
                f"{ps:.4f} | "
                f"{trig:^8s} | "
                f"{result_text:7s} | "
                f"{elapsed:.3f}s"
            )

    all_df = pd.DataFrame(rows)
    all_df.to_csv(out_dir / "stage1_fusion_all_windows.csv", index=False)
    passed = all_df[all_df.stage1_anomaly == 1].copy()
    passed.to_csv(out_dir / "stage1_fusion_passed_windows.csv", index=False)
    alerts = export_deployment_alerts_json(all_df, out_dir)

    stage2_dir = save_stage2_ready(out_dir, passed, tensors)
    plot_passed_blocked(all_df, out_dir); plot_filtering_summary(all_df, out_dir)
    plot_full_pipeline_metrics(all_df, out_dir); plot_stage2_confusion(all_df, out_dir, label_names); plot_inference_time(all_df, out_dir); plot_stage2_confusion_percent(all_df, out_dir, label_names)
    summary = compute_summary(all_df, net_thr, proc_thr)
    summary["stage2_ready_dir"] = str(stage2_dir); summary["stage2_ready_windows"] = int(len(passed))
    summary["alerts_path"] = str(out_dir / "alerts.json")
    summary["stage3_alerts_path"] = str(Path("outputs") / "stage2" / "alerts.json")
    summary["alerts_count"] = int(len(alerts))
    (out_dir / "stage1_fusion_summary.json").write_text(json.dumps(summary, indent=2))

    print("Done.")
    print("Summary:", summary)
    print("Outputs:", out_dir)

if __name__ == "__main__":
    main()