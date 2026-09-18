"""Phase 32 shared library: in-distribution (per-day final-20%-time) split,
cross-day (whole-day0302) split, metric computation, and flat-model support.

Both splits reuse the identical 10s canonical contracts:
  - In-distribution: per day, train on the first ceil-free 80% of the
    time-ordered windows, hold out the LAST 20% (ceil) of each day's time
    range for validation. Every stage present in training (IA, Impact, C2)
    also appears in validation.
  - Cross-day generalization stress test (kept, secondary): train on
    day14+day15+day28, validate on whole day0302 (unseen C2 dynamics).

Metric set (shared everywhere Phase 32 reports): infiltration
F1/precision/recall/FPR at threshold 0.5, infiltration AUC-ROC/AUC-PR,
stage macro-F1 (malicious windows only, benign excluded), rollout lead
time (windows before attack start that mean K-step rollout probability
crosses 0.5, 12-lead search), and training time in seconds.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from torch_geometric.data import Batch

from model.world_model import NetworkWorldModel
from model.encoder_flat import FlatWindowEncoder
from pipeline.graph_builder import load_graph_sequence
from training.world_model_trainer import (
    WorldModelTrainingConfig,
    train_world_model,
)

DAY_NAMES = ["day14.json", "day15.json", "day28.json", "day0302.json"]
CONTRACT_DIR = REPO_ROOT / "data" / "processed" / "graph_contracts"
CONTRACT_ALIASES = {
    "day14.json": "cic-2018-02-14-10s.json",
    "day15.json": "cic-2018-02-15-10s.json",
    "day28.json": "cic-2018-02-28-10s.json",
    "day0302.json": "cic-2018-03-02-10s.json",
}

CLASS_NAMES = ["RECONNAISSANCE", "INITIAL_ACCESS", "LATERAL_MOVEMENT",
               "COMMAND_AND_CONTROL", "EXFILTRATION", "IMPACT"]

EPOCHS = 5
CHUNK_LENGTH = 64
LEARNING_RATE = 1e-3
RANDOM_SEED = 42
HIDDEN_DIM = 64
STATE_DIM = 64
SAGE_LAYERS = 2
TRANSFORMER_LAYERS = 2
TRANSFORMER_HEADS = 4
DROPOUT = 0.1
THRESHOLD = 0.5
LEAD_SEARCH = 12


def tail_count(n: int, fraction: float = 0.2) -> int:
    return math.ceil(n * fraction)


def resolve_contract_path(name: str) -> Path:
    """Resolve both the legacy ignored directory and clean-clone filenames."""
    candidates = (
        CONTRACT_DIR / name,
        REPO_ROOT / "data" / "processed" / CONTRACT_ALIASES[name],
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    rendered = " or ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"missing graph contract: expected {rendered}")


def build_splits():
    sequences = {name: load_graph_sequence(resolve_contract_path(name))
                 for name in DAY_NAMES}
    schemas = {(tuple(s.node_feature_names), tuple(s.edge_feature_names))
               for s in sequences.values()}
    if len(schemas) != 1:
        raise SystemExit("feature schemas differ between contracts")
    node_features, edge_features = schemas.pop()
    per_day = {name: list(sequences[name].graphs) for name in DAY_NAMES}
    in_train, in_val = [], []
    for name in DAY_NAMES:
        graphs = per_day[name]
        tail = tail_count(len(graphs))
        in_train.append(graphs[:len(graphs) - tail])
        in_val.append(graphs[len(graphs) - tail:])
    cross_train = [per_day[n] for n in DAY_NAMES[:3]]
    cross_val = [per_day[DAY_NAMES[3]]]
    split_report = {}
    for name in DAY_NAMES:
        graphs = per_day[name]
        tail = tail_count(len(graphs))
        split_report[name] = {
            "total": len(graphs),
            "train": len(graphs) - tail,
            "val": tail,
            "train_stages": _stage_counts(graphs[:len(graphs) - tail]),
            "val_stages": _stage_counts(graphs[len(graphs) - tail:]),
        }
    return node_features, edge_features, in_train, in_val, cross_train, cross_val, split_report


def _stage_counts(graphs) -> dict:
    counts: dict[str, int] = {}
    for graph in graphs:
        key = str(int(graph.y_stage.item()))
        counts[key] = counts.get(key, 0) + 1
    return counts


def make_model(node_dim: int, edge_dim: int, encoder: str = "gnn",
               k_unused=None, dropout: float = DROPOUT) -> NetworkWorldModel:
    model = NetworkWorldModel(node_dim, edge_dim, hidden_dim=HIDDEN_DIM,
                              state_dim=STATE_DIM, sage_layers=SAGE_LAYERS,
                              transformer_layers=TRANSFORMER_LAYERS,
                              transformer_heads=TRANSFORMER_HEADS,
                              dropout=dropout)
    if encoder == "flat":
        model.encoder = FlatWindowEncoder(
            node_dim, edge_dim, hidden_dim=HIDDEN_DIM,
            output_dim=STATE_DIM, dropout=DROPOUT)
    elif encoder != "gnn":
        raise ValueError(f"unknown encoder: {encoder}")
    return model


def train_variant(tag: str, train_graphs, val_graphs, encoder: str,
                   checkpoint_name: str, plot_title: str, *,
                   dynamics_weight: float = 1.0,
                   infiltration_weight: float = 1.0,
                   stage_weight: float = 1.0,
                   infiltration_alpha: float = 0.25,
                   weight_decay: float = 0.0,
                   lr_schedule: str = "none",
                   dropout: float = DROPOUT,
                   epochs: int = EPOCHS) -> dict:
    torch.manual_seed(RANDOM_SEED)
    model = make_model(len(train_graphs_schema[0]), len(train_graphs_schema[1]),
                       encoder=encoder, dropout=dropout)
    started = time.time()
    history = train_world_model(
        model, train_graphs, val_graphs,
        config=WorldModelTrainingConfig(
            epochs=epochs, chunk_length=CHUNK_LENGTH,
            learning_rate=LEARNING_RATE, random_seed=RANDOM_SEED,
            dynamics_weight=dynamics_weight,
            infiltration_weight=infiltration_weight,
            stage_weight=stage_weight,
            infiltration_alpha=infiltration_alpha,
            weight_decay=weight_decay,
            lr_schedule=lr_schedule,
            dropout=dropout),
        checkpoint_path=REPO_ROOT / "python-ml" / "weights" / checkpoint_name,
        config_path=REPO_ROOT / "results" / f"phase32_{tag}_config.json",
        history_path=REPO_ROOT / "results" / f"phase32_{tag}_history.json",
    )
    elapsed = time.time() - started
    epochs = list(range(1, len(history.training_loss) + 1))
    plt.figure(figsize=(8, 5))
    plt.plot(epochs, list(history.training_loss), marker="o", label="train")
    plt.plot(epochs, list(history.validation_loss), marker="s", label="validation")
    plt.xlabel("epoch")
    plt.ylabel("loss")
    plt.title(plot_title)
    plt.legend()
    plt.tight_layout()
    plt.savefig(REPO_ROOT / "results" / f"loss_curve_phase32_{tag}.png", dpi=100)
    plt.close()
    log = {
        "tag": tag,
        "encoder": encoder,
        "train_windows": sum(len(g) for g in train_graphs),
        "validation_windows": sum(len(g) for g in val_graphs),
        "epochs": EPOCHS,
        "chunk_length": CHUNK_LENGTH,
        "learning_rate": LEARNING_RATE,
        "random_seed": RANDOM_SEED,
        "loss_weights": {
            "dynamics": dynamics_weight,
            "infiltration": infiltration_weight,
            "stage": stage_weight,
            "infiltration_alpha": infiltration_alpha,
        },
        "training_loss": list(history.training_loss),
        "validation_loss": list(history.validation_loss),
        "best_epoch": history.best_epoch,
        "best_validation_loss": history.best_validation_loss,
        "checkpoint": f"python-ml/weights/{checkpoint_name}",
        "elapsed_seconds": elapsed,
    }
    (REPO_ROOT / "results" / f"phase32_{tag}_training_log.json").write_text(
        json.dumps(log, indent=2) + "\n", encoding="utf-8")
    return log


train_graphs_schema: tuple = ((), ())


def head_metrics(model, graphs, threshold: float = THRESHOLD):
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
    pred = (inf_prob >= threshold).float()
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
    malicious = stage_targets >= 0
    stage_pred = stage_prob[malicious].argmax(dim=-1)
    stage_targets = stage_targets[malicious]
    per_class, precisions, recalls, f1s = [], [], [], []
    for class_index in range(len(CLASS_NAMES)):
        mask = stage_targets == class_index
        support = int(mask.sum())
        if not support:
            per_class.append({"class": CLASS_NAMES[class_index], "support": 0,
                              "precision": 0.0, "recall": 0.0, "f1": 0.0})
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
    macro_p = sum(precisions) / len(precisions)
    return {
        "windows_evaluated": len(graphs) - 1,
        "infiltration": {"threshold": threshold, "tp": tp, "fp": fp, "fn": fn,
                         "tn": tn, "precision": precision, "recall": recall,
                         "f1": f1, "fpr": fpr, "auc_roc": auc_roc, "auc_pr": auc_pr,
                         "prob_mean": float(inf_prob.mean()),
                         "prob_std": float(inf_prob.std()),
                         "prob_max": float(inf_prob.max())},
        "stage": {"macro_precision": macro_p,
                  "macro_recall": sum(recalls) / len(recalls),
                  "macro_f1": sum(f1s) / len(f1s),
                  "malicious_windows": int(malicious.sum()),
                  "per_class": per_class},
    }


def _auc_roc(scores: list[float], labels: list[int]) -> float:
    positives = sum(labels)
    negatives = len(labels) - positives
    if not positives or not negatives:
        return 0.0
    concordant = 0.0
    positive_scores = [score for score, label in zip(scores, labels) if label]
    negative_scores = [score for score, label in zip(scores, labels) if not label]
    for positive in positive_scores:
        for negative in negative_scores:
            concordant += float(positive > negative)
            concordant += 0.5 * float(positive == negative)
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


def rollout_lead(model, graphs, window_seconds: int, k: int,
                 threshold: float = THRESHOLD):
    blocks = attack_blocks(graphs)
    picked = sorted(blocks, key=lambda b: b[1] - b[0], reverse=True)[:3]
    results = []
    with torch.no_grad():
        for attack_start, attack_end in picked:
            curve = []
            lead_windows = None
            for lead in range(LEAD_SEARCH, 0, -1):
                context_end = attack_start - lead
                if context_end < 1:
                    continue
                context = Batch.from_data_list(
                    list(graphs[max(0, context_end - 63):context_end]))
                states = model.encoder(context).unsqueeze(0)
                rollout = model.dynamics.rollout(states, steps=k)
                mean_prob = float(
                    model.heads(rollout)["infiltration_probability"].mean())
                curve.append({"lead_windows": lead, "mean_prob": mean_prob})
                if mean_prob >= threshold and lead_windows is None:
                    lead_windows = lead
            results.append({
                "attack_start_window": attack_start,
                "attack_end_window": attack_end,
                "attack_length_windows": attack_end - attack_start + 1,
                "threshold": threshold,
                "rollout_k": k,
                "lead_windows": lead_windows,
                "lead_seconds": (lead_windows * window_seconds
                                 if lead_windows is not None else None),
                "curve": sorted(curve, key=lambda row: -row["lead_windows"]),
            })
    return results


def evaluate_checkpoint(checkpoint_rel: str, graphs, window_seconds: int,
                        k: int, encoder: str, node_dim: int, edge_dim: int,
                        threshold: float = THRESHOLD):
    model = make_model(node_dim, edge_dim, encoder=encoder)
    payload = torch.load(REPO_ROOT / checkpoint_rel, map_location="cpu",
                         weights_only=False)
    model.load_state_dict(payload["model_state_dict"])
    model.eval()
    metrics = head_metrics(model, graphs, threshold=threshold)
    leads = rollout_lead(model, graphs, window_seconds, k, threshold=threshold)
    return {"checkpoint": checkpoint_rel, "rollout_k": k, "encoder": encoder,
            "val_windows": len(graphs), **metrics, "rollout_attacks": leads,
            "checkpoint_epoch": payload.get("epoch"),
            "checkpoint_val_loss": payload.get("validation_loss")}


def set_schema(node_features, edge_features) -> None:
    global train_graphs_schema
    train_graphs_schema = (node_features, edge_features)
