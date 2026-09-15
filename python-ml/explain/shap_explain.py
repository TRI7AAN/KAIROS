"""SHAP explanations via a distilled tabular surrogate model.

Intended responsibility (deferred to later phases):
  - Train a distilled gradient-boosted tree (or shallow MLP) on flattened
    features to approximate the world model's forecast output.
  - Run KernelSHAP / TreeSHAP on the surrogate and rank which flags,
    ports, or flow statistics contributed most to a prediction.

TODO: implement in Phase 6 (SHAP surrogate + integration).
"""
# TODO: implement in Phase 6
