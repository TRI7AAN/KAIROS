"""Leakage-safe training utilities for temporal graph dynamics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

import torch

from model.dynamics_transformer import TemporalDynamicsModel


@dataclass(frozen=True)
class DynamicsTrainingConfig:
    epochs: int = 50
    learning_rate: float = 1e-3
    gradient_clip_norm: float = 1.0
    validation_days: int = 1


@dataclass(frozen=True)
class DynamicsTrainingHistory:
    training_loss: tuple[float, ...]
    validation_loss: tuple[float, ...]
    best_epoch: int
    best_validation_loss: float


def split_embeddings_by_day(
    states: torch.Tensor,
    epoch_seconds: torch.Tensor,
    *,
    validation_days: int = 1,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Hold out the latest complete UTC day(s); never split windows randomly."""
    if states.ndim != 2 or epoch_seconds.ndim != 1:
        raise ValueError("states and timestamps must be [time, dim] and [time]")
    if states.shape[0] != epoch_seconds.shape[0] or states.shape[0] < 4:
        raise ValueError("states and timestamps need at least four matching rows")
    if validation_days < 1:
        raise ValueError("validation_days must be positive")
    days = [
        datetime.fromtimestamp(float(value), tz=timezone.utc).date()
        for value in epoch_seconds
    ]
    unique_days = sorted(set(days))
    if len(unique_days) <= validation_days:
        raise ValueError("not enough distinct days for day-based validation")
    validation_set = set(unique_days[-validation_days:])
    split_index = next(index for index, day in enumerate(days) if day in validation_set)
    if any(day not in validation_set for day in days[split_index:]):
        raise ValueError("timestamps must be chronologically grouped by day")
    return states[:split_index], states[split_index:]


def train_dynamics(
    model: TemporalDynamicsModel,
    training_states: torch.Tensor,
    validation_states: torch.Tensor,
    *,
    config: DynamicsTrainingConfig,
    checkpoint_path: str | Path,
    config_path: str | Path | None = None,
) -> DynamicsTrainingHistory:
    """Train with teacher forcing, clipping, validation, and best checkpointing."""
    if config.epochs < 1 or config.learning_rate <= 0 or config.gradient_clip_norm <= 0:
        raise ValueError("invalid training configuration")
    training_states = _as_batch(training_states)
    validation_states = _as_batch(validation_states)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    training_history: list[float] = []
    validation_history: list[float] = []
    best_loss = float("inf")
    best_epoch = -1
    checkpoint = Path(checkpoint_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(config.epochs):
        model.train()
        optimizer.zero_grad()
        training_loss = model.next_state_loss(training_states)
        training_loss.backward()
        torch.nn.utils.clip_grad_norm_(
            model.parameters(), config.gradient_clip_norm
        )
        optimizer.step()

        model.eval()
        with torch.no_grad():
            validation_loss = model.next_state_loss(validation_states)
        train_value = float(training_loss.detach())
        validation_value = float(validation_loss)
        training_history.append(train_value)
        validation_history.append(validation_value)
        if validation_value < best_loss:
            best_loss = validation_value
            best_epoch = epoch
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "validation_loss": validation_value,
                    "config": asdict(config),
                },
                checkpoint,
            )

    if config_path is not None:
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")
    return DynamicsTrainingHistory(
        tuple(training_history),
        tuple(validation_history),
        best_epoch,
        best_loss,
    )


def _as_batch(states: torch.Tensor) -> torch.Tensor:
    if states.ndim == 2:
        states = states.unsqueeze(0)
    if states.ndim != 3 or states.shape[1] < 2:
        raise ValueError("state sequences must be [batch, time>=2, dimension]")
    return states
