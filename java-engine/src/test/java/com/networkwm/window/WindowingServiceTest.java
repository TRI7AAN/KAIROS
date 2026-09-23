package com.networkwm.window;

import com.networkwm.bridge.CppBridge;
import com.networkwm.ingestion.IngestionService.AttackStage;
import com.networkwm.ingestion.IngestionService.FlowRecord;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class WindowingServiceTest {
    @Test
    void bucketsAggregatesAndMergesNativeFlowByTimestampAndFiveTuple() {
        FlowRecord flow = new FlowRecord(
                Instant.ofEpochSecond(21),
                "10.0.0.1",
                "10.0.0.2",
                1234,
                80,
                6,
                Map.of(
                        "totlen_fwd_pkts", 100.0,
                        "totlen_bwd_pkts", 40.0,
                        "syn_flag_cnt", 2.0,
                        "ack_flag_cnt", 1.0),
                "FTP-BruteForce",
                "FTP-BruteForce",
                AttackStage.INITIAL_ACCESS);
        CppBridge.FlowFeatures packet = new CppBridge.FlowFeatures(
                "10.0.0.1", "10.0.0.2", 1234, 80, 6, 2,
                21_000_000L, 22_000_000L,
                63.0, 1.0, 0.0, 0, 0, 0, 6.0, 2.0, 0.0);

        List<WindowingService.TrafficWindow> windows =
                new WindowingService().windowAndMerge(
                        List.of(flow), List.of(packet), Duration.ofSeconds(10));

        assertEquals(1, windows.size());
        WindowingService.TrafficWindow window = windows.get(0);
        assertEquals(Instant.ofEpochSecond(20), window.start());
        assertEquals(Instant.ofEpochSecond(30), window.end());
        assertEquals(AttackStage.INITIAL_ACCESS, window.stage());
        assertTrue(window.topologyAvailable());
        assertEquals(1, window.flows().size());
        assertNotNull(window.flows().get(0).flow());
        assertNotNull(window.flows().get(0).packetFeatures());

        WindowingService.HostAggregate source = window.hosts().get("10.0.0.1");
        assertEquals(100.0, source.outboundBytes());
        assertEquals(40.0, source.inboundBytes());
        assertEquals(1, source.uniqueDestinationPorts());
        assertEquals(2.0, source.synAckRatio());
    }

    @Test
    void marksOfficialEndpointFreeCsvRowsAsTopologyUnavailable() {
        FlowRecord flow = new FlowRecord(
                Instant.ofEpochSecond(5),
                "", "", 0, 443, 6,
                Map.of("totlen_fwd_pkts", 10.0, "totlen_bwd_pkts", 4.0),
                "Benign", "Benign", AttackStage.NONE);

        WindowingService.TrafficWindow window =
                new WindowingService().windowAndMerge(
                        List.of(flow), List.of(), Duration.ofSeconds(10)).get(0);

        assertFalse(window.topologyAvailable());
        assertTrue(window.hosts().containsKey(WindowingService.NETWORK_FALLBACK_NODE));
        assertFalse(window.hosts().get(
                WindowingService.NETWORK_FALLBACK_NODE).topologyAvailable());
    }

    @Test
    void carriesPortScanEvidenceIntoFusedWindowHosts() {
        FlowRecord flow = new FlowRecord(
                Instant.ofEpochSecond(21),
                "10.0.0.9",
                "10.0.0.10",
                4000,
                80,
                6,
                Map.of("totlen_fwd_pkts", 50.0, "totlen_bwd_pkts", 10.0),
                "Benign",
                "Benign",
                AttackStage.NONE);
        CppBridge.FlowFeatures packet = new CppBridge.FlowFeatures(
                "10.0.0.9", "10.0.0.10", 4000, 80, 6, 3,
                21_000_000L, 23_000_000L,
                60.0, 0.0, 0.0, 0, 0, 0, 10.0, 0.0, 0.0);
        CppBridge.ExtractionBatch batch = new CppBridge.ExtractionBatch(
                List.of(packet),
                List.of(new CppBridge.PortScanFeatures(
                        "10.0.0.9", 20_000_000L,
                        30, 25, 0.9, "sequential")));

        List<WindowingService.TrafficWindow> windows =
                new WindowingService().windowAndMerge(
                        List.of(flow), batch, Duration.ofSeconds(10));

        assertEquals(1, windows.size());
        WindowingService.HostAggregate scanner =
                windows.get(0).hosts().get("10.0.0.9");
        assertNotNull(scanner);
        assertEquals(30L, scanner.scanObservedPackets());
        assertEquals(25L, scanner.scanUniqueDestinationPorts());
        assertEquals(0.9, scanner.scanSequentialTransitionRatio(), 1e-12);
        assertTrue(scanner.scanSequential());
        assertFalse(scanner.scanRandomized());
    }
}
