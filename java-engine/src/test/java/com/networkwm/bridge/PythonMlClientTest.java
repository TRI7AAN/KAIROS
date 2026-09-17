package com.networkwm.bridge;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networkwm.graph.GraphContractService.GraphSequence;
import com.sun.net.httpserver.HttpServer;
import okhttp3.OkHttpClient;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PythonMlClientTest {
    private static final String VALID_RESPONSE = """
            {
              "artifact_version":"kairos.prediction.v1",
              "probability":0.73,
              "predicted_stage":"INITIAL_ACCESS",
              "top_5_features":[
                {"feature":"flow_count","value":4.0,"shap_value":0.2}
              ],
              "attention_summary":{
                "context_windows":8,
                "top_context_for_final_query":[],
                "causal_future_attention_mass":0.0
              },
              "rollout":{
                "steps":3,
                "probabilities":[0.73,0.75,0.78],
                "predicted_stages":["INITIAL_ACCESS","INITIAL_ACCESS","IMPACT"],
                "max_probability":0.78
              },
              "latency_ms":140.0
            }
            """;

    @Test
    void postsTypedContractAndParsesPrediction() throws Exception {
        AtomicReference<String> body = new AtomicReference<>();
        HttpServer server = server(200, VALID_RESPONSE, body);
        try {
            PythonMlClient client = client(server);
            GraphSequence sequence = new GraphSequence(
                    "kairos.sequence.v1", List.of("flow_count"),
                    List.of("bytes"), List.of());

            PythonMlClient.PredictionResponse response =
                    client.predict(sequence, 3);

            assertEquals(0.73, response.probability());
            assertEquals("INITIAL_ACCESS", response.predictedStage());
            assertEquals(1, response.topFeatures().size());
            assertEquals(0.78, response.rollout().maxProbability());
            JsonNode request = new ObjectMapper().readTree(body.get());
            assertEquals(3, request.get("rolloutSteps").asInt());
            assertEquals("kairos.sequence.v1",
                    request.get("contract").get("contractVersion").asText());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void propagatesNonSuccessStatus() throws Exception {
        HttpServer server = server(400, "{\"error\":\"bad contract\"}",
                new AtomicReference<>());
        try {
            Exception error = assertThrows(
                    Exception.class,
                    () -> client(server).predict(new GraphSequence(
                            "kairos.sequence.v1", List.of(), List.of(), List.of()),
                            3));
            assertTrue(error.getMessage().contains("HTTP 400"));
        } finally {
            server.stop(0);
        }
    }

    private static PythonMlClient client(HttpServer server) {
        return new PythonMlClient(
                "http://127.0.0.1:" + server.getAddress().getPort(),
                new OkHttpClient(),
                new ObjectMapper());
    }

    private static HttpServer server(
            int status,
            String response,
            AtomicReference<String> requestBody) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/predict", exchange -> {
            requestBody.set(new String(
                    exchange.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8));
            byte[] encoded = response.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "application/json");
            exchange.sendResponseHeaders(status, encoded.length);
            exchange.getResponseBody().write(encoded);
            exchange.close();
        });
        server.start();
        return server;
    }
}
