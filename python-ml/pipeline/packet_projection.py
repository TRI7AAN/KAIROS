"""Loss-aware packet-to-CIC projection for frozen-model inference.

The trained checkpoint consumes the exact CIC aggregate schema. Packet capture
cannot reconstruct every CICFlowMeter field, so this module maps only directly
observable quantities and fills unavailable fields with zero. The drift guard
then labels the projected sample; callers must surface that quality signal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

import numpy as np


def _schema_from_surrogate(
    feature_names: Sequence[str],
) -> tuple[list[str], list[str]]:
    node_names: list[str] = []
    edge_names: list[str] = []
    for name in feature_names:
        if name.startswith("node."):
            target = node_names
            encoded = name[len("node.") :]
        elif name.startswith("edge."):
            target = edge_names
            encoded = name[len("edge.") :]
        else:
            continue
        base = encoded.rsplit(".", 1)[0]
        if not target or target[-1] != base:
            target.append(base)
    return node_names, edge_names


def _number(features: Mapping[str, Any], name: str) -> float:
    value = features.get(name, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"packet feature {name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"packet feature {name} must be finite")
    return result


def _flow_values(features: Mapping[str, Any]) -> dict[str, float]:
    packets = max(0.0, _number(features, "packet.packet_count"))
    duration = max(0.0, _number(features, "packet.duration_micros"))
    duration_seconds = max(duration / 1_000_000.0, 1e-9)
    payload_mean = max(0.0, _number(features, "packet.payload_size_mean"))
    payload_std = max(0.0, _number(features, "packet.payload_size_stddev"))
    payload_bytes = packets * payload_mean
    packet_rate = packets / duration_seconds if duration > 0.0 else packets
    byte_rate = payload_bytes / duration_seconds if duration > 0.0 else payload_bytes
    return {
        "dst_port": max(0.0, _number(features, "destination_port")),
        "protocol": max(0.0, _number(features, "protocol")),
        "flow_duration": duration,
        "flow_pkts_s": packet_rate,
        "flow_byts_s": byte_rate,
        "tot_fwd_pkts": packets,
        "subflow_fwd_pkts": packets,
        "fwd_act_data_pkts": packets,
        "totlen_fwd_pkts": payload_bytes,
        "subflow_fwd_byts": payload_bytes,
        "fwd_pkt_len_mean": payload_mean,
        "fwd_pkt_len_std": payload_std,
        "fwd_seg_size_avg": payload_mean,
        "pkt_len_mean": payload_mean,
        "pkt_len_std": payload_std,
        "pkt_len_var": payload_std * payload_std,
        "pkt_size_avg": payload_mean,
        "fwd_pkts_s": packet_rate,
    }


def _aggregate(values: Sequence[float], statistic: str) -> float:
    data = np.asarray(values if values else [0.0], dtype=np.float64)
    if statistic == "mean":
        return float(data.mean())
    if statistic == "std":
        return float(data.std())
    if statistic == "max":
        return float(data.max())
    if statistic == "sum":
        return float(data.sum())
    raise ValueError(f"unsupported CIC aggregate statistic: {statistic}")


def project_packet_contract(
    contract: Mapping[str, Any],
    surrogate_feature_names: Sequence[str],
) -> tuple[dict[str, Any], bool]:
    """Return an exact CIC-schema contract when packet.* input is detected."""
    incoming_edge_names = list(contract.get("edgeFeatureNames", []))
    if not any(name.startswith("packet.") for name in incoming_edge_names):
        return dict(contract), False

    node_names, edge_names = _schema_from_surrogate(surrogate_feature_names)
    projected_windows: list[dict[str, Any]] = []
    evidence_windows: list[dict[str, Any]] = []
    for window in contract.get("windows", []):
        if not isinstance(window, Mapping):
            raise ValueError("packet contract windows must be objects")
        flows: list[dict[str, float]] = []
        destination_ports: set[int] = set()
        total_bytes = 0.0
        packet_features: list[Mapping[str, Any]] = []
        for edge in window.get("edges", []):
            if not isinstance(edge, Mapping):
                raise ValueError("packet contract edges must be objects")
            features = edge.get("features", {})
            if not isinstance(features, Mapping):
                raise ValueError("packet edge features must be an object")
            flow = _flow_values(features)
            flows.append(flow)
            packet_features.append(features)
            total_bytes += flow["totlen_fwd_pkts"]
            port = int(flow["dst_port"])
            if port > 0:
                destination_ports.add(port)

        scan_ports = max(
            (
                _number(node.get("features", {}),
                        "packet.capture_scan_unique_destination_ports")
                for node in window.get("nodes", [])
                if isinstance(node, Mapping)
                and isinstance(node.get("features", {}), Mapping)
            ),
            default=0.0,
        )

        edge_features: dict[str, float] = {}
        for encoded in edge_names:
            base, statistic = encoded.rsplit(".", 1)
            edge_features[encoded] = _aggregate(
                [flow.get(base, 0.0) for flow in flows],
                statistic,
            )

        node_source = {
            "ack_count": 0.0,
            "flow_count": float(len(flows)),
            "inbound_bytes": 0.0,
            "outbound_bytes": total_bytes,
            "syn_ack_ratio": 0.0,
            "syn_count": 0.0,
            "topology_available": 0.0,
            "unique_destination_ports": max(
                float(len(destination_ports)), scan_ports
            ),
        }
        node_features = {name: node_source.get(name, 0.0) for name in node_names}
        evidence_windows.append({
            "window_start": window.get("windowStart"),
            "empty_window": len(flows) == 0,
            "packet_count": sum(
                _number(item, "packet.packet_count")
                for item in packet_features
            ),
            "ttl_mean": _aggregate([
                _number(item, "packet.ttl_mean")
                for item in packet_features
            ], "mean"),
            "ttl_variance_mean": _aggregate([
                _number(item, "packet.ttl_variance")
                for item in packet_features
            ], "mean"),
            "tcp_window_trend_mean": _aggregate([
                _number(item, "packet.tcp_window_trend")
                for item in packet_features
            ], "mean"),
            "fragment_count": sum(
                _number(item, "packet.fragment_count")
                for item in packet_features
            ),
            "retransmission_count": sum(
                _number(item, "packet.retransmission_count")
                for item in packet_features
            ),
            "truncated_packet_count": sum(
                _number(item, "packet.truncated_packet_count")
                for item in packet_features
            ),
            "capture_scan_unique_destination_ports": scan_ports,
        })
        projected_windows.append({
            "schemaVersion": window.get("schemaVersion", "kairos.graph.v1"),
            "windowStart": window.get("windowStart"),
            "windowEnd": window.get("windowEnd"),
            "topologyAvailable": False,
            "nodes": [{"id": "__network__", "features": node_features}],
            "edges": [{
                "id": "packet-projection-edge",
                "source": "__network__",
                "destination": "__network__",
                "features": edge_features,
                "actualTopology": False,
                "vectorFallback": True,
            }],
            "label": window.get(
                "label", {"infiltration": False, "stage": "NONE"}
            ),
        })

    projected = {
        "contractVersion": contract.get("contractVersion", "kairos.sequence.v1"),
        "nodeFeatureNames": node_names,
        "edgeFeatureNames": edge_names,
        "windows": projected_windows,
        "inputProjection": "packet-to-cic-v1",
        "inputProjectionDetail": {
            "projection": "packet-to-cic-v1",
            "model_input": (
                "CIC-compatible packet aggregates; additional packet and "
                "capture-level scan signals are retained as analyst evidence"
            ),
            "preserved_empty_windows": sum(
                1 for item in evidence_windows if item["empty_window"]
            ),
            "windows": evidence_windows,
            "unmapped_model_features": [
                "ttl_mean", "ttl_variance_mean", "tcp_window_trend_mean",
                "fragment_count", "retransmission_count",
                "truncated_packet_count",
                "capture_scan_unique_destination_ports",
            ],
        },
    }
    return projected, True
