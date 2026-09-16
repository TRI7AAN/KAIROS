"""Validated loader for the versioned Java host-flow graph contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any, Mapping

import torch
from torch_geometric.data import Data

CONTRACT_VERSION = "kairos.sequence.v1"
GRAPH_SCHEMA_VERSION = "kairos.graph.v1"
STAGE_TO_INDEX = {
    "RECONNAISSANCE": 0,
    "INITIAL_ACCESS": 1,
    "LATERAL_MOVEMENT": 2,
    "COMMAND_AND_CONTROL": 3,
    "EXFILTRATION": 4,
    "IMPACT": 5,
    "NONE": -1,
}


class GraphContractError(ValueError):
    """Raised when Java graph JSON violates the versioned wire contract."""


@dataclass(frozen=True)
class LoadedGraphSequence:
    contract_version: str
    node_feature_names: tuple[str, ...]
    edge_feature_names: tuple[str, ...]
    graphs: tuple[Data, ...]


def load_graph_sequence(
    source: str | Path | Mapping[str, Any],
) -> LoadedGraphSequence:
    """Load, validate, and tensorize one ordered graph sequence."""
    payload = _read_payload(source)
    _require(payload.get("contractVersion") == CONTRACT_VERSION,
             f"unsupported contractVersion: {payload.get('contractVersion')!r}")

    node_features = _feature_schema(payload, "nodeFeatureNames")
    edge_features = _feature_schema(payload, "edgeFeatureNames")
    windows = payload.get("windows")
    _require(isinstance(windows, list), "windows must be a list")

    graphs: list[Data] = []
    previous_start: datetime | None = None
    for index, window in enumerate(windows):
        _require(isinstance(window, Mapping), f"window {index} must be an object")
        _require(window.get("schemaVersion") == GRAPH_SCHEMA_VERSION,
                 f"window {index} has unsupported schemaVersion")
        start = _parse_timestamp(window.get("windowStart"), "windowStart", index)
        end = _parse_timestamp(window.get("windowEnd"), "windowEnd", index)
        _require(start < end, f"window {index} has a non-positive duration")
        if previous_start is not None:
            _require(start >= previous_start, "windows are not time ordered")
        previous_start = start
        graphs.append(_to_pyg(
            window, node_features, edge_features, start, end, index))

    return LoadedGraphSequence(
        contract_version=CONTRACT_VERSION,
        node_feature_names=node_features,
        edge_feature_names=edge_features,
        graphs=tuple(graphs),
    )


def load_graph_sequences(
    sources: list[str | Path | Mapping[str, Any]],
) -> LoadedGraphSequence:
    """Load day-level contracts and join them without changing feature order."""
    if not sources:
        raise GraphContractError("at least one graph sequence is required")
    loaded = [load_graph_sequence(source) for source in sources]
    node_schema = loaded[0].node_feature_names
    edge_schema = loaded[0].edge_feature_names
    graphs: list[Data] = []
    previous_epoch: float | None = None
    for sequence in loaded:
        _require(
            sequence.node_feature_names == node_schema,
            "node feature schemas differ between sequences",
        )
        _require(
            sequence.edge_feature_names == edge_schema,
            "edge feature schemas differ between sequences",
        )
        for graph in sequence.graphs:
            epoch = float(graph.window_start_epoch.item())
            _require(
                previous_epoch is None or epoch >= previous_epoch,
                "joined graph sequences are not time ordered",
            )
            previous_epoch = epoch
            graphs.append(graph)
    return LoadedGraphSequence(
        CONTRACT_VERSION, node_schema, edge_schema, tuple(graphs)
    )


def _read_payload(source: str | Path | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        return source
    path = Path(source)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GraphContractError(f"unable to read graph contract: {path}") from error
    _require(isinstance(payload, Mapping), "root JSON value must be an object")
    return payload


def _feature_schema(
    payload: Mapping[str, Any], field: str
) -> tuple[str, ...]:
    values = payload.get(field)
    _require(isinstance(values, list), f"{field} must be a list")
    _require(all(isinstance(value, str) and value for value in values),
             f"{field} entries must be non-empty strings")
    _require(len(values) == len(set(values)), f"{field} entries must be unique")
    return tuple(values)


def _to_pyg(
    window: Mapping[str, Any],
    node_schema: tuple[str, ...],
    edge_schema: tuple[str, ...],
    start: datetime,
    end: datetime,
    window_index: int,
) -> Data:
    nodes = window.get("nodes")
    edges = window.get("edges")
    _require(isinstance(nodes, list), f"window {window_index} nodes must be a list")
    _require(isinstance(edges, list), f"window {window_index} edges must be a list")

    node_ids: list[str] = []
    node_rows: list[list[float]] = []
    node_index: dict[str, int] = {}
    for node in nodes:
        _require(isinstance(node, Mapping), "node must be an object")
        node_id = node.get("id")
        _require(isinstance(node_id, str) and node_id, "node id must be non-empty")
        _require(node_id not in node_index, f"duplicate node id: {node_id}")
        node_index[node_id] = len(node_ids)
        node_ids.append(node_id)
        node_rows.append(_feature_vector(node.get("features"), node_schema, "node"))

    edge_ids: list[str] = []
    edge_pairs: list[list[int]] = []
    edge_rows: list[list[float]] = []
    for edge in edges:
        _require(isinstance(edge, Mapping), "edge must be an object")
        edge_id = edge.get("id")
        source = edge.get("source")
        destination = edge.get("destination")
        _require(isinstance(edge_id, str) and edge_id, "edge id must be non-empty")
        _require(edge_id not in edge_ids, f"duplicate edge id: {edge_id}")
        _require(source in node_index and destination in node_index,
                 f"edge {edge_id} references an unknown node")
        edge_ids.append(edge_id)
        edge_pairs.append([node_index[source], node_index[destination]])
        edge_rows.append(_feature_vector(
            edge.get("features"), edge_schema, "edge"))

    label = window.get("label")
    _require(isinstance(label, Mapping), "window label must be an object")
    infiltration = label.get("infiltration")
    stage = label.get("stage")
    _require(isinstance(infiltration, bool), "infiltration label must be boolean")
    _require(stage in STAGE_TO_INDEX, f"unsupported attack stage: {stage!r}")

    x = torch.tensor(node_rows, dtype=torch.float32)
    if not node_rows:
        x = torch.empty((0, len(node_schema)), dtype=torch.float32)
    edge_index = (
        torch.tensor(edge_pairs, dtype=torch.long).t().contiguous()
        if edge_pairs else torch.empty((2, 0), dtype=torch.long)
    )
    edge_attr = torch.tensor(edge_rows, dtype=torch.float32)
    if not edge_rows:
        edge_attr = torch.empty((0, len(edge_schema)), dtype=torch.float32)

    data = Data(
        x=x,
        edge_index=edge_index,
        edge_attr=edge_attr,
        y_infiltration=torch.tensor([float(infiltration)], dtype=torch.float32),
        y_stage=torch.tensor([STAGE_TO_INDEX[stage]], dtype=torch.long),
    )
    data.node_ids = tuple(node_ids)
    data.edge_ids = tuple(edge_ids)
    data.window_start = start.isoformat()
    data.window_end = end.isoformat()
    data.window_start_epoch = torch.tensor([start.timestamp()], dtype=torch.float64)
    data.window_duration_seconds = torch.tensor(
        [(end - start).total_seconds()], dtype=torch.float32)
    data.topology_available = bool(window.get("topologyAvailable", False))
    data.schema_version = GRAPH_SCHEMA_VERSION
    return data


def _feature_vector(
    raw_features: Any,
    schema: tuple[str, ...],
    kind: str,
) -> list[float]:
    _require(isinstance(raw_features, Mapping), f"{kind} features must be an object")
    undeclared = set(raw_features) - set(schema)
    _require(not undeclared, f"{kind} has undeclared features: {sorted(undeclared)}")
    row = [float(raw_features.get(name, 0.0)) for name in schema]
    _require(all(math.isfinite(value) for value in row),
             f"{kind} features must be finite")
    return row


def _parse_timestamp(raw: Any, field: str, index: int) -> datetime:
    _require(isinstance(raw, str), f"window {index} {field} must be an ISO timestamp")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise GraphContractError(
            f"window {index} has invalid {field}: {raw!r}") from error


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GraphContractError(message)
