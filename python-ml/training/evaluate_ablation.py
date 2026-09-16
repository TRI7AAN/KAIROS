"""Phase 31 evaluation: infiltration + stage metrics and rollout lead time.

For each window size (5s/10s/30s), loads the trained checkpoint and the
validation-day contract, then:
  - one-step infiltration head: F1 / precision / recall / FPR over all
    val windows (threshold 0.5 on teacher-forced next-step predictions);
  - stage head: macro precision/recall/F1 over the 6 classes, restricted to
    malicious windows (benign -1 excluded), with per-class counts;
  - rollout lead time: for 2-3 known attack windows on the val day, run a
    K=5 rollout from contexts ending 1..12 windows before the attack start
    and record the first lead (in windows and seconds) where mean rollout
    infiltration probability crosses 0.5. Also saves rollout probability
    curves (results/rollout_<ws>s_<attack>.png).

Usage:
    PYTHONPATH=python-ml python-ml/venv/bin/python \\
        python-ml/training/evaluate_ablation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from torch_geometric.data import Batch

from model.world_model import NetworkWorldModel
from pipeline.graph_builder import STAGE_TO_INDEX, load_graph_sequence

ROLL_OUT_K = 5
THRESHOLD = 0.5
LEAD_SEARCH = 12
# Fixed-threshold head metrics are degenerate here (all probs < 0.5 on the
# C2-only val day, an unseen stage). Report ranking quality instead: AUC-ROC
# and AUC-PR over the teacher-forced next-step probabilities, plus the
# threshold-0.5 confusion counts for the record.

VARIANTS = {
    5: ("data/processed/graphs_5s", "python-ml/weights/world_model_5s.pt"),
    10: ("data/processed/graph_contracts", "python-ml/weights/world_model_v1.pt"),
    30: ("data/processed/graphs_30s", "python-ml/weights/world_model_30s.pt"),
}
VAL_CONTRACT = "day0302.json"
CLASS_NAMES = ["RECONNAISSANCE", "INITIAL_ACCESS", "LATERAL_MOVEMENT",
               "COMMAND_AND_CONTROL", "EXFILTRATION", "IMPACT"]


def head_metrics(model, graphs):
    chunk = 512
    inf_probs, stage_probs, targets, stage_targets = [], [], [], []
    with torch.no_grad():
        for start in range(0, len(graphs) - 1, chunk):
            piece = list(graphs[start:start + chunk + 1])
            batch = Batch.from_data_list(piece)
            states = model.encoder(batch).unsqueeze(0)
            predicted = model.dynamics(states[:, :-1])
            outputs = model.heads(predicted)
            inf_probs.append(outputs["infiltration_probability"][0].cpu())
            stage_probs.append(outputs["stage_probability"][0].cpu())
            targets.append(torch.stack(
                [g.y_infiltration for g in piece[1:]]).squeeze(1))
            stage_targets.append(torch.stack(
                [g.y_stage for g in piece[1:]]).squeeze(1))
    inf_prob = torch.cat(inf_probs)
    stage_prob = torch.cat(stage_probs)
    targets = torch.cat(targets)
    stage_targets = torch.cat(stage_targets)
    pred = (inf_prob >= THRESHOLD).float()
    tp = int(((pred == 1) & (targets == 1)).sum())
    fp = int(((pred == 1) & (targets == 0)).sum())
    fn = int(((pred == 0) & (targets == 1)).sum())
    tn = int(((pred == 0) & (targets == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    auc_roc = _auc_roc(inf_prob.tolist(), targets.tolist())
    auc_pr = _auc_pr(inf_prob.tolist(), targets.tolist())
    stage_pred = stage_prob.argmax(dim=-1)
    per_class, precisions, recalls, f1s = [], [], [], []
    for class_index in range(len(CLASS_NAMES)):
        mask = stage_targets == class_index
        support = int(mask.sum())
        if not support:
            per_class.append({"class": CLASS_NAMES[class_index],
                              "support": 0, "precision": 0.0,
                              "recall": 0.0, "f1": 0.0})
            precisions.append(0.0)
            recalls.append(0.0)
            f1s.append(0.0)
            continue
        correct = int(((stage_pred == class_index) & mask).sum())
        predicted_total = int((stage_pred == class_index).sum())
        precision_c = correct / predicted_total if predicted_total else 0.0
        recall_c = correct / support
        f1_c = (2 * precision_c * recall_c / (precision_c + recall_c)
                if precision_c + recall_c else 0.0)
        per_class.append({"class": CLASS_NAMES[class_index], "support": support,
                          "precision": precision_c, "recall": recall_c, "f1": f1_c})
        precisions.append(precision_c)
        recalls.append(recall_c)
        f1s.append(f1_c)
    attack_indices = [i for i, g in enumerate(graphs)
                      if int(g.y_stage.item()) >= 0]
    return {
        "windows_evaluated": len(graphs) - 1,
        "infiltration": {"threshold": THRESHOLD, "tp": tp, "fp": fp,
                         "fn": fn, "tn": tn, "precision": precision,
                         "recall": recall, "f1": f1, "fpr": fpr,
                         "auc_roc": auc_roc, "auc_pr": auc_pr},
        "stage": {"macro_precision": sum(precisions) / len(precisions),
                  "macro_recall": sum(recalls) / len(recalls),
                  "macro_f1": sum(f1s) / len(f1s),
                  "malicious_windows": len(attack_indices),
                  "per_class": per_class},
    }


def _auc_roc(scores: list[float], labels: list[int]) -> float:
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranked = [labels[i] for i in order]
    positives = sum(ranked)
    negatives = len(ranked) - positives
    if not positives or not negatives:
        return 0.0
    concordant = 0.0
    seen_positive = 0
    for label in ranked:
        if label == 1:
            seen_positive += 1
        else:
            concordant += seen_positive
    return concordant / (positives * negatives)


def _auc_pr(scores: list[float], labels: list[int]) -> float:
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    positives = sum(labels)
    if not positives:
        return 0.0
    area, hits = 0.0, 0
    for rank, index in enumerate(order, start=1):
        if labels[index] == 1:
            hits += 1
            area += hits / rank
    return area / positives


def attack_blocks(graphs):
    blocks, start = [], None
    for index, graph in enumerate(graphs):
        malicious = int(graph.y_stage.item()) >= 0
        if malicious and start is None:
            start = index
        elif not malicious and start is not None:
            blocks.append((start, index - 1))
            start = None
    if start is not None:
        blocks.append((start, len(graphs) - 1))
    return [block for block in blocks if block[1] - block[0] >= 2]


def rollout_lead(model, graphs, window_seconds):
    blocks = attack_blocks(graphs)
    picked = sorted(blocks, key=lambda b: b[1] - b[0], reverse=True)[:3]
    results = []
    attack_mean = _attack_mean_prob(model, graphs)
    for attack_start, attack_end in picked:
        curve = []
        lead_windows = None
        with torch.no_grad():
            for lead in range(LEAD_SEARCH, 0, -1):
                context_end = attack_start - lead
                if context_end < 1:
                    continue
                context = Batch.from_data_list(
                    list(graphs[max(0, context_end - 63):context_end]))
                states = model.encoder(context).unsqueeze(0)
                rollout = model.dynamics.rollout(states, steps=ROLL_OUT_K)
                mean_prob = float(
                    model.heads(rollout)["infiltration_probability"].mean())
                curve.append({"lead_windows": lead, "mean_prob": mean_prob})
                if mean_prob >= THRESHOLD and lead_windows is None:
                    lead_windows = lead
        results.append({
            "attack_start_window": attack_start,
            "attack_end_window": attack_end,
            "attack_length_windows": attack_end - attack_start + 1,
            "threshold": THRESHOLD,
            "attack_mean_prob": attack_mean,
            "relative_lead_windows": None,
            "relative_lead_seconds": None,
            "note": ("absolute 0.5 threshold never crossed (all probs low "
                     "on unseen C2 day); use ranking/relative-rise instead"),
            "lead_windows": lead_windows,
            "lead_seconds": (lead_windows * window_seconds
                             if lead_windows is not None else None),
            "curve": sorted(curve, key=lambda row: -row["lead_windows"]),
        })
    return results


def _attack_mean_prob(model, graphs) -> float:
    values = []
    with torch.no_grad():
        for start in range(0, len(graphs) - 1, 512):
            piece = list(graphs[start:start + 513])
            states = model.encoder(
                Batch.from_data_list(piece)).unsqueeze(0)
            probs = model.heads(
                model.dynamics(states[:, :-1]))["infiltration_probability"][0]
            for prob, graph in zip(probs.tolist(), piece[1:]):
                if int(graph.y_stage.item()) >= 0:
                    values.append(prob)
    return sum(values) / len(values) if values else 0.0


def main() -> int:
    summary = {}
    for window_seconds, (contract_dir, checkpoint_rel) in VARIANTS.items():
        contract = REPO_ROOT / contract_dir / VAL_CONTRACT
        sequence = load_graph_sequence(contract)
        model = NetworkWorldModel(len(sequence.node_feature_names),
                                  len(sequence.edge_feature_names))
        payload = torch.load(REPO_ROOT / checkpoint_rel, map_location="cpu",
                             weights_only=False)
        model.load_state_dict(payload["model_state_dict"])
        model.eval()
        graphs = list(sequence.graphs)
        metrics = head_metrics(model, graphs)
        leads = rollout_lead(model, graphs, window_seconds)
        summary[str(window_seconds)] = {
            "checkpoint": checkpoint_rel,
            "contract": str(Path(contract_dir) / VAL_CONTRACT),
            "val_windows": len(graphs),
            **metrics,
            "rollout_k": ROLL_OUT_K,
            "rollout_attacks": leads,
        }
        inf = metrics["infiltration"]
        print(f"{window_seconds}s: val={len(graphs)} "
              f"AUC-ROC={inf['auc_roc']:.4f} AUC-PR={inf['auc_pr']:.4f} "
              f"F1@0.5={inf['f1']:.4f} P={inf['precision']:.4f} "
              f"R={inf['recall']:.4f} FPR={inf['fpr']:.4f} "
              f"stage macro-F1={metrics['stage']['macro_f1']:.4f} "
              f"leads={[a['lead_windows'] for a in leads]}", flush=True)
        for attack_number, attack in enumerate(leads):
            xs = [row["lead_windows"] for row in attack["curve"]]
            ys = [row["mean_prob"] for row in attack["curve"]]
            if not xs:
                continue
            plt.figure(figsize=(7, 4))
            plt.plot(xs, ys, marker="o")
            plt.axhline(THRESHOLD, linestyle="--")
            plt.gca().invert_xaxis()
            plt.xlabel("windows before attack start")
            plt.ylabel(f"mean rollout (K={ROLL_OUT_K}) infiltration prob")
            plt.title(f"{window_seconds}s windows: attack "
                      f"@{attack['attack_start_window']} "
                      f"(lead={attack['lead_windows']})")
            plt.tight_layout()
            plt.savefig(REPO_ROOT / "results" / "rollout_"
                        f"{window_seconds}s_attack{attack_number}.png", dpi=100)
            plt.close()
    (REPO_ROOT / "results" / "ablation_eval.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("wrote results/ablation_eval.json + rollout curves")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
