"""Phase 72 tests: drift guard reactivity without gitignored fixtures."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]

from live_drift import assess_quality


class DriftGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        payload = np.load(
            REPO_ROOT / "results" / "live_drift_reference.npz",
            allow_pickle=False,
        )
        cls.means = np.asarray(payload["means"], dtype=np.float64)
        cls.stds = np.asarray(payload["stds"], dtype=np.float64)

    def test_reference_center_is_ok(self):
        report = assess_quality(self.means.copy())
        self.assertEqual(report.quality, "ok")

    def test_shifted_window_is_flagged(self):
        shifted = self.means.copy()
        top = np.argsort(np.abs(self.means))[-40:]
        shifted[top] = (
            self.means[top] + 25 * np.maximum(self.stds[top], 1.0)
        )
        report = assess_quality(shifted)
        self.assertIn(report.quality, ("degraded", "unreliable"))

    def test_malformed_window_is_unreliable(self):
        row = self.means.copy()
        row[0] = float("nan")
        report = assess_quality(row)
        self.assertEqual(report.quality, "unreliable")


if __name__ == "__main__":
    unittest.main()
