package com.networkwm.graph;

import com.networkwm.bridge.CppBridge;
import com.networkwm.ingestion.IngestionService.AttackStage;
import com.networkwm.ingestion.IngestionService.FlowRecord;
import com.networkwm.window.WindowingService.CombinedFlow;
import com.networkwm.window.WindowingService.HostAggregate;
import com.networkwm.window.WindowingService.TrafficWindow;
import com.networkwm.window.WindowingService;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

/**
 * Converts ordered traffic windows into host-flow graph snapshots.
 */
@Service
public final class GraphConstructionService {
    public static final String SCHEMA_VERSION = "kairos.graph.v1";

    public List<GraphSnapshot> build(List<TrafficWindow> windows) {
        Objects.requireNonNull(windows, "windows");
        return windows.stream().map(this::build).toList();
    }

    public GraphSnapshot build(TrafficWindow window) {
        Objects.requireNonNull(window, "window");
        List<GraphNode> nodes = window.hosts().values().stream()
                .map(this::node)
                .sorted(java.util.Comparator.comparing(GraphNode::id))
                .toList();

        List<GraphEdge> edges = new ArrayList<>();
        for (int index = 0; index < window.flows().size(); ++index) {
            CombinedFlow combined = window.flows().get(index);
            EndpointPair endpoints = endpoints(combined);
            edges.add(new GraphEdge(
                    "edge-" + index,
                    endpoints.source(),
                    endpoints.destination(),
                    edgeFeatures(combined),
                    combined.packetOnly(),
                    combined.flowOnly()));
        }

        return new GraphSnapshot(
                SCHEMA_VERSION,
                window.start(),
                window.end(),
                window.topologyAvailable(),
                nodes,
                List.copyOf(edges),
                new GraphLabel(window.stage() != AttackStage.NONE, window.stage()));
    }

    private GraphNode node(HostAggregate host) {
        Map<String, Double> features = new LinkedHashMap<>();
        features.put("inbound_bytes", host.inboundBytes());
        features.put("outbound_bytes", host.outboundBytes());
        features.put("flow_count", (double) host.flowCount());
        features.put("unique_destination_ports",
                (double) host.uniqueDestinationPorts());
        features.put("syn_count", host.synCount());
        features.put("ack_count", host.ackCount());
        features.put("syn_ack_ratio", host.synAckRatio());
        features.put("topology_available", host.topologyAvailable() ? 1.0 : 0.0);
        return new GraphNode(host.hostId(), Map.copyOf(features));
    }

    private static EndpointPair endpoints(CombinedFlow combined) {
        FlowRecord flow = combined.flow();
        if (flow != null && !flow.sourceIp().isBlank()
                && !flow.destinationIp().isBlank()) {
            return new EndpointPair(flow.sourceIp(), flow.destinationIp());
        }
        CppBridge.FlowFeatures packet = combined.packetFeatures();
        if (packet != null) {
            return new EndpointPair(packet.sourceIp(), packet.destinationIp());
        }
        return new EndpointPair(
                WindowingService.NETWORK_FALLBACK_NODE,
                WindowingService.NETWORK_FALLBACK_NODE);
    }

    private static Map<String, Double> edgeFeatures(CombinedFlow combined) {
        Map<String, Double> features = new TreeMap<>();
        FlowRecord flow = combined.flow();
        if (flow != null) {
            features.putAll(flow.features());
            features.putIfAbsent("source_port", (double) flow.sourcePort());
            features.putIfAbsent("destination_port", (double) flow.destinationPort());
            features.putIfAbsent("protocol", (double) flow.protocol());
        }

        CppBridge.FlowFeatures packet = combined.packetFeatures();
        if (packet != null) {
            features.put("packet.packet_count", (double) packet.packetCount());
            features.put("packet.duration_micros",
                    (double) Math.max(0L,
                            packet.lastSeenEpochMicros()
                                    - packet.firstSeenEpochMicros()));
            features.put("packet.ttl_mean", packet.ttlMean());
            features.put("packet.ttl_variance", packet.ttlVariance());
            features.put("packet.tcp_window_trend", packet.tcpWindowTrend());
            features.put("packet.fragment_count", (double) packet.fragmentCount());
            features.put("packet.retransmission_count",
                    (double) packet.retransmissionCount());
            features.put("packet.truncated_packet_count",
                    (double) packet.truncatedPacketCount());
            features.put("packet.payload_size_mean", packet.payloadSizeMean());
            features.put("packet.payload_size_stddev", packet.payloadSizeStddev());
            features.put("packet.payload_size_skew", packet.payloadSizeSkew());
            features.putIfAbsent("source_port", (double) packet.sourcePort());
            features.putIfAbsent("destination_port",
                    (double) packet.destinationPort());
            features.putIfAbsent("protocol", (double) packet.protocol());
        }
        return Map.copyOf(features);
    }

    private record EndpointPair(String source, String destination) {
    }

    public record GraphSnapshot(
            String schemaVersion,
            Instant windowStart,
            Instant windowEnd,
            boolean topologyAvailable,
            List<GraphNode> nodes,
            List<GraphEdge> edges,
            GraphLabel label) {
        public GraphSnapshot {
            nodes = List.copyOf(nodes);
            edges = List.copyOf(edges);
        }
    }

    public record GraphNode(String id, Map<String, Double> features) {
        public GraphNode {
            features = Map.copyOf(features);
        }
    }

    public record GraphEdge(
            String id,
            String source,
            String destination,
            Map<String, Double> features,
            boolean packetOnly,
            boolean flowOnly) {
        public GraphEdge {
            features = Map.copyOf(features);
        }
    }

    public record GraphLabel(boolean infiltration, AttackStage stage) {
    }
}
