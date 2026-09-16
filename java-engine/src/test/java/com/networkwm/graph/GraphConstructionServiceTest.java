package com.networkwm.graph;

import com.networkwm.ingestion.IngestionService.AttackStage;
import com.networkwm.ingestion.IngestionService.FlowRecord;
import com.networkwm.window.WindowingService.CombinedFlow;
import com.networkwm.window.WindowingService.HostAggregate;
import com.networkwm.window.WindowingService.TrafficWindow;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GraphConstructionServiceTest {
    @Test
    void buildsDeterministicHostFlowGraph() {
        FlowRecord flow = new FlowRecord(
                Instant.ofEpochSecond(10),
                "10.0.0.1", "10.0.0.2", 1234, 80, 6,
                Map.of("flow_duration", 25.0),
                "FTP-BruteForce", "FTP-BruteForce", AttackStage.INITIAL_ACCESS);
        HostAggregate source = new HostAggregate(
                "10.0.0.1", 10, 20, 1, 1, 2, 1, 2, true);
        HostAggregate destination = new HostAggregate(
                "10.0.0.2", 20, 10, 1, 0, 2, 1, 2, true);
        TrafficWindow window = new TrafficWindow(
                Instant.ofEpochSecond(10),
                Instant.ofEpochSecond(20),
                List.of(new CombinedFlow(flow, null)),
                Map.of(source.hostId(), source, destination.hostId(), destination),
                AttackStage.INITIAL_ACCESS,
                true);

        GraphConstructionService.GraphSnapshot graph =
                new GraphConstructionService().build(window);

        assertEquals(GraphConstructionService.SCHEMA_VERSION, graph.schemaVersion());
        assertEquals(2, graph.nodes().size());
        assertEquals("10.0.0.1", graph.nodes().get(0).id());
        assertEquals(1, graph.edges().size());
        assertEquals("10.0.0.1", graph.edges().get(0).source());
        assertEquals("10.0.0.2", graph.edges().get(0).destination());
        assertEquals(25.0, graph.edges().get(0).features().get("flow_duration"));
        assertTrue(graph.edges().get(0).flowOnly());
        assertFalse(graph.edges().get(0).packetOnly());
        assertTrue(graph.label().infiltration());
        assertEquals(AttackStage.INITIAL_ACCESS, graph.label().stage());
    }
}
