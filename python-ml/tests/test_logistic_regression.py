"""Tests for Phases 12-16 baseline flattening, splitting, and evaluation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from baseline.logistic_regression import (
    flatten_graph_sequence,
    run_baselines,
    time_based_split,
)
from pipeline.graph_builder import load_graph_sequence


def sequence_payload(window_count: int = 30) -> dict:
    windows = []
    for index in range(window_count):
        malicious = index % 3 != 0
        stage = "INITIAL_ACCESS" if index % 2 == 0 else "LATERAL_MOVEMENT"
        if not malicious:
            stage = "NONE"
        windows.append(
            {
                "schemaVersion": "kairos.graph.v1",
                "windowStart": f"2026-01-01T00:{index // 6:02d}:{(index % 6) * 10:02d}Z",
                "windowEnd": f"2026-01-01T00:{index // 6:02d}:{(index % 6) * 10 + 10:02d}Z"
                if index % 6 < 5
                else f"2026-01-01T00:{index // 6 + 1:02d}:00Z",
                "topologyAvailable": True,
                "nodes": [
                    {"id": "a", "features": {"flow_count": float(index + 1)}},
                    {"id": "b", "features": {"flow_count": float(malicious)}},
                ],
                "edges": [
                    {
                        "id": f"edge-{index}",
                        "source": "a",
                        "destination": "b",
                        "features": {"bytes": float(index * 2 + malicious)},
                    }
                ],
                "label": {"infiltration": malicious, "stage": stage},
            }
        )
    return {
        "contractVersion": "kairos.sequence.v1",
        "nodeFeatureNames": ["flow_count"],
        "edgeFeatureNames": ["bytes"],
        "windows": windows,
    }


class LogisticRegressionBaselineTest(unittest.TestCase):
    def test_flattening_has_stable_width_and_expected_statistics(self) -> None:
        dataset = flatten_graph_sequence(load_graph_sequence(sequence_payload(6)))

        self.assertEqual(dataset.features.shape, (6, 12))
        self.assertEqual(dataset.feature_names[:4], (
            "node_count",
            "edge_count",
            "window_duration_seconds",
            "topology_available",
        ))
        self.assertEqual(dataset.feature_names[4], "node.flow_count.mean")
        self.assertEqual(dataset.features[0, 0:4].tolist(), [2.0, 1.0, 10.0, 1.0])
        self.assertTrue(np.all(np.diff(dataset.timestamps) >= 0))

    def test_scaler_is_fit_only_on_past_training_windows(self) -> None:
        dataset = flatten_graph_sequence(load_graph_sequence(sequence_payload(10)))
        split = time_based_split(dataset, test_fraction=0.2)

        self.assertEqual(split.x_train.shape[0], 8)
        self.assertEqual(split.x_test.shape[0], 2)
        self.assertLess(split.train_timestamps[-1], split.test_timestamps[0])
        np.testing.assert_allclose(split.x_train.mean(axis=0), 0.0, atol=1e-12)

    def test_training_evaluation_and_artifact_persistence(self) -> None:
        sequence = load_graph_sequence(sequence_payload())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = run_baselines(
                sequence,
                results_directory=root / "results",
                weights_directory=root / "weights",
                test_fraction=0.2,
            )

            self.assertIn("false_positive_rate", run.metrics["binary"])
            self.assertEqual(
                len(run.metrics["stage"]["confusion_matrix"]), 6
            )
            self.assertTrue((root / "results" / "baseline_metrics.json").is_file())
            self.assertTrue(
                (root / "results" / "baseline_binary_confusion_matrix.csv").is_file()
            )
            self.assertTrue((root / "weights" / "baseline_scaler.joblib").is_file())
            self.assertTrue((root / "weights" / "baseline_binary_lr.joblib").is_file())
            self.assertTrue((root / "weights" / "baseline_stage_lr.joblib").is_file())


if __name__ == "__main__":
    unittest.main()
