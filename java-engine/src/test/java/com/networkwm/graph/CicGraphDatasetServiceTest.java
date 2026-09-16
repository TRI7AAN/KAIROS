package com.networkwm.graph;

import com.networkwm.graph.GraphContractService.GraphSequence;
import com.networkwm.ingestion.IngestionService.AttackStage;
import com.networkwm.ingestion.IngestionService.FlowRecord;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CicGraphDatasetServiceTest {
    @Test
    void aggregatesEndpointFreeFlowsIntoCompactOrderedVectorWindows() {
        List<FlowRecord> records = List.of(
                flow(Instant.ofEpochSecond(1), 10.0, AttackStage.NONE),
                flow(Instant.ofEpochSecond(7), 30.0, AttackStage.INITIAL_ACCESS),
                flow(Instant.ofEpochSecond(12), 50.0, AttackStage.NONE));

        GraphSequence sequence = new CicGraphDatasetService().aggregate(
                records, Duration.ofSeconds(10));

        assertEquals(2, sequence.windows().size());
        var first = sequence.windows().get(0);
        assertFalse(first.topologyAvailable());
        assertEquals("__network__", first.nodes().get(0).id());
        assertEquals(1, first.edges().size());
        assertEquals(20.0,
                first.edges().get(0).features().get("flow_duration.mean"));
        assertEquals(10.0,
                first.edges().get(0).features().get("flow_duration.std"));
        assertEquals(40.0,
                first.edges().get(0).features().get("flow_duration.sum"));
        assertEquals(2.0, first.nodes().get(0).features().get("flow_count"));
        assertTrue(first.label().infiltration());
        assertEquals(AttackStage.INITIAL_ACCESS, first.label().stage());
        assertFalse(sequence.edgeFeatureNames().isEmpty());
    }

    private static FlowRecord flow(
            Instant timestamp,
            double duration,
            AttackStage stage) {
        return new FlowRecord(
                timestamp,
                "",
                "",
                0,
                443,
                6,
                Map.of(
                        "flow_duration", duration,
                        "totlen_fwd_pkts", duration,
                        "totlen_bwd_pkts", duration / 2.0),
                stage == AttackStage.NONE ? "Benign" : "Infiltration",
                stage == AttackStage.NONE ? "Benign" : "Infiltration",
                stage);
    }
}
