"""Offline Flask inference service for the KAIROS world model."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))
sys.path.insert(0, str(REPO_ROOT / "python-ml" / "training"))

from flask import Flask, jsonify, request
import numpy as np
import torch
from torch_geometric.data import Batch

from explain.shap_explain import (
    TEMPORAL_FEATURE_NAMES,
    build_explanation,
    explain_row,
    flatten_graph,
    flattened_feature_names,
    load_surrogate,
    temporal_context,
)
from live_drift import assess_quality
from phase32_common import CLASS_NAMES, make_model
from pipeline.graph_builder import GraphContractError, load_graph_sequence

DEFAULT_CHECKPOINT = REPO_ROOT / "python-ml" / "weights" / "world_model_v1.pt"
DEFAULT_SURROGATE = REPO_ROOT / "python-ml" / "weights" / "shap_surrogate_v1.joblib"
MAX_CONTEXT_WINDOWS = 512
ATTENTION_CONTEXT_WINDOWS = 64
MAX_ROLLOUT_STEPS = 10


class SurrogateUnavailableError(RuntimeError):
    """The SHAP surrogate artifact is missing or unreadable."""


class PredictionService:
    """Load immutable artifacts once and serve deterministic CPU inference."""

    def __init__(
        self,
        checkpoint_path: str | Path = DEFAULT_CHECKPOINT,
        surrogate_path: str | Path = DEFAULT_SURROGATE,
    ) -> None:
        self.checkpoint_path = Path(checkpoint_path)
        try:
            self.surrogate, self.surrogate_feature_names = load_surrogate(
                surrogate_path)
        except (OSError, ValueError) as error:
            raise SurrogateUnavailableError(
                "explainability service unavailable: "
                f"cannot load SHAP surrogate from {surrogate_path}"
            ) from error
        self._checkpoint = torch.load(
            self.checkpoint_path, map_location="cpu", weights_only=False)
        self._models: dict[tuple[int, int], torch.nn.Module] = {}

    def _model(self, node_dim: int, edge_dim: int):
        dimensions = (node_dim, edge_dim)
        if dimensions not in self._models:
            model = make_model(node_dim, edge_dim, encoder="gnn")
            try:
                model.load_state_dict(self._checkpoint["model_state_dict"])
            except RuntimeError as error:
                raise GraphContractError(
                    "contract feature dimensions do not match the trained model"
                ) from error
            model.eval()
            self._models[dimensions] = model
        return self._models[dimensions]

    def predict(self, contract: Mapping[str, Any], rollout_steps: int = 3) -> dict:
        if not isinstance(rollout_steps, int) or isinstance(rollout_steps, bool):
            raise ValueError("rolloutSteps must be an integer")
        if not 1 <= rollout_steps <= MAX_ROLLOUT_STEPS:
            raise ValueError(
                f"rolloutSteps must be between 1 and {MAX_ROLLOUT_STEPS}")

        sequence = load_graph_sequence(contract)
        if not sequence.graphs:
            raise GraphContractError("at least one graph window is required")
        graphs = list(sequence.graphs[-MAX_CONTEXT_WINDOWS:])
        names = (
            flattened_feature_names(
                sequence.node_feature_names, sequence.edge_feature_names)
            + list(TEMPORAL_FEATURE_NAMES)
        )
        if names != self.surrogate_feature_names:
            raise GraphContractError(
                "contract feature schema does not match the explanation artifact")

        model = self._model(
            len(sequence.node_feature_names), len(sequence.edge_feature_names))
        started = time.perf_counter()
        with torch.inference_mode():
            states = model.encoder(Batch.from_data_list(graphs)).unsqueeze(0)
            teacher_states = model.dynamics(states)
            teacher_outputs = model.heads(teacher_states)
            context_probabilities = (
                teacher_outputs["infiltration_probability"][0].cpu().tolist())
            immediate_probability = float(context_probabilities[-1])
            immediate_stage_index = int(
                teacher_outputs["stage_probability"][0, -1].argmax().item())

            future_states = model.dynamics.rollout(states, rollout_steps)
            future_outputs = model.heads(future_states)
            rollout_probabilities = [
                float(value) for value in
                future_outputs["infiltration_probability"][0].cpu().tolist()
            ]
            rollout_stages = [
                CLASS_NAMES[int(index)] for index in
                future_outputs["stage_probability"][0].argmax(dim=-1).cpu().tolist()
            ]

            attention_states = states[:, -ATTENTION_CONTEXT_WINDOWS:]
            attention = model.dynamics.attention_weights(attention_states)
            mean_attention = attention.mean(dim=(0, 1, 2))
            final_attention = mean_attention[-1]
            top = torch.topk(final_attention, k=min(5, len(final_attention)))

        row = np.concatenate((
            flatten_graph(graphs[-1]),
            temporal_context(
                context_probabilities,
                len(context_probabilities) - 1,
                len(context_probabilities),
            ),
        ))
        quality = assess_quality(row[:-len(TEMPORAL_FEATURE_NAMES)])
        contributions, base_value = explain_row(
            self.surrogate, names, row, top_n=5)
        top_context = [
            {
                "context_index": int(index),
                "windows_before_forecast": len(final_attention) - int(index),
                "seconds_before_forecast": (
                    len(final_attention) - int(index)
                ) * int(round(float(graphs[-1].window_duration_seconds.item()))),
                "attention_weight": float(weight),
            }
            for weight, index in zip(top.values, top.indices)
        ]
        attention_summary = {
            "context_windows": int(len(final_attention)),
            "top_context_for_final_query": top_context,
            "causal_future_attention_mass": float(
                torch.triu(mean_attention, diagonal=1).sum().item()),
        }
        response = build_explanation(
            probability=immediate_probability,
            predicted_stage=CLASS_NAMES[immediate_stage_index],
            contributions=contributions,
            attention_summary=attention_summary,
        )
        response.update({
            "artifact_version": "kairos.prediction.v1",
            "forecast_horizon_windows": 1,
            "quality": quality.quality,
            "quality_detail": {
                "max_abs_z": quality.max_abs_z,
                "mean_abs_z": quality.mean_abs_z,
                "frac_z_gt_5": quality.frac_z_gt_5,
                "frac_z_gt_3": quality.frac_z_gt_3,
                "checked_features": quality.checked_features,
            },
            "window_seconds": float(
                graphs[-1].window_duration_seconds.item()),
            "rollout": {
                "steps": rollout_steps,
                "probabilities": rollout_probabilities,
                "predicted_stages": rollout_stages,
                "max_probability": max(rollout_probabilities),
            },
            "surrogate": {
                "prediction": float(self.surrogate.predict(row.reshape(1, -1))[0]),
                "base_value": base_value,
            },
            "model_artifact": self._checkpoint.get(
                "artifact_version", "unknown"),
            "latency_ms": (time.perf_counter() - started) * 1000.0,
        })
        return response


def create_app(prediction_service: PredictionService | None = None,
               surrogate_path: str | Path | None = None) -> Flask:
    app = Flask(__name__)
    service_holder: dict[str, PredictionService | None] = {
        "service": prediction_service}

    def service() -> PredictionService:
        if service_holder["service"] is None:
            service_holder["service"] = PredictionService(
                surrogate_path=surrogate_path
                if surrogate_path is not None else DEFAULT_SURROGATE)
        return service_holder["service"]

    @app.errorhandler(SurrogateUnavailableError)
    def surrogate_unavailable(error):
        return jsonify({"error": str(error)}), 503

    @app.get("/health")
    def health():
        return jsonify({
            "status": "ok",
            "service": "kairos-python-ml",
            "offline": True,
        })

    @app.post("/predict")
    def predict_route():
        payload = request.get_json(silent=True)
        if not isinstance(payload, Mapping):
            return jsonify({"error": "request body must be a JSON object"}), 400
        contract = payload.get("contract", payload)
        rollout_steps = payload.get("rolloutSteps", 3)
        try:
            result = service().predict(contract, rollout_steps)
        except SurrogateUnavailableError as error:
            return jsonify({"error": str(error)}), 503
        except (GraphContractError, ValueError, TypeError) as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(result)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("KAIROS_ML_HOST", "127.0.0.1"),
        port=int(os.environ.get("KAIROS_ML_PORT", "5000")),
        debug=False,
    )
