"""Feature flattening, TreeSHAP attribution, and explanation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
import shap

STATISTICS = ("mean", "std", "max", "sum")
TEMPORAL_FEATURE_NAMES = (
    "forecast_context.position_fraction",
    "forecast_history.last_probability",
    "forecast_history.mean_probability",
    "forecast_history.std_probability",
    "forecast_history.max_probability",
)


@dataclass(frozen=True)
class FeatureContribution:
    feature: str
    value: float
    shap_value: float


def _summary(values: np.ndarray) -> np.ndarray:
    if values.ndim != 2 or values.shape[0] == 0:
        raise ValueError("feature values must be a non-empty matrix")
    return np.stack((
        values.mean(axis=0),
        values.std(axis=0),
        values.max(axis=0),
        values.sum(axis=0),
    ), axis=1).reshape(-1)


def flatten_graph(graph) -> np.ndarray:
    """Match the frozen baseline's stable per-window aggregation order."""
    fixed = np.asarray([
        float(graph.x.shape[0]),
        float(graph.edge_index.shape[1]),
        float(graph.window_duration_seconds.item()),
        float(graph.topology_available),
    ], dtype=np.float64)
    node = _summary(graph.x.detach().cpu().numpy())
    edge = _summary(graph.edge_attr.detach().cpu().numpy())
    return np.concatenate((fixed, node, edge))


def flattened_feature_names(
    node_feature_names: Sequence[str],
    edge_feature_names: Sequence[str],
) -> list[str]:
    names = [
        "node_count",
        "edge_count",
        "window_duration_seconds",
        "topology_available",
    ]
    names.extend(
        f"node.{feature}.{statistic}"
        for feature in node_feature_names
        for statistic in STATISTICS
    )
    names.extend(
        f"edge.{feature}.{statistic}"
        for feature in edge_feature_names
        for statistic in STATISTICS
    )
    return names


def temporal_context(
    probabilities: Sequence[float], position: int, total: int,
) -> np.ndarray:
    """Return causal forecast-history features without reading current/future values."""
    if position < 0 or total <= 0 or position >= total:
        raise ValueError("position must identify an item in a non-empty sequence")
    history = np.asarray(probabilities[:position], dtype=np.float64)
    if history.size == 0:
        statistics = (0.0, 0.0, 0.0, 0.0)
    else:
        statistics = (
            float(history[-1]),
            float(history.mean()),
            float(history.std()),
            float(history.max()),
        )
    denominator = max(total - 1, 1)
    return np.asarray(
        (position / denominator, *statistics), dtype=np.float64)


def save_surrogate(model, feature_names: Sequence[str], path: str | Path) -> None:
    joblib.dump({
        "artifact_version": "kairos.shap-surrogate.v1",
        "model": model,
        "feature_names": list(feature_names),
    }, Path(path))


def load_surrogate(path: str | Path):
    payload = joblib.load(Path(path))
    if payload.get("artifact_version") != "kairos.shap-surrogate.v1":
        raise ValueError("unsupported surrogate artifact")
    return payload["model"], payload["feature_names"]


def explain_row(
    model,
    feature_names: Sequence[str],
    row: np.ndarray,
    *,
    top_n: int = 5,
) -> tuple[list[FeatureContribution], float]:
    matrix = np.asarray(row, dtype=np.float64).reshape(1, -1)
    if matrix.shape[1] != len(feature_names):
        raise ValueError("row width does not match feature schema")
    explanation = shap.TreeExplainer(model)(matrix)
    values = np.asarray(explanation.values)[0]
    base = float(np.asarray(explanation.base_values).reshape(-1)[0])
    order = np.argsort(np.abs(values))[::-1][:top_n]
    return [
        FeatureContribution(
            feature=str(feature_names[index]),
            value=float(matrix[0, index]),
            shap_value=float(values[index]),
        )
        for index in order
    ], base


def build_explanation(
    *,
    probability: float,
    predicted_stage: str,
    contributions: Sequence[FeatureContribution],
    attention_summary: dict,
) -> dict:
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be within [0, 1]")
    return {
        "probability": float(probability),
        "predicted_stage": predicted_stage,
        "top_5_features": [
            {
                "feature": item.feature,
                "value": item.value,
                "shap_value": item.shap_value,
            }
            for item in contributions[:5]
        ],
        "attention_summary": attention_summary,
    }
