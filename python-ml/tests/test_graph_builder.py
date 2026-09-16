"""Cross-language contract tests for Java graph JSON consumed by Python."""

from __future__ import annotations

import copy
import unittest

from pipeline.graph_builder import GraphContractError, load_graph_sequence


def valid_payload() -> dict:
    return {
        "contractVersion": "kairos.sequence.v1",
        "nodeFeatureNames": ["flow_count"],
        "edgeFeatureNames": ["protocol", "packet.ttl_mean"],
        "windows": [
            {
                "schemaVersion": "kairos.graph.v1",
                "windowStart": "2026-01-01T00:00:00Z",
                "windowEnd": "2026-01-01T00:00:10Z",
                "topologyAvailable": True,
                "nodes": [
                    {"id": "10.0.0.1", "features": {"flow_count": 2.0}},
                    {"id": "10.0.0.2", "features": {"flow_count": 1.0}},
                ],
                "edges": [
                    {
                        "id": "flow-1",
                        "source": "10.0.0.1",
                        "destination": "10.0.0.2",
                        "features": {"protocol": 6.0, "packet.ttl_mean": 63.5},
                    }
                ],
                "label": {"infiltration": True, "stage": "INITIAL_ACCESS"},
            }
        ],
    }


class GraphBuilderTest(unittest.TestCase):
    def test_valid_contract_is_tensorized_in_declared_feature_order(self) -> None:
        sequence = load_graph_sequence(valid_payload())

        self.assertEqual(sequence.node_feature_names, ("flow_count",))
        self.assertEqual(
            sequence.edge_feature_names, ("protocol", "packet.ttl_mean")
        )
        graph = sequence.graphs[0]
        self.assertEqual(tuple(graph.x.shape), (2, 1))
        self.assertEqual(tuple(graph.edge_index.shape), (2, 1))
        self.assertEqual(tuple(graph.edge_attr.shape), (1, 2))
        self.assertEqual(graph.x.tolist(), [[2.0], [1.0]])
        self.assertEqual(graph.edge_attr.tolist(), [[6.0, 63.5]])
        self.assertEqual(graph.y_infiltration.item(), 1.0)
        self.assertEqual(graph.y_stage.item(), 1)
        self.assertTrue(graph.topology_available)

    def test_unknown_edge_endpoint_is_rejected(self) -> None:
        payload = copy.deepcopy(valid_payload())
        payload["windows"][0]["edges"][0]["destination"] = "missing-host"

        with self.assertRaisesRegex(GraphContractError, "unknown node"):
            load_graph_sequence(payload)

    def test_undeclared_and_nonfinite_features_are_rejected(self) -> None:
        payload = copy.deepcopy(valid_payload())
        payload["windows"][0]["nodes"][0]["features"]["surprise"] = 4.0
        with self.assertRaisesRegex(GraphContractError, "undeclared"):
            load_graph_sequence(payload)

        payload = copy.deepcopy(valid_payload())
        payload["windows"][0]["edges"][0]["features"]["protocol"] = float("nan")
        with self.assertRaisesRegex(GraphContractError, "finite"):
            load_graph_sequence(payload)


if __name__ == "__main__":
    unittest.main()
