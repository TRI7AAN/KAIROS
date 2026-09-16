package com.networkwm.graph;

import com.networkwm.graph.GraphConstructionService.GraphEdge;
import com.networkwm.graph.GraphConstructionService.GraphLabel;
import com.networkwm.graph.GraphConstructionService.GraphNode;
import com.networkwm.graph.GraphConstructionService.GraphSnapshot;
import com.networkwm.graph.GraphContractService.GraphSequence;
import com.networkwm.ingestion.IngestionService;
import com.networkwm.ingestion.IngestionService.AttackStage;
import com.networkwm.ingestion.IngestionService.FlowRecord;
import com.networkwm.window.WindowingService;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Path;
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
 * Memory-bounded vector-mode aggregation for endpoint-free CIC CSV datasets.
 */
@Service
public final class CicGraphDatasetService {
    private final IngestionService ingestion;
    private final GraphContractService contract;

    public CicGraphDatasetService() {
        this(new IngestionService(), new GraphContractService());
    }

    CicGraphDatasetService(
            IngestionService ingestion,
            GraphContractService contract) {
        this.ingestion = ingestion;
        this.contract = contract;
    }

    public ExportSummary export(
            List<Path> csvFiles,
            Path destination,
            Duration windowSize) throws IOException {
        Objects.requireNonNull(csvFiles, "csvFiles");
        Objects.requireNonNull(destination, "destination");
        Accumulator accumulator = new Accumulator(windowSize);
        long rows = 0L;
        for (Path csvFile : csvFiles) {
            IngestionService.IngestionSummary summary = ingestion.ingest(
                    csvFile,
                    IngestionService.cicIds2018Timelines(),
                    accumulator::accept);
            rows += summary.rowsEmitted();
        }
        GraphSequence sequence = accumulator.finish(contract);
        contract.write(destination, sequence);
        return new ExportSummary(rows, sequence.windows().size(), destination);
    }

    public GraphSequence aggregate(
            List<FlowRecord> records,
            Duration windowSize) {
        Accumulator accumulator = new Accumulator(windowSize);
        records.forEach(accumulator::accept);
        return accumulator.finish(contract);
    }

    private static final class Accumulator {
        private final long windowSeconds;
        private final Map<Instant, WindowStatistics> windows = new TreeMap<>();

        private Accumulator(Duration windowSize) {
            Objects.requireNonNull(windowSize, "windowSize");
            if (windowSize.isZero() || windowSize.isNegative()
                    || windowSize.getNano() != 0) {
                throw new IllegalArgumentException(
                        "windowSize must be a positive whole number of seconds");
            }
            windowSeconds = windowSize.getSeconds();
        }

        private void accept(FlowRecord flow) {
            long startSecond = Math.floorDiv(
                    flow.timestamp().getEpochSecond(), windowSeconds)
                    * windowSeconds;
            Instant start = Instant.ofEpochSecond(startSecond);
            windows.computeIfAbsent(start, ignored -> new WindowStatistics())
                    .accept(flow);
        }

        private GraphSequence finish(GraphContractService contract) {
            List<GraphSnapshot> snapshots = new ArrayList<>(windows.size());
            windows.forEach((start, statistics) ->
                    snapshots.add(statistics.snapshot(start, windowSeconds)));
            return contract.sequence(snapshots);
        }
    }

    private static final class WindowStatistics {
        private final Map<String, FeatureStatistics> features = new TreeMap<>();
        private final Map<AttackStage, Long> stageCounts = new HashMap<>();
        private final Set<Integer> destinationPorts = new LinkedHashSet<>();
        private long flowCount;
        private double inboundBytes;
        private double outboundBytes;
        private double synCount;
        private double ackCount;

        private void accept(FlowRecord flow) {
            ++flowCount;
            flow.features().forEach((name, value) ->
                    features.computeIfAbsent(
                            name, ignored -> new FeatureStatistics()).accept(value));
            outboundBytes += feature(
                    flow, "totlen_fwd_pkts", "total_length_of_fwd_packets");
            inboundBytes += feature(
                    flow, "totlen_bwd_pkts", "total_length_of_bwd_packets");
            synCount += feature(flow, "syn_flag_cnt", "syn_flag_count");
            ackCount += feature(flow, "ack_flag_cnt", "ack_flag_count");
            if (flow.destinationPort() > 0) {
                destinationPorts.add(flow.destinationPort());
            }
            if (flow.stage() != AttackStage.NONE) {
                stageCounts.merge(flow.stage(), 1L, Long::sum);
            }
        }

        private GraphSnapshot snapshot(Instant start, long windowSeconds) {
            Map<String, Double> nodeFeatures = new LinkedHashMap<>();
            nodeFeatures.put("inbound_bytes", inboundBytes);
            nodeFeatures.put("outbound_bytes", outboundBytes);
            nodeFeatures.put("flow_count", (double) flowCount);
            nodeFeatures.put(
                    "unique_destination_ports", (double) destinationPorts.size());
            nodeFeatures.put("syn_count", synCount);
            nodeFeatures.put("ack_count", ackCount);
            nodeFeatures.put("syn_ack_ratio", synCount / Math.max(ackCount, 1.0));
            nodeFeatures.put("topology_available", 0.0);

            Map<String, Double> edgeFeatures = new LinkedHashMap<>();
            features.forEach((name, values) -> {
                edgeFeatures.put(name + ".mean", values.mean);
                edgeFeatures.put(name + ".std", values.standardDeviation());
                edgeFeatures.put(name + ".max", values.maximum);
                edgeFeatures.put(name + ".sum", values.sum);
            });
            AttackStage stage = stageCounts.entrySet().stream()
                    .max(Comparator.<Map.Entry<AttackStage, Long>>
                            comparingLong(Map.Entry::getValue)
                            .thenComparing(entry -> entry.getKey().name()))
                    .map(Map.Entry::getKey)
                    .orElse(AttackStage.NONE);
            String fallback = WindowingService.NETWORK_FALLBACK_NODE;
            return new GraphSnapshot(
                    GraphConstructionService.SCHEMA_VERSION,
                    start,
                    start.plusSeconds(windowSeconds),
                    false,
                    List.of(new GraphNode(fallback, Map.copyOf(nodeFeatures))),
                    List.of(new GraphEdge(
                            "aggregate-edge",
                            fallback,
                            fallback,
                            Map.copyOf(edgeFeatures),
                            false,
                            true)),
                    new GraphLabel(stage != AttackStage.NONE, stage));
        }
    }

    private static final class FeatureStatistics {
        private long count;
        private double mean;
        private double m2;
        private double maximum = Double.NEGATIVE_INFINITY;
        private double sum;

        private void accept(double value) {
            ++count;
            sum += value;
            maximum = Math.max(maximum, value);
            double delta = value - mean;
            mean += delta / count;
            m2 += delta * (value - mean);
        }

        private double standardDeviation() {
            return count == 0 ? 0.0 : Math.sqrt(Math.max(0.0, m2 / count));
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

    public record ExportSummary(
            long rowsAggregated,
            long windowsExported,
            Path destination) {
    }
}
