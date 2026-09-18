"""Flask API contract tests for Phase 44."""

from __future__ import annotations

import unittest

from app import create_app


class FakePredictionService:
    def __init__(self):
        self.calls = []

    def predict(self, contract, rollout_steps=3):
        self.calls.append((contract, rollout_steps))
        return {
            "artifact_version": "kairos.prediction.v1",
            "probability": 0.7,
            "predicted_stage": "INITIAL_ACCESS",
            "top_5_features": [],
            "attention_summary": {},
        }


class PredictionApiTest(unittest.TestCase):
    def setUp(self):
        self.service = FakePredictionService()
        self.client = create_app(self.service).test_client()

    def test_health_is_offline_and_does_not_load_model(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["offline"], True)
        self.assertEqual(self.service.calls, [])

    def test_predict_accepts_wrapped_contract_and_rollout(self):
        contract = {"contractVersion": "kairos.sequence.v1"}
        response = self.client.post(
            "/predict", json={"contract": contract, "rolloutSteps": 5})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["probability"], 0.7)
        self.assertEqual(self.service.calls, [(contract, 5)])

    def test_non_object_json_is_rejected(self):
        response = self.client.post("/predict", json=[1, 2, 3])
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_missing_surrogate_returns_503_not_500(self):
        client = create_app(
            surrogate_path="/tmp/kairos-test-missing-surrogate.joblib",
        ).test_client()
        contract = {"contractVersion": "kairos.sequence.v1"}
        response = client.post("/predict", json={"contract": contract})
        self.assertEqual(response.status_code, 503)
        self.assertIn(
            "explainability service unavailable",
            response.get_json()["error"],
        )


if __name__ == "__main__":
    unittest.main()
