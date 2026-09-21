package com.networkwm.bridge;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;

/**
 * Typed JNI bridge to the dependency-free C++ packet feature extractor.
 */
public final class CppBridge {
    private static final ObjectMapper JSON = new ObjectMapper();

    static {
        String explicitLibrary = System.getProperty("kairos.native.library");
        if (explicitLibrary == null || explicitLibrary.isBlank()) {
            explicitLibrary = System.getenv("KAIROS_NATIVE_LIBRARY");
        }
        if (explicitLibrary == null || explicitLibrary.isBlank()) {
            System.loadLibrary("kairos_native");
        } else {
            System.load(Path.of(explicitLibrary).toAbsolutePath().normalize().toString());
        }
    }

    public ExtractionBatch extract(Path capturePath) throws IOException {
        return extract(capturePath, 4096L, new ScanConfig(20, 0.70));
    }

    public ExtractionBatch extract(
            Path capturePath,
            long maximumPackets,
            ScanConfig scanConfig) throws IOException {
        Objects.requireNonNull(capturePath, "capturePath");
        Objects.requireNonNull(scanConfig, "scanConfig");
        if (!Files.isRegularFile(capturePath)) {
            throw new IOException("Capture does not exist or is not a file: " + capturePath);
        }
        if (maximumPackets <= 0L) {
            throw new IllegalArgumentException("maximumPackets must be positive");
        }
        if (scanConfig.minimumUniquePorts() < 2) {
            throw new IllegalArgumentException("minimumUniquePorts must be at least 2");
        }
        if (!Double.isFinite(scanConfig.sequentialRatioThreshold())
                || scanConfig.sequentialRatioThreshold() < 0.0
                || scanConfig.sequentialRatioThreshold() > 1.0) {
            throw new IllegalArgumentException(
                    "sequentialRatioThreshold must be finite and between 0 and 1");
        }

        String encoded = extractNative(
                capturePath.toAbsolutePath().normalize().toString(),
                maximumPackets,
                scanConfig.minimumUniquePorts(),
                scanConfig.sequentialRatioThreshold());
        try {
            return JSON.readValue(encoded, ExtractionBatch.class);
        } catch (JsonProcessingException error) {
            throw new IOException("Native extractor returned invalid JSON", error);
        }
    }

    private static native String extractNative(
            String capturePath,
            long maximumPackets,
            int minimumUniquePorts,
            double sequentialRatioThreshold) throws IOException;

    public record ScanConfig(int minimumUniquePorts, double sequentialRatioThreshold) {
    }

    public record ExtractionBatch(
            List<FlowFeatures> flows,
            List<PortScanFeatures> portScans) {
        public ExtractionBatch {
            flows = List.copyOf(flows);
            portScans = List.copyOf(portScans);
        }
    }

    public record FlowFeatures(
            String sourceIp,
            String destinationIp,
            int sourcePort,
            int destinationPort,
            int protocol,
            long packetCount,
            long firstSeenEpochMicros,
            long lastSeenEpochMicros,
            double ttlMean,
            double ttlVariance,
            double tcpWindowTrend,
            long fragmentCount,
            long retransmissionCount,
            long truncatedPacketCount,
            double payloadSizeMean,
            double payloadSizeStddev,
            double payloadSizeSkew) {
    }

    public record PortScanFeatures(
            String sourceIp,
            long observedPackets,
            long uniqueDestinationPorts,
            double sequentialTransitionRatio,
            String pattern) {
    }
}
