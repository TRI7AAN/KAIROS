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
            nodes.add(new GraphNode(id, Map.copyOf(features)));
        });
        nodes.sort(java.util.Comparator.comparing(GraphNode::id));

        GraphSnapshot snapshot = new GraphSnapshot(
                GraphConstructionService.SCHEMA_VERSION,
                windowStart,
                windowEnd,
                true,
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
    }
}
