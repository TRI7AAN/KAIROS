"""End-to-end graph encoder, temporal dynamics, and forecast heads."""

from __future__ import annotations

from torch import nn

from model.dynamics_transformer import TemporalDynamicsModel
from model.encoder_gnn import GraphEncoder
from model.forecast_heads import ForecastHeads


class NetworkWorldModel(nn.Module):
    def __init__(
        self,
        node_feature_dim: int,
        edge_feature_dim: int,
        *,
        hidden_dim: int = 64,
        state_dim: int = 64,
        sage_layers: int = 2,
        transformer_layers: int = 2,
        transformer_heads: int = 4,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.encoder = GraphEncoder(
            node_feature_dim,
            edge_feature_dim,
            hidden_dim=hidden_dim,
            output_dim=state_dim,
            num_layers=sage_layers,
            pooling="attention",
            dropout=dropout,
        )
        self.dynamics = TemporalDynamicsModel(
            state_dim,
            num_heads=transformer_heads,
            num_layers=transformer_layers,
            dropout=dropout,
        )
        self.heads = ForecastHeads(state_dim, stage_count=6)
