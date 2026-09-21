"""Generate the canonical judge-facing benchmark table from result artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def _load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text())


def main() -> int:
    aligned = _load("ps_aligned_benchmark.json")
    unseen = _load("ctu13_unseen_scenario12.json")
    legacy = _load("phase32_completed.json")
    primary = aligned["horizons"]["6"]
    ctu = unseen["horizons"]["1"]
    lr = primary["binary"]["logistic_regression"][
        "test_at_calibrated_threshold"
    ]
    kairos = primary["binary"]["kairos_temporal_head"][
        "test_at_calibrated_threshold"
    ]
    ctu_lr = ctu["logistic_regression"]["holdout"]
    ctu_kairos = ctu["kairos_temporal_head"]["holdout"]

    rows = [
        {
            "model": "LogisticRegression",
            "role": "required_same-feature_baseline",
            "split": "CIC per-day final-20% untouched; 60s future label",
            **_binary(lr),
            "stage_macro_f1_observed": primary["stage"][
                "logistic_regression"
            ]["observed_macro_f1"],
            "stage_macro_f1_six_class": primary["stage"][
                "logistic_regression"
            ]["six_class_macro_f1"],
            "lead_time_seconds": 60,
            "note": "Same backward-only temporal features, target, split, and calibration protocol.",
        },
        {
            "model": "ExtraTrees-temporal-forecast-component",
            "role": "primary_ps_benchmark",
            "split": "CIC per-day final-20% untouched; 60s future label",
            **_binary(kairos),
            "stage_macro_f1_observed": primary["stage"][
                "kairos_temporal_head"
            ]["observed_macro_f1"],
            "stage_macro_f1_six_class": primary["stage"][
                "kairos_temporal_head"
            ]["six_class_macro_f1"],
            "lead_time_seconds": 60,
            "note": (
                "Separate ExtraTrees classifier on hand-crafted "
                "backward-only temporal summaries. Improves F1, precision, "
                "recall, FPR, ROC-AUC, and observed-stage macro-F1 over "
                "same-feature LR, but consumes no GNN-Transformer rollout, "
                "latent, or attention features — it is not the world-model "
                "core (next row, F1 0.3545, which does not beat the "
                "baseline)."
            ),
        },
        {
            "model": "WorldModel-GNN-Transformer-core",
            "role": "transition_core_diagnostic",
            "split": "legacy next-window head on CIC final-20%",
            "infiltration_f1": 0.3545,
            "precision": 0.5027,
            "recall": 0.2738,
            "fpr": 0.1694,
            "roc_auc": 0.5813,
            "stage_macro_f1_observed": 0.067,
            "stage_macro_f1_six_class": 0.0335,
            "lead_time_seconds": 120,
            "note": (
                "Retained for autoregressive state rollout and attention. "
                "Scores F1 0.3545 on its native next-window head versus "
                "0.6770 for the same-split baseline: the world-model core "
                "does not beat the baseline on raw F1. Not used as the "
                "headline baseline comparison because the old LR task was "
                "current-window classification rather than future-window "
                "forecasting."
            ),
        },
        {
            "model": "CTU12-LogisticRegression",
            "role": "external_same-feature_baseline",
            "split": "train S6; validate S11; zero-shot S12; 10s",
            **_binary(ctu_lr),
            "stage_macro_f1_observed": None,
            "stage_macro_f1_six_class": None,
            "lead_time_seconds": 10,
            "note": "Official From-Botnet labels; Scenario12 excluded from all fitting/selection.",
        },
        {
            "model": "CTU12-KAIROS-temporal-head",
            "role": "external_generalization_stress_test",
            "split": "train S6; validate S11; zero-shot S12; 10s",
            **_binary(ctu_kairos),
            "stage_macro_f1_observed": None,
            "stage_macro_f1_six_class": None,
            "lead_time_seconds": 10,
            "note": (
                "Improves F1, precision, and recall on untouched Scenario12, "
                "but FPR worsens (+0.0839) and holdout ROC-AUC is below 0.5 "
                "(0.4579): predictions anti-correlate with ground truth on "
                "this unseen botnet family — substantial domain shift, not "
                "solved generalization."
            ),
        },
    ]
    artifact = {
        "artifact_version": "kairos.benchmark.v2",
        "primary_horizon_seconds": 60,
        "estimator": {
            "cic_temporal_trees": aligned["estimator"]["trees"],
            "ctu_temporal_trees": unseen["estimator"]["trees"],
            "baseline": "balanced LR + StandardScaler",
            "seed": 42,
        },
        "primary_requirement_status": {
            "measurable_improvement_over_logistic_regression": True,
            "same_features": True,
            "same_future_target": True,
            "untouched_test": True,
            "improvement": primary["improvement"],
            "attribution": {
                "improvement_from_world_model_core": False,
                "improvement_source": (
                    "separate ExtraTrees discriminative head on "
                    "hand-crafted temporal summaries; consumes no "
                    "GNN-Transformer rollout, latent, or attention features"
                ),
                "world_model_core_native_head_f1": 0.3545,
                "world_model_core_beats_baseline": False,
            },
        },
        "protocol_source": "results/ps_aligned_benchmark.json",
        "external_generalization_source": "results/ctu13_unseen_scenario12.json",
        "legacy_transition_source": "results/phase32_completed.json",
        "rows": rows,
        "takeaway": (
            "On the task-aligned CIC 60-second forecast, a separate "
            "ExtraTrees classifier improves every required binary metric "
            "over same-feature logistic regression — but it consumes no "
            "world-model representations, and the GNN-Transformer core "
            "(F1 0.3545 vs baseline 0.6770) does not beat the baseline. "
            "Scenario12 h1 shows limited zero-shot F1/precision/recall "
            "improvement with high-FPR domain shift and below-random "
            "ranking (AUC 0.4579, anti-correlated on this botnet family); "
            "h3 (F1 -0.1203) and h6 (F1 -0.0324) regress and are disclosed "
            "in phase-status. Thresholds are development-calibrated under "
            "prevalence shift (dev 7.7% vs test 38.5%); stage 1.0 reflects "
            "near-trivial CIC separability."
        ),
    }
    (RESULTS / "benchmark_table.json").write_text(
        json.dumps(artifact, indent=2) + "\n"
    )
    fields = [
        "model", "role", "split", "infiltration_f1", "precision", "recall",
        "fpr", "roc_auc", "stage_macro_f1_observed",
        "stage_macro_f1_six_class", "lead_time_seconds", "note",
    ]
    with (RESULTS / "benchmark_table.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print("wrote results/benchmark_table.json and results/benchmark_table.csv")
    return 0


def _binary(row: dict) -> dict:
    return {
        "infiltration_f1": row["f1"],
        "precision": row["precision"],
        "recall": row["recall"],
        "fpr": row["fpr"],
        "roc_auc": row["roc_auc"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
