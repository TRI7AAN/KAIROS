package com.networkwm.bridge;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.networkwm.graph.GraphContractService.GraphSequence;
import okhttp3.HttpUrl;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Typed, bounded REST client for the private Python world-model service. */
@Service
public final class PythonMlClient {
    private static final MediaType JSON =
            MediaType.get("application/json; charset=utf-8");
    private static final int MAX_ERROR_BODY_CHARS = 2_000;

    private final OkHttpClient http;
    private final ObjectMapper mapper;
    private final HttpUrl predictUrl;

    public PythonMlClient() {
        this(
                configuredBaseUrl(),
                new OkHttpClient.Builder()
                        .connectTimeout(Duration.ofSeconds(2))
                        .readTimeout(Duration.ofSeconds(10))
                        .writeTimeout(Duration.ofSeconds(10))
                        .callTimeout(Duration.ofSeconds(15))
                        .build(),
                new ObjectMapper()
                        .registerModule(new JavaTimeModule())
                        .disable(
                                SerializationFeature.WRITE_DATES_AS_TIMESTAMPS));
    }

    public PythonMlClient(
            String baseUrl,
            OkHttpClient http,
            ObjectMapper mapper) {
        this.http = Objects.requireNonNull(http, "http");
        this.mapper = Objects.requireNonNull(mapper, "mapper")
                .copy()
                .registerModule(new JavaTimeModule())
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        HttpUrl parsed = HttpUrl.parse(Objects.requireNonNull(baseUrl, "baseUrl"));
        if (parsed == null || !List.of("http", "https").contains(parsed.scheme())) {
            throw new IllegalArgumentException("Invalid Python ML base URL");
        }
        HttpUrl resolved = parsed.resolve("/predict");
        if (resolved == null) {
            throw new IllegalArgumentException("Unable to resolve /predict URL");
        }
        predictUrl = resolved;
    }

    public PredictionResponse predict(
            GraphSequence contract,
            int rolloutSteps) throws IOException {
        Objects.requireNonNull(contract, "contract");
        if (rolloutSteps < 1 || rolloutSteps > 10) {
            throw new IllegalArgumentException(
                    "rolloutSteps must be between 1 and 10");
        }
        byte[] encoded = mapper.writeValueAsBytes(
                new PredictionRequest(contract, rolloutSteps));
        Request request = new Request.Builder()
                .url(predictUrl)
                .post(RequestBody.create(encoded, JSON))
                .header("Accept", "application/json")
                .build();
        try (Response response = http.newCall(request).execute()) {
            String body = response.body() == null ? "" : response.body().string();
            if (!response.isSuccessful()) {
                String safeBody = body.substring(
                        0, Math.min(body.length(), MAX_ERROR_BODY_CHARS));
                throw new IOException(
                        "Python ML service returned HTTP "
                                + response.code() + ": " + safeBody);
            }
            if (body.isBlank()) {
                throw new IOException("Python ML service returned an empty response");
            }
            PredictionResponse parsed =
                    mapper.readValue(body, PredictionResponse.class);
            validate(parsed);
            return parsed;
        }
    }

    private static void validate(PredictionResponse response) throws IOException {
        if (response.artifactVersion() == null
                || !response.artifactVersion().startsWith("kairos.prediction.")) {
            throw new IOException("Unsupported Python prediction artifact");
        }
        if (!Double.isFinite(response.probability())
                || response.probability() < 0.0
                || response.probability() > 1.0) {
            throw new IOException("Invalid infiltration probability");
        }
        if (response.predictedStage() == null
                || response.predictedStage().isBlank()) {
            throw new IOException("Missing predicted stage");
        }
        if (response.topFeatures() == null
                || response.attentionSummary() == null) {
            throw new IOException("Incomplete explanation payload");
        }
    }

    private static String configuredBaseUrl() {
        String property = System.getProperty("kairos.ml.url");
        if (property != null && !property.isBlank()) {
            return property;
        }
        String environment = System.getenv("KAIROS_ML_URL");
        return environment == null || environment.isBlank()
                ? "http://127.0.0.1:5000" : environment;
    }

    public record PredictionRequest(
            GraphSequence contract,
            @JsonProperty("rolloutSteps") int rolloutSteps) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record PredictionResponse(
            @JsonProperty("artifact_version") String artifactVersion,
            double probability,
            @JsonProperty("predicted_stage") String predictedStage,
            @JsonProperty("top_5_features") List<FeatureContribution> topFeatures,
            @JsonProperty("attention_summary") AttentionSummary attentionSummary,
            Rollout rollout,
            @JsonProperty("latency_ms") double latencyMs,
            String quality,
            @JsonProperty("quality_detail")
                    Map<String, Object> qualityDetail,
            @JsonProperty("validated_forecast")
                    Map<String, Object> validatedForecast,
            @JsonProperty("stage_coverage")
                    Map<String, Object> stageCoverage,
            @JsonProperty("input_projection_detail")
                    Map<String, Object> inputProjectionDetail) {
        public PredictionResponse(
                String artifactVersion,
                double probability,
                String predictedStage,
                List<FeatureContribution> topFeatures,
                AttentionSummary attentionSummary,
                Rollout rollout,
                double latencyMs,
                String quality,
                Map<String, Object> qualityDetail) {
            this(
                    artifactVersion,
                    probability,
                    predictedStage,
                    topFeatures,
                    attentionSummary,
                    rollout,
                    latencyMs,
                    quality,
                    qualityDetail,
                    Map.of(),
                    Map.of(),
                    Map.of());
        }

        public PredictionResponse {
            topFeatures = topFeatures == null ? null : List.copyOf(topFeatures);
            qualityDetail = qualityDetail == null
                    ? Map.of() : Map.copyOf(qualityDetail);
            validatedForecast = validatedForecast == null
                    ? Map.of() : Map.copyOf(validatedForecast);
            stageCoverage = stageCoverage == null
                    ? Map.of() : Map.copyOf(stageCoverage);
            inputProjectionDetail = inputProjectionDetail == null
                    ? Map.of() : Map.copyOf(inputProjectionDetail);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record FeatureContribution(
            String feature,
            double value,
            @JsonProperty("shap_value") double shapValue) {
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record AttentionSummary(
            @JsonProperty("context_windows") int contextWindows,
            @JsonProperty("top_context_for_final_query")
                    List<Map<String, Object>> topContext,
            @JsonProperty("causal_future_attention_mass")
                    double causalFutureAttentionMass) {
        public AttentionSummary {
            topContext = topContext == null ? List.of() : List.copyOf(topContext);
        }
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public record Rollout(
            int steps,
            List<Double> probabilities,
            @JsonProperty("predicted_stages") List<String> predictedStages,
            @JsonProperty("max_probability") double maxProbability) {
        public Rollout {
            probabilities = probabilities == null
                    ? List.of() : List.copyOf(probabilities);
            predictedStages = predictedStages == null
                    ? List.of() : List.copyOf(predictedStages);
        }
    }
}
