"""Validation helpers for canonical flow features received from Java.

Intended responsibility (deferred to later phases):
  - Define and validate the ordered CICFlowMeter-style feature schema consumed
    by training and inference.
  - Reject malformed, non-finite, or schema-incompatible records before tensor
    conversion.
  - Raw CSV parsing, normalization, windowing, label attachment, and graph
    construction are owned by java-engine so there is one canonical pipeline.

TODO: implement alongside the serialization contract in Phase 11.
"""
# TODO: implement in Phase 11
