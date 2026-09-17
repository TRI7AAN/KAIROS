package com.networkwm.narrative;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.genai.Client;
import com.google.genai.types.GenerateContentConfig;
import com.google.genai.types.GenerateContentResponse;
import com.networkwm.bridge.PythonMlClient.PredictionResponse;
import com.networkwm.narrative.LocalNarrativeService.Narrative;
import org.springframework.stereotype.Service;

import java.util.Objects;

/** Optional online narrative enhancement. Never participates in prediction. */
@Service
public final class GeminiNarrativeService {
    private static final int MAX_NARRATIVE_CHARS = 4_000;

    private final String apiKey;
    private final String model;
    private final Generator generator;
    private final ObjectMapper mapper;

    public GeminiNarrativeService() {
        this(
                configuredApiKey(),
                configuredModel(),
                GeminiNarrativeService::callGemini,
                new ObjectMapper());
    }

    public GeminiNarrativeService(
            String apiKey,
            String model,
            Generator generator,
            ObjectMapper mapper) {
        this.apiKey = apiKey == null ? "" : apiKey.trim();
        this.model = Objects.requireNonNull(model, "model");
        this.generator = Objects.requireNonNull(generator, "generator");
        this.mapper = Objects.requireNonNull(mapper, "mapper");
    }

    public boolean isConfigured() {
        return !apiKey.isBlank();
    }

    public Narrative generate(PredictionResponse prediction) {
        Objects.requireNonNull(prediction, "prediction");
        if (!isConfigured()) {
            throw new IllegalStateException(
                    "Gemini narrative requested without GOOGLE_API_KEY");
        }
        String prompt;
        try {
            prompt = """
                    You are a defensive SOC analyst. Convert the KAIROS JSON
                    forecast below into a concise analyst briefing of at most
                    120 words. Use only facts present in the JSON. Do not claim
                    causality, do not invent hosts, CVEs, malware, or actions.
                    State that the score is a forecast and recommend human
                    verification. Return plain text only.

                    """ + mapper.writeValueAsString(prediction);
        } catch (JsonProcessingException error) {
            throw new IllegalStateException(
                    "Unable to serialize prediction for Gemini", error);
        }
        String generated = generator.generate(apiKey, model, prompt);
        if (generated == null || generated.isBlank()) {
            throw new IllegalStateException("Gemini returned an empty narrative");
        }
        String cleaned = generated.strip();
        if (cleaned.length() > MAX_NARRATIVE_CHARS) {
            cleaned = cleaned.substring(0, MAX_NARRATIVE_CHARS);
        }
        return new Narrative("gemini-online", cleaned);
    }

    private static String callGemini(
            String apiKey,
            String model,
            String prompt) {
        GenerateContentConfig config = GenerateContentConfig.builder()
                .candidateCount(1)
                .maxOutputTokens(220)
                .temperature(0.2F)
                .build();
        try (Client client = Client.builder().apiKey(apiKey).build()) {
            GenerateContentResponse response =
                    client.models.generateContent(model, prompt, config);
            return response.text();
        }
    }

    private static String configuredApiKey() {
        String primary = System.getenv("GOOGLE_API_KEY");
        if (primary != null && !primary.isBlank()) {
            return primary;
        }
        String legacy = System.getenv("GEMINI_API_KEY");
        return legacy == null ? "" : legacy;
    }

    private static String configuredModel() {
        String configured = System.getenv("GEMINI_MODEL");
        return configured == null || configured.isBlank()
                ? "gemini-flash-latest" : configured;
    }

    @FunctionalInterface
    public interface Generator {
        String generate(String apiKey, String model, String prompt);
    }
}
