"""Mandatory load-test for the Fix 3 checkpoint (file existence is not proof).

Loads python-ml/weights/world_model_v1.pt, rebuilds the NetworkWorldModel with
the saved schema dims, runs one forward pass plus one full K-step (K=5)
autoregressive rollout, and asserts real, non-NaN, correctly shaped output.
It prefers a local real day28 contract and falls back to a deterministic,
schema-correct fixture so this mandatory check also works after a clean clone.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))

import torch
from torch_geometric.data import Batch, Data

from model.world_model import NetworkWorldModel
from pipeline.graph_builder import load_graph_sequence

CHECKPOINT = REPO_ROOT / "python-ml" / "weights" / "world_model_v1.pt"
CONTRACT_CANDIDATES = (
    REPO_ROOT / "data" / "processed" / "graph_contracts" / "day28.json",
    REPO_ROOT / "data" / "processed" / "cic-2018-02-28-10s.json",
)
CHUNK_LENGTH = 64
ROLLOUT_K = 5


def main() -> int:
    payload = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    artifact_version = payload.get("artifact_version", "")
    assert artifact_version.startswith("kairos.world-model.v1"), (
        artifact_version, payload.keys())
    saved_config = payload["config"]
    print(f"checkpoint epoch={payload['epoch']} "
          f"val_loss={payload['validation_loss']:.6f}")

    contract = next((path for path in CONTRACT_CANDIDATES if path.is_file()), None)
    if contract is not None:
        sequence = load_graph_sequence(contract)
        graphs = list(sequence.graphs[:CHUNK_LENGTH])
        node_feature_count = len(sequence.node_feature_names)
        edge_feature_count = len(sequence.edge_feature_names)
        source = str(contract)
    else:
        state = payload["model_state_dict"]
        edge_feature_count = state["encoder.edge_projection.weight"].shape[1]
        hidden_count = state["encoder.edge_projection.weight"].shape[0]
        node_feature_count = (
            state["encoder.input_projection.weight"].shape[1] - hidden_count
        )
        graphs = _deterministic_graphs(node_feature_count, edge_feature_count)
        source = "deterministic clean-clone fixture"
    model = NetworkWorldModel(
        node_feature_count, edge_feature_count)
    model.load_state_dict(payload["model_state_dict"])
    model.eval()

    batch = Batch.from_data_list(graphs)
    with torch.no_grad():
        states = model.encoder(batch).unsqueeze(0)
        assert states.shape == (1, CHUNK_LENGTH, 64), tuple(states.shape)
        assert torch.isfinite(states).all()
        dynamics_out = model.dynamics(states[:, :-1])
        assert dynamics_out.shape == (1, CHUNK_LENGTH - 1, 64)
        assert torch.isfinite(dynamics_out).all()
        outputs = model.heads(dynamics_out)
        inf_prob = outputs["infiltration_probability"]
        stage_prob = outputs["stage_probability"]
        assert inf_prob.shape == (1, CHUNK_LENGTH - 1), tuple(inf_prob.shape)
        assert stage_prob.shape == (1, CHUNK_LENGTH - 1, 6)
        assert torch.isfinite(inf_prob).all() and torch.isfinite(stage_prob).all()
        assert bool(((inf_prob > 0.0) & (inf_prob < 1.0)).any()), \
            "infiltration probabilities are degenerate"
        rollout = model.dynamics.rollout(states, steps=ROLLOUT_K)
        assert rollout.shape == (1, ROLLOUT_K, 64), tuple(rollout.shape)
        assert torch.isfinite(rollout).all()
        rollout_out = model.heads(rollout)
        assert torch.isfinite(
            rollout_out["infiltration_probability"]).all()
        assert torch.isfinite(rollout_out["stage_probability"]).all()
        spread = float(rollout.std())
        assert spread > 0.0, "rollout states are constant"

    print(f"input source: {source}")
    print(f"forward ok: states mean={float(states.mean()):.4f} "
          f"inf_prob[0,:3]={inf_prob[0, :3].tolist()}")
    print(f"rollout ok: K={ROLLOUT_K} shape={tuple(rollout.shape)} "
          f"std={spread:.4f} "
          f"roll_inf={rollout_out['infiltration_probability'][0].tolist()}")
    print("LOAD TEST PASS")
    return 0


def _deterministic_graphs(node_width: int, edge_width: int) -> list[Data]:
    graphs = []
    node_base = torch.linspace(-1.0, 1.0, node_width)
    edge_base = torch.linspace(0.0, 1.0, edge_width)
    for index in range(CHUNK_LENGTH):
        graphs.append(Data(
            x=(node_base + index / CHUNK_LENGTH).reshape(1, -1),
            edge_index=torch.tensor([[0], [0]], dtype=torch.long),
            edge_attr=(edge_base + index / CHUNK_LENGTH).reshape(1, -1),
            y_infiltration=torch.tensor([float(index % 7 == 0)]),
            y_stage=torch.tensor([-1], dtype=torch.long),
        ))
    return graphs


if __name__ == "__main__":
    raise SystemExit(main())
