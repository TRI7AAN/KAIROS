#pragma once

#include <cstdint>
#include <functional>
#include <string>
#include <vector>

#include "feature_extractor.hpp"

namespace networkwm {

struct LiveWindowPacket {
    std::string source_ip;
    std::string destination_ip;
    std::uint16_t source_port{};
    std::uint16_t destination_port{};
    std::uint8_t protocol{};
    std::uint8_t ttl{};
    bool fragmented{};
    std::uint32_t payload_size{};
    bool capture_truncated{};
    bool is_tcp{};
    std::uint16_t tcp_window{};
    std::uint32_t tcp_sequence{};
    std::uint32_t sequence_span{};
    std::uint64_t timestamp_micros{};
};

struct LiveFeatureWindow {
    std::uint64_t window_index{};
    std::uint64_t window_start_epoch_micros{};
    std::uint64_t window_end_epoch_micros{};
    std::vector<FlowFeatures> flows;
    std::vector<PortScanFeatures> port_scans;
};

using LiveWindowCallback = std::function<void(const LiveFeatureWindow&)>;

/**
 * Phase 68: live feature-window emitter over the EXISTING packet/flow
 * feature schema.
 *
 * Packets are fed via observe() in capture-time order (the same fields the
 * static FeatureExtractor aggregates: TTL stats, window-size trend,
 * fragment flags, retransmission count, payload-size stats). Every
 * window_seconds (default 10s) of packet timestamps, the emitter aggregates
 * the buffered packets into FlowFeatures with the shared finish() math and
 * runs the shared PortScanDetector, then invokes the callback with a
 * LiveFeatureWindow. No new feature names are invented: downstream Java
 * code maps these records through the same edge-feature keys
 * (packet.ttl_mean, packet.payload_size_stddev, ...) used for static
 * PCAP input, so live windows validate against kairos.sequence.v1 /
 * kairos.graph.v1 unchanged.
 *
 * Window boundaries follow capture time: window N covers
 * [first_packet_time + N*window, first_packet_time + (N+1)*window).
 * Late packets for an already-emitted window are merged into the current
 * window rather than reopening history.
 */
class LiveFeatureEmitter {
public:
    explicit LiveFeatureEmitter(std::uint64_t window_seconds = 10U,
                                PortScanConfig scan_config = {});
    ~LiveFeatureEmitter();

    LiveFeatureEmitter(const LiveFeatureEmitter&) = delete;
    LiveFeatureEmitter& operator=(const LiveFeatureEmitter&) = delete;
    LiveFeatureEmitter(LiveFeatureEmitter&&) noexcept;
    LiveFeatureEmitter& operator=(LiveFeatureEmitter&&) noexcept;

    void set_callback(LiveWindowCallback callback);

    void observe(const LiveWindowPacket& packet);

    LiveFeatureWindow flush();

    std::uint64_t windows_emitted() const noexcept;
    std::uint64_t packets_observed() const noexcept;

private:
    struct Impl;
    Impl* impl_;
};

std::string live_window_to_json(const LiveFeatureWindow& window);

} // namespace networkwm
