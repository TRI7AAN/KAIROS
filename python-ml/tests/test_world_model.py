"""Tests for Phases 21-28 temporal dynamics, rollout, heads, and losses."""

from __future__ import annotations

from datetime import datetime, timezone
import tempfile
import unittest
from pathlib import Path

import torch

from model.dynamics_transformer import TemporalDynamicsModel
from model.forecast_heads import ForecastHeads, joint_world_model_loss
from training.dynamics_trainer import (
    DynamicsTrainingConfig,
    split_embeddings_by_day,
    train_dynamics,
)


class WorldModelTest(unittest.TestCase):
    def setUp(self) -> None:
        torch.manual_seed(11)

    def test_causal_transformer_teacher_forcing_and_rollout(self) -> None:
        model = TemporalDynamicsModel(
            8, num_heads=4, num_layers=2, dropout=0.0, max_length=32
        )
        model.eval()
        states = torch.randn(2, 6, 8)
        changed_future = states.clone()
        changed_future[:, -1] += 100.0

        original = model(states)
        changed = model(changed_future)
        torch.testing.assert_close(original[:, :-1], changed[:, :-1])
        loss = model.next_state_loss(states)
        self.assertGreater(float(loss), 0.0)
        rollout = model.rollout(states[:, :3], steps=5)
        self.assertEqual(tuple(rollout.shape), (2, 5, 8))
        self.assertTrue(torch.isfinite(rollout).all())
        attention = model.attention_weights(states)
        self.assertEqual(tuple(attention.shape), (2, 2, 4, 6, 6))
        self.assertTrue(torch.isfinite(attention).all())
        self.assertTrue(torch.all(attention[..., 0, 1:] == 0))
        torch.testing.assert_close(attention.sum(dim=-1), torch.ones(2, 2, 4, 6))


    def test_day_split_and_training_checkpoint_reduce_validation_loss(self) -> None:
        timestamps = torch.tensor([
            datetime(2026, 1, day, hour, tzinfo=timezone.utc).timestamp()
            for day in (1, 2, 3)
            for hour in range(4)
        ])
        states = torch.randn(12, 8)
        training_day, validation_day = split_embeddings_by_day(
            states, timestamps, validation_days=1
        )
        self.assertEqual(training_day.shape[0], 8)
        self.assertEqual(validation_day.shape[0], 4)

        training = torch.randn(4, 7, 8)
        training = training[:, :1].repeat(1, 7, 1)
        validation = torch.randn(2, 7, 8)
        validation = validation[:, :1].repeat(1, 7, 1)
        model = TemporalDynamicsModel(
            8, num_heads=4, num_layers=2, dropout=0.0, max_length=16
        )
        model.eval()
        with torch.no_grad():
            initial_validation = float(model.next_state_loss(validation))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            history = train_dynamics(
                model,
                training,
                validation,
                config=DynamicsTrainingConfig(
                    epochs=40,
                    learning_rate=0.02,
                    gradient_clip_norm=1.0,
                ),
                checkpoint_path=root / "world_model.pt",
                config_path=root / "training_config.json",
            )
            self.assertTrue((root / "world_model.pt").is_file())
            self.assertTrue((root / "training_config.json").is_file())
        self.assertLess(history.best_validation_loss, initial_validation)
        self.assertEqual(len(history.training_loss), 40)
        self.assertGreaterEqual(history.best_epoch, 0)

    def test_forecast_probabilities_and_joint_focal_loss(self) -> None:
        heads = ForecastHeads(8, stage_count=6)
        predicted = torch.randn(2, 4, 8, requires_grad=True)
        target = torch.randn(2, 4, 8)
        outputs = heads(predicted)
        infiltration = torch.tensor(
            [[0.0, 0.0, 1.0, 1.0], [0.0, 1.0, 1.0, 1.0]]
        )
        stages = torch.tensor(
            [[-1, -1, 0, 1], [-1, 0, 1, 2]], dtype=torch.long
        )
        loss = joint_world_model_loss(
            predicted, target, outputs, infiltration, stages
        )

        self.assertEqual(tuple(outputs["infiltration_probability"].shape), (2, 4))
        self.assertEqual(tuple(outputs["stage_probability"].shape), (2, 4, 6))
        torch.testing.assert_close(
            outputs["stage_probability"].sum(dim=-1),
            torch.ones(2, 4),
        )
        self.assertTrue(torch.isfinite(loss.total))
        loss.total.backward()
        self.assertIsNotNone(predicted.grad)


if __name__ == "__main__":
    unittest.main()
