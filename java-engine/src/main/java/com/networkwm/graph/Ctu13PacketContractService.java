package com.networkwm.graph;

import com.networkwm.bridge.CppBridge;
import com.networkwm.graph.GraphConstructionService.GraphEdge;
import com.networkwm.graph.GraphConstructionService.GraphLabel;
import com.networkwm.graph.GraphConstructionService.GraphNode;
import com.networkwm.graph.GraphConstructionService.GraphSnapshot;
import com.networkwm.graph.GraphContractService.GraphSequence;
import com.networkwm.ingestion.IngestionService.AttackStage;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * Phase 58: packet-native CTU-13 contract.
 *
 * <p>Unlike CIC vector mode (single {@code __network__} node), CTU-13
 * truncated captures retain real endpoint IPs, so this service preserves
 * host-to-host topology. Edge features are packet-native
 * ({@code packet.*}) and intentionally use a different schema from the
 * CIC-trained model — the Python contract loader must reject the mismatch
 * rather than silently score it. See {@code results/ctu13_*} artifacts.
 */
@Service
public final class Ctu13PacketContractService {
    private final GraphContractService contract;

    public Ctu13PacketContractService() {
        this(new GraphContractService());
    }

    Ctu13PacketContractService(GraphContractService contract) {
        this.contract = Objects.requireNonNull(contract, "contract");
    }

    /**
     * Split a capture-wide extraction into gap-preserving state windows.
     *
     * Long-lived 5-tuples are already divided by the native extractor. Keeping
     * timeline construction here guarantees that uploads and training exports
     * use the identical bucket and empty-window semantics.
     */
    public GraphSequence fromTimeline(
            CppBridge.ExtractionBatch batch,
            long windowSeconds) {
        Objects.requireNonNull(batch, "batch");
        if (windowSeconds <= 0L) {
            throw new IllegalArgumentException("windowSeconds must be positive");
        }
        List<CppBridge.FlowFeatures> allFlows =
                batch.flows() == null ? List.of() : batch.flows();
        if (allFlows.isEmpty()) {
            throw new IllegalArgumentException(
                    "capture contains no supported IPv4 TCP/UDP/ICMP flows");
        }

        TreeMap<Long, List<CppBridge.FlowFeatures>> byWindow = new TreeMap<>();
        for (CppBridge.FlowFeatures flow : allFlows) {
            long epochSeconds = Math.floorDiv(
                    flow.firstSeenEpochMicros(), 1_000_000L);
            long bucket = Math.floorDiv(epochSeconds, windowSeconds)
                    * windowSeconds;
            byWindow.computeIfAbsent(
                    bucket, ignored -> new ArrayList<>()).add(flow);
        }

        List<GraphSnapshot> windows = new ArrayList<>();
        GraphSequence schema = null;
        for (long bucket = byWindow.firstKey();
                bucket <= byWindow.lastKey(); bucket += windowSeconds) {
            List<CppBridge.FlowFeatures> flows =
                    byWindow.getOrDefault(bucket, List.of());
            TreeSet<String> sources = new TreeSet<>();
            for (CppBridge.FlowFeatures flow : flows) {
                sources.add(flow.sourceIp());
            }
            long windowBucket = bucket;
            List<CppBridge.PortScanFeatures> scans =
                    (batch.portScans() == null ? List
                            .<CppBridge.PortScanFeatures>of()
                            : batch.portScans()).stream()
                    .filter(scan -> sources.contains(scan.sourceIp()))
                    .filter(scan -> Math.floorDiv(
                            scan.windowStartEpochMicros(), 1_000_000L)
                            == windowBucket)
                    .toList();
            GraphSequence one = fromExtraction(
                    new CppBridge.ExtractionBatch(flows, scans),
                    Instant.ofEpochSecond(bucket),
                    windowSeconds);
            if (schema == null) {
                schema = one;
            }
            windows.addAll(one.windows());
        }
        return new GraphSequence(
                schema.contractVersion(),
                schema.nodeFeatureNames(),
                schema.edgeFeatureNames(),
                windows);
    }

