package com.networkwm.api;

import com.networkwm.bridge.CppBridge;
import com.networkwm.bridge.CppBridge.ExtractionBatch;
import com.networkwm.graph.CicGraphDatasetService;
import com.networkwm.graph.GraphConstructionService;
import com.networkwm.graph.GraphConstructionService.GraphSnapshot;
import com.networkwm.graph.GraphContractService;
import com.networkwm.graph.GraphContractService.GraphSequence;
import com.networkwm.ingestion.IngestionService.FlowRecord;
import com.networkwm.window.WindowingService;
import com.networkwm.window.WindowingService.TrafficWindow;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

/** Bounded CSV/PCAP upload-to-graph adapter for offline inference. */
@Service
public final class UploadGraphService {
    public static final long MAX_UPLOAD_BYTES = 750L * 1024L * 1024L;
    public static final long MAX_CAPTURE_PACKETS = 2_000_000L;
    private static final long WINDOW_SECONDS = 10L;

    private final CicGraphDatasetService cic;
    private final WindowingService windowing;
    private final GraphConstructionService graphs;
    private final GraphContractService contracts;
    private final PacketExtractor packetExtractor;

    @Autowired
    public UploadGraphService(CicGraphDatasetService cic) {
        this(
                cic,
                new WindowingService(),
                new GraphConstructionService(),
                new GraphContractService(),
                path -> new CppBridge().extract(
                        path,
                        MAX_CAPTURE_PACKETS,
                        new CppBridge.ScanConfig(20, 0.70)));
    }

    UploadGraphService(
            CicGraphDatasetService cic,
            WindowingService windowing,
            GraphConstructionService graphs,
            GraphContractService contracts,
            PacketExtractor packetExtractor) {
        this.cic = Objects.requireNonNull(cic, "cic");
        this.windowing = Objects.requireNonNull(windowing, "windowing");
        this.graphs = Objects.requireNonNull(graphs, "graphs");
        this.contracts = Objects.requireNonNull(contracts, "contracts");
        this.packetExtractor = Objects.requireNonNull(
                packetExtractor, "packetExtractor");
    }

    public GraphSequence fromUpload(MultipartFile file) throws IOException {
        Objects.requireNonNull(file, "file");
        if (file.isEmpty()) {
            throw new IllegalArgumentException("uploaded file is empty");
        }
        if (file.getSize() > MAX_UPLOAD_BYTES) {
            throw new IllegalArgumentException(
                    "uploaded file exceeds the 750 MiB limit");
        }
        String filename = file.getOriginalFilename() == null
                ? "" : file.getOriginalFilename();
        String lower = filename.toLowerCase(Locale.ROOT);
        boolean csv = lower.endsWith(".csv");
        boolean pcap = lower.endsWith(".pcap") || lower.endsWith(".pcapng");
        if (!csv && !pcap) {
            throw new IllegalArgumentException(
                    "upload must be CICFlowMeter .csv, .pcap, or .pcapng");
        }

        String suffix = csv ? ".csv" : lower.endsWith(".pcapng")
                ? ".pcapng" : ".pcap";
        Path temporary = Files.createTempFile("kairos-upload-", suffix);
        try {
            file.transferTo(temporary);
            return csv ? fromCsv(temporary) : fromCapture(temporary);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    GraphSequence fromCsv(Path csv) throws IOException {
        return cic.aggregateCsv(csv, Duration.ofSeconds(WINDOW_SECONDS));
    }

    /**
     * Builds one fused flow+packet record per 5-tuple from a single capture.
     *
     * <p>Flow-level summaries are derived from the same extraction batch via
     * {@link CaptureFlowDeriver} and merged with the native packet features
     * by {@link WindowingService#windowAndMerge} 5-tuple matching, so every
     * combined flow carries real measured values on both sides — never
     * zero-filled placeholders from an unrelated source.
     */
    GraphSequence fromCapture(Path capture) throws IOException {
        ExtractionBatch extracted = packetExtractor.extract(capture);
        List<CppBridge.FlowFeatures> packetFlows =
                extracted.flows() == null
                        ? List.of() : extracted.flows();
        if (packetFlows.isEmpty()) {
            throw new IllegalArgumentException(
                    "capture contains no supported IPv4 TCP/UDP/ICMP flows");
        }

        List<FlowRecord> derivedFlows =
                CaptureFlowDeriver.deriveFlowRecords(packetFlows);
        List<TrafficWindow> windows = windowing.windowAndMerge(
                derivedFlows, extracted, Duration.ofSeconds(WINDOW_SECONDS));
        List<GraphSnapshot> snapshots = graphs.build(windows);
        return contracts.sequence(snapshots);
    }

    @FunctionalInterface
    interface PacketExtractor {
        ExtractionBatch extract(Path capture) throws IOException;
    }
}
