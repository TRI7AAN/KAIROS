"""Flat (non-graph) window encoder for the Phase 32 GNN-vs-flat ablation.

Collapses each per-window graph into one fixed-width summary vector —
[node_count, edge_count, window_duration_seconds, topology_available] plus
per-feature mean/std/max/sum over node rows and edge rows, the exact
aggregation used by the frozen non-temporal logistic baseline — then
projects to the shared state_dim. Drop-in replacement for GraphEncoder:
forward(Batch) -> (num_graphs, output_dim), so the identical Transformer
dynamics and forecast heads are reused and only graph structure is removed.
"""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F


class FlatWindowEncoder(nn.Module):
    def __init__(
        self,
        node_feature_dim: int,
        edge_feature_dim: int,
        *,
        hidden_dim: int = 64,
        output_dim: int = 64,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        if node_feature_dim < 1 or edge_feature_dim < 1:
            raise ValueError("feature dimensions must be positive")
        self.node_feature_dim = node_feature_dim
        self.edge_feature_dim = edge_feature_dim
        self.flat_dim = 4 + node_feature_dim * 4 + edge_feature_dim * 4
        self.projection = nn.Linear(self.flat_dim, output_dim)
        self.norm = nn.LayerNorm(output_dim)
        self.dropout_p = dropout

    def forward(self, data) -> torch.Tensor:
        graphs = data.to_data_list() if hasattr(data, "to_data_list") else [data]
        rows = [self._flatten(graph) for graph in graphs]
        flat = torch.stack(rows).to(dtype=torch.float32)
        return self.norm(F.dropout(
            self.projection(flat), p=self.dropout_p, training=self.training
        ))

    def _flatten(self, graph) -> torch.Tensor:
        if graph.x.shape[0] == 0:
            raise ValueError("each graph must contain at least one node")
        parts = [
            float(graph.x.shape[0]),
            float(graph.edge_index.shape[1]),
            float(graph.window_duration_seconds.item()),
            float(bool(graph.topology_available)),
        ]
        parts.extend(_summary(graph.x))
        if graph.edge_attr.shape[0] == 0:
            parts.extend([0.0] * (self.edge_feature_dim * 4))
        else:
            if graph.edge_attr.shape[1] != self.edge_feature_dim:
                raise ValueError("edge feature width does not match encoder schema")
            parts.extend(_summary(graph.edge_attr))
        return torch.tensor(parts, dtype=torch.float32)


def _summary(values: torch.Tensor) -> list[float]:
    out: list[float] = []
    for column in values.T:
        out.extend([
            float(column.mean()),
            float(column.std(unbiased=False)),
            float(column.max()),
            float(column.sum()),
        ])
    return out
