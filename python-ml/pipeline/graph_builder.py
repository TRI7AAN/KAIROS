"""Host-flow graph snapshot builder.

Intended responsibility (deferred to later phases):
  - Convert each time window of traffic observations into a host-flow graph
    snapshot (hosts as nodes, flows as edges carrying feature vectors).
  - Serialize ordered graph sequences with next-state labels to .pt files
    (torch_geometric.data.Data per window).
  - Spot-check graph output against known attack timestamps.

TODO: implement in Phase 3 (graph construction).
"""
# TODO: implement in Phase 3
