"""CTU-13 Scenario 6 frozen-model development smoke (no fake metrics).

Loads a bounded packet-native contract produced by
Ctu13PacketExporter, applies the explicit loss-aware packet-to-CIC projection,
and records frozen-model inference plus packet characterization. Scenario 6 is
development data and is never reported as zero-shot evaluation.

Usage:
  PYTHONPATH=python-ml .venv/bin/python python-ml/training/run_ctu13_zero_shot.py \
    --contract /tmp/ctu13-packet-contract.json \
    --output results/ctu13_zero_shot_attempt.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))

from app import PredictionService  # noqa: E402
from pipeline.graph_builder import GraphContractError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rollout-steps", type=int, default=3)
    args = parser.parse_args()

    contract = json.loads(Path(args.contract).read_text())
    windows = contract.get("windows", [])
    first = windows[0] if windows else {}
    characterization = {
        "windows": len(windows),
        "nodes_first_window": len(first.get("nodes", [])),
        "edges_first_window": len(first.get("edges", [])),
        "topology_available": first.get("topologyAvailable", None),
        "node_feature_names": contract.get("nodeFeatureNames", []),
        "edge_feature_names": contract.get("edgeFeatureNames", []),
    }

    service = PredictionService()
    try:
        result = service.predict(contract, args.rollout_steps)
        outcome = {
            "status": "scored",
            "probability": result["probability"],
            "predicted_stage": result["predicted_stage"],
            "quality": result["quality"],
            "quality_detail": result["quality_detail"],
            "input_projection": result["input_projection"],
        }
    except (GraphContractError, ValueError) as error:
        outcome = {
            "status": "schema_blocked",
            "reason": str(error)[:500],
        }

    artifact = {
        "artifact_version": "kairos.ctu13-development-smoke.v2",
        "dataset_role": "extractor-development; excluded from zero-shot evaluation",
        "method": "frozen CIC-trained world_model_v1.pt, no retraining; "
        "packet-native CTU-13 contract with loss-aware packet-to-CIC projection",
        "characterization": characterization,
        "outcome": outcome,
        "interpretation": (
            "Scenario 6 validates bounded packet extraction and pipeline wiring. "
            "The projection maps only header-observable quantities into the frozen "
            "CIC schema and zero-fills unavailable CICFlowMeter fields. "
            "Its probability is a development smoke result, not a zero-shot metric. "
            "No F1/precision/recall/FPR is reported because Scenario 6 is explicitly "
            "excluded from the leakage-free evaluation holdout."
        ),
    }
    Path(args.output).write_text(json.dumps(artifact, indent=2))
    print(json.dumps(artifact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
