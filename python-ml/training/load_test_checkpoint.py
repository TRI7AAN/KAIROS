"""Mandatory load-test for the Fix 3 checkpoint (file existence is not proof).

Loads python-ml/weights/world_model_v1.pt, rebuilds the NetworkWorldModel with
the saved schema dims, runs one forward pass plus one full K-step (K=5)
autoregressive rollout on a real sample window chunk from day28, and asserts
real, non-NaN, correctly shaped output.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))

import torch
from torch_geometric.data import Batch

from model.world_model import NetworkWorldModel
from pipeline.graph_builder import load_graph_sequence

CHECKPOINT = REPO_ROOT / "python-ml" / "weights" / "world_model_v1.pt"
CONTRACT = REPO_ROOT / "data" / "processed" / "graph_contracts" / "day28.json"
CHUNK_LENGTH = 64
ROLLOUT_K = 5


def main() -> int:
    payload = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    assert payload.get("artifact_version") == "kairos.world-model.v1", payload.keys()
    saved_config = payload["config"]
    print(f"checkpoint epoch={payload['epoch']} "
          f"val_loss={payload['validation_loss']:.6f}")

    sequence = load_graph_sequence(CONTRACT)
    model = NetworkWorldModel(
        len(sequence.node_feature_names), len(sequence.edge_feature_names))
    model.load_state_dict(payload["model_state_dict"])
    model.eval()

    graphs = list(sequence.graphs[:CHUNK_LENGTH])
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

    print(f"forward ok: states mean={float(states.mean()):.4f} "
          f"inf_prob[0,:3]={inf_prob[0, :3].tolist()}")
    print(f"rollout ok: K={ROLLOUT_K} shape={tuple(rollout.shape)} "
          f"std={spread:.4f} "
          f"roll_inf={rollout_out['infiltration_probability'][0].tolist()}")
    print("LOAD TEST PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
