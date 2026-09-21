package com.networkwm.window;

import com.networkwm.bridge.CppBridge;
import com.networkwm.ingestion.IngestionService.AttackStage;
import com.networkwm.ingestion.IngestionService.FlowRecord;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;

/**
 * Creates ordered network-state windows and merges timestamped native features.
 */
@Service
public final class WindowingService {
    public static final Duration DEFAULT_WINDOW = Duration.ofSeconds(10);
    public static final String NETWORK_FALLBACK_NODE = "__network__";

    public List<TrafficWindow> windowAndMerge(
            List<FlowRecord> flowRecords,
            CppBridge.ExtractionBatch packetBatch) {
        return windowAndMerge(flowRecords, packetBatch, DEFAULT_WINDOW);
    }

    public List<TrafficWindow> windowAndMerge(
            List<FlowRecord> flowRecords,
            CppBridge.ExtractionBatch packetBatch,
            Duration windowSize) {
        Objects.requireNonNull(packetBatch, "packetBatch");
        return windowAndMergeInternal(
                flowRecords,
                packetBatch.flows() == null
                        ? List.of() : packetBatch.flows(),
                packetBatch.portScans() == null
                        ? List.of() : packetBatch.portScans(),
                windowSize);
    }

    public List<TrafficWindow> windowAndMerge(
            List<FlowRecord> flowRecords,
            List<CppBridge.FlowFeatures> packetFlows,
            Duration windowSize) {
        return windowAndMergeInternal(
                flowRecords, packetFlows, List.of(), windowSize);
    }

    private List<TrafficWindow> windowAndMergeInternal(
            List<FlowRecord> flowRecords,
            List<CppBridge.FlowFeatures> packetFlows,
            List<CppBridge.PortScanFeatures> portScans,
            Duration windowSize) {
        Objects.requireNonNull(flowRecords, "flowRecords");
        Objects.requireNonNull(packetFlows, "packetFlows");
        Objects.requireNonNull(portScans, "portScans");
        long windowSeconds = validateWindow(windowSize);

        Map<Instant, MutableWindow> windows = new TreeMap<>();
        for (FlowRecord flow : flowRecords) {
            Instant start = floor(flow.timestamp(), windowSeconds);
            windows.computeIfAbsent(
                    start, ignored -> new MutableWindow(start, windowSeconds))
                    .addFlow(flow);
        }
        for (CppBridge.FlowFeatures packet : packetFlows) {
            Instant timestamp = microsToInstant(packet.firstSeenEpochMicros());
            Instant start = floor(timestamp, windowSeconds);
            windows.computeIfAbsent(
                    start, ignored -> new MutableWindow(start, windowSeconds))
                    .addPacket(packet);
        }
        for (CppBridge.PortScanFeatures scan : portScans) {
            if (scan == null || scan.sourceIp() == null
                    || scan.sourceIp().isBlank()) {
                continue;
            }
            for (MutableWindow window : windows.values()) {
                window.observeScan(scan);
            }
        }

        return windows.values().stream()
                .map(MutableWindow::finish)
                .toList();
    }

    private static long validateWindow(Duration windowSize) {
        Objects.requireNonNull(windowSize, "windowSize");
        if (windowSize.isNegative() || windowSize.isZero()
                || windowSize.getNano() != 0) {
            throw new IllegalArgumentException(
                    "windowSize must be a positive whole number of seconds");
        }
        return windowSize.getSeconds();
    }

    private static Instant floor(Instant timestamp, long windowSeconds) {
        long startSecond = Math.floorDiv(timestamp.getEpochSecond(), windowSeconds)
                * windowSeconds;
        return Instant.ofEpochSecond(startSecond);
    }

    private static Instant microsToInstant(long epochMicros) {
        long seconds = Math.floorDiv(epochMicros, 1_000_000L);
        long micros = Math.floorMod(epochMicros, 1_000_000L);
        return Instant.ofEpochSecond(seconds, micros * 1_000L);
    }

    private static final class MutableWindow {
        private final Instant start;
        private final long windowSeconds;
        private final List<MutableCombinedFlow> flows = new ArrayList<>();
        private final Map<FlowIdentity, List<MutableCombinedFlow>> matchable =
                new HashMap<>();
        private final Map<String, MutableHost> hosts = new LinkedHashMap<>();
        private final Map<AttackStage, Long> maliciousStageCounts = new HashMap<>();
        private boolean topologyAvailable = true;

        private MutableWindow(Instant start, long windowSeconds) {
            this.start = start;
            this.windowSeconds = windowSeconds;
        }

