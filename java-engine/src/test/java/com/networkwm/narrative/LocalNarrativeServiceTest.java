package com.networkwm.narrative;

import com.networkwm.bridge.PythonMlClient.AttentionSummary;
import com.networkwm.bridge.PythonMlClient.FeatureContribution;
import com.networkwm.bridge.PythonMlClient.PredictionResponse;
import com.networkwm.bridge.PythonMlClient.Rollout;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class LocalNarrativeServiceTest {
    @Test
    void producesOfflineEvidenceBoundNarrative() {
        PredictionResponse prediction = new PredictionResponse(
                "kairos.prediction.v1",
                0.73,
                "INITIAL_ACCESS",
                List.of(
                        new FeatureContribution("flow_count", 4.0, 0.2),
                        new FeatureContribution("benign_signal", 1.0, -0.1)),
                new AttentionSummary(8, List.of(), 0.0),
                new Rollout(
                        3, List.of(0.73, 0.75, 0.78),
                        List.of("INITIAL_ACCESS", "INITIAL_ACCESS", "IMPACT"),
                        0.78),
                140.0,
                "ok",
                java.util.Map.of());

        LocalNarrativeService.Narrative narrative =
                new LocalNarrativeService().generate(prediction);

        assertEquals("offline-local", narrative.mode());
        assertTrue(narrative.text().contains("73.0%"));
        assertTrue(narrative.text().contains("initial access"));
        assertTrue(narrative.text().contains("flow_count"));
        assertTrue(narrative.text().contains("78.0%"));
    }
}
