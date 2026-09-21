"""Three-domain CTU-13 generalization evaluation.

Scenario 6 is development data, Scenario 11 is external validation for
threshold selection, and Scenario 12 is the untouched final holdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
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

from pipeline.ctu13_flow import FEATURE_NAMES, load_ctu13_windows
from pipeline.temporal_forecaster import temporal_feature_names, temporal_vector

SEED = 42


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _samples(windows, history: int, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    rows, labels = [], []
    for current in range(history - 1, len(windows.features) - horizon):
        rows.append(temporal_vector(
            windows.features[current - history + 1:current + 1]
        ))
        labels.append(int(windows.malicious[current + horizon]))
    return np.asarray(rows, dtype=np.float64), np.asarray(labels, dtype=np.int64)


def _metrics(labels: np.ndarray, probability: np.ndarray,
             threshold: float = 0.5) -> dict:
    prediction = (probability >= threshold).astype(np.int64)
    matrix = confusion_matrix(labels, prediction, labels=[0, 1])
    tn, fp, fn, tp = matrix.ravel()
    precision, recall, f1, _ = precision_recall_fscore_support(
        labels, prediction, average="binary", zero_division=0
    )
    return {
        "threshold": threshold,
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "fpr": float(fp / (fp + tn)) if fp + tn else 0.0,
        "roc_auc": float(roc_auc_score(labels, probability))
        if np.unique(labels).size == 2 else None,
        "average_precision": float(average_precision_score(labels, probability))
        if np.unique(labels).size == 2 else None,
        "confusion_matrix": matrix.tolist(),
        "support": int(labels.size),
        "positive_support": int(labels.sum()),
    }


def _select_threshold(labels: np.ndarray, probability: np.ndarray) -> dict:
    candidates = np.linspace(0.05, 0.99, 189)
    rows = [_metrics(labels, probability, float(value))
            for value in candidates]
    winner = max(
        rows,
        key=lambda row: (
            row["f1"], -row["fpr"], row["recall"],
            -abs(row["threshold"] - 0.5),
        ),
    )
    return {
        "source": "CTU-13 Scenario 11 external validation only",
        "objective": "maximum F1, then lower FPR and higher recall",
        "threshold": winner["threshold"],
        "metrics": winner,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--development",
        type=Path,
        default=REPO_ROOT / "data/raw/ctu13_scenario6"
        / "capture20110816.binetflow",
    )
    parser.add_argument(
        "--validation",
        type=Path,
        default=REPO_ROOT / "data/raw/ctu13_scenario11"
        / "capture20110818-2.binetflow",
    )
    parser.add_argument(
        "--holdout",
        type=Path,
        default=REPO_ROOT / "data/raw/ctu13_scenario12"
        / "capture20110819.binetflow",
    )
    parser.add_argument("--history", type=int, default=6)
    parser.add_argument("--horizons", type=int, nargs="+", default=[1, 3, 6])
    parser.add_argument("--trees", type=int, default=200)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "results" / "ctu13_unseen_scenario12.json",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=REPO_ROOT / "python-ml" / "weights"
        / "ctu13_s6_s11_to_s12_forecaster.joblib",
    )
    args = parser.parse_args()

    development = load_ctu13_windows(args.development)
    validation = load_ctu13_windows(args.validation)
    holdout = load_ctu13_windows(args.holdout)
    results = {}
    models = {}
    for horizon in args.horizons:
        train_x, train_y = _samples(development, args.history, horizon)
        validation_x, validation_y = _samples(
            validation, args.history, horizon
        )
        test_x, test_y = _samples(holdout, args.history, horizon)
        if any(
            np.unique(labels).size < 2
            for labels in (train_y, validation_y, test_y)
        ):
            raise ValueError(
                f"horizon {horizon} needs benign and malicious samples "
                "in development, validation, and holdout"
            )
        baseline = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                class_weight="balanced", max_iter=2500, random_state=SEED
            ),
        )
        kairos = ExtraTreesClassifier(
            n_estimators=args.trees,
            max_features="sqrt",
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=SEED,
            n_jobs=-1,
        )
        baseline.fit(train_x, train_y)
        kairos.fit(train_x, train_y)
        baseline_selection = _select_threshold(
            validation_y, baseline.predict_proba(validation_x)[:, 1]
        )
        kairos_selection = _select_threshold(
            validation_y, kairos.predict_proba(validation_x)[:, 1]
        )

        final_x = np.concatenate((train_x, validation_x), axis=0)
        final_y = np.concatenate((train_y, validation_y), axis=0)
        baseline.fit(final_x, final_y)
        kairos.fit(final_x, final_y)
        baseline_metrics = _metrics(
            test_y,
            baseline.predict_proba(test_x)[:, 1],
            baseline_selection["threshold"],
        )
        kairos_metrics = _metrics(
            test_y,
            kairos.predict_proba(test_x)[:, 1],
            kairos_selection["threshold"],
        )
        results[str(horizon)] = {
            "horizon_windows": horizon,
            "horizon_seconds": horizon * development.window_seconds,
            "development_samples": int(train_y.size),
            "external_validation_samples": int(validation_y.size),
            "final_fit_samples": int(final_y.size),
            "holdout_samples": int(test_y.size),
            "development_positive": int(train_y.sum()),
            "holdout_positive": int(test_y.sum()),
            "logistic_regression": {
                "threshold_selection": baseline_selection,
                "holdout": baseline_metrics,
            },
            "kairos_temporal_head": {
                "threshold_selection": kairos_selection,
                "holdout": kairos_metrics,
            },
            "improvement": {
                "f1_absolute": kairos_metrics["f1"] - baseline_metrics["f1"],
                "precision_absolute": (
                    kairos_metrics["precision"] - baseline_metrics["precision"]
                ),
                "recall_absolute": (
                    kairos_metrics["recall"] - baseline_metrics["recall"]
                ),
                "fpr_absolute_reduction": (
                    baseline_metrics["fpr"] - kairos_metrics["fpr"]
                ),
            },
        }
        models[str(horizon)] = kairos
        print(
            f"h={horizon}: KAIROS F1={kairos_metrics['f1']:.4f} "
            f"LR F1={baseline_metrics['f1']:.4f}",
            flush=True,
        )

    artifact = {
        "artifact_version": "kairos.ctu13-zero-shot.v1",
        "estimator": {
            "trees": args.trees,
            "random_seed": SEED,
            "temporal_head": (
                "ExtraTreesClassifier(max_features=sqrt, "
                "min_samples_leaf=2, class_weight=balanced_subsample)"
            ),
            "baseline": "LogisticRegression(class_weight=balanced)+StandardScaler",
        },
        "protocol": {
            "development": "CTU-13 Scenario 6 / DonBot",
            "external_validation": "CTU-13 Scenario 11 / RBot",
            "untouched_holdout": "CTU-13 Scenario 12 / NSIS.ay",
            "task": "predict From-Botnet window at t+h from observations through t",
            "threshold": "selected on Scenario 11 external validation",
            "threshold_selection": (
                "Scenario 6 fits provisional model; Scenario 11 selects "
                "threshold; final model refits on Scenario 6 + Scenario 11; "
                "Scenario 12 remains untouched until final scoring"
            ),
            "stage_metrics": None,
            "stage_note": (
                "Official CTU bidirectional labels identify From-Botnet but do "
                "not provide MITRE stages; stage metrics are not fabricated."
            ),
            "feature_levels": {
                "flow": [
                    "duration", "flow count", "unique endpoints",
                    "protocol", "direction", "ports",
                ],
                "packet_observable": [
                    "packet count", "byte count", "source/destination bytes",
                    "bytes per packet", "bytes/packets per second",
                ],
            },
            "leakage_controls": [
                "Scenario 12 excluded from training, selection, and preprocessing",
                "threshold selected on Scenario 11; no Scenario 12 calibration",
                "backward-only histories",
                "source sequences never concatenated",
            ],
        },
        "feature_names": list(temporal_feature_names(FEATURE_NAMES)),
        "sources": {
            "scenario6": {
                "path": str(args.development.relative_to(REPO_ROOT)),
                "sha256": _hash(args.development),
                "rows": development.rows,
                "windows": int(len(development.features)),
                "malicious_windows": int(development.malicious.sum()),
            },
            "scenario11": {
                "path": str(args.validation.relative_to(REPO_ROOT)),
                "sha256": _hash(args.validation),
                "role": "external validation and threshold selection",
                "rows": validation.rows,
                "windows": int(len(validation.features)),
                "malicious_windows": int(validation.malicious.sum()),
            },
            "scenario12": {
                "path": str(args.holdout.relative_to(REPO_ROOT)),
                "sha256": _hash(args.holdout),
                "role": "untouched final holdout",
                "rows": holdout.rows,
                "windows": int(len(holdout.features)),
                "malicious_windows": int(holdout.malicious.sum()),
            },
        },
        "horizons": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2) + "\n")
    args.weights.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "artifact_version": "kairos.ctu13-s6-s11-to-s12-forecaster.v1",
        "history_windows": args.history,
        "window_seconds": development.window_seconds,
        "feature_names": list(temporal_feature_names(FEATURE_NAMES)),
        "models_by_horizon": models,
    }, args.weights)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
