package com.networkwm.narrative;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.networkwm.bridge.PythonMlClient.AttentionSummary;
import com.networkwm.bridge.PythonMlClient.FeatureContribution;
import com.networkwm.bridge.PythonMlClient.PredictionResponse;
import com.networkwm.bridge.PythonMlClient.Rollout;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NarrativeModeServiceTest {
    @Test
    void geminiUsesStructuredPredictionWithoutChangingIt() {
        AtomicReference<String> prompt = new AtomicReference<>();
        GeminiNarrativeService gemini = new GeminiNarrativeService(
                "test-key",
                "test-model",
                (key, model, value) -> {
                    assertEquals("test-key", key);
                    assertEquals("test-model", model);
                    prompt.set(value);
                    return "  Forecast briefing.  ";
                },
                new ObjectMapper());

        LocalNarrativeService.Narrative result = gemini.generate(prediction());

        assertEquals("gemini-online", result.mode());
        assertEquals("Forecast briefing.", result.text());
        assertTrue(prompt.get().contains("\"probability\":0.73"));
        assertTrue(prompt.get().contains("Do not claim"));
    }

    @Test
    void offlineIsDefaultEvenWhenGeminiHasAKey() {
        GeminiNarrativeService gemini = new GeminiNarrativeService(
                "test-key", "test-model",
                (key, model, prompt) -> "online",
                new ObjectMapper());
        NarrativeModeService router = new NarrativeModeService(
                new LocalNarrativeService(), gemini, () -> false);

        assertEquals("offline-local", router.generate(prediction()).mode());
    }

    @Test
    void onlineFailureFallsBackToLocal() {
        GeminiNarrativeService gemini = new GeminiNarrativeService(
                "test-key", "test-model",
                (key, model, prompt) -> {
                    throw new IllegalStateException("simulated outage");
                },
                new ObjectMapper());
        NarrativeModeService router = new NarrativeModeService(
                new LocalNarrativeService(), gemini, () -> true);

        assertEquals(
                "offline-local-fallback",
                router.generate(prediction()).mode());
    }

    private static PredictionResponse prediction() {
        return new PredictionResponse(
                "kairos.prediction.v1",
                0.73,
                "INITIAL_ACCESS",
                List.of(new FeatureContribution(
                        "flow_count", 4.0, 0.2)),
                new AttentionSummary(8, List.of(), 0.0),
                new Rollout(
                        3,
                        List.of(0.73, 0.75, 0.78),
                        List.of(
                                "INITIAL_ACCESS",
                                "INITIAL_ACCESS",
                                "IMPACT"),
                        0.78),
                140.0,
                "ok",
                java.util.Map.of());
    }
}
