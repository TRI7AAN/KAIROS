"""Lightweight Flask REST service wrapping the world-model inference pipeline.

Intended responsibility (deferred to later phases):
  - Expose a /predict route that accepts a per-window feature tensor
    (dispatched from the java-engine REST client) and runs it through the
    GNN encoder + Temporal Transformer dynamics model + forecast heads.
  - Return a JSON payload containing infiltration probability, predicted
    MITRE stage, and SHAP feature attributions.

TODO: implement in Phase 3 (service wiring) and Phase 4 (model inference).
"""
# TODO: implement in Phase 3/4
