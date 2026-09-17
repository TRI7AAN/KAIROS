"""Regression tests for Phase 32 metric helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
import torch


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml" / "training"))

from phase32_common import _auc_roc
from model.encoder_flat import _summary


class Phase32MetricsTest(unittest.TestCase):
    def test_auc_roc_perfect_ordering(self) -> None:
        self.assertEqual(_auc_roc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]), 1.0)

    def test_auc_roc_reversed_ordering(self) -> None:
        self.assertEqual(_auc_roc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]), 0.0)

    def test_auc_roc_ties_receive_half_credit(self) -> None:
        self.assertEqual(_auc_roc([0.5, 0.5], [0, 1]), 0.5)


    def test_flat_summary_keeps_per_feature_statistic_order(self) -> None:
        values = torch.tensor([[1.0, 10.0], [3.0, 14.0]])
        self.assertEqual(_summary(values), [
            2.0, 1.0, 3.0, 4.0,
            12.0, 2.0, 14.0, 24.0,
        ])


if __name__ == "__main__":
    unittest.main()
