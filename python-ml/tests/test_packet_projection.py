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
                "nodes": [],
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
                        "protocol": 6,
                    },
                }],
                "label": {"malicious": False, "stage": "NONE"},
            }],
        }

        projected, changed = project_packet_contract(packet, self.FEATURES)

        self.assertTrue(changed)
        self.assertEqual("packet-to-cic-v1", projected["inputProjection"])
        self.assertEqual(["flow_count", "topology_available"],
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

    def test_non_packet_contract_is_unchanged(self):
        contract = {"edgeFeatureNames": ["dst_port.mean"], "windows": []}
        projected, changed = project_packet_contract(contract, self.FEATURES)
        self.assertFalse(changed)
        self.assertEqual(contract, projected)


if __name__ == "__main__":
    unittest.main()
