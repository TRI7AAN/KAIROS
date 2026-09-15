#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace networkwm {

/**
 * Packet-level feature extractor (C++ engine).
 *
 * Intended responsibility (deferred to later phases):
 *   - Parse raw PCAP byte streams at native speed.
 *   - Compute per-flow packet-level signals: TTL mean/variance,
 *     TCP window-size trend, IP fragment flag counts, retransmission
 *     counts, payload size statistics, and port-scan signature
 *     detection (sequential vs randomized access patterns).
 *   - Emit structured feature records consumed by the Java ingestion
 *     service via JNI/JNA (or subprocess IPC in the prototype).
 *
 * TODO: implement in Phase 2 (cpp-engine feature extraction).
 */
class FeatureExtractor {
public:
    FeatureExtractor();
    ~FeatureExtractor();

    // Disable copy; allow move.
    FeatureExtractor(const FeatureExtractor&) = delete;
    FeatureExtractor& operator=(const FeatureExtractor&) = delete;
    FeatureExtractor(FeatureExtractor&&) noexcept;
    FeatureExtractor& operator=(FeatureExtractor&&) noexcept;

    /**
     * Open a PCAP file for reading.
     * TODO: implement in Phase 2.
     */
    bool open(const std::string& pcap_path);

    /**
     * Read and aggregate the next batch of packets into flow records.
     * TODO: implement in Phase 2.
     */
    std::vector<std::uint8_t> extract_next_batch();

private:
    struct Impl;
    Impl* impl_;
};

} // namespace networkwm
