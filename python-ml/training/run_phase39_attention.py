"""Phase 39: extract causal Transformer attention and render a heatmap."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))
sys.path.insert(0, str(REPO_ROOT / "python-ml" / "training"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
from torch_geometric.data import Batch

from phase32_common import build_splits, make_model

CONTEXT_WINDOWS = 64


def main() -> int:
    phase33 = json.loads(
        (REPO_ROOT / "results" / "phase33_rollout_proof.json").read_text(
            encoding="utf-8"
        )
    )
    attack = phase33["attacks"][0]
    attack_start = attack["attack_start_window"]
    node, edge, _, in_val, _, _, _ = build_splits()
    validation = [graph for day in in_val for graph in day]
    context_start = max(0, attack_start - CONTEXT_WINDOWS)
    context_graphs = validation[context_start:attack_start]

    model = make_model(len(node), len(edge), encoder="gnn")
    payload = torch.load(
        REPO_ROOT / "python-ml" / "weights" / "world_model_v1.pt",
        map_location="cpu",
        weights_only=False,
    )
    model.load_state_dict(payload["model_state_dict"])
    model.eval()
    with torch.no_grad():
        states = model.encoder(Batch.from_data_list(context_graphs)).unsqueeze(0)
        attention = model.dynamics.attention_weights(states).cpu()

    # [layers, batch, heads, query, key] -> [query, key]
    mean_attention = attention.mean(dim=(0, 1, 2))
    final_query = mean_attention[-1]
    top = torch.topk(final_query, k=min(10, len(final_query)))
    top_context = [
        {
            "context_index": int(index),
            "windows_before_attack": len(context_graphs) - int(index),
            "seconds_before_attack": (len(context_graphs) - int(index)) * 10,
            "attention_weight": float(weight),
        }
        for weight, index in zip(top.values, top.indices)
    ]
    future_mass = float(
        torch.triu(mean_attention, diagonal=1).sum()
    )
    row_sum_error = float(
        (mean_attention.sum(dim=-1) - 1.0).abs().max()
    )

    torch.save(
        {
            "attention": attention,
            "mean_attention": mean_attention,
            "context_start_validation_index": context_start,
            "attack_start_validation_index": attack_start,
        },
        REPO_ROOT / "results" / "phase39_attention_weights.pt",
    )
    result = {
        "artifact_version": "kairos.phase39.v1",
        "shape_layers_batch_heads_query_key": list(attention.shape),
        "context_windows": len(context_graphs),
        "window_seconds": 10,
        "attack_start_validation_index": attack_start,
        "top_context_for_final_query": top_context,
        "causal_future_attention_mass": future_mass,
        "max_row_sum_error": row_sum_error,
        "heatmap": "results/phase39_attention_heatmap.png",
        "tensor": "results/phase39_attention_weights.pt",
        "interpretation": (
            "Weights explain which prior latent windows each Transformer query "
            "attended to. They are temporal attribution signals, not causal "
            "proof and not raw-feature SHAP values."
        ),
    }
    (REPO_ROOT / "results" / "phase39_attention_summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    figure, axis = plt.subplots(figsize=(9, 8))
    image = axis.imshow(mean_attention.numpy(), cmap="magma", aspect="auto")
    axis.set_xlabel("Key window in 64-window context")
    axis.set_ylabel("Query window in 64-window context")
    axis.set_title("KAIROS Phase 39 — Mean causal Transformer attention")
    figure.colorbar(image, ax=axis, label="Attention weight")
    figure.tight_layout()
    figure.savefig(
        REPO_ROOT / "results" / "phase39_attention_heatmap.png", dpi=180
    )
    plt.close(figure)
    print(json.dumps({
        "shape": result["shape_layers_batch_heads_query_key"],
        "future_attention_mass": future_mass,
        "max_row_sum_error": row_sum_error,
        "top_final_query_context": top_context[:3],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
