# KAIROS graph sequence contract v1

The Java engine exports ordered traffic windows as `kairos.sequence.v1`. Each
window uses the graph schema `kairos.graph.v1`, and the Python pipeline rejects
unknown versions instead of silently accepting incompatible data.

## Shape

- `nodeFeatureNames` and `edgeFeatureNames` define the only valid feature names
  and their tensor column order. Missing declared values are filled with zero.
- Every node has a stable host ID and finite numeric features.
- Every directed edge references existing source and destination nodes and has
  finite flow/packet features.
- Window timestamps are ISO-8601, have positive duration, and are time ordered.
- Each label contains `infiltration` (binary) and a named attack `stage`.

## Labels

The binary target is `0` for benign and `1` for malicious. The six-class stage
head maps `RECONNAISSANCE`, `INITIAL_ACCESS`, `LATERAL_MOVEMENT`,
`COMMAND_AND_CONTROL`, `EXFILTRATION`, and `IMPACT` to indices `0..5`.
`NONE` maps to `-1` and must be ignored by the stage loss; it remains a valid
negative example for the binary infiltration head.

## Topology availability

PCAP and enriched flow sources produce host-to-host topology. The official
CIC-IDS2017 processed CSV files do not contain source or destination IPs, so
those windows intentionally set `topologyAvailable` to `false` and use one
`__network__` node with self-loop flow edges. KAIROS never fabricates endpoint
identities. This preserves temporal feature/label information while clearly
distinguishing vector-mode data from real graph-mode data.
