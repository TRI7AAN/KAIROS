package com.networkwm.api;

/**
 * REST controller exposing the forecast API.
 *
 * Intended responsibility (deferred to later phases):
 *   - Expose the /predict endpoint that accepts uploaded PCAP/CSV data,
 *     drives the ingestion/windowing/graph pipeline, calls the python-ml
 *     service, optionally invokes the Gemini narrative service, and returns
 *     the full forecast response (probability, stage, SHAP, narrative).
 *
 * TODO: implement in Phase 4 (REST API) and Phase 5 (narrative wiring).
 */
public class ForecastController {
    // TODO: implement in Phase 4/5.
}
