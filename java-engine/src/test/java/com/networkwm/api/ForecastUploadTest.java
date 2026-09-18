package com.networkwm.api;

import com.networkwm.bridge.PythonMlClient.AttentionSummary;
import com.networkwm.bridge.PythonMlClient.FeatureContribution;
import com.networkwm.bridge.PythonMlClient.PredictionResponse;
import com.networkwm.bridge.PythonMlClient.Rollout;
import com.networkwm.bridge.PythonMlClient;
import com.networkwm.graph.CicGraphDatasetService;
import com.networkwm.narrative.GeminiNarrativeService;
import com.networkwm.narrative.LocalNarrativeService;
import com.networkwm.narrative.NarrativeModeService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/** Phase 50: upload -> windowing/graph -> Python client -> narrative chain. */
@SpringBootTest(classes = ForecastUploadTest.Config.class)
@AutoConfigureMockMvc
class ForecastUploadTest {
    private static final String CSV = String.join("\n",
            "Flow Duration,TotLen Fwd Pkts,TotLen Bwd Pkts,Timestamp,Label",
            "100,80,20,14/02/2018 10:45:00,Benign",
            "300,250,50,14/02/2018 10:45:05,FTP-BruteForce",
            "500,400,100,14/02/2018 10:45:12,Benign");

    @Autowired
    private MockMvc mvc;

    @MockBean
    private PythonMlClient python;

    @org.springframework.boot.test.context.TestConfiguration
    static class Config {
        @org.springframework.context.annotation.Bean
        ForecastController forecastController(PythonMlClient python) {
            return new ForecastController(
                    python,
                    new NarrativeModeService(
                            new LocalNarrativeService(),
                            new GeminiNarrativeService(
                                    "", "test-model",
                                    (key, model, prompt) -> {
                                        throw new IllegalStateException(
                                                "must stay offline");
                                    },
                                    new com.fasterxml.jackson.databind
                                            .ObjectMapper()),
                            () -> false),
                    new UploadGraphService(new CicGraphDatasetService()));
        }
    }

    @Test
    void uploadProducesForecastWithOfflineNarrative() throws Exception {
        when(python.predict(any(), anyInt())).thenReturn(new PredictionResponse(
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
                140.0));

        MockMultipartFile file = new MockMultipartFile(
                "file", "traffic.csv", "text/csv",
                CSV.getBytes(StandardCharsets.UTF_8));

        mvc.perform(multipart("/forecast/upload")
                        .file(file)
                        .param("rolloutSteps", "3")
                        .contentType(MediaType.MULTIPART_FORM_DATA))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.artifactVersion")
                        .value("kairos.forecast.v1"))
                .andExpect(jsonPath("$.prediction.probability").value(0.73))
                .andExpect(jsonPath("$.prediction.predicted_stage")
                        .value("INITIAL_ACCESS"))
                .andExpect(jsonPath("$.narrative.mode").value("offline-local"))
                .andExpect(jsonPath("$.narrative.text").isNotEmpty());
    }

    @Test
    void uploadRejectsNonCsv() throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file", "capture.pcap", "application/octet-stream",
                new byte[]{1, 2, 3});

        mvc.perform(multipart("/forecast/upload")
                        .file(file)
                        .contentType(MediaType.MULTIPART_FORM_DATA))
                .andExpect(status().isBadRequest());
    }
}
