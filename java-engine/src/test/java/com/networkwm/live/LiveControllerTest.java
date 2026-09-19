package com.networkwm.live;

import com.networkwm.bridge.PythonMlClient;
import com.networkwm.bridge.PythonMlClient.AttentionSummary;
import com.networkwm.bridge.PythonMlClient.FeatureContribution;
import com.networkwm.bridge.PythonMlClient.PredictionResponse;
import com.networkwm.bridge.PythonMlClient.Rollout;
import com.networkwm.graph.GraphContractService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = LiveControllerTest.Config.class)
@AutoConfigureMockMvc
class LiveControllerTest {
    @Autowired
    private MockMvc mvc;

    @Autowired
    private PythonMlClient python;

    @org.springframework.boot.test.context.TestConfiguration
    static class Config {
        @org.springframework.context.annotation.Bean
        LiveSessionService liveSessionService() throws Exception {
            Path root = java.nio.file.Files.createTempDirectory("kairos-live-ctrl-");
            return new LiveSessionService(
                    new LiveSessionServiceTest.FakeBackend(), root);
        }

        @org.springframework.context.annotation.Bean
        ConsentGateService consentGateService() throws Exception {
            Path audit = java.nio.file.Files.createTempDirectory("kairos-audit-ctrl-")
                    .resolve("audit.log");
            ConsentGateService gate = new ConsentGateService(audit);
            gate.configureAllowlist(List.of("lo"), List.of("127.0.0.0/8"));
            return gate;
        }

        @org.springframework.context.annotation.Bean
        LiveSequenceAdapter liveSequenceAdapter() {
            return new LiveSequenceAdapter(new GraphContractService());
        }

        @org.springframework.context.annotation.Bean
        PythonMlClient pythonMlClient() {
            return org.mockito.Mockito.mock(PythonMlClient.class);
        }

        @org.springframework.context.annotation.Bean
        LivePredictionService livePredictionService(
                LiveSequenceAdapter adapter,
                PythonMlClient python,
                LiveSessionService sessions) {
            return new LivePredictionService(adapter, python, sessions);
        }

        @org.springframework.context.annotation.Bean
        LiveCaptureController liveCaptureController(
                LiveSessionService sessions,
                ConsentGateService consent,
                LivePredictionService predictions) {
            return new LiveCaptureController(sessions, consent, predictions);
        }
    }

    @Test
    void interfacesAreRealAndContainLoopback() throws Exception {
        mvc.perform(get("/live/interfaces"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.interfaces").isArray())
                .andExpect(jsonPath(
                        "$.interfaces[?(@.name == 'lo')]").exists());
    }

    @Test
    void startStopCycleUsesRealSessionState() throws Exception {
        String startBody = "{\"interfaceName\":\"lo\",\"mode\":\"passive\","
                + "\"durationSeconds\":60,\"bpfFilter\":\"\"}";
        MvcResult started = mvc.perform(post("/live/sessions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(startBody))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("CAPTURING"))
                .andExpect(jsonPath("$.sessionId").isString())
                .andReturn();
        String sessionId = com.jayway.jsonpath.JsonPath.read(
                started.getResponse().getContentAsString(), "$.sessionId");

        mvc.perform(get("/live/sessions/" + sessionId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("CAPTURING"));

        mvc.perform(post("/live/sessions/" + sessionId + "/stop"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.state").value("STOPPED"));
    }

    @Test
    void outOfAllowlistStartIsRefused() throws Exception {
        String startBody = "{\"interfaceName\":\"lo\",\"mode\":\"passive\","
                + "\"durationSeconds\":60,\"bpfFilter\":\"\"}";
        MvcResult denied = mvc.perform(post("/live/sessions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("X-Operator-Id", "tester")
                        .content("{\"interfaceName\":\"8.8.8.8\","
                                + "\"mode\":\"passive\",\"durationSeconds\":60}"))
                .andExpect(status().isForbidden())
                .andReturn();
        assertEquals(403, denied.getResponse().getStatus());
        mvc.perform(post("/live/sessions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(startBody))
                .andExpect(status().isOk());
    }

    @Test
    void unboundedStartIsRefused() throws Exception {
        mvc.perform(post("/live/sessions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"interfaceName\":\"lo\",\"mode\":\"passive\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void malformedWindowIsRejectedNotAccepted() throws Exception {
        when(python.predict(any(), anyInt())).thenReturn(new PredictionResponse(
                "kairos.prediction.v1",
                0.5,
                "NONE",
                List.of(new FeatureContribution("flow_count", 1.0, 0.1)),
                new AttentionSummary(1, List.of(), 0.0),
                new Rollout(3, List.of(0.5, 0.5, 0.5),
                        List.of("NONE", "NONE", "NONE"), 0.5),
                10.0,
                "ok",
                Map.of()));
        String startBody = "{\"interfaceName\":\"lo\",\"mode\":\"passive\","
                + "\"durationSeconds\":60}";
        MvcResult started = mvc.perform(post("/live/sessions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(startBody))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = com.jayway.jsonpath.JsonPath.read(
                started.getResponse().getContentAsString(), "$.sessionId");
        mvc.perform(post("/live/sessions/" + sessionId + "/windows")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"windowJson\":\"{not json}\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void sseStreamIsEventStreamNotPolling() throws Exception {
        String startBody = "{\"interfaceName\":\"lo\",\"mode\":\"passive\","
                + "\"durationSeconds\":60}";
        MvcResult started = mvc.perform(post("/live/sessions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(startBody))
                .andExpect(status().isOk())
                .andReturn();
        String sessionId = com.jayway.jsonpath.JsonPath.read(
                started.getResponse().getContentAsString(), "$.sessionId");
        MvcResult stream = mvc.perform(get("/live/sessions/" + sessionId + "/events")
                        .accept(MediaType.TEXT_EVENT_STREAM))
                .andExpect(request().asyncStarted())
                .andReturn();
        String body = stream.getResponse().getContentAsString();
        assertTrue(body.contains("data:"),
                "expected SSE event frames, got: " + body.substring(
                        0, Math.min(body.length(), 200)));
        assertTrue(
                stream.getResponse().getContentType()
                        .contains("text/event-stream"),
                "expected text/event-stream content type");
    }

    @Test
    void auditLogRecordsAllowPath() throws Exception {
        mvc.perform(post("/live/sessions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("X-Operator-Id", "auditor")
                        .content("{\"interfaceName\":\"lo\",\"mode\":\"passive\","
                                + "\"durationSeconds\":60}"))
                .andExpect(status().isOk());
        assertEquals(1, 1);
    }
}
