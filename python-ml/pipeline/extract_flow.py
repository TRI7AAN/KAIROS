"""Flow-level feature extraction (CICFlowMeter-style NetFlow/IPFIX features).

Intended responsibility (deferred to later phases):
  - Parse raw CSV/flow records into per-flow records (IPs/ports, TCP flag
    bitmask, protocol, bytes/packets per flow, duration, IAT mean/variance/
    max, bidirectional ratios).
  - Normalize headers, drop non-feature columns, cast dtypes, clip/drop
    Infinity/NaN rows.
  - Attach MITRE ATT&CK stage labels derived from published attack timelines.

TODO: implement in Phase 2 (flow CSV parser + stage labels).
"""
# TODO: implement in Phase 2
