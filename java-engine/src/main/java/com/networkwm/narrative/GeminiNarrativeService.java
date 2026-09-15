package com.networkwm.narrative;

/**
 * Gemini narrative service.
 *
 * Intended responsibility (deferred to later phases):
 *   - Convert the structured technical output from the python-ml service
 *     (probability score, predicted MITRE stage, top SHAP features) into
 *     a natural-language SOC analyst briefing via the Google Gen AI Java SDK.
 *   - This is a human-facing layer on top of, never a replacement for, the
 *     mandatory SHAP/attention explainability.
 *
 * TODO: implement in Phase 5 (Gemini narrative integration).
 */
public class GeminiNarrativeService {
    // TODO: implement in Phase 5.
}
