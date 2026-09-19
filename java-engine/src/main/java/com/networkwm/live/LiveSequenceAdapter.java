package com.networkwm.live;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.networkwm.graph.GraphConstructionService.GraphEdge;
import com.networkwm.graph.GraphConstructionService.GraphLabel;
import com.networkwm.graph.GraphConstructionService.GraphNode;
import com.networkwm.graph.GraphConstructionService.GraphSnapshot;
import com.networkwm.graph.GraphContractService;
import com.networkwm.graph.GraphContractService.GraphSequence;
import com.networkwm.ingestion.IngestionService.AttackStage;
import com.networkwm.window.WindowingService;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

/**
 * Phase 71: live-window to {@code kairos.sequence.v1} sequence adapter.
 *
 * Converts live feature windows (the Phase 68 emitter JSON shape, produced
 * from the same packet/flow schema as the static pipeline) into graph
 * snapshots identical in schema to static windows, then runs the existing
 * {@link GraphContractService} validation on every converted window.
 * Malformed live windows are rejected with a clear error and never passed
 * downstream silently.
 */
@Service
public final class LiveSequenceAdapter {
    private static final ObjectMapper JSON = new ObjectMapper();

    private final GraphContractService contract;

    public LiveSequenceAdapter(GraphContractService contract) {
        this.contract = Objects.requireNonNull(contract, "contract");
    }

    public GraphSequence adapt(String liveWindowJson) throws IOException {
        return adapt(List.of(liveWindowJson));
    }

    public GraphSequence adapt(List<String> liveWindowJson) throws IOException {
        Objects.requireNonNull(liveWindowJson, "liveWindowJson");
        if (liveWindowJson.isEmpty()) {
            throw new IllegalArgumentException("at least one live window is required");
        }
        List<GraphSnapshot> snapshots = new ArrayList<>();
        int index = 0;
        for (String encoded : liveWindowJson) {
            snapshots.add(snapshot(index, encoded));
            index++;
        }
        return contract.sequence(snapshots);
    }

    private static GraphSnapshot snapshot(int index, String encoded) throws IOException {
        if (encoded == null || encoded.isBlank()) {
            throw new IllegalArgumentException(
                    "live window " + index + " is blank");
        }
        final JsonNode root;
        try {
            root = JSON.readTree(encoded);
        } catch (IOException error) {
            throw new IllegalArgumentException(
                    "live window " + index + " is not valid JSON", error);
        }
        long startMicros = requiredLong(root, "windowStartEpochMicros", index);
        long endMicros = requiredLong(root, "windowEndEpochMicros", index);
        if (endMicros <= startMicros) {
            throw new IllegalArgumentException(
                    "live window " + index + " has a non-positive duration");
        }
        Instant start = microsToInstant(startMicros);
        Instant end = microsToInstant(endMicros);

        JsonNode flows = root.get("flows");
        if (flows == null || !flows.isArray()) {
            throw new IllegalArgumentException(
                    "live window " + index + " is missing a flows array");
        }
        if (flows.isEmpty()) {
            throw new IllegalArgumentException(
                    "live window " + index + " carries no flows");
        }

        Map<String, HostAccumulator> hosts = new LinkedHashMap<>();
        List<FlowEdge> edges = new ArrayList<>();
        int edgeIndex = 0;
        for (JsonNode flow : flows) {
            String source = requiredText(flow, "sourceIp", index);
            String destination = requiredText(flow, "destinationIp", index);
            if (source.isBlank() || destination.isBlank()) {
                throw new IllegalArgumentException(
                        "live window " + index + " has a blank endpoint");
            }
            long packetCount = requiredLong(flow, "packetCount", index);
            if (packetCount <= 0) {
                throw new IllegalArgumentException(
                        "live window " + index + " has a non-positive packetCount");
            }
            Map<String, Double> features = packetEdgeFeatures(flow, index);
            edges.add(new FlowEdge(
                    "live-edge-" + index + "-" + edgeIndex,
                    source, destination, features));
            edgeIndex++;
            hosts.computeIfAbsent(source, HostAccumulator::new)
                    .observeSource(flow, packetCount);
            hosts.computeIfAbsent(destination, HostAccumulator::new)
                    .observeDestination(flow, packetCount);
        }

        List<GraphNode> nodes = new ArrayList<>();
        for (HostAccumulator host : hosts.values()) {
            nodes.add(host.node());
        }
        nodes.sort(java.util.Comparator.comparing(GraphNode::id));
        List<GraphEdge> graphEdges = new ArrayList<>();
        for (FlowEdge edge : edges) {
            graphEdges.add(new GraphEdge(
                    edge.id(), edge.source(), edge.destination(),
                    edge.features(), true, false));
        }
        return new GraphSnapshot(
                com.networkwm.graph.GraphConstructionService.SCHEMA_VERSION,
                start,
                end,
                true,
                List.copyOf(nodes),
                List.copyOf(graphEdges),
                new GraphLabel(false, AttackStage.NONE));
    }

