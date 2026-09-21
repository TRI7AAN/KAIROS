"""Leakage-controlled, task-aligned benchmark for SIH PS 26153.

Both the logistic baseline and the KAIROS nonlinear forecast head receive the
same backward-only temporal feature vector and predict the same future window.
The final 20% of every source day is an untouched chronological test. The
first 80% is development data; decision thresholds are selected from
leave-one-source-day-out predictions inside development data only.

The feature vector contains graph summaries from the current and previous
windows (current, mean, std, delta, mean absolute velocity). No future value or
label is included. This runner intentionally avoids the historical apples-to-
oranges comparison between a current-window baseline and a next-window model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.base import clone
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))
sys.path.insert(0, str(REPO_ROOT / "python-ml" / "training"))

from baseline.logistic_regression import flatten_graph_sequence
from phase32_common import (
    CLASS_NAMES,
    DAY_NAMES,
    resolve_contract_path,
)
from pipeline.graph_builder import load_graph_sequence
from pipeline.temporal_forecaster import (
    temporal_feature_names,
    temporal_vector,
)

SEED = 42
WINDOW_SECONDS = 10
DEVELOPMENT_FRACTION = 0.80


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _development_boundary(size: int) -> int:
    boundary = int(size * DEVELOPMENT_FRACTION)
    if boundary < 2 or boundary >= size:
        raise ValueError(f"sequence of {size} windows is too short for 80/20")
    return boundary


def build_samples(days: list[dict], *, history: int, horizon: int) -> dict:
    if history < 2:
        raise ValueError("history must be at least two windows")
    if horizon < 1:
        raise ValueError("horizon must be positive")

    parts = {
        split: {"x": [], "binary": [], "stage": [], "day": [],
                "current_index": [], "target_index": []}
        for split in ("development", "test")
    }
    feature_names: tuple[str, ...] | None = None
    split_report: dict[str, dict] = {}

    for day in days:
        dataset = flatten_graph_sequence(day["sequence"])
        if feature_names is None:
            feature_names = temporal_feature_names(dataset.feature_names)
        elif feature_names != temporal_feature_names(dataset.feature_names):
            raise ValueError("feature schemas differ across source days")

        size = dataset.features.shape[0]
        development_end = _development_boundary(size)
        split_report[day["name"]] = {
            "windows": size,
            "development_target_range": [
                history - 1 + horizon, development_end - 1
            ],
            "test_target_range": [development_end, size - 1],
        }
        for current in range(history - 1, size - horizon):
            target = current + horizon
            split = "development" if target < development_end else "test"
            block = dataset.features[current - history + 1:current + 1]
            part = parts[split]
            part["x"].append(temporal_vector(block))
            part["binary"].append(int(dataset.infiltration_labels[target]))
            part["stage"].append(int(dataset.stage_labels[target]))
            part["day"].append(day["name"])
            part["current_index"].append(current)
            part["target_index"].append(target)

    result = {"feature_names": feature_names or (), "split_report": split_report}
    for split, part in parts.items():
        result[split] = {
            "x": np.asarray(part["x"], dtype=np.float64),
            "binary": np.asarray(part["binary"], dtype=np.int64),
            "stage": np.asarray(part["stage"], dtype=np.int64),
            "day": np.asarray(part["day"], dtype=object),
            "current_index": np.asarray(part["current_index"], dtype=np.int64),
            "target_index": np.asarray(part["target_index"], dtype=np.int64),
        }
    return result


def _binary_metrics(labels: np.ndarray, probabilities: np.ndarray,
                    threshold: float) -> dict:
    prediction = (probabilities >= threshold).astype(np.int64)
    matrix = confusion_matrix(labels, prediction, labels=[0, 1])
    tn, fp, fn, tp = matrix.ravel()
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, prediction, average="binary", zero_division=0
    )
    return {
        "threshold": float(threshold),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "fpr": float(fp / (fp + tn)) if fp + tn else 0.0,
        "roc_auc": float(roc_auc_score(labels, probabilities))
        if np.unique(labels).size == 2 else None,
        "average_precision": float(average_precision_score(labels, probabilities))
        if np.unique(labels).size == 2 else None,
        "confusion_matrix": matrix.tolist(),
        "support": int(labels.size),
        "positive_support": int(labels.sum()),
    }


def _select_threshold(labels: np.ndarray, probabilities: np.ndarray) -> dict:
    candidates = np.unique(np.concatenate((
        np.linspace(0.05, 0.95, 181),
        np.quantile(probabilities, np.linspace(0.01, 0.99, 99)),
    )))
    rows = [_binary_metrics(labels, probabilities, float(value))
            for value in candidates]
    winner = max(rows, key=lambda row: (
        row["f1"], -row["fpr"], row["recall"], -abs(row["threshold"] - 0.5)
    ))
    return {
        "selection_split": "leave-one-source-day-out development predictions",
        "objective": "maximum F1; lower FPR, higher recall, then proximity to 0.5",
        "threshold": winner["threshold"],
        "calibration_metrics": winner,
    }


def _stage_metrics(labels: np.ndarray, predictions: np.ndarray) -> dict:
    observed = sorted(int(value) for value in np.unique(labels) if value >= 0)
    if not observed:
        return {
            "observed_classes": [],
            "observed_macro_f1": 0.0,
            "six_class_macro_f1": 0.0,
            "support": 0,
        }
    precision, recall, f1, support = precision_recall_fscore_support(
        labels, predictions, labels=list(range(len(CLASS_NAMES))),
        zero_division=0,
    )
    rows = [
        {
            "class": CLASS_NAMES[index],
            "support": int(support[index]),
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
        }
        for index in range(len(CLASS_NAMES))
    ]
    return {
        "observed_classes": [CLASS_NAMES[index] for index in observed],
        "observed_macro_f1": float(np.mean(f1[observed])),
        "six_class_macro_f1": float(np.mean(f1)),
        "support": int(labels.size),
        "per_class": rows,
        "confusion_matrix": confusion_matrix(
            labels, predictions, labels=list(range(len(CLASS_NAMES)))
        ).tolist(),
    }


def _binary_estimators(trees: int) -> dict:
    return {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(
                class_weight="balanced", max_iter=2500, random_state=SEED
            ),
        ),
        "kairos_temporal_head": ExtraTreesClassifier(
            n_estimators=trees,
            max_features="sqrt",
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=SEED,
            n_jobs=-1,
        ),
    }


def _stage_estimators(trees: int) -> dict:
    return {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(
                class_weight="balanced", max_iter=2500, random_state=SEED
            ),
        ),
        "kairos_temporal_head": ExtraTreesClassifier(
            n_estimators=trees,
            max_features="sqrt",
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=SEED,
            n_jobs=-1,
        ),
    }


def _out_of_day_probabilities(prototype, development: dict) -> np.ndarray:
    """Generate calibration probabilities without scoring a fitted row on itself."""
    probabilities = np.full(development["binary"].shape, np.nan, dtype=np.float64)
    for held_day in sorted(np.unique(development["day"])):
        held_mask = development["day"] == held_day
        fit_mask = ~held_mask
        if np.unique(development["binary"][fit_mask]).size < 2:
            raise ValueError(
                f"development fold excluding {held_day} has fewer than two classes"
            )
        model = clone(prototype)
        model.fit(
            development["x"][fit_mask], development["binary"][fit_mask]
        )
        probabilities[held_mask] = model.predict_proba(
            development["x"][held_mask]
        )[:, 1]
    if not np.isfinite(probabilities).all():
        raise ValueError("out-of-day calibration produced non-finite probabilities")
    return probabilities


def _fit_models(samples: dict, *, trees: int) -> dict:
    development = samples["development"]
    test = samples["test"]

    prototypes = _binary_estimators(trees)
    selections = {}
    for name, prototype in prototypes.items():
        out_of_day = _out_of_day_probabilities(prototype, development)
        selections[name] = _select_threshold(
            development["binary"], out_of_day
        )

    fitted = {}
    durations = {}
    binary_rows = {}
    for name, prototype in prototypes.items():
        model = clone(prototype)
        started = time.monotonic()
        model.fit(development["x"], development["binary"])
        durations[name] = time.monotonic() - started
        fitted[name] = model
        test_probability = model.predict_proba(test["x"])[:, 1]
        binary_rows[name] = {
            "training_seconds": durations[name],
            "threshold_selection": selections[name],
            "test_at_calibrated_threshold": _binary_metrics(
                test["binary"], test_probability,
                selections[name]["threshold"],
            ),
            "test_at_fixed_0_5": _binary_metrics(
                test["binary"], test_probability, 0.5
            ),
        }

    stage_development_mask = development["stage"] >= 0
    stage_test_mask = test["stage"] >= 0
    stage_models = {}
    stage_rows = {}
    for name, prototype in _stage_estimators(trees).items():
        model = clone(prototype)
        model.fit(
            development["x"][stage_development_mask],
            development["stage"][stage_development_mask],
        )
        stage_models[name] = model
        stage_rows[name] = _stage_metrics(
            test["stage"][stage_test_mask],
            model.predict(test["x"][stage_test_mask]),
        )

    return {
        "binary": binary_rows,
        "stage": stage_rows,
        "models": {
            "binary": fitted,
            "stage": stage_models,
        },
    }


def _summarize_improvement(result: dict) -> dict:
    baseline = result["binary"]["logistic_regression"][
        "test_at_calibrated_threshold"
    ]
    kairos = result["binary"]["kairos_temporal_head"][
        "test_at_calibrated_threshold"
    ]
    baseline_stage = result["stage"]["logistic_regression"]
    kairos_stage = result["stage"]["kairos_temporal_head"]
    return {
        "f1_absolute": kairos["f1"] - baseline["f1"],
        "precision_absolute": kairos["precision"] - baseline["precision"],
        "recall_absolute": kairos["recall"] - baseline["recall"],
        "fpr_absolute_reduction": baseline["fpr"] - kairos["fpr"],
        "roc_auc_absolute": (
            kairos["roc_auc"] - baseline["roc_auc"]
            if kairos["roc_auc"] is not None and baseline["roc_auc"] is not None
            else None
        ),
        "observed_stage_macro_f1_absolute": (
            kairos_stage["observed_macro_f1"]
            - baseline_stage["observed_macro_f1"]
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", type=int, default=6)
    parser.add_argument("--horizons", type=int, nargs="+", default=[1, 3, 6])
    parser.add_argument("--trees", type=int, default=150)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "results" / "ps_aligned_benchmark.json",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=REPO_ROOT / "python-ml" / "weights"
        / "ps_aligned_temporal_forecaster.joblib",
    )
    args = parser.parse_args()

    source_days = []
    sources = []
    for name in DAY_NAMES:
        path = resolve_contract_path(name)
        source_days.append({
            "name": name,
            "path": path,
            "sequence": load_graph_sequence(path),
        })
        sources.append({
            "name": name,
            "path": str(path.relative_to(REPO_ROOT)),
            "sha256": _sha256(path),
        })

    horizons = {}
    persisted_models = {}
    feature_names = None
    for horizon in args.horizons:
        samples = build_samples(
            source_days, history=args.history, horizon=horizon
        )
        fitted = _fit_models(samples, trees=args.trees)
        improvement = _summarize_improvement(fitted)
        horizons[str(horizon)] = {
            "horizon_windows": horizon,
            "horizon_seconds": horizon * WINDOW_SECONDS,
            "history_windows": args.history,
            "history_seconds": args.history * WINDOW_SECONDS,
            "split_report": samples["split_report"],
            "sample_counts": {
                split: int(samples[split]["x"].shape[0])
                for split in ("development", "test")
            },
            "feature_count": int(samples["development"]["x"].shape[1]),
            "binary": fitted["binary"],
            "stage": fitted["stage"],
            "improvement": improvement,
        }
        persisted_models[str(horizon)] = {
            "binary": fitted["models"]["binary"]["kairos_temporal_head"],
            "stage": fitted["models"]["stage"]["kairos_temporal_head"],
            "threshold": fitted["binary"]["kairos_temporal_head"][
                "threshold_selection"
            ]["threshold"],
        }
        feature_names = samples["feature_names"]
        metric = horizons[str(horizon)]["binary"]["kairos_temporal_head"][
            "test_at_calibrated_threshold"
        ]
        baseline = horizons[str(horizon)]["binary"]["logistic_regression"][
            "test_at_calibrated_threshold"
        ]
        print(
            f"h={horizon} ({horizon * WINDOW_SECONDS}s): "
            f"KAIROS F1={metric['f1']:.4f} FPR={metric['fpr']:.4f}; "
            f"LR F1={baseline['f1']:.4f} FPR={baseline['fpr']:.4f}",
            flush=True,
        )

    artifact = {
        "artifact_version": "kairos.ps-aligned-benchmark.v1",
        "random_seed": SEED,
        "window_seconds": WINDOW_SECONDS,
        "estimator": {
            "trees": args.trees,
            "history_windows": args.history,
            "horizons": args.horizons,
            "binary": "ExtraTreesClassifier(n_estimators=args.trees,max_features=sqrt,min_samples_leaf=2,class_weight=balanced_subsample,random_state=42)",
            "baseline": "LogisticRegression(class_weight=balanced,max_iter=2500)+StandardScaler",
        },
        "protocol": {
            "task": "predict infiltration/stage at t+h using observations through t",
            "features": "identical backward-only temporal graph summaries for both models",
            "split": "per-day first 80% development / final 20% untouched chronological test",
            "selection": "model fixed in code; threshold from leave-one-source-day-out development predictions",
            "leakage_controls": [
                "future window values and labels excluded from features",
                "each calibration scaler/model fitted without its held-out source day",
                "final scaler/model fitted on development data only",
                "test excluded from model and threshold selection",
                "source sequence boundaries never crossed",
            ],
            "baseline": "class-balanced logistic regression",
            "kairos_head": "separate class-balanced ExtraTrees temporal forecasting component",
            "caveat": (
                "This discriminative head complements the GNN-Transformer world "
                "model; it does not replace transition-state rollout evaluation. "
                "Development prevalence 7.7% vs test 38.5% makes absolute thresholds "
                "prevalence-sensitive; stage 1.0 reflects near-trivial CIC separability. "
                "CTU canonical row is h1/10s; h3/h6 regress and are disclosed in phase-status."
            ),
        },
        "sources": sources,
        "horizons": horizons,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    args.weights.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "artifact_version": "kairos.ps-aligned-temporal-forecaster.v1",
        "history_windows": args.history,
        "window_seconds": WINDOW_SECONDS,
        "feature_names": feature_names,
        "models_by_horizon": persisted_models,
        "source_sha256": {row["name"]: row["sha256"] for row in sources},
    }, args.weights)
    print(f"wrote {args.output}", flush=True)
    print(f"wrote {args.weights}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
