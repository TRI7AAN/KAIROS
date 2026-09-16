"""Deterministic non-temporal logistic-regression baselines for KAIROS graphs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.preprocessing import StandardScaler

from pipeline.graph_builder import LoadedGraphSequence, STAGE_TO_INDEX

MALICIOUS_STAGES = tuple(
    stage for stage, index in sorted(STAGE_TO_INDEX.items(), key=lambda item: item[1])
    if index >= 0
)
STATISTICS = ("mean", "std", "max", "sum")


@dataclass(frozen=True)
class FlattenedDataset:
    features: np.ndarray
    feature_names: tuple[str, ...]
    timestamps: np.ndarray
    infiltration_labels: np.ndarray
    stage_labels: np.ndarray


@dataclass(frozen=True)
class TemporalSplit:
    x_train: np.ndarray
    x_test: np.ndarray
    binary_train: np.ndarray
    binary_test: np.ndarray
    stage_train: np.ndarray
    stage_test: np.ndarray
    train_timestamps: np.ndarray
    test_timestamps: np.ndarray
    scaler: StandardScaler


@dataclass(frozen=True)
class FittedBaseline:
    model: LogisticRegression
    training_seconds: float
    converged: bool
    iterations: tuple[int, ...]


@dataclass(frozen=True)
class BaselineRun:
    dataset: FlattenedDataset
    split: TemporalSplit
    binary: FittedBaseline
    stage: FittedBaseline
    metrics: dict


def flatten_graph_sequence(sequence: LoadedGraphSequence) -> FlattenedDataset:
    """Aggregate each graph into one fixed-width, non-temporal feature row."""
    feature_names = _flattened_feature_names(sequence)
    rows: list[list[float]] = []
    timestamps: list[float] = []
    binary_labels: list[int] = []
    stage_labels: list[int] = []

    for graph in sequence.graphs:
        row = [
            float(graph.x.shape[0]),
            float(graph.edge_index.shape[1]),
            float(graph.window_duration_seconds.item()),
            float(graph.topology_available),
        ]
        row.extend(_summary_values(graph.x.detach().cpu().numpy()))
        row.extend(_summary_values(graph.edge_attr.detach().cpu().numpy()))
        rows.append(row)
        timestamps.append(float(graph.window_start_epoch.item()))
        binary_labels.append(int(graph.y_infiltration.item()))
        stage_labels.append(int(graph.y_stage.item()))

    features = np.asarray(rows, dtype=np.float64)
    if not rows:
        features = np.empty((0, len(feature_names)), dtype=np.float64)
    timestamps_array = np.asarray(timestamps, dtype=np.float64)
    if timestamps_array.size > 1 and np.any(np.diff(timestamps_array) < 0):
        raise ValueError("graph sequence must be time ordered")
    if not np.isfinite(features).all():
        raise ValueError("flattened features must be finite")
    return FlattenedDataset(
        features=features,
        feature_names=feature_names,
        timestamps=timestamps_array,
        infiltration_labels=np.asarray(binary_labels, dtype=np.int64),
        stage_labels=np.asarray(stage_labels, dtype=np.int64),
    )


def time_based_split(
    dataset: FlattenedDataset,
    *,
    test_fraction: float = 0.2,
) -> TemporalSplit:
    """Split strictly by time and fit scaling statistics on training rows only."""
    if not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction must be between zero and one")
    row_count = dataset.features.shape[0]
    if row_count < 2:
        raise ValueError("at least two ordered windows are required")
    test_count = max(1, int(np.ceil(row_count * test_fraction)))
    split_index = row_count - test_count
    if split_index < 1:
        raise ValueError("time split leaves no training windows")

    raw_train = dataset.features[:split_index]
    raw_test = dataset.features[split_index:]
    scaler = StandardScaler()
    x_train = scaler.fit_transform(raw_train)
    x_test = scaler.transform(raw_test)
    return TemporalSplit(
        x_train=x_train,
        x_test=x_test,
        binary_train=dataset.infiltration_labels[:split_index],
        binary_test=dataset.infiltration_labels[split_index:],
        stage_train=dataset.stage_labels[:split_index],
        stage_test=dataset.stage_labels[split_index:],
        train_timestamps=dataset.timestamps[:split_index],
        test_timestamps=dataset.timestamps[split_index:],
        scaler=scaler,
    )


def train_binary_baseline(
    split: TemporalSplit,
    *,
    max_iter: int = 1000,
    random_state: int = 42,
) -> FittedBaseline:
    """Fit infiltration-vs-benign logistic regression."""
    return _fit_logistic(
        split.x_train,
        split.binary_train,
        max_iter=max_iter,
        random_state=random_state,
    )


def train_stage_baseline(
    split: TemporalSplit,
    *,
    max_iter: int = 1000,
    random_state: int = 42,
) -> FittedBaseline:
    """Fit six-way stage LR using malicious windows; benign stage -1 is masked."""
    mask = split.stage_train >= 0
    return _fit_logistic(
        split.x_train[mask],
        split.stage_train[mask],
        max_iter=max_iter,
        random_state=random_state,
    )


def evaluate_baselines(
    split: TemporalSplit,
    binary: FittedBaseline,
    stage: FittedBaseline,
) -> dict:
    """Calculate reproducible binary and stage metrics on the future holdout."""
    binary_prediction = binary.model.predict(split.x_test)
    binary_precision, binary_recall, binary_f1, _ = precision_recall_fscore_support(
        split.binary_test,
        binary_prediction,
        average="binary",
        zero_division=0,
    )
    binary_matrix = confusion_matrix(
        split.binary_test, binary_prediction, labels=[0, 1]
    )
    tn, fp, _, _ = binary_matrix.ravel()
    false_positive_rate = float(fp / (fp + tn)) if fp + tn else 0.0

    stage_mask = split.stage_test >= 0
    if np.any(stage_mask):
        stage_prediction = stage.model.predict(split.x_test[stage_mask])
        stage_precision, stage_recall, stage_f1, _ = precision_recall_fscore_support(
            split.stage_test[stage_mask],
            stage_prediction,
            labels=list(range(len(MALICIOUS_STAGES))),
            average="macro",
            zero_division=0,
        )
        stage_matrix = confusion_matrix(
            split.stage_test[stage_mask],
            stage_prediction,
            labels=list(range(len(MALICIOUS_STAGES))),
        )
        stage_evaluated = int(stage_mask.sum())
    else:
        stage_precision = stage_recall = stage_f1 = 0.0
        stage_matrix = np.zeros(
            (len(MALICIOUS_STAGES), len(MALICIOUS_STAGES)), dtype=np.int64
        )
        stage_evaluated = 0

    return {
        "split": {
            "method": "strict_time_order",
            "train_windows": int(split.x_train.shape[0]),
            "test_windows": int(split.x_test.shape[0]),
            "train_end_epoch": float(split.train_timestamps[-1]),
            "test_start_epoch": float(split.test_timestamps[0]),
        },
        "binary": {
            "precision": float(binary_precision),
            "recall": float(binary_recall),
            "f1": float(binary_f1),
            "false_positive_rate": false_positive_rate,
            "confusion_matrix": binary_matrix.tolist(),
            "early_warning_lead_time_seconds": None,
            "early_warning_note": "Not applicable to a non-temporal baseline.",
            "training_seconds": binary.training_seconds,
            "converged": binary.converged,
            "iterations": list(binary.iterations),
        },
        "stage": {
            "class_names": list(MALICIOUS_STAGES),
            "evaluated_malicious_windows": stage_evaluated,
            "macro_precision": float(stage_precision),
            "macro_recall": float(stage_recall),
            "macro_f1": float(stage_f1),
            "confusion_matrix": stage_matrix.tolist(),
            "training_seconds": stage.training_seconds,
            "converged": stage.converged,
            "iterations": list(stage.iterations),
        },
    }


def run_baselines(
    sequence: LoadedGraphSequence,
    *,
    results_directory: str | Path,
    weights_directory: str | Path,
    test_fraction: float = 0.2,
    max_iter: int = 1000,
    random_state: int = 42,
) -> BaselineRun:
    """Run Phases 12-16 and persist models, scaler, metrics, and matrices."""
    dataset = flatten_graph_sequence(sequence)
    split = time_based_split(dataset, test_fraction=test_fraction)
    binary = train_binary_baseline(
        split, max_iter=max_iter, random_state=random_state
    )
    stage = train_stage_baseline(
        split, max_iter=max_iter, random_state=random_state
    )
    metrics = evaluate_baselines(split, binary, stage)
    metrics["artifact"] = {
        "version": "kairos.baseline.v1",
        "source_contract_version": sequence.contract_version,
        "feature_names": list(dataset.feature_names),
        "random_state": random_state,
    }

    results_path = Path(results_directory)
    weights_path = Path(weights_directory)
    results_path.mkdir(parents=True, exist_ok=True)
    weights_path.mkdir(parents=True, exist_ok=True)
    (results_path / "baseline_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    np.savetxt(
        results_path / "baseline_binary_confusion_matrix.csv",
        np.asarray(metrics["binary"]["confusion_matrix"], dtype=np.int64),
        delimiter=",",
        fmt="%d",
    )
    np.savetxt(
        results_path / "baseline_stage_confusion_matrix.csv",
        np.asarray(metrics["stage"]["confusion_matrix"], dtype=np.int64),
        delimiter=",",
        fmt="%d",
    )
    joblib.dump(split.scaler, weights_path / "baseline_scaler.joblib")
    joblib.dump(binary.model, weights_path / "baseline_binary_lr.joblib")
    joblib.dump(stage.model, weights_path / "baseline_stage_lr.joblib")
    return BaselineRun(dataset, split, binary, stage, metrics)


def _flattened_feature_names(
    sequence: LoadedGraphSequence,
) -> tuple[str, ...]:
    names = ["node_count", "edge_count", "window_duration_seconds", "topology_available"]
    for prefix, schema in (
        ("node", sequence.node_feature_names),
        ("edge", sequence.edge_feature_names),
    ):
        for feature in schema:
            names.extend(f"{prefix}.{feature}.{stat}" for stat in STATISTICS)
    return tuple(names)


def _summary_values(values: np.ndarray) -> list[float]:
    if values.ndim != 2:
        raise ValueError("graph feature tensors must be two-dimensional")
    if values.shape[1] == 0:
        return []
    if values.shape[0] == 0:
        return [0.0] * (values.shape[1] * len(STATISTICS))
    summary: list[float] = []
    for column in values.T:
        summary.extend(
            [
                float(np.mean(column)),
                float(np.std(column)),
                float(np.max(column)),
                float(np.sum(column)),
            ]
        )
    return summary


def _fit_logistic(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    max_iter: int,
    random_state: int,
) -> FittedBaseline:
    classes = np.unique(labels)
    if features.shape[0] == 0 or classes.size < 2:
        raise ValueError("logistic regression requires at least two training classes")
    model = LogisticRegression(
        class_weight="balanced",
        max_iter=max_iter,
        random_state=random_state,
        solver="lbfgs",
    )
    started = time.perf_counter()
    model.fit(features, labels)
    training_seconds = time.perf_counter() - started
    iterations = tuple(int(value) for value in model.n_iter_)
    return FittedBaseline(
        model=model,
        training_seconds=training_seconds,
        converged=all(value < max_iter for value in iterations),
        iterations=iterations,
    )
