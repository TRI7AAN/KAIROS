"""Causal temporal dynamics over graph-state embeddings."""

from __future__ import annotations

import math

import torch
from torch import nn
from torch.nn import functional as F


class SinusoidalPositionEncoding(nn.Module):
    def __init__(self, dimension: int, max_length: int = 4096) -> None:
        super().__init__()
        if dimension < 1 or max_length < 2:
            raise ValueError("invalid positional encoding dimensions")
        position = torch.arange(max_length, dtype=torch.float32).unsqueeze(1)
        divisor = torch.exp(
            torch.arange(0, dimension, 2, dtype=torch.float32)
            * (-math.log(10000.0) / dimension)
        )
        encoding = torch.zeros(max_length, dimension)
        encoding[:, 0::2] = torch.sin(position * divisor)
        if dimension > 1:
            encoding[:, 1::2] = torch.cos(position * divisor[: encoding[:, 1::2].shape[1]])
        self.register_buffer("encoding", encoding.unsqueeze(0), persistent=False)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        if states.shape[1] > self.encoding.shape[1]:
            raise ValueError("sequence exceeds configured maximum length")
        return states + self.encoding[:, : states.shape[1]].to(
            device=states.device, dtype=states.dtype
        )


class TemporalDynamicsModel(nn.Module):
    """Learn P(S[t+1] | S[0:t]) with a causal Transformer."""

    def __init__(
        self,
        state_dim: int,
        *,
        num_heads: int = 4,
        num_layers: int = 2,
        feedforward_dim: int | None = None,
        dropout: float = 0.1,
        max_length: int = 4096,
    ) -> None:
        super().__init__()
        if state_dim < 1 or state_dim % num_heads:
            raise ValueError("state_dim must be positive and divisible by num_heads")
        if num_layers < 1:
            raise ValueError("num_layers must be positive")
        feedforward_dim = feedforward_dim or state_dim * 4
        self.position = SinusoidalPositionEncoding(state_dim, max_length)
        layer = nn.TransformerEncoderLayer(
            d_model=state_dim,
            nhead=num_heads,
            dim_feedforward=feedforward_dim,
            dropout=dropout,
            batch_first=True,
            norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(layer, num_layers=num_layers)
        self.output_projection = nn.Linear(state_dim, state_dim)

    def forward(self, states: torch.Tensor) -> torch.Tensor:
        if states.ndim != 3:
            raise ValueError("states must have shape [batch, time, state_dim]")
        if states.shape[1] < 1:
            raise ValueError("at least one state is required")
        encoded = self.position(states)
        mask = nn.Transformer.generate_square_subsequent_mask(
            states.shape[1], device=states.device
        )
        return self.output_projection(
            self.transformer(encoded, mask=mask, is_causal=True)
        )

    def next_state_loss(self, states: torch.Tensor) -> torch.Tensor:
        """Teacher-forced one-step transition loss."""
        if states.shape[1] < 2:
            raise ValueError("at least two states are required")
        prediction = self(states[:, :-1])
        return F.mse_loss(prediction, states[:, 1:])

    @torch.no_grad()
    def rollout(self, context: torch.Tensor, steps: int) -> torch.Tensor:
        """Autoregressively feed each predicted state back for K future steps."""
        if steps < 1:
            raise ValueError("steps must be positive")
        if context.ndim != 3 or context.shape[1] < 1:
            raise ValueError("context must have shape [batch, time, state_dim]")
        generated = context
        predictions = []
        for _ in range(steps):
            next_state = self(generated)[:, -1:, :]
            predictions.append(next_state)
            generated = torch.cat((generated, next_state), dim=1)
        return torch.cat(predictions, dim=1)
