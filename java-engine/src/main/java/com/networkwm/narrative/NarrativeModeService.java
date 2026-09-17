package com.networkwm.narrative;

import com.networkwm.bridge.PythonMlClient.PredictionResponse;
import com.networkwm.narrative.LocalNarrativeService.Narrative;
import org.springframework.stereotype.Service;

import org.springframework.beans.factory.annotation.Autowired;
import java.util.Objects;
import java.util.function.BooleanSupplier;

/** Enforces offline-by-default narrative selection with safe fallback. */
@Service
public final class NarrativeModeService {
    private final LocalNarrativeService local;
    private final GeminiNarrativeService gemini;
    private final BooleanSupplier onlineRequested;

    @Autowired
    public NarrativeModeService(
            LocalNarrativeService local,
            GeminiNarrativeService gemini) {
        this(local, gemini, NarrativeModeService::configuredOnlineMode);
    }

    NarrativeModeService(
            LocalNarrativeService local,
            GeminiNarrativeService gemini,
            BooleanSupplier onlineRequested) {
        this.local = Objects.requireNonNull(local, "local");
        this.gemini = Objects.requireNonNull(gemini, "gemini");
        this.onlineRequested =
                Objects.requireNonNull(onlineRequested, "onlineRequested");
    }

    public Narrative generate(PredictionResponse prediction) {
        if (!onlineRequested.getAsBoolean() || !gemini.isConfigured()) {
            return local.generate(prediction);
        }
        try {
            return gemini.generate(prediction);
        } catch (RuntimeException error) {
            Narrative fallback = local.generate(prediction);
            return new Narrative(
                    "offline-local-fallback",
                    fallback.text());
        }
    }

    private static boolean configuredOnlineMode() {
        String property = System.getProperty("kairos.online.mode");
        String configured =
                property == null ? System.getenv("ONLINE_MODE") : property;
        return configured != null
                && ("true".equalsIgnoreCase(configured)
                || "1".equals(configured)
                || "yes".equalsIgnoreCase(configured));
    }
}
