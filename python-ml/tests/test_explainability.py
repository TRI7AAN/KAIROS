"""Unit tests for causal explainability helpers and the Phase 42 schema."""

from __future__ import annotations

import unittest

from explain.shap_explain import (
    FeatureContribution,
    build_explanation,
    temporal_context,
)


class ExplainabilityTest(unittest.TestCase):
    def test_temporal_context_is_causal(self):
        values = temporal_context([0.2, 0.4, 0.9], position=2, total=3)
        self.assertEqual(values[0], 1.0)
        self.assertAlmostEqual(values[1], 0.4)
        self.assertAlmostEqual(values[2], 0.3)
        self.assertAlmostEqual(values[3], 0.1)
        self.assertAlmostEqual(values[4], 0.4)

    def test_first_temporal_context_has_zero_history(self):
        self.assertEqual(
            temporal_context([0.8], position=0, total=1).tolist(),
            [0.0, 0.0, 0.0, 0.0, 0.0],
        )

    def test_phase42_schema_limits_features_to_five(self):
        contributions = [
            FeatureContribution(f"f{index}", float(index), 0.1)
            for index in range(7)
        ]
        result = build_explanation(
            probability=0.75,
            predicted_stage="INITIAL_ACCESS",
            contributions=contributions,
            attention_summary={"context_windows": 4},
        )
        self.assertEqual(set(result), {
            "probability", "predicted_stage", "top_5_features",
            "attention_summary",
        })
        self.assertEqual(len(result["top_5_features"]), 5)

    def test_invalid_probability_is_rejected(self):
        with self.assertRaises(ValueError):
            build_explanation(
                probability=1.1,
                predicted_stage="IMPACT",
                contributions=[],
                attention_summary={},
            )


if __name__ == "__main__":
    unittest.main()
