package com.networkwm.live;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = LiveControllerTest.Config.class)
@AutoConfigureMockMvc
class Phase76ActiveRefusalTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void activeModeRefusedWithoutAnyFlag() throws Exception {
        mvc.perform(post("/live/sessions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"interfaceName\":\"lo\",\"mode\":\"active\","
                                + "\"durationSeconds\":10}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void activeModeRefusedEvenForAllowlistedTarget() throws Exception {
        mvc.perform(post("/live/sessions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .header("X-Operator-Id", "phase76-auditor")
                        .content("{\"interfaceName\":\"lo\",\"mode\":\"active\","
                                + "\"durationSeconds\":10,"
                                + "\"packetLimit\":100}"))
                .andExpect(status().isForbidden());
    }

    @Test
    void passiveOffAllowlistStillRefusedWithFlagSemantics() throws Exception {
        mvc.perform(post("/live/sessions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"interfaceName\":\"9.9.9.9\",\"mode\":\"passive\","
                                + "\"durationSeconds\":10}"))
                .andExpect(status().isForbidden());
    }
}
