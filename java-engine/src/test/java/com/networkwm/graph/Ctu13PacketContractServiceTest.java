package com.networkwm.graph;

import com.networkwm.bridge.CppBridge;
import com.networkwm.graph.GraphContractService.GraphSequence;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class Ctu13PacketContractServiceTest {
    private static CppBridge.FlowFeatures flow(
            String source, String destination, int destinationPort) {
        return new CppBridge.FlowFeatures(
                source, destination, 1234, destinationPort, 6,
                10L, 1_000_000L, 2_000_000L,
                64.0, 1.0, 0.5,
                0L, 1L, 0L,
                100.0, 10.0, 0.1);
    }

    @Test
    void preservesRealTopologyInsteadOfFallbackNode() {
        CppBridge.ExtractionBatch batch = new CppBridge.ExtractionBatch(
                List.of(
                        flow("147.32.84.165", "10.0.0.5", 443),
                        flow("10.0.0.5", "147.32.84.165", 80)),
                List.of());

        GraphSequence sequence = new Ctu13PacketContractService().fromExtraction(
                batch, Instant.parse("2011-08-16T13:31:00Z"), 10L);

        assertEquals("kairos.sequence.v1", sequence.contractVersion());
        assertEquals(1, sequence.windows().size());
        assertTrue(sequence.windows().get(0).topologyAvailable());
        assertTrue(sequence.windows().get(0).nodes().stream()
                .anyMatch(node -> node.id().equals("147.32.84.165")));
        assertTrue(sequence.nodeFeatureNames().contains("topology_available"));
        assertTrue(sequence.edgeFeatureNames().contains("packet.packet_count"));
    }

    @Test
    void blankIpsAreRejectedRatherThanInvented() {
        CppBridge.ExtractionBatch batch = new CppBridge.ExtractionBatch(
                List.of(flow("", "10.0.0.5", 443)),
                List.of());

        assertThrows(
                IllegalArgumentException.class,
                () -> new Ctu13PacketContractService().fromExtraction(
                        batch, Instant.now(), 10L));
    }
}
