package com.networkwm.bridge;

/**
 * REST client to the python-ml world-model service.
 *
 * Intended responsibility (deferred to later phases):
 *   - POST feature tensors (per-window graph snapshots) to the python-ml
 *     service's /predict endpoint.
 *   - Receive and deserialize the JSON response containing infiltration
 *     probability, predicted MITRE stage, and SHAP feature attributions.
 *
 * TODO: implement in Phase 4 (inter-service communication).
 */
public class PythonMlClient {
    // TODO: implement in Phase 4.
}