    public GraphSequence fromExtraction(
            CppBridge.ExtractionBatch batch,
            Instant windowStart,
            long windowSeconds) {
        Objects.requireNonNull(batch, "batch");
        Objects.requireNonNull(windowStart, "windowStart");
        if (windowSeconds <= 0L) {
            throw new IllegalArgumentException("windowSeconds must be positive");
        }
        Instant windowEnd = windowStart.plusSeconds(windowSeconds);

        Map<String, HostStats> hosts = new TreeMap<>();
        List<GraphEdge> edges = new ArrayList<>();
        List<CppBridge.FlowFeatures> flows =
                batch.flows() == null ? List.of() : batch.flows();
        List<CppBridge.PortScanFeatures> scans =
                batch.portScans() == null ? List.of() : batch.portScans();

        for (int index = 0; index < flows.size(); ++index) {
            CppBridge.FlowFeatures flow = flows.get(index);
            String source = normalizeIp(flow.sourceIp());
            String destination = normalizeIp(flow.destinationIp());
            hosts.computeIfAbsent(source, ignored -> new HostStats())
                    .observeOutbound(flow);
            hosts.computeIfAbsent(destination, ignored -> new HostStats())
                    .observeInbound(flow);

            Map<String, Double> edgeFeatures = new TreeMap<>();
            edgeFeatures.put("packet.packet_count", (double) flow.packetCount());
            edgeFeatures.put("packet.duration_micros",
                    (double) Math.max(0L,
                            flow.lastSeenEpochMicros() - flow.firstSeenEpochMicros()));
            edgeFeatures.put("packet.ttl_mean", flow.ttlMean());
            edgeFeatures.put("packet.ttl_variance", flow.ttlVariance());
            edgeFeatures.put("packet.tcp_window_trend", flow.tcpWindowTrend());
            edgeFeatures.put("packet.fragment_count", (double) flow.fragmentCount());
            edgeFeatures.put("packet.retransmission_count",
                    (double) flow.retransmissionCount());
            edgeFeatures.put("packet.truncated_packet_count",
                    (double) flow.truncatedPacketCount());
            edgeFeatures.put("packet.payload_size_mean", flow.payloadSizeMean());
            edgeFeatures.put("packet.payload_size_stddev", flow.payloadSizeStddev());
            edgeFeatures.put("packet.payload_size_skew", flow.payloadSizeSkew());
            edgeFeatures.put("source_port", (double) flow.sourcePort());
            edgeFeatures.put("destination_port", (double) flow.destinationPort());
            edgeFeatures.put("protocol", (double) flow.protocol());

            edges.add(new GraphEdge(
                    "edge-" + index, source, destination,
                    Map.copyOf(edgeFeatures), true, false));
        }

        for (CppBridge.PortScanFeatures scan : scans) {
            String source = normalizeIp(scan.sourceIp());
            hosts.computeIfAbsent(source, ignored -> new HostStats())
                    .observeCaptureScan(scan);
        }

        if (hosts.isEmpty()) {
            hosts.put("__network__", new HostStats());
        }

        List<GraphNode> nodes = new ArrayList<>();
        hosts.forEach((id, stats) -> {
            Map<String, Double> features = new LinkedHashMap<>();
            features.put("inbound_bytes", stats.inboundBytes);
            features.put("outbound_bytes", stats.outboundBytes);
            features.put("flow_count", (double) stats.flowCount);
            features.put("unique_destination_ports",
                    (double) stats.destinationPorts.size());
            features.put("syn_count", 0.0);
            features.put("ack_count", 0.0);
            features.put("syn_ack_ratio", 0.0);
            features.put("topology_available", 1.0);
            features.put("packet.capture_scan_observed_packets",
                    (double) stats.scanObservedPackets);
            features.put("packet.capture_scan_unique_destination_ports",
                    (double) stats.scanUniqueDestinationPorts);
            features.put("packet.capture_scan_sequential_transition_ratio",
                    stats.scanSequentialTransitionRatio);
            features.put("packet.capture_scan_pattern_sequential",
                    stats.scanSequential ? 1.0 : 0.0);
            features.put("packet.capture_scan_pattern_randomized",
                    stats.scanRandomized ? 1.0 : 0.0);
            if ("__network__".equals(id)) {
                features.put("topology_available", 0.0);
            }
            nodes.add(new GraphNode(id, Map.copyOf(features)));
        });
        nodes.sort(java.util.Comparator.comparing(GraphNode::id));

        GraphSnapshot snapshot = new GraphSnapshot(
                GraphConstructionService.SCHEMA_VERSION,
                windowStart,
                windowEnd,
                !flows.isEmpty(),
                List.copyOf(nodes),
                List.copyOf(edges),
                new GraphLabel(false, AttackStage.NONE));
        return contract.sequence(List.of(snapshot));
    }

    private static String normalizeIp(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException(
                    "CTU-13 packet flows must carry endpoint IPs; refusing to invent topology");
        }
        return raw.trim();
    }

    private static final class HostStats {
        private double inboundBytes;
        private double outboundBytes;
        private long flowCount;
        private final TreeSet<Integer> destinationPorts = new TreeSet<>();
        private long scanObservedPackets;
        private long scanUniqueDestinationPorts;
        private double scanSequentialTransitionRatio;
        private boolean scanSequential;
        private boolean scanRandomized;

        private void observeOutbound(CppBridge.FlowFeatures flow) {
            ++flowCount;
            outboundBytes += flow.payloadSizeMean() * flow.packetCount();
            if (flow.destinationPort() > 0) {
                destinationPorts.add(flow.destinationPort());
            }
        }

        private void observeInbound(CppBridge.FlowFeatures flow) {
            inboundBytes += flow.payloadSizeMean() * flow.packetCount();
        }

        private void observeCaptureScan(CppBridge.PortScanFeatures scan) {
            scanObservedPackets = Math.max(
                    scanObservedPackets, scan.observedPackets());
            scanUniqueDestinationPorts = Math.max(
                    scanUniqueDestinationPorts,
                    scan.uniqueDestinationPorts());
            scanSequentialTransitionRatio = Math.max(
                    scanSequentialTransitionRatio,
                    scan.sequentialTransitionRatio());
            String pattern = scan.pattern() == null
                    ? "" : scan.pattern().toLowerCase(java.util.Locale.ROOT);
            scanSequential |= pattern.contains("sequential");
            scanRandomized |= pattern.contains("random");
        }
    }
}
