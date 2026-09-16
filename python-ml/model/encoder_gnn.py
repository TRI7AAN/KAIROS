"""GraphSAGE encoder and graph-level pooling for KAIROS traffic windows."""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F
from torch_geometric.nn import SAGEConv, global_add_pool, global_mean_pool
from torch_geometric.utils import softmax


class GraphEncoder(nn.Module):
    """Encode variable-sized host-flow graphs into fixed-width state vectors."""

    def __init__(
        self,
        node_feature_dim: int,
        edge_feature_dim: int,
        *,
        hidden_dim: int = 64,
        output_dim: int = 64,
        num_layers: int = 2,
        pooling: str = "mean",
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        if node_feature_dim < 0 or edge_feature_dim < 0:
            raise ValueError("feature dimensions cannot be negative")
        if num_layers not in (2, 3):
            raise ValueError("GraphSAGE encoder must use two or three layers")
        if pooling not in ("mean", "attention"):
            raise ValueError("pooling must be 'mean' or 'attention'")

        self.node_feature_dim = node_feature_dim
        self.edge_feature_dim = edge_feature_dim
        self.pooling = pooling
        self.dropout = dropout
        self.edge_projection = (
            nn.Linear(edge_feature_dim, hidden_dim)
            if edge_feature_dim > 0
            else None
        )
        input_dim = node_feature_dim + (hidden_dim if edge_feature_dim > 0 else 0)
        self.input_projection = nn.Linear(input_dim, hidden_dim)
        self.convolutions = nn.ModuleList(
            SAGEConv(hidden_dim, hidden_dim) for _ in range(num_layers)
        )
        self.output_projection = nn.Linear(hidden_dim, output_dim)
        self.attention_gate = (
            nn.Linear(output_dim, 1) if pooling == "attention" else None
        )

    def forward(self, data) -> torch.Tensor:
        if data.x.ndim != 2 or data.x.shape[1] != self.node_feature_dim:
            raise ValueError("node feature width does not match encoder schema")
        if data.x.shape[0] == 0:
            raise ValueError("each graph must contain at least one node")

        node_values = torch.sign(data.x) * torch.log1p(torch.abs(data.x))
        node_parts = [node_values]
        if self.edge_projection is not None:
            if data.edge_attr.ndim != 2 or data.edge_attr.shape[1] != self.edge_feature_dim:
                raise ValueError("edge feature width does not match encoder schema")
            aggregated = data.x.new_zeros((data.x.shape[0], self.edge_projection.out_features))
            counts = data.x.new_zeros((data.x.shape[0], 1))
            if data.edge_index.shape[1] > 0:
                edge_values = torch.sign(data.edge_attr) * torch.log1p(
                    torch.abs(data.edge_attr)
                )
                edge_state = F.relu(self.edge_projection(edge_values))
                destinations = data.edge_index[1]
                aggregated.index_add_(0, destinations, edge_state)
                counts.index_add_(
                    0,
                    destinations,
                    torch.ones(
                        (destinations.shape[0], 1),
                        dtype=data.x.dtype,
                        device=data.x.device,
                    ),
                )
                aggregated = aggregated / counts.clamp_min(1.0)
            node_parts.append(aggregated)

        hidden = F.relu(self.input_projection(torch.cat(node_parts, dim=-1)))
        for convolution in self.convolutions:
            residual = hidden
            hidden = F.relu(convolution(hidden, data.edge_index))
            hidden = F.dropout(hidden, p=self.dropout, training=self.training)
            hidden = hidden + residual
        hidden = self.output_projection(hidden)

        batch = getattr(data, "batch", None)
        if batch is None:
            batch = torch.zeros(data.x.shape[0], dtype=torch.long, device=data.x.device)
        if self.pooling == "mean":
            return global_mean_pool(hidden, batch)

        scores = self.attention_gate(hidden).squeeze(-1)
        weights = softmax(scores, batch)
        return global_add_pool(hidden * weights.unsqueeze(-1), batch)
