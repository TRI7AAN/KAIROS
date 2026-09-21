"""Packet projection contract tests."""

from __future__ import annotations

import unittest

from pipeline.packet_projection import project_packet_contract


class PacketProjectionTest(unittest.TestCase):
    FEATURES = [
        "node.flow_count.mean",
        "node.flow_count.std",
        "node.flow_count.max",
        "node.flow_count.sum",
        "node.unique_destination_ports.mean",
        "node.unique_destination_ports.std",
        "node.unique_destination_ports.max",
        "node.unique_destination_ports.sum",
        "node.topology_available.mean",
        "node.topology_available.std",
        "node.topology_available.max",
        "node.topology_available.sum",
        "edge.dst_port.mean.mean",
        "edge.dst_port.mean.std",
        "edge.dst_port.mean.max",
        "edge.dst_port.mean.sum",
        "edge.flow_duration.sum.mean",
        "edge.flow_duration.sum.std",
        "edge.flow_duration.sum.max",
        "edge.flow_duration.sum.sum",
        "edge.tot_fwd_pkts.sum.mean",
        "edge.tot_fwd_pkts.sum.std",
        "edge.tot_fwd_pkts.sum.max",
        "edge.tot_fwd_pkts.sum.sum",
    ]

    def test_packet_contract_is_projected_without_inventing_topology(self):
        packet = {
            "contractVersion": "kairos.sequence.v1",
            "nodeFeatureNames": ["topology_available"],
            "edgeFeatureNames": [
                "destination_port",
                "packet.duration_micros",
                "packet.packet_count",
                "packet.payload_size_mean",
                "packet.payload_size_stddev",
                "protocol",
            ],
            "windows": [{
                "schemaVersion": "kairos.graph.v1",
                "windowStart": "2026-01-01T00:00:00Z",
                "windowEnd": "2026-01-01T00:00:10Z",
                "topologyAvailable": True,
                "nodes": [{
                    "id": "10.0.0.1",
                    "features": {
                        "topology_available": 1,
                        "packet.capture_scan_unique_destination_ports": 22,
                    },
                }],
                "edges": [{
                    "id": "flow-1",
                    "source": "10.0.0.1",
                    "destination": "10.0.0.2",
                    "features": {
                        "destination_port": 443,
                        "packet.duration_micros": 2_000_000,
                        "packet.packet_count": 4,
                        "packet.payload_size_mean": 100,
                        "packet.payload_size_stddev": 5,
                        "packet.ttl_mean": 63,
                        "packet.ttl_variance": 2,
                        "packet.tcp_window_trend": -1.5,
                        "packet.fragment_count": 1,
                        "packet.retransmission_count": 2,
                        "packet.truncated_packet_count": 3,
                        "protocol": 6,
                    },
                }],
                "label": {"malicious": False, "stage": "NONE"},
            }],
        }

        projected, changed = project_packet_contract(packet, self.FEATURES)

        self.assertTrue(changed)
        self.assertEqual("packet-to-cic-v1", projected["inputProjection"])
        self.assertEqual(["flow_count", "unique_destination_ports", "topology_available"],
                         projected["nodeFeatureNames"])
        self.assertEqual(
            ["dst_port.mean", "flow_duration.sum", "tot_fwd_pkts.sum"],
            projected["edgeFeatureNames"],
        )
        window = projected["windows"][0]
        self.assertFalse(window["topologyAvailable"])
        self.assertEqual("__network__", window["nodes"][0]["id"])
        edge = window["edges"][0]
        self.assertEqual(443.0, edge["features"]["dst_port.mean"])
        self.assertEqual(2_000_000.0,
                         edge["features"]["flow_duration.sum"])
        self.assertEqual(4.0, edge["features"]["tot_fwd_pkts.sum"])
        detail = projected["inputProjectionDetail"]
        self.assertEqual(0, detail["preserved_empty_windows"])
        self.assertEqual(22.0,
                         window["nodes"][0]["features"].get(
                             "unique_destination_ports"))
        evidence = detail["windows"][0]
        self.assertEqual(63.0, evidence["ttl_mean"])
        self.assertEqual(2.0, evidence["retransmission_count"])
        self.assertEqual(22.0,
                         evidence["capture_scan_unique_destination_ports"])
        unavailable = detail["unavailable_model_features"]
        self.assertIn("syn_count", unavailable["node"])
        self.assertIn("ack_count", unavailable["node"])
        self.assertNotIn("dst_port.mean", unavailable["edge"])
        self.assertNotIn("flow_duration.sum", unavailable["edge"])
        self.assertNotIn("tot_fwd_pkts.sum", unavailable["edge"])
        self.assertTrue(unavailable["note"])

    def test_non_packet_contract_is_unchanged(self):
        contract = {"edgeFeatureNames": ["dst_port.mean"], "windows": []}
        projected, changed = project_packet_contract(contract, self.FEATURES)
        self.assertFalse(changed)
        self.assertEqual(contract, projected)


if __name__ == "__main__":
    unittest.main()
