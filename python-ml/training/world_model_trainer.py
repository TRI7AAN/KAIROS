"""End-to-end training across day-separated KAIROS graph contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable, Sequence

import torch
from torch_geometric.data import Batch, Data

from model.forecast_heads import joint_world_model_loss
from model.world_model import NetworkWorldModel


@dataclass(frozen=True)
class WorldModelTrainingConfig:
    epochs: int = 5
    chunk_length: int = 64
    learning_rate: float = 1e-3
    gradient_clip_norm: float = 1.0
    dynamics_weight: float = 1.0
    infiltration_weight: float = 1.0
    stage_weight: float = 1.0
    infiltration_alpha: float = 0.25
    focal_gamma: float = 2.0
    random_seed: int = 42


@dataclass(frozen=True)
class WorldModelTrainingHistory:
    training_loss: tuple[float, ...]
    validation_loss: tuple[float, ...]
    best_epoch: int
    best_validation_loss: float


def train_world_model(
    model: NetworkWorldModel,
    training_days: Sequence[Sequence[Data]],
    validation_days: Sequence[Sequence[Data]],
    *,
    config: WorldModelTrainingConfig,
    checkpoint_path: str | Path,
    config_path: str | Path,
    history_path: str | Path,
) -> WorldModelTrainingHistory:
    if config.epochs < 1 or config.chunk_length < 2:
        raise ValueError("epochs must be positive and chunk_length at least two")
    if not training_days or not validation_days:
        raise ValueError("at least one training and validation day are required")
    torch.manual_seed(config.random_seed)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate)
    training_history: list[float] = []
    validation_history: list[float] = []
    best_loss = float("inf")
    best_epoch = -1
    checkpoint = Path(checkpoint_path)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(config.epochs):
        model.train()
        training_total = 0.0
        training_chunks = 0
        for graphs in training_days:
            for chunk in _chunks(graphs, config.chunk_length):
                optimizer.zero_grad()
                loss = _chunk_loss(model, chunk, config)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), config.gradient_clip_norm
                )
                optimizer.step()
                training_total += float(loss.detach())
                training_chunks += 1
        if training_chunks == 0:
            raise ValueError("training data contains no sequence chunks")

        model.eval()
        validation_total = 0.0
        validation_chunks = 0
        with torch.no_grad():
            for graphs in validation_days:
                for chunk in _chunks(graphs, config.chunk_length):
                    validation_total += float(_chunk_loss(model, chunk, config))
                    validation_chunks += 1
        if validation_chunks == 0:
            raise ValueError("validation data contains no sequence chunks")
        training_value = training_total / training_chunks
        validation_value = validation_total / validation_chunks
        training_history.append(training_value)
        validation_history.append(validation_value)
        if validation_value < best_loss:
            best_loss = validation_value
            best_epoch = epoch
            torch.save(
                {
                    "artifact_version": "kairos.world-model.v1",
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "validation_loss": validation_value,
                    "config": asdict(config),
                },
                checkpoint,
            )

    configuration = Path(config_path)
    configuration.parent.mkdir(parents=True, exist_ok=True)
    configuration.write_text(
        json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8"
    )
    history = WorldModelTrainingHistory(
        tuple(training_history),
        tuple(validation_history),
        best_epoch,
        best_loss,
    )
    history_file = Path(history_path)
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(
        json.dumps(
            {
                "artifact_version": "kairos.world-model-training.v1",
                "training_loss": list(history.training_loss),
                "validation_loss": list(history.validation_loss),
                "best_epoch": history.best_epoch,
                "best_validation_loss": history.best_validation_loss,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return history


def _chunks(
    graphs: Sequence[Data],
    chunk_length: int,
) -> Iterable[Sequence[Data]]:
    step = chunk_length - 1
    for start in range(0, len(graphs) - 1, step):
        chunk = graphs[start : start + chunk_length]
        if len(chunk) >= 2:
            yield chunk


def _chunk_loss(
    model: NetworkWorldModel,
    graphs: Sequence[Data],
    config: WorldModelTrainingConfig,
) -> torch.Tensor:
    batch = Batch.from_data_list(list(graphs))
    states = model.encoder(batch).unsqueeze(0)
    predicted_states = model.dynamics(states[:, :-1])
    outputs = model.heads(predicted_states)
    infiltration = torch.cat(
        [graph.y_infiltration for graph in graphs[1:]]
    ).unsqueeze(0)
    stages = torch.cat([graph.y_stage for graph in graphs[1:]]).unsqueeze(0)
    losses = joint_world_model_loss(
        predicted_states,
        states[:, 1:].detach(),
        outputs,
        infiltration,
        stages,
        dynamics_weight=config.dynamics_weight,
        infiltration_weight=config.infiltration_weight,
        stage_weight=config.stage_weight,
        focal_gamma=config.focal_gamma,
        binary_focal_alpha=config.infiltration_alpha,
    )
    return losses.total
