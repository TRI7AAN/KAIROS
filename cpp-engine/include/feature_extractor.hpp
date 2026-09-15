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
    double ttl_mean{};
    double ttl_variance{};
    double tcp_window_trend{};
    std::uint64_t fragment_count{};
    std::uint64_t retransmission_count{};
    double payload_size_mean{};
    double payload_size_stddev{};
    double payload_size_skew{};
};

/**
 * Dependency-free classic-PCAP reader and per-direction 5-tuple aggregator.
 *
 * Phase 4 supports Ethernet (including VLAN tags) and raw-IPv4 captures, IPv4,
 * and TCP/UDP flows. Malformed or unsupported packets are skipped safely.
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

    /** Open and validate a classic PCAP file, resetting prior state. */
    bool open(const std::string& pcap_path);

    /**
     * Parse up to max_packets capture records and aggregate them by 5-tuple.
     * An empty result means EOF or an error; inspect eof() and last_error().
     */
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
