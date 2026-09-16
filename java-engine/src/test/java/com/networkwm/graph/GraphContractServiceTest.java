package com.networkwm.graph;

import com.networkwm.graph.GraphConstructionService.GraphEdge;
import com.networkwm.graph.GraphConstructionService.GraphLabel;
import com.networkwm.graph.GraphConstructionService.GraphNode;
import com.networkwm.graph.GraphConstructionService.GraphSnapshot;
import com.networkwm.ingestion.IngestionService.AttackStage;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GraphContractServiceTest {
    @Test
    void roundTripsOneCompleteWindowWithStableFeatureSchemas() throws Exception {
        GraphSnapshot window = new GraphSnapshot(
                GraphConstructionService.SCHEMA_VERSION,
                Instant.parse("2018-02-14T10:32:00Z"),
                Instant.parse("2018-02-14T10:32:10Z"),
                true,
                List.of(
                        new GraphNode("source", Map.of("flow_count", 1.0)),
                        new GraphNode("destination", Map.of("flow_count", 1.0))),
                List.of(new GraphEdge(
                        "edge-0", "source", "destination",
                        Map.of("protocol", 6.0, "packet.ttl_mean", 63.0),
                        false, false)),
                new GraphLabel(true, AttackStage.INITIAL_ACCESS));

        GraphContractService service = new GraphContractService();
        GraphContractService.GraphSequence original =
                service.sequence(List.of(window));
        String encoded = service.toJson(original);
        GraphContractService.GraphSequence decoded = service.fromJson(encoded);

        assertEquals(GraphContractService.CONTRACT_VERSION,
                decoded.contractVersion());
        assertEquals(List.of("flow_count"), decoded.nodeFeatureNames());
        assertEquals(List.of("packet.ttl_mean", "protocol"),
                decoded.edgeFeatureNames());
        assertEquals(1, decoded.windows().size());
        assertEquals(window.windowStart(), decoded.windows().get(0).windowStart());
        assertEquals(AttackStage.INITIAL_ACCESS,
                decoded.windows().get(0).label().stage());
        assertTrue(encoded.contains("\"contractVersion\":\"kairos.sequence.v1\""));
    }
}
