"""Memory-bounded CTU-13 labeled bidirectional-flow window adapter."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from pathlib import Path

import numpy as np

FEATURE_NAMES = (
    "flow_count",
    "unique_source_count",
    "unique_destination_count",
    "unique_destination_port_count",
    "duration_mean",
    "duration_std",
    "duration_max",
    "duration_sum",
    "packet_count_mean",
    "packet_count_std",
    "packet_count_max",
    "packet_count_sum",
    "byte_count_mean",
    "byte_count_std",
    "byte_count_max",
    "byte_count_sum",
    "source_byte_sum",
    "destination_byte_sum",
    "payload_bytes_per_packet_mean",
    "flow_bytes_per_second_mean",
    "flow_packets_per_second_mean",
    "tcp_fraction",
    "udp_fraction",
    "icmp_fraction",
    "bidirectional_fraction",
)
TIME_FORMAT = "%Y/%m/%d %H:%M:%S.%f"


@dataclass(frozen=True)
class Ctu13Windows:
    source: str
    window_seconds: int
    start_epochs: np.ndarray
    features: np.ndarray
    malicious: np.ndarray
    malicious_flow_count: np.ndarray
    rows: int


@dataclass
class _Stats:
    count: int = 0
    malicious_count: int = 0
    sources: set[str] = field(default_factory=set)
    destinations: set[str] = field(default_factory=set)
    destination_ports: set[int] = field(default_factory=set)
    protocol_counts: dict[str, int] = field(default_factory=dict)
    bidirectional: int = 0
    duration: list[float] = field(default_factory=list)
    packets: list[float] = field(default_factory=list)
    bytes_: list[float] = field(default_factory=list)
    source_bytes: list[float] = field(default_factory=list)
    payload_per_packet: list[float] = field(default_factory=list)
    bytes_per_second: list[float] = field(default_factory=list)
    packets_per_second: list[float] = field(default_factory=list)

    def accept(self, row: dict[str, str]) -> None:
        duration = _number(row, "Dur")
        packets = _number(row, "TotPkts")
        total_bytes = _number(row, "TotBytes")
        source_bytes = min(total_bytes, _number(row, "SrcBytes"))
        safe_duration = max(duration, 1e-9)
        safe_packets = max(packets, 1.0)
        protocol = row.get("Proto", "").strip().lower()
        label = row.get("Label", "").strip()

        self.count += 1
        self.malicious_count += int(label.startswith("flow=From-Botnet"))
        self.sources.add(row.get("SrcAddr", "").strip())
        self.destinations.add(row.get("DstAddr", "").strip())
        port = _port(row.get("Dport", ""))
        if port is not None:
            self.destination_ports.add(port)
        self.protocol_counts[protocol] = self.protocol_counts.get(protocol, 0) + 1
        self.bidirectional += int("<->" in row.get("Dir", ""))
        self.duration.append(duration)
        self.packets.append(packets)
        self.bytes_.append(total_bytes)
        self.source_bytes.append(source_bytes)
        self.payload_per_packet.append(total_bytes / safe_packets)
        self.bytes_per_second.append(total_bytes / safe_duration)
        self.packets_per_second.append(packets / safe_duration)

    def vector(self) -> list[float]:
        destination_bytes = sum(self.bytes_) - sum(self.source_bytes)
        return [
            float(self.count),
            float(len(self.sources)),
            float(len(self.destinations)),
            float(len(self.destination_ports)),
            *_summary(self.duration),
            *_summary(self.packets),
            *_summary(self.bytes_),
            float(sum(self.source_bytes)),
            float(max(0.0, destination_bytes)),
            float(np.mean(self.payload_per_packet)) if self.count else 0.0,
            float(np.mean(self.bytes_per_second)) if self.count else 0.0,
            float(np.mean(self.packets_per_second)) if self.count else 0.0,
            self.protocol_counts.get("tcp", 0) / max(self.count, 1),
            self.protocol_counts.get("udp", 0) / max(self.count, 1),
            self.protocol_counts.get("icmp", 0) / max(self.count, 1),
            self.bidirectional / max(self.count, 1),
        ]


def load_ctu13_windows(
    path: str | Path,
    *,
    window_seconds: int = 10,
) -> Ctu13Windows:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    source = Path(path)
    buckets: dict[int, _Stats] = {}
    rows = 0
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "StartTime", "Dur", "Proto", "SrcAddr", "Dir", "DstAddr",
            "Dport", "TotPkts", "TotBytes", "SrcBytes", "Label",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            missing = sorted(required - set(reader.fieldnames or ()))
            raise ValueError(f"CTU-13 flow file missing columns: {missing}")
        for row in reader:
            timestamp = datetime.strptime(
                row["StartTime"].strip(), TIME_FORMAT
            ).replace(tzinfo=timezone.utc)
            epoch = int(timestamp.timestamp())
            bucket = epoch - epoch % window_seconds
            buckets.setdefault(bucket, _Stats()).accept(row)
            rows += 1
    if not buckets:
        raise ValueError("CTU-13 flow file contains no rows")

    first, last = min(buckets), max(buckets)
    epochs = np.arange(first, last + window_seconds, window_seconds, dtype=np.int64)
    features = []
    labels = []
    malicious_counts = []
    for epoch in epochs:
        stats = buckets.get(int(epoch), _Stats())
        features.append(stats.vector())
        labels.append(int(stats.malicious_count > 0))
        malicious_counts.append(stats.malicious_count)
    matrix = np.asarray(features, dtype=np.float64)
    if matrix.shape[1] != len(FEATURE_NAMES) or not np.isfinite(matrix).all():
        raise ValueError("CTU-13 window features are invalid")
    return Ctu13Windows(
        source=str(source),
        window_seconds=window_seconds,
        start_epochs=epochs,
        features=matrix,
        malicious=np.asarray(labels, dtype=np.int64),
        malicious_flow_count=np.asarray(malicious_counts, dtype=np.int64),
        rows=rows,
    )


def _number(row: dict[str, str], name: str) -> float:
    raw = row.get(name, "").strip()
    try:
        value = float(raw or 0.0)
    except ValueError as error:
        raise ValueError(f"invalid CTU-13 numeric value for {name}: {raw!r}") from error
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"invalid CTU-13 numeric value for {name}: {raw!r}")
    return value


def _port(raw: str) -> int | None:
    value = raw.strip()
    if not value:
        return None
    try:
        port = int(value, 0)
    except ValueError:
        return None
    return port if 0 <= port <= 65535 else None


def _summary(values: list[float]) -> list[float]:
    if not values:
        return [0.0, 0.0, 0.0, 0.0]
    array = np.asarray(values, dtype=np.float64)
    return [
        float(array.mean()),
        float(array.std()),
        float(array.max()),
        float(array.sum()),
    ]