        private void addFlow(FlowRecord flow) {
            MutableCombinedFlow combined = new MutableCombinedFlow(flow, null);
            flows.add(combined);
            FlowIdentity identity = FlowIdentity.from(flow);
            if (identity != null) {
                matchable.computeIfAbsent(identity, ignored -> new ArrayList<>())
                        .add(combined);
                addEndpointHosts(flow);
            } else {
                topologyAvailable = false;
                addFallbackHost(flow);
            }
            if (flow.stage() != AttackStage.NONE) {
                maliciousStageCounts.merge(flow.stage(), 1L, Long::sum);
            }
        }

        private void addPacket(CppBridge.FlowFeatures packet) {
            FlowIdentity identity = FlowIdentity.from(packet);
            List<MutableCombinedFlow> candidates = matchable.get(identity);
            if (candidates != null) {
                for (MutableCombinedFlow candidate : candidates) {
                    if (candidate.packet == null) {
                        candidate.packet = packet;
                        return;
                    }
                }
            }
            flows.add(new MutableCombinedFlow(null, packet));
            addPacketHosts(packet);
        }

        private void addEndpointHosts(FlowRecord flow) {
            double forwardBytes = feature(flow, "totlen_fwd_pkts",
                    "total_length_of_fwd_packets");
            double backwardBytes = feature(flow, "totlen_bwd_pkts",
                    "total_length_of_bwd_packets");
            double syn = feature(flow, "syn_flag_cnt", "syn_flag_count");
            double ack = feature(flow, "ack_flag_cnt", "ack_flag_count");

            MutableHost source = hosts.computeIfAbsent(
                    flow.sourceIp(), id -> new MutableHost(id, true));
            source.outboundBytes += forwardBytes;
            source.inboundBytes += backwardBytes;
            source.flowCount++;
            source.synCount += syn;
            source.ackCount += ack;
            if (flow.destinationPort() > 0) {
                source.uniqueDestinationPorts.add(flow.destinationPort());
            }

            MutableHost destination = hosts.computeIfAbsent(
                    flow.destinationIp(), id -> new MutableHost(id, true));
            destination.outboundBytes += backwardBytes;
            destination.inboundBytes += forwardBytes;
            destination.flowCount++;
            destination.synCount += syn;
            destination.ackCount += ack;
        }

        private void addFallbackHost(FlowRecord flow) {
            MutableHost network = hosts.computeIfAbsent(
                    NETWORK_FALLBACK_NODE,
                    id -> new MutableHost(id, false));
            network.outboundBytes += feature(flow, "totlen_fwd_pkts",
                    "total_length_of_fwd_packets");
            network.inboundBytes += feature(flow, "totlen_bwd_pkts",
                    "total_length_of_bwd_packets");
            network.flowCount++;
            network.synCount += feature(flow, "syn_flag_cnt", "syn_flag_count");
            network.ackCount += feature(flow, "ack_flag_cnt", "ack_flag_count");
            if (flow.destinationPort() > 0) {
                network.uniqueDestinationPorts.add(flow.destinationPort());
            }
        }

        private void addPacketHosts(CppBridge.FlowFeatures packet) {
            double logicalBytes = packet.payloadSizeMean() * packet.packetCount();
            MutableHost source = hosts.computeIfAbsent(
                    packet.sourceIp(), id -> new MutableHost(id, true));
            source.outboundBytes += logicalBytes;
            source.flowCount++;
            if (packet.destinationPort() > 0) {
                source.uniqueDestinationPorts.add(packet.destinationPort());
            }
            MutableHost destination = hosts.computeIfAbsent(
                    packet.destinationIp(), id -> new MutableHost(id, true));
            destination.inboundBytes += logicalBytes;
            destination.flowCount++;
        }

        /**
         * Attaches capture-level port-scan evidence to the scanning host.
         *
         * <p>Mirrors {@code Ctu13PacketContractService} semantics: a scan is
         * recorded only in windows where its source already appears as a
         * host, so scan evidence is never attached to an invented host.
         */
        private void observeScan(CppBridge.PortScanFeatures scan) {
            MutableHost host = hosts.get(scan.sourceIp());
            if (host == null) {
                return;
            }
            host.scanObservedPackets = Math.max(
                    host.scanObservedPackets, scan.observedPackets());
            host.scanUniqueDestinationPorts = Math.max(
                    host.scanUniqueDestinationPorts,
                    scan.uniqueDestinationPorts());
            host.scanSequentialTransitionRatio = Math.max(
                    host.scanSequentialTransitionRatio,
                    scan.sequentialTransitionRatio());
            String pattern = scan.pattern() == null
                    ? "" : scan.pattern().toLowerCase(java.util.Locale.ROOT);
            host.scanSequential |= pattern.contains("sequential");
            host.scanRandomized |= pattern.contains("random");
        }

