package com.networkwm.narrative;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.networkwm.bridge.PythonMlClient.AttentionSummary;
import com.networkwm.bridge.PythonMlClient.FeatureContribution;
import com.networkwm.bridge.PythonMlClient.PredictionResponse;
import com.networkwm.bridge.PythonMlClient.Rollout;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GeminiNarrativeServiceTest {
    @Test
    void unconfiguredServiceReportsNotConfigured() {
        GeminiNarrativeService service = new GeminiNarrativeService(
                "", "gemini-2.5-flash-lite",
                (key, model, prompt) -> "never",
                new ObjectMapper());

        assertFalse(service.isConfigured());
    }

    @Test
    void generateWithoutKeyThrowsWithHelpfulMessage() {
        GeminiNarrativeService service = new GeminiNarrativeService(
                "   ", "gemini-2.5-flash-lite",
                (key, model, prompt) -> "never",
                new ObjectMapper());

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> service.generate(prediction()));
        assertTrue(error.getMessage().contains("GEMINI_API_KEY"));
    }

    @Test
    void emptyGeminiResponseThrows() {
        GeminiNarrativeService service = new GeminiNarrativeService(
                "test-key", "gemini-2.5-flash-lite",
                (key, model, prompt) -> "   ",
                new ObjectMapper());

        assertThrows(
                IllegalStateException.class,
                () -> service.generate(prediction()));
    }

    @Test
    void longResponseIsTruncatedToBound() {
        String oversized = "x".repeat(5_000);
        GeminiNarrativeService service = new GeminiNarrativeService(
                "test-key", "gemini-2.5-flash-lite",
                (key, model, prompt) -> oversized,
                new ObjectMapper());

        LocalNarrativeService.Narrative result = service.generate(prediction());

        assertEquals("gemini-online", result.mode());
        assertEquals(4_000, result.text().length());
    }

    @Test
    void nullPredictionIsRejected() {
        GeminiNarrativeService service = new GeminiNarrativeService(
                "test-key", "gemini-2.5-flash-lite",
                (key, model, prompt) -> "ok",
                new ObjectMapper());

        assertThrows(
                NullPointerException.class,
                () -> service.generate(null));
    }

    private static PredictionResponse prediction() {
        return new PredictionResponse(
                "kairos.prediction.v1",
                0.73,
                "INITIAL_ACCESS",
                List.of(new FeatureContribution("flow_count", 4.0, 0.2)),
                new AttentionSummary(8, List.of(), 0.0),
                new Rollout(
                        3,
                        List.of(0.73, 0.75, 0.78),
                        List.of("INITIAL_ACCESS", "INITIAL_ACCESS", "IMPACT"),
                        0.78),
                140.0,
                "ok",
                java.util.Map.of());
    }
}
