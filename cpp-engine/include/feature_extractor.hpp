#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace networkwm {

struct FlowKey {
    std::string source_ip;
    std::string destination_ip;
    std::uint16_t source_port{};
    std::uint16_t destination_port{};
    std::uint8_t protocol{};

    bool operator<(const FlowKey& other) const noexcept;
};

struct FlowFeatures {
    FlowKey key;
    std::uint64_t packet_count{};
    std::uint64_t first_seen_epoch_micros{};
    std::uint64_t last_seen_epoch_micros{};
    double ttl_mean{};
    double ttl_variance{};
    double tcp_window_trend{};
    std::uint64_t fragment_count{};
    std::uint64_t retransmission_count{};
    std::uint64_t truncated_packet_count{};
    double payload_size_mean{};
    double payload_size_stddev{};
    double payload_size_skew{};
};

enum class PortScanPattern {
    none,
    sequential,
    randomized,
};

const char* to_string(PortScanPattern pattern) noexcept;

struct PortScanConfig {
    std::size_t minimum_unique_ports{20};
    double sequential_ratio_threshold{0.70};
};

struct PortScanFeatures {
    std::string source_ip;
    std::uint64_t observed_packets{};
    std::size_t unique_destination_ports{};
    double sequential_transition_ratio{};
    PortScanPattern pattern{PortScanPattern::none};
};

/** Callable per-window detector; observations must be supplied in time order. */
class PortScanDetector {
public:
    explicit PortScanDetector(PortScanConfig config = {});
    ~PortScanDetector();

    PortScanDetector(const PortScanDetector&) = delete;
    PortScanDetector& operator=(const PortScanDetector&) = delete;
    PortScanDetector(PortScanDetector&&) noexcept;
    PortScanDetector& operator=(PortScanDetector&&) noexcept;

    void observe(const FlowKey& flow);
    std::vector<PortScanFeatures> results(
        bool include_below_threshold = false) const;
    void reset();

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

struct ExtractionBatch {
    std::vector<FlowFeatures> flows;
    std::vector<PortScanFeatures> port_scans;
};

/**
 * Dependency-free classic-PCAP/PCAPNG reader and per-direction 5-tuple
 * aggregator. Aggregates are split on fixed 10-second boundaries so a
 * long-lived connection contributes evidence to every network-state window it
 * traverses instead of being assigned only to its first packet timestamp.
 *
 * Phase 4 supports Ethernet (including VLAN tags) and raw-IPv4 captures, IPv4,
 * and TCP/UDP/ICMP flows. For header-truncated captures, logical payload size is
 * recovered from IPv4 and transport length headers instead of snap length.
 * Malformed or unsupported packets are skipped safely.
 * Retransmissions are counted when an identical TCP sequence/payload range is
 * observed again in the same batch.
 */
class FeatureExtractor {
public:
    FeatureExtractor();
    ~FeatureExtractor();

    FeatureExtractor(const FeatureExtractor&) = delete;
    FeatureExtractor& operator=(const FeatureExtractor&) = delete;
    FeatureExtractor(FeatureExtractor&&) noexcept;
    FeatureExtractor& operator=(FeatureExtractor&&) noexcept;

    /** Open and validate a classic PCAP or PCAPNG file, resetting prior state. */
    bool open(const std::string& pcap_path);

    /**
     * Parse one packet window, returning flow features and detected port scans.
     */
    ExtractionBatch extract_next_batch_analysis(
        std::size_t max_packets = 4096,
        PortScanConfig scan_config = {});

    /** Compatibility helper returning only the flow portion of a batch. */
    std::vector<FlowFeatures> extract_next_batch_features(
        std::size_t max_packets = 4096);

    /**
     * Compatibility transport: UTF-8 JSON encoding of the next feature batch.
     */
    std::vector<std::uint8_t> extract_next_batch();

    bool eof() const noexcept;
    const std::string& last_error() const noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace networkwm