        private TrafficWindow finish() {
            List<CombinedFlow> immutableFlows = flows.stream()
                    .map(value -> new CombinedFlow(value.flow, value.packet))
                    .toList();
            Map<String, HostAggregate> immutableHosts = new LinkedHashMap<>();
            hosts.entrySet().stream()
                    .sorted(Map.Entry.comparingByKey())
                    .forEach(entry -> immutableHosts.put(
                            entry.getKey(), entry.getValue().finish()));
            AttackStage stage = maliciousStageCounts.entrySet().stream()
                    .max(Comparator.<Map.Entry<AttackStage, Long>>
                            comparingLong(Map.Entry::getValue)
                            .thenComparing(entry -> entry.getKey().name()))
                    .map(Map.Entry::getKey)
                    .orElse(AttackStage.NONE);
            return new TrafficWindow(
                    start,
                    start.plusSeconds(windowSeconds),
                    immutableFlows,
                    immutableHosts,
                    stage,
                    topologyAvailable);
        }
    }

    private static double feature(FlowRecord flow, String... aliases) {
        for (String alias : aliases) {
            Double value = flow.features().get(alias);
            if (value != null) {
                return value;
            }
        }
        return 0.0;
    }

    private static final class MutableCombinedFlow {
        private final FlowRecord flow;
        private CppBridge.FlowFeatures packet;

        private MutableCombinedFlow(
                FlowRecord flow,
                CppBridge.FlowFeatures packet) {
            this.flow = flow;
            this.packet = packet;
        }
    }

    private static final class MutableHost {
        private final String hostId;
        private final boolean topologyAvailable;
        private double inboundBytes;
        private double outboundBytes;
        private long flowCount;
        private double synCount;
        private double ackCount;
        private final Set<Integer> uniqueDestinationPorts = new LinkedHashSet<>();
        private long scanObservedPackets;
        private long scanUniqueDestinationPorts;
        private double scanSequentialTransitionRatio;
        private boolean scanSequential;
        private boolean scanRandomized;

        private MutableHost(String hostId, boolean topologyAvailable) {
            this.hostId = hostId;
            this.topologyAvailable = topologyAvailable;
        }

        private HostAggregate finish() {
            return new HostAggregate(
                    hostId,
                    inboundBytes,
                    outboundBytes,
                    flowCount,
                    uniqueDestinationPorts.size(),
                    synCount,
                    ackCount,
                    synCount / Math.max(ackCount, 1.0),
                    topologyAvailable,
                    scanObservedPackets,
                    scanUniqueDestinationPorts,
                    scanSequentialTransitionRatio,
                    scanSequential,
                    scanRandomized);
        }
    }

    private record FlowIdentity(
            String sourceIp,
            String destinationIp,
            int sourcePort,
            int destinationPort,
            int protocol) {
        private static FlowIdentity from(FlowRecord flow) {
            if (flow.sourceIp().isBlank() || flow.destinationIp().isBlank()) {
                return null;
            }
            return new FlowIdentity(
                    flow.sourceIp(), flow.destinationIp(), flow.sourcePort(),
                    flow.destinationPort(), flow.protocol());
        }

        private static FlowIdentity from(CppBridge.FlowFeatures flow) {
            return new FlowIdentity(
                    flow.sourceIp(), flow.destinationIp(), flow.sourcePort(),
                    flow.destinationPort(), flow.protocol());
        }
    }

    public record CombinedFlow(
            FlowRecord flow,
            CppBridge.FlowFeatures packetFeatures) {
        public boolean packetOnly() {
            return flow == null;
        }

        public boolean flowOnly() {
            return packetFeatures == null;
        }
    }

    public record HostAggregate(
            String hostId,
            double inboundBytes,
            double outboundBytes,
            long flowCount,
            long uniqueDestinationPorts,
            double synCount,
            double ackCount,
            double synAckRatio,
            boolean topologyAvailable,
            long scanObservedPackets,
            long scanUniqueDestinationPorts,
            double scanSequentialTransitionRatio,
            boolean scanSequential,
            boolean scanRandomized) {
    }

    public record TrafficWindow(
            Instant start,
            Instant end,
            List<CombinedFlow> flows,
            Map<String, HostAggregate> hosts,
            AttackStage stage,
            boolean topologyAvailable) {
        public TrafficWindow {
            flows = List.copyOf(flows);
            hosts = Map.copyOf(hosts);
        }
    }
}
