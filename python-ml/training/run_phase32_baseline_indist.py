"""Phase 32 baseline re-run on the IDENTICAL in-distribution split.

Uses only public functions from the frozen baseline module (no changes to
python-ml/baseline/): flatten the same four canonical 10s contracts, build
the same per-day first-80%-train / last-20%-val split the world-model
control uses (10,560 train / 2,642 val), fit the scaler on training rows
only, train both LRs, and evaluate the identical metric set.

Writes results/baseline_metrics_indist.json (+ _indist confusion CSVs) and
adds a "comparison" note object to results/baseline_metrics.json WITHOUT
touching any frozen metric value.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))

import numpy as np
import joblib
from sklearn.preprocessing import StandardScaler

from baseline.logistic_regression import (
    evaluate_baselines,
    flatten_graph_sequence,
    train_binary_baseline,
    train_stage_baseline,
    TemporalSplit,
)
from pipeline.graph_builder import load_graph_sequences
from phase32_common import resolve_contract_path

DAY_NAMES = ["day14.json", "day15.json", "day28.json", "day0302.json"]
TEST_FRACTION = 0.2


def main() -> int:
    contracts = [resolve_contract_path(name) for name in DAY_NAMES]
    day_counts = []
    for contract in contracts:
        with contract.open("r", encoding="utf-8") as handle:
            day_counts.append(len(json.load(handle)["windows"]))
    sequence = load_graph_sequences(contracts)
    dataset = flatten_graph_sequence(sequence)
    assert dataset.features.shape[0] == sum(day_counts)

    bounds, start = [], 0
    for count in day_counts:
        tail = math.ceil(count * TEST_FRACTION)
        bounds.append((start, start + count - tail, start + count))
        start += count
    train_idx = np.concatenate([np.arange(a, b) for a, b, _ in bounds])
    val_idx = np.concatenate([np.arange(b, c) for _, b, c in bounds])

    scaler = StandardScaler()
    x_train = scaler.fit_transform(dataset.features[train_idx])
    x_test = scaler.transform(dataset.features[val_idx])
    split = TemporalSplit(
        x_train=x_train,
        x_test=x_test,
        binary_train=dataset.infiltration_labels[train_idx],
        binary_test=dataset.infiltration_labels[val_idx],
        stage_train=dataset.stage_labels[train_idx],
        stage_test=dataset.stage_labels[val_idx],
        train_timestamps=dataset.timestamps[train_idx],
        test_timestamps=dataset.timestamps[val_idx],
        scaler=scaler,
    )
    binary = train_binary_baseline(split)
    stage = train_stage_baseline(split)
    metrics = evaluate_baselines(split, binary, stage)
    metrics["split"] = {
        "method": "per_day_final_20pct_time_holdout",
        "description": ("per-day first-80% train / last-20% val across "
                        "day14/day15/day28/day0302; identical windows to the "
                        "Phase 32 world-model in-distribution control"),
        "train_windows": int(x_train.shape[0]),
        "test_windows": int(x_test.shape[0]),
        "per_day": [
            {"day": day, "train": b - a, "val": c - b}
            for day, (a, b, c) in zip(DAY_NAMES, bounds)
        ],
    }
    metrics["artifact"] = {
        "version": "kairos.baseline.v1",
        "source_contract_version": sequence.contract_version,
        "random_state": 42,
        "note": ("Identical-split rerun of the frozen baseline logic for a "
                 "valid head-to-head with the Phase 32 world-model control. "
                 "Frozen baseline code untouched (git diff baseline-v1 -- "
                 "python-ml/baseline/ stays empty); canonical frozen numbers "
                 "remain in results/baseline_metrics.json."),
    }
    results_dir = REPO_ROOT / "results"
    weights_dir = REPO_ROOT / "python-ml" / "weights"
    joblib.dump(scaler, weights_dir / "baseline_scaler_indist.joblib")
    joblib.dump(binary.model, weights_dir / "baseline_binary_lr_indist.joblib")
    joblib.dump(stage.model, weights_dir / "baseline_stage_lr_indist.joblib")

    (results_dir / "baseline_metrics_indist.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    np.savetxt(
        results_dir / "baseline_binary_confusion_matrix_indist.csv",
        np.asarray(metrics["binary"]["confusion_matrix"], dtype=np.int64),
        delimiter=",", fmt="%d")
    np.savetxt(
        results_dir / "baseline_stage_confusion_matrix_indist.csv",
        np.asarray(metrics["stage"]["confusion_matrix"], dtype=np.int64),
        delimiter=",", fmt="%d")
    print(f"in-dist baseline: binary F1={metrics['binary']['f1']:.4f} "
          f"P={metrics['binary']['precision']:.4f} "
          f"R={metrics['binary']['recall']:.4f} "
          f"FPR={metrics['binary']['false_positive_rate']:.4f} "
          f"stage macro-F1={metrics['stage']['macro_f1']:.4f}", flush=True)

    frozen_path = results_dir / "baseline_metrics.json"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    frozen["comparison"] = {
        "in_distribution_validation_primary": {
            "split": (f"per-day final-20%-time holdout, {len(train_idx):,} train / "
                      f"{len(val_idx):,} val; results/baseline_metrics_indist.json"),
            "baseline_binary": {
                "f1": metrics["binary"]["f1"],
                "precision": metrics["binary"]["precision"],
                "recall": metrics["binary"]["recall"],
                "false_positive_rate":
                    metrics["binary"]["false_positive_rate"],
            },
            "baseline_stage_macro_f1": metrics["stage"]["macro_f1"],
            "world_model_winner_10s": "see results/phase32_completed.json",
        },
        "cross_day_generalization_stress_test_secondary": {
            "split": ("whole day0302 held out; world-model control in "
                      "results/phase32_step0.json; frozen baseline numbers "
                      "above use a joined final-20% holdout inside day0302"),
            "note": ("Cross-day numbers are a generalization stress test, "
                     "not the head-to-head metric set."),
        },
        "note": ("Baseline and world model now share one identical "
                 "in-distribution split for a valid head-to-head. Frozen "
                 "metric values above this key are unchanged."),
    }
    frozen_path.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")
    print("updated results/baseline_metrics.json comparison notes; "
          "frozen metric values unchanged", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
