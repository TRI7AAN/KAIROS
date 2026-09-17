package com.networkwm.narrative;

import com.networkwm.bridge.PythonMlClient.FeatureContribution;
import com.networkwm.bridge.PythonMlClient.PredictionResponse;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.stream.Collectors;

/** Deterministic offline analyst narrative; performs no network calls. */
@Service
public final class LocalNarrativeService {
    public Narrative generate(PredictionResponse prediction) {
        Objects.requireNonNull(prediction, "prediction");
        double percentage = prediction.probability() * 100.0;
        String severity = percentage >= 80.0 ? "critical"
                : percentage >= 60.0 ? "high"
                : percentage >= 40.0 ? "moderate" : "low";
        String stage = prediction.predictedStage()
                .toLowerCase(Locale.ROOT).replace('_', ' ');
        List<String> positiveDrivers = prediction.topFeatures().stream()
                .filter(feature -> feature.shapValue() > 0.0)
                .limit(3)
                .map(FeatureContribution::feature)
                .toList();
        String drivers = positiveDrivers.isEmpty()
                ? "No positive SHAP driver dominated this forecast"
                : "Primary positive drivers were "
                        + positiveDrivers.stream().collect(
                                Collectors.joining(", "));
        String rollout = prediction.rollout() == null
                ? ""
                : String.format(
                        Locale.ROOT,
                        " The %d-window rollout peaked at %.1f%%.",
                        prediction.rollout().steps(),
                        prediction.rollout().maxProbability() * 100.0);
        String text = String.format(
                Locale.ROOT,
                "%s risk: %.1f%% probability of malicious activity, with the "
                        + "next state classified as %s. %s.%s Review the "
                        + "flagged flows and temporal context before escalation.",
                capitalize(severity),
                percentage,
                stage,
                drivers,
                rollout);
        return new Narrative("offline-local", text);
    }

    private static String capitalize(String value) {
        return Character.toUpperCase(value.charAt(0)) + value.substring(1);
    }

    public record Narrative(String mode, String text) {
    }
}
