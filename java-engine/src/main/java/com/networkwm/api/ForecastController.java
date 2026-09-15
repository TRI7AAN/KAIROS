package com.networkwm.api;

/**
 * REST controller exposing the forecast API.
 *
 * Intended responsibility (deferred to later phases):
 *   - Expose the public /forecast endpoint that accepts uploaded PCAP/CSV data,
 *     drives the ingestion/windowing/graph pipeline, calls the python-ml
 *     service, optionally invokes the Gemini narrative service, and returns
 *     the full forecast response (probability, stage, SHAP, narrative).
 *
 *   - The Python /predict endpoint is internal to the Java-to-Python bridge.
 *
 * TODO: implement in Phase 46 (REST API) and Phase 49 (narrative wiring).
 */
public class ForecastController {
    // TODO: implement in Phase 46/49.
}
