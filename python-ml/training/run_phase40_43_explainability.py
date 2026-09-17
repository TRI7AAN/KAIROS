"""Phases 40-43: distill, explain with TreeSHAP, standardize, and time."""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))
sys.path.insert(0, str(REPO_ROOT / "python-ml" / "training"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import shap
import torch
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from torch_geometric.data import Batch

from explain.shap_explain import (
    build_explanation,
    explain_row,
    flatten_graph,
    TEMPORAL_FEATURE_NAMES,
    temporal_context,
    flattened_feature_names,
    save_surrogate,
)
from phase32_common import CLASS_NAMES, build_splits, make_model

SURROGATE_PATH = REPO_ROOT / "python-ml" / "weights" / "shap_surrogate_v1.joblib"
RANDOM_SEED = 42


def distillation_rows(model, days):
    features = []
    probabilities = []
    stages = []
    model.eval()
    with torch.no_grad():
        for graphs in days:
            for start in range(0, len(graphs) - 1, 512):
                piece = list(graphs[start:start + 513])
                batch = Batch.from_data_list(piece)
                states = model.encoder(batch).unsqueeze(0)
                predicted = model.dynamics(states[:, :-1])
                outputs = model.heads(predicted)
                piece_probabilities = (
                    outputs["infiltration_probability"][0].cpu().tolist())
                probabilities.extend(piece_probabilities)
                stages.extend(
                    outputs["stage_probability"][0].argmax(dim=-1).cpu().tolist()
                )
                # Each forecast is produced from the current state and targets
                # the following window. Explain the input that caused the
                # forecast, rather than leaking the future target window.
                features.extend(np.concatenate((
                    flatten_graph(graph),
                    temporal_context(piece_probabilities, index, len(piece_probabilities)),
                )) for index, graph in enumerate(piece[:-1]))
    return (
        np.asarray(features, dtype=np.float32),
        np.asarray(probabilities, dtype=np.float64),
        np.asarray(stages, dtype=np.int64),
    )


def main() -> int:
    node, edge, in_train, in_val, _, _, _ = build_splits()
    names = flattened_feature_names(node, edge) + list(TEMPORAL_FEATURE_NAMES)
    model = make_model(len(node), len(edge), encoder="gnn")
    payload = torch.load(
        REPO_ROOT / "python-ml" / "weights" / "world_model_v1.pt",
        map_location="cpu",
        weights_only=False,
    )
    model.load_state_dict(payload["model_state_dict"])
    model.eval()

    # Distillation fidelity is a model-imitation question, distinct from the
    # chronological generalization tests used for attack-detection metrics.
    # Sample teacher outputs across both chronological partitions, then hold
    # out a seeded 20% solely to validate the explanation surrogate.
    x_early, y_early, stage_early = distillation_rows(model, in_train)
    x_late, y_late, stage_late = distillation_rows(model, in_val)
    x_all = np.concatenate((x_early, x_late), axis=0)
    y_all = np.concatenate((y_early, y_late), axis=0)
    stage_all = np.concatenate((stage_early, stage_late), axis=0)
    x_train, x_val, y_train, y_val, _, stage_val = train_test_split(
        x_all, y_all, stage_all, test_size=0.2, random_state=RANDOM_SEED)
    if x_train.shape[1] != len(names):
        raise RuntimeError("flattened feature schema width mismatch")

    started = time.perf_counter()
    surrogate = ExtraTreesRegressor(
        n_estimators=100,
        max_depth=18,
        min_samples_leaf=2,
        max_features=0.25,
        n_jobs=-1,
        random_state=RANDOM_SEED,
    )
    surrogate.fit(x_train, y_train)
    training_seconds = time.perf_counter() - started
    predicted = surrogate.predict(x_val)
    fidelity = {
        "r2": float(r2_score(y_val, predicted)),
        "mae": float(mean_absolute_error(y_val, predicted)),
        "rmse": float(math.sqrt(mean_squared_error(y_val, predicted))),
        "pearson_correlation": float(np.corrcoef(y_val, predicted)[0, 1]),
        "world_probability_min_max": [float(y_val.min()), float(y_val.max())],
        "surrogate_probability_min_max": [
            float(predicted.min()), float(predicted.max())
        ],
    }
    save_surrogate(surrogate, names, SURROGATE_PATH)

    rng = np.random.default_rng(RANDOM_SEED)
    sample_indices = rng.choice(len(x_val), size=min(32, len(x_val)), replace=False)
    sample = x_val[sample_indices]
    explainer = shap.TreeExplainer(surrogate)
    explanations = explainer(sample)
    shap_values = np.asarray(explanations.values)
    mean_absolute = np.abs(shap_values).mean(axis=0)
    top_indices = np.argsort(mean_absolute)[::-1][:20]
    global_importance = [
        {
            "feature": names[index],
            "mean_absolute_shap": float(mean_absolute[index]),
        }
        for index in top_indices
    ]
    additivity_error = float(np.max(np.abs(
        np.asarray(explanations.base_values).reshape(-1)
        + shap_values.sum(axis=1)
        - surrogate.predict(sample)
    )))

    attention = json.loads(
        (REPO_ROOT / "results" / "phase39_attention_summary.json").read_text(
            encoding="utf-8"
        )
    )
    contributions, base_value = explain_row(
        surrogate, names, x_val[0], top_n=5
    )
    explanation_object = build_explanation(
        probability=float(y_val[0]),
        predicted_stage=CLASS_NAMES[int(stage_val[0])],
        contributions=contributions,
        attention_summary={
            "context_windows": attention["context_windows"],
            "top_context_for_final_query":
                attention["top_context_for_final_query"][:5],
            "causal_future_attention_mass":
                attention["causal_future_attention_mass"],
        },
    )
    explanation_object["surrogate"] = {
        "prediction": float(surrogate.predict(x_val[0:1])[0]),
        "base_value": base_value,
        "fidelity_r2": fidelity["r2"],
    }
    (REPO_ROOT / "results" / "phase42_explanation_example.json").write_text(
        json.dumps(explanation_object, indent=2) + "\n", encoding="utf-8"
    )

    latency_ms = []
    for index in range(min(30, len(x_val))):
        tick = time.perf_counter()
        row_contributions, _ = explain_row(
            surrogate, names, x_val[index], top_n=5
        )
        build_explanation(
            probability=float(y_val[index]),
            predicted_stage=CLASS_NAMES[int(stage_val[index])],
            contributions=row_contributions,
            attention_summary={
                "context_windows": attention["context_windows"],
                "top_context_for_final_query":
                    attention["top_context_for_final_query"][:5],
            },
        )
        latency_ms.append((time.perf_counter() - tick) * 1000.0)
    latency_ms.sort()
    latency = {
        "runs": len(latency_ms),
        "min_ms": latency_ms[0],
        "median_ms": float(np.median(latency_ms)),
        "p95_ms": float(np.percentile(latency_ms, 95)),
        "max_ms": latency_ms[-1],
        "target_ms": 2000.0,
        "passes_under_2_seconds": latency_ms[-1] < 2000.0,
        "scope": (
            "TreeSHAP attribution plus Phase 42 JSON construction for one "
            "already-tensorized forecast window; model inference is measured "
            "separately by the Phase 44 endpoint."
        ),
    }

    phase40 = {
        "artifact_version": "kairos.phase40.v1",
        "model": "ExtraTreesRegressor",
        "configuration": {
            "n_estimators": 100,
            "max_depth": 18,
            "min_samples_leaf": 2,
            "max_features": 0.25,
            "random_seed": RANDOM_SEED,
        },
        "validation_scope": (
            "Seeded 20% holdout over teacher outputs from all in-distribution "
            "CIC days. This measures surrogate-to-teacher fidelity only; it "
            "is not an attack-detection or future-generalization metric."
        ),
        "training_rows": len(x_train),
        "validation_rows": len(x_val),
        "feature_count": len(names),
        "training_seconds": training_seconds,
        "fidelity": fidelity,
        "artifact": "python-ml/weights/shap_surrogate_v1.joblib",
    }
    phase41 = {
        "artifact_version": "kairos.phase41.v1",
        "method": "TreeSHAP",
        "explained_validation_rows": len(sample),
        "max_additivity_error": additivity_error,
        "global_top_features": global_importance,
        "plausibility_status": (
            "pass" if additivity_error < 1e-5 and np.isfinite(shap_values).all()
            else "fail"
        ),
        "limitation": (
            "SHAP explains the distilled surrogate approximation, not the "
            "world model directly; fidelity metrics must accompany every claim."
        ),
        "plot": "results/phase41_shap_global_importance.png",
    }
    (REPO_ROOT / "results" / "phase40_surrogate_metrics.json").write_text(
        json.dumps(phase40, indent=2) + "\n", encoding="utf-8"
    )
    (REPO_ROOT / "results" / "phase41_shap_validation.json").write_text(
        json.dumps(phase41, indent=2) + "\n", encoding="utf-8"
    )
    (REPO_ROOT / "results" / "phase43_explainability_latency.json").write_text(
        json.dumps(latency, indent=2) + "\n", encoding="utf-8"
    )

    display = global_importance[:15][::-1]
    figure, axis = plt.subplots(figsize=(10, 7))
    axis.barh(
        [item["feature"] for item in display],
        [item["mean_absolute_shap"] for item in display],
    )
    axis.set_xlabel("Mean |SHAP value|")
    axis.set_title("KAIROS Phase 41 — Surrogate global feature importance")
    figure.tight_layout()
    figure.savefig(
        REPO_ROOT / "results" / "phase41_shap_global_importance.png", dpi=180
    )
    plt.close(figure)

    print(json.dumps({
        "fidelity": fidelity,
        "shap_additivity_error": additivity_error,
        "top_5_features": global_importance[:5],
        "latency": latency,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
