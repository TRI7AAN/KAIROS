"""Regression guards for judge-facing PS alignment evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> dict:
    return json.loads((ROOT / "results" / name).read_text())


def test_primary_benchmark_beats_same_feature_logistic_on_required_metrics():
    artifact = _load("benchmark_table.json")
    status = artifact["primary_requirement_status"]
    assert status["same_features"] is True
    assert status["same_future_target"] is True
    assert status["untouched_test"] is True
    rows = {row["role"]: row for row in artifact["rows"]}
    baseline = rows["required_same-feature_baseline"]
    kairos = rows["primary_ps_benchmark"]
    assert kairos["infiltration_f1"] > baseline["infiltration_f1"]
    assert kairos["precision"] > baseline["precision"]
    assert kairos["recall"] > baseline["recall"]
    assert kairos["fpr"] < baseline["fpr"]
    assert kairos["roc_auc"] > baseline["roc_auc"]


def test_ctu_final_holdout_is_separate_from_development_and_selection():
    artifact = _load("ctu13_unseen_scenario12.json")
    protocol = artifact["protocol"]
    assert artifact["estimator"]["trees"] == 200
    assert artifact["estimator"]["random_seed"] == 42
    assert "Scenario 6" in protocol["development"]
    assert "Scenario 11" in protocol["external_validation"]
    assert "Scenario 12" in protocol["untouched_holdout"]
    holdout = artifact["sources"]["scenario12"]
    assert holdout["role"] == "untouched final holdout"
    assert artifact["sources"]["scenario6"]["sha256"] != holdout["sha256"]
    assert artifact["sources"]["scenario11"]["sha256"] != holdout["sha256"]


def test_deployed_temporal_weight_is_present_and_under_git_size_limit():
    path = ROOT / "python-ml" / "weights" / "ps_aligned_temporal_forecaster.joblib"
    assert path.is_file()
    assert 0 < path.stat().st_size < 100 * 1024 * 1024
