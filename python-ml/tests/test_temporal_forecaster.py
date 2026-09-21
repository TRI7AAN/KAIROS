"""Tests for the deployed PS-aligned temporal forecast head."""

from __future__ import annotations

import unittest

import numpy as np

from pipeline.temporal_forecaster import (
    TemporalForecasterError,
    predict_temporal_forecasts,
    temporal_feature_names,
    temporal_vector,
)


class _BinaryModel:
    def predict_proba(self, rows):
        return np.asarray([[0.2, 0.8] for _ in rows])


class _StageModel:
    def predict(self, rows):
        return np.asarray([3 for _ in rows])


class _Dataset:
    def __init__(self, features):
        self.features = features
        self.feature_names = ("a", "b")


class _Sequence:
    def __init__(self, count):
        self.graphs = tuple(object() for _ in range(count))


class TemporalForecasterTest(unittest.TestCase):
    def test_temporal_vector_is_backward_only_summary(self):
        values = np.asarray([[1.0, 4.0], [3.0, 8.0]])
        row = temporal_vector(values)
        np.testing.assert_allclose(
            row,
            [3.0, 8.0, 2.0, 6.0, 1.0, 2.0, 2.0, 4.0, 2.0, 4.0],
        )

    def test_vector_rejects_single_window(self):
        with self.assertRaises(TemporalForecasterError):
            temporal_vector(np.asarray([[1.0, 2.0]]))

    def test_feature_names_match_summary_order(self):
        names = temporal_feature_names(("a", "b"))
        self.assertEqual(names[0], "current.a")
        self.assertEqual(names[-1], "history_abs_velocity.b")

    def test_insufficient_history_returns_typed_unavailable(self):
        result = predict_temporal_forecasts(
            _Sequence(2),
            {
                "history_windows": 6,
                "models_by_horizon": {},
            },
        )
        self.assertEqual(result["available"], False)
        self.assertEqual(result["reason"], "insufficient_history")


if __name__ == "__main__":
    unittest.main()