    private static Map<String, Double> packetEdgeFeatures(JsonNode flow, int index) {
        Map<String, Double> features = new TreeMap<>();
        putFinite(features, "packet.packet_count",
                requiredDouble(flow, "packetCount", index), index);
        long first = requiredLong(flow, "firstSeenEpochMicros", index);
        long last = requiredLong(flow, "lastSeenEpochMicros", index);
        if (last < first) {
            throw new IllegalArgumentException(
                    "live window " + index + " has lastSeen before firstSeen");
        }
        putFinite(features, "packet.duration_micros",
                (double) (last - first), index);
        putFinite(features, "packet.ttl_mean",
                requiredDouble(flow, "ttlMean", index), index);
        putFinite(features, "packet.ttl_variance",
                requiredDouble(flow, "ttlVariance", index), index);
        putFinite(features, "packet.tcp_window_trend",
                requiredDouble(flow, "tcpWindowTrend", index), index);
        putFinite(features, "packet.fragment_count",
                requiredDouble(flow, "fragmentCount", index), index);
        putFinite(features, "packet.retransmission_count",
                requiredDouble(flow, "retransmissionCount", index), index);
        putFinite(features, "packet.truncated_packet_count",
                requiredDouble(flow, "truncatedPacketCount", index), index);
        putFinite(features, "packet.payload_size_mean",
                requiredDouble(flow, "payloadSizeMean", index), index);
        putFinite(features, "packet.payload_size_stddev",
                requiredDouble(flow, "payloadSizeStddev", index), index);
        putFinite(features, "packet.payload_size_skew",
                requiredDouble(flow, "payloadSizeSkew", index), index);
        if (flow.has("sourcePort")) {
            putFinite(features, "source_port",
                    requiredDouble(flow, "sourcePort", index), index);
        }
        if (flow.has("destinationPort")) {
            putFinite(features, "destination_port",
                    requiredDouble(flow, "destinationPort", index), index);
        }
        if (flow.has("protocol")) {
            putFinite(features, "protocol",
                    requiredDouble(flow, "protocol", index), index);
        }
        return Map.copyOf(features);
    }

    private static void putFinite(
            Map<String, Double> features, String name, double value, int index) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException(
                    "live window " + index + " has non-finite " + name);
        }
        features.put(name, value);
    }

    private static String requiredText(JsonNode node, String field, int index) {
        JsonNode value = node.get(field);
        if (value == null || !value.isTextual()) {
            throw new IllegalArgumentException(
                    "live window " + index + " is missing text field " + field);
        }
        return value.asText();
    }

    private static long requiredLong(JsonNode node, String field, int index) {
        JsonNode value = node.get(field);
        if (value == null || !value.isNumber()) {
            throw new IllegalArgumentException(
                    "live window " + index + " is missing numeric field " + field);
        }
        double asDouble = value.asDouble();
        if (!Double.isFinite(asDouble)) {
            throw new IllegalArgumentException(
                    "live window " + index + " has non-finite field " + field);
        }
        return value.asLong();
    }

    private static double requiredDouble(JsonNode node, String field, int index) {
        JsonNode value = node.get(field);
        if (value == null || !value.isNumber()) {
            throw new IllegalArgumentException(
                    "live window " + index + " is missing numeric field " + field);
        }
        double asDouble = value.asDouble();
        if (!Double.isFinite(asDouble)) {
            throw new IllegalArgumentException(
                    "live window " + index + " has non-finite field " + field);
        }
        return asDouble;
    }

    private static Instant microsToInstant(long epochMicros) {
        long seconds = Math.floorDiv(epochMicros, 1_000_000L);
        long micros = Math.floorMod(epochMicros, 1_000_000L);
        return Instant.ofEpochSecond(seconds, micros * 1_000L);
    }

    private record FlowEdge(
            String id, String source, String destination,
            Map<String, Double> features) {
    }

    private static final class HostAccumulator {
        private final String hostId;
        private double inboundBytes;
        private double outboundBytes;
        private long flowCount;
        private final java.util.Set<Integer> ports = new java.util.LinkedHashSet<>();

        private HostAccumulator(String hostId) {
            this.hostId = hostId;
        }

        private void observeSource(JsonNode flow, long packetCount) {
            double mean = flow.get("payloadSizeMean").asDouble();
            outboundBytes += mean * packetCount;
            flowCount++;
            ports.add(flow.get("destinationPort").asInt(0));
        }

        private void observeDestination(JsonNode flow, long packetCount) {
            double mean = flow.get("payloadSizeMean").asDouble();
            inboundBytes += mean * packetCount;
            flowCount++;
        }

        private GraphNode node() {
            Map<String, Double> features = new LinkedHashMap<>();
            features.put("inbound_bytes", inboundBytes);
            features.put("outbound_bytes", outboundBytes);
            features.put("flow_count", (double) flowCount);
            features.put(
                    "unique_destination_ports", (double) ports.stream()
                            .filter(port -> port > 0).count());
            features.put("syn_count", 0.0);
            features.put("ack_count", 0.0);
            features.put("syn_ack_ratio", 0.0);
            features.put("topology_available", 1.0);
            return new GraphNode(hostId, Map.copyOf(features));
        }
    }

    @SuppressWarnings("unused")
    private static String fallbackNode() {
        return WindowingService.NETWORK_FALLBACK_NODE;
    }
}
