package com.networkwm.api;

import com.networkwm.bridge.CppBridge;
import com.networkwm.ingestion.IngestionService.AttackStage;
import com.networkwm.ingestion.IngestionService.FlowRecord;

import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Derives flow-level summaries from a PCAP extraction batch.
 *
 * <p>Every value produced here is computed from the same underlying packets
 * as the native {@code packet.*} features, so routing the derived records
 * together with the packet flows through
 * {@code WindowingService.windowAndMerge()} fuses both feature levels by
 * 5-tuple into one record per flow — never mixing a CSV with an unrelated
 * capture.
 *
 * <p>Derived features use the {@code flow.*} prefix to distinguish
 * capture-derived summaries from CICFlowMeter-measured fields. Anything the
 * capture cannot observe (TCP flag counts, backward-direction splits,
 * inter-arrival statistics) is omitted entirely — never zero-filled — so
 * downstream stages can report it as unavailable instead of measured.
 */
final class CaptureFlowDeriver {
    private CaptureFlowDeriver() {
    }

    static List<FlowRecord> deriveFlowRecords(
            List<CppBridge.FlowFeatures> packetFlows) {
        Objects.requireNonNull(packetFlows, "packetFlows");
        List<FlowRecord> records = new ArrayList<>(packetFlows.size());
        for (CppBridge.FlowFeatures packet : packetFlows) {
            Objects.requireNonNull(packet, "packet flow");
            long durationMicros = Math.max(0L,
                    packet.lastSeenEpochMicros()
                            - packet.firstSeenEpochMicros());
            double packetCount = packet.packetCount();
            double payloadBytesEstimate =
                    packet.payloadSizeMean() * packetCount;
            double durationSeconds = durationMicros / 1_000_000.0;

            Map<String, Double> features = new LinkedHashMap<>();
            features.put("flow.packet_count", packetCount);
            features.put("flow.duration_micros", (double) durationMicros);
            features.put(
                    "flow.payload_bytes_estimate", payloadBytesEstimate);
            features.put(
                    "flow.payload_size_mean", packet.payloadSizeMean());
            features.put("flow.packet_rate_per_s", durationSeconds > 0.0
                    ? packetCount / durationSeconds : packetCount);
            features.put("flow.byte_rate_per_s", durationSeconds > 0.0
                    ? payloadBytesEstimate / durationSeconds
                    : payloadBytesEstimate);
            for (double value : features.values()) {
                if (!Double.isFinite(value) || value < 0.0) {
                    throw new IllegalArgumentException(
                            "capture-derived flow feature is not a finite "
                                    + "non-negative value");
                }
            }

            records.add(new FlowRecord(
                    microsToInstant(packet.firstSeenEpochMicros()),
                    packet.sourceIp(),
                    packet.destinationIp(),
                    packet.sourcePort(),
                    packet.destinationPort(),
                    packet.protocol(),
                    Map.copyOf(features),
                    "",
                    "",
                    AttackStage.NONE));
        }
        return List.copyOf(records);
    }

    private static Instant microsToInstant(long epochMicros) {
        long seconds = Math.floorDiv(epochMicros, 1_000_000L);
        long micros = Math.floorMod(epochMicros, 1_000_000L);
        return Instant.ofEpochSecond(seconds, micros * 1_000L);
    }
}
