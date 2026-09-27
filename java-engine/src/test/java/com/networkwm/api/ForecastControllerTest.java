package com.networkwm.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.networkwm.bridge.PythonMlClient;
import com.networkwm.graph.CicGraphDatasetService;
import com.networkwm.narrative.GeminiNarrativeService;
import com.networkwm.narrative.LocalNarrativeService;
import com.networkwm.narrative.NarrativeModeService;
import com.sun.net.httpserver.HttpServer;
import okhttp3.OkHttpClient;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Phase 50: full backend chain — CSV upload -&gt; windowing/graph -&gt;
 * Python inference (stubbed HTTP) -&gt; offline narrative -&gt; forecast.
 */
class ForecastControllerTest {
    private static final String CSV = String.join("\n",
            "Flow Duration,TotLen Fwd Pkts,TotLen Bwd Pkts,Timestamp,Label",
            "100,80,20,14/02/2018 10:45:00,Benign",
            "300,250,50,14/02/2018 10:45:05,FTP-BruteForce",
            "500,400,100,14/02/2018 10:45:12,Benign");

    private static final String VALID_PREDICTION = """
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
    void uploadCsvFlowsThroughPythonStubToOfflineForecast() throws Exception {
        HttpServer python = stubPython(200, VALID_PREDICTION);
        try {
            ForecastController controller = controller(python);

            var responseEntity = controller.forecastUpload(
                    new BytesMultipartFile("traffic.csv", CSV.getBytes()), 3);
            ForecastController.ForecastResponse response =
                    (ForecastController.ForecastResponse) responseEntity.getBody();

            assertEquals(200, responseEntity.getStatusCode().value());
            assertEquals("kairos.forecast.v1", response.artifactVersion());
            assertEquals(0.73, response.prediction().probability());
            assertEquals("INITIAL_ACCESS", response.prediction().predictedStage());
            assertEquals("offline-local", response.narrative().mode());
            assertTrue(response.narrative().text().contains("73.0%"));
        } finally {
            python.stop(0);
        }
    }

    @Test
    void nullContractIsRejectedAsBadRequest() throws Exception {
        HttpServer python = stubPython(200, VALID_PREDICTION);
        try {
            ForecastController controller = controller(python);

            ResponseStatusException error = assertThrows(
                    ResponseStatusException.class,
                    () -> controller.forecast(
                            new ForecastController.ForecastRequest(null, 3)));

            assertEquals(HttpStatus.BAD_REQUEST, error.getStatusCode());
        } finally {
            python.stop(0);
        }
    }

    @Test
    void pythonOutageSurfacesAsBadGateway() throws Exception {
        HttpServer python = stubPython(500, "{\"error\":\"boom\"}");
        try {
            ForecastController controller = controller(python);

            var contract = new UploadGraphService(new CicGraphDatasetService())
                    .fromUpload(new BytesMultipartFile("traffic.csv", CSV.getBytes()));

            ResponseStatusException error = assertThrows(
                    ResponseStatusException.class,
                    () -> controller.forecast(
                            new ForecastController.ForecastRequest(contract, 3)));

            assertEquals(HttpStatus.BAD_GATEWAY, error.getStatusCode());
        } finally {
            python.stop(0);
        }
    }

    @Test
    void pythonContractRejectionSurfacesAsBadRequestWithDetail() throws Exception {
        HttpServer python = stubPython(400,
                "{\"error\":\"contract feature schema does not match\"}");
        try {
            ForecastController controller = controller(python);

            var responseEntity = controller.forecastUpload(
                    new BytesMultipartFile("traffic.csv", CSV.getBytes()), 3);

            assertEquals(HttpStatus.BAD_REQUEST, responseEntity.getStatusCode());
            assertTrue(((ForecastController.UploadError) responseEntity.getBody())
                    .detail().contains("contract feature schema"));
        } finally {
            python.stop(0);
        }
    }

    @Test
    void pythonServerFailureOnUploadSurfacesAsBadGateway() throws Exception {
        HttpServer python = stubPython(500, "{\"error\":\"boom\"}");
        try {
            ForecastController controller = controller(python);

            var responseEntity = controller.forecastUpload(
                    new BytesMultipartFile("traffic.csv", CSV.getBytes()), 3);

            assertEquals(
                    HttpStatus.BAD_GATEWAY, responseEntity.getStatusCode());
        } finally {
            python.stop(0);
        }
    }

    @Test
    void unsupportedUploadExtensionIsRejected() throws Exception {        HttpServer python = stubPython(200, VALID_PREDICTION);
        try {
            ForecastController controller = controller(python);

            var response = controller.forecastUpload(
                    new BytesMultipartFile("capture.txt", new byte[]{1}), 3);

            assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
            assertTrue(((ForecastController.UploadError) response.getBody())
                    .detail().contains(".pcap"));
        } finally {
            python.stop(0);
        }
    }

    private static ForecastController controller(HttpServer python) {
        String baseUrl = "http://127.0.0.1:" + python.getAddress().getPort();
        PythonMlClient ml = new PythonMlClient(
                baseUrl, new OkHttpClient(), new ObjectMapper());
        NarrativeModeService narratives = new NarrativeModeService(
                new LocalNarrativeService(),
                new GeminiNarrativeService(
                        "", "gemini-2.5-flash-lite",
                        (key, model, prompt) -> "never",
                        new ObjectMapper()),
                () -> false);
        UploadGraphService uploads =
                new UploadGraphService(new CicGraphDatasetService());
        return new ForecastController(ml, narratives, uploads);
    }

    private static HttpServer stubPython(int status, String body) throws IOException {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/predict", exchange -> {
            exchange.getRequestBody().readAllBytes();
            byte[] encoded = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "application/json");
            exchange.sendResponseHeaders(status, encoded.length);
            exchange.getResponseBody().write(encoded);
            exchange.close();
        });
        server.start();
        return server;
    }

    private record BytesMultipartFile(
            String originalFilename,
            byte[] contents) implements MultipartFile {
        @Override
        public String getName() {
            return "file";
        }

        @Override
        public String getOriginalFilename() {
            return originalFilename;
        }

        @Override
        public String getContentType() {
            return "text/csv";
        }

        @Override
        public boolean isEmpty() {
            return contents.length == 0;
        }

        @Override
        public long getSize() {
            return contents.length;
        }

        @Override
        public byte[] getBytes() {
            return contents.clone();
        }

        @Override
        public InputStream getInputStream() {
            return new ByteArrayInputStream(contents);
        }

        @Override
        public void transferTo(File destination) throws IOException {
            Files.write(destination.toPath(), contents);
        }

        @Override
        public void transferTo(Path destination) throws IOException {
            Files.write(destination, contents);
        }
    }
}
