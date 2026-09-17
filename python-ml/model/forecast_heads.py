"""Shared forecast heads and focal joint objective for KAIROS rollouts."""

from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn
from torch.nn import functional as F


class ForecastHeads(nn.Module):
    def __init__(self, state_dim: int, stage_count: int = 6) -> None:
        super().__init__()
        if state_dim < 1 or stage_count < 2:
            raise ValueError("invalid forecast head dimensions")
        self.infiltration = nn.Linear(state_dim, 1)
        self.stage = nn.Linear(state_dim, stage_count)

    def forward(self, states: torch.Tensor) -> dict[str, torch.Tensor]:
        infiltration_logits = self.infiltration(states).squeeze(-1)
        stage_logits = self.stage(states)
        return {
            "infiltration_logits": infiltration_logits,
            "infiltration_probability": torch.sigmoid(infiltration_logits),
            "stage_logits": stage_logits,
            "stage_probability": torch.softmax(stage_logits, dim=-1),
        }


@dataclass(frozen=True)
class JointLoss:
    total: torch.Tensor
    dynamics: torch.Tensor
    infiltration: torch.Tensor
    stage: torch.Tensor


def binary_focal_loss(
    logits: torch.Tensor,
    targets: torch.Tensor,
    *,
    alpha: float = 0.25,
    gamma: float = 2.0,
) -> torch.Tensor:
    targets = targets.to(dtype=logits.dtype)
    cross_entropy = F.binary_cross_entropy_with_logits(
        logits, targets, reduction="none"
    )
    probability = torch.sigmoid(logits)
    p_target = probability * targets + (1.0 - probability) * (1.0 - targets)
    alpha_target = alpha * targets + (1.0 - alpha) * (1.0 - targets)
    return (alpha_target * (1.0 - p_target).pow(gamma) * cross_entropy).mean()


def multiclass_focal_loss(
    logits: torch.Tensor,
    targets: torch.Tensor,
    *,
    gamma: float = 2.0,
    ignore_index: int = -1,
) -> torch.Tensor:
    mask = targets != ignore_index
    if not torch.any(mask):
        return logits.sum() * 0.0
    selected_logits = logits[mask]
    selected_targets = targets[mask]
    cross_entropy = F.cross_entropy(
        selected_logits, selected_targets, reduction="none"
    )
    p_target = torch.softmax(selected_logits, dim=-1).gather(
        1, selected_targets.unsqueeze(1)
    ).squeeze(1)
    return ((1.0 - p_target).pow(gamma) * cross_entropy).mean()


def joint_world_model_loss(
    predicted_states: torch.Tensor,
    target_states: torch.Tensor,
    outputs: dict[str, torch.Tensor],
    infiltration_targets: torch.Tensor,
    stage_targets: torch.Tensor,
    *,
    dynamics_weight: float = 1.0,
    infiltration_weight: float = 1.0,
    stage_weight: float = 1.0,
    binary_focal_alpha: float = 0.25,
    focal_gamma: float = 2.0,
) -> JointLoss:
    dynamics = F.mse_loss(predicted_states, target_states)
    infiltration = binary_focal_loss(
        outputs["infiltration_logits"],
        infiltration_targets,
        gamma=focal_gamma,
        alpha=binary_focal_alpha,
    )
    stage = multiclass_focal_loss(
        outputs["stage_logits"],
        stage_targets,
        gamma=focal_gamma,
    )
    total = (
        dynamics_weight * dynamics
        + infiltration_weight * infiltration
        + stage_weight * stage
    )
    return JointLoss(total, dynamics, infiltration, stage)
