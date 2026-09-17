"""Phases 34-35: MITRE mapping cross-check and per-class error analysis."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))
sys.path.insert(0, str(REPO_ROOT / "python-ml" / "training"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from torch_geometric.data import Batch

from phase32_common import CLASS_NAMES, build_splits, make_model

MAPPING_TABLE = {
    "FTP-BruteForce": "INITIAL_ACCESS",
    "SSH-Bruteforce": "INITIAL_ACCESS",
    "DoS attacks-GoldenEye": "IMPACT",
    "DoS attacks-Slowloris": "IMPACT",
    "Infiltration": "INITIAL_ACCESS",
    "Bot": "COMMAND_AND_CONTROL",
}
CHECKPOINT = REPO_ROOT / "python-ml" / "weights" / "world_model_v1.pt"


def predictions_for_days(model, days) -> tuple[list[int], list[int]]:
    targets: list[int] = []
    predictions: list[int] = []
    with torch.no_grad():
        for graphs in days:
            for start in range(0, len(graphs) - 1, 512):
                piece = list(graphs[start:start + 513])
                batch = Batch.from_data_list(piece)
                states = model.encoder(batch).unsqueeze(0)
                predicted_states = model.dynamics(states[:, :-1])
                stage = model.heads(predicted_states)["stage_probability"][0]
                expected = torch.stack(
                    [graph.y_stage for graph in piece[1:]]
                ).squeeze(1)
                malicious = expected >= 0
                targets.extend(expected[malicious].tolist())
                predictions.extend(stage[malicious].argmax(dim=-1).tolist())
    return targets, predictions


def main() -> int:
    node, edge, _, in_val, _, _, split_report = build_splits()
    model = make_model(len(node), len(edge), encoder="gnn")
    payload = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    model.load_state_dict(payload["model_state_dict"])
    model.eval()
    targets, predictions = predictions_for_days(model, in_val)

    matrix = [[0 for _ in CLASS_NAMES] for _ in CLASS_NAMES]
    for expected, predicted in zip(targets, predictions):
        matrix[expected][predicted] += 1

    per_class = []
    for index, name in enumerate(CLASS_NAMES):
        support = sum(matrix[index])
        predicted_total = sum(row[index] for row in matrix)
        correct = matrix[index][index]
        precision = correct / predicted_total if predicted_total else 0.0
        recall = correct / support if support else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
        per_class.append({
            "class": name,
            "support": support,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "correct": correct,
        })

    observed = [row for row in per_class if row["support"]]
    accuracy = (
        sum(matrix[index][index] for index in range(len(CLASS_NAMES)))
        / len(targets) if targets else 0.0
    )
    macro_f1_observed = (
        sum(row["f1"] for row in observed) / len(observed) if observed else 0.0
    )
    confusions = []
    for actual_index, row in enumerate(matrix):
        for predicted_index, count in enumerate(row):
            if actual_index != predicted_index and count:
                confusions.append({
                    "actual": CLASS_NAMES[actual_index],
                    "predicted": CLASS_NAMES[predicted_index],
                    "count": count,
                })
    confusions.sort(key=lambda row: row["count"], reverse=True)

    phase34 = {
        "artifact_version": "kairos.phase34.v1",
        "manual_mapping_source": (
            "java-engine/src/main/java/com/networkwm/ingestion/"
            "IngestionService.java:cicIds2018Timelines"
        ),
        "manual_mapping": MAPPING_TABLE,
        "validation_split": split_report,
        "malicious_windows_evaluated": len(targets),
        "stage_accuracy": accuracy,
        "observed_class_macro_f1": macro_f1_observed,
        "all_six_class_macro_f1": (
            sum(row["f1"] for row in per_class) / len(CLASS_NAMES)
        ),
        "observed_classes": [row["class"] for row in observed],
        "unobserved_classes": [
            row["class"] for row in per_class if not row["support"]
        ],
        "result": (
            "weak_agreement" if accuracy < 0.5 else "moderate_or_better_agreement"
        ),
        "limitation": (
            "Only INITIAL_ACCESS, COMMAND_AND_CONTROL, and IMPACT occur in the "
            "selected CIC-IDS2018 contracts; the other three ATT&CK stages "
            "cannot be validated from this dataset."
        ),
    }
    phase35 = {
        "artifact_version": "kairos.phase35.v1",
        "class_names": CLASS_NAMES,
        "confusion_matrix_rows_actual_columns_predicted": matrix,
        "per_class": per_class,
        "largest_confusions": confusions[:10],
        "worst_supported_class": (
            min(observed, key=lambda row: row["f1"])["class"]
            if observed else None
        ),
        "diagnosis": (
            "Stage-head quality is substantially below the frozen logistic "
            "baseline. Error concentration and missing-class coverage must be "
            "resolved in Phases 36-38 before stage forecasts are demo-ready."
        ),
    }
    (REPO_ROOT / "results" / "phase34_mitre_crosscheck.json").write_text(
        json.dumps(phase34, indent=2) + "\n", encoding="utf-8"
    )
    (REPO_ROOT / "results" / "phase35_class_error_analysis.json").write_text(
        json.dumps(phase35, indent=2) + "\n", encoding="utf-8"
    )
    with (REPO_ROOT / "results" / "phase35_stage_confusion_matrix.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(["actual/predicted", *CLASS_NAMES])
        for name, row in zip(CLASS_NAMES, matrix):
            writer.writerow([name, *row])

    figure, axis = plt.subplots(figsize=(9, 7))
    image = axis.imshow(matrix, cmap="Blues")
    axis.set_xticks(range(len(CLASS_NAMES)), CLASS_NAMES, rotation=35, ha="right")
    axis.set_yticks(range(len(CLASS_NAMES)), CLASS_NAMES)
    axis.set_xlabel("Predicted stage")
    axis.set_ylabel("Manual timeline stage")
    axis.set_title("KAIROS Phase 35 — Stage-head confusion matrix")
    for row_index, row in enumerate(matrix):
        for column_index, count in enumerate(row):
            axis.text(column_index, row_index, str(count),
                      ha="center", va="center",
                      color="white" if count > max(map(max, matrix)) / 2 else "black")
    figure.colorbar(image, ax=axis)
    figure.tight_layout()
    figure.savefig(
        REPO_ROOT / "results" / "phase35_stage_confusion_heatmap.png", dpi=180
    )
    plt.close(figure)

    print(json.dumps({
        "stage_accuracy": accuracy,
        "observed_macro_f1": macro_f1_observed,
        "worst_supported_class": phase35["worst_supported_class"],
        "largest_confusion": confusions[0] if confusions else None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
