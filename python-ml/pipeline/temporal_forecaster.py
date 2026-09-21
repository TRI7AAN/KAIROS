"""Runtime support for the PS-aligned temporal forecast-head artifact."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import joblib
import numpy as np

from baseline.logistic_regression import flatten_graph_sequence
from pipeline.graph_builder import LoadedGraphSequence

ARTIFACT_VERSION = "kairos.ps-aligned-temporal-forecaster.v1"
SUMMARY_NAMES = (
    "current",
    "history_mean",
    "history_std",
    "history_delta",
    "history_abs_velocity",
)


class TemporalForecasterError(ValueError):
    """Raised when the temporal head artifact and graph input are incompatible."""


def temporal_feature_names(base_names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        f"{summary}.{name}"
        for summary in SUMMARY_NAMES
        for name in base_names
    )


def temporal_vector(values: np.ndarray) -> np.ndarray:
    if values.ndim != 2 or values.shape[0] < 2:
        raise TemporalForecasterError(
            "temporal forecast requires at least two feature windows"
        )
    current = values[-1]
    mean = values.mean(axis=0)
    std = values.std(axis=0)
    delta = current - values[0]
    velocity = np.abs(np.diff(values, axis=0)).mean(axis=0)
    vector = np.concatenate((current, mean, std, delta, velocity))
    if not np.isfinite(vector).all():
        raise TemporalForecasterError("temporal features must be finite")
    return vector


def load_temporal_forecaster(path: str | Path) -> dict[str, Any]:
    try:
        artifact = joblib.load(path)
    except (OSError, ValueError, TypeError) as error:
        raise TemporalForecasterError(
            f"cannot load temporal forecaster from {path}"
        ) from error
    if not isinstance(artifact, dict) or artifact.get(
        "artifact_version"
    ) != ARTIFACT_VERSION:
        raise TemporalForecasterError("unsupported temporal forecaster artifact")
    if not isinstance(artifact.get("models_by_horizon"), dict):
        raise TemporalForecasterError("temporal forecaster has no horizon models")
    return artifact


def predict_temporal_forecasts(
    sequence: LoadedGraphSequence,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    history = int(artifact.get("history_windows", 0))
    if history < 2:
        raise TemporalForecasterError("artifact history_windows is invalid")
    if len(sequence.graphs) < history:
        return {
            "available": False,
            "required_history_windows": history,
            "received_history_windows": len(sequence.graphs),
            "reason": "insufficient_history",
            "horizons": [],
        }

    dataset = flatten_graph_sequence(sequence)
    actual_names = temporal_feature_names(dataset.feature_names)
    expected_names = tuple(artifact.get("feature_names", ()))
    if actual_names != expected_names:
        raise TemporalForecasterError(
            "contract feature schema does not match temporal forecast artifact"
        )
    row = temporal_vector(dataset.features[-history:]).reshape(1, -1)
    window_seconds = float(artifact.get("window_seconds", 10))
    forecasts = []
    for raw_horizon, bundle in sorted(
        artifact["models_by_horizon"].items(),
        key=lambda item: int(item[0]),
    ):
        horizon = int(raw_horizon)
        binary = bundle["binary"]
        stage = bundle["stage"]
        probability = float(binary.predict_proba(row)[0, 1])
        stage_index = int(stage.predict(row)[0])
        threshold = float(bundle["threshold"])
        forecasts.append({
            "horizon_windows": horizon,
            "horizon_seconds": horizon * window_seconds,
            "probability": probability,
            "threshold": threshold,
            "alert": probability >= threshold,
            "predicted_stage_index": stage_index,
        })
    return {
        "available": True,
        "artifact_version": artifact["artifact_version"],
        "required_history_windows": history,
        "received_history_windows": len(sequence.graphs),
        "horizons": forecasts,
    }
