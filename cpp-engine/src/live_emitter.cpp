#include "live_emitter.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>

namespace networkwm {
namespace {

struct RunningAggregate {
    std::uint64_t packet_count{};
    std::uint64_t first_seen_epoch_micros{};
    std::uint64_t last_seen_epoch_micros{};
    double ttl_sum{};
    double ttl_square_sum{};
    std::uint64_t fragment_count{};
    std::uint64_t retransmission_count{};
    std::uint64_t truncated_packet_count{};
    double payload_sum{};
    double payload_square_sum{};
    double payload_cube_sum{};
    double window_count{};
    double window_index_sum{};
    double window_value_sum{};
    double window_index_square_sum{};
    double window_index_value_sum{};
    std::set<std::pair<std::uint32_t, std::uint32_t>> tcp_segments;

    void add(const LiveWindowPacket& packet, std::uint64_t index) {
        ++packet_count;
        if (first_seen_epoch_micros == 0U ||
            packet.timestamp_micros < first_seen_epoch_micros) {
            first_seen_epoch_micros = packet.timestamp_micros;
        }
        last_seen_epoch_micros =
            std::max(last_seen_epoch_micros, packet.timestamp_micros);
        const double ttl = packet.ttl;
        ttl_sum += ttl;
        ttl_square_sum += ttl * ttl;
        fragment_count += packet.fragmented ? 1U : 0U;
        truncated_packet_count += packet.capture_truncated ? 1U : 0U;
        const double payload = packet.payload_size;
        payload_sum += payload;
        payload_square_sum += payload * payload;
        payload_cube_sum += payload * payload * payload;
        if (!packet.is_tcp) {
            return;
        }
        const double window_value = packet.tcp_window;
        window_count += 1.0;
        window_index_sum += static_cast<double>(index);
        window_value_sum += window_value;
        window_index_square_sum +=
            static_cast<double>(index) * static_cast<double>(index);
        window_index_value_sum += static_cast<double>(index) * window_value;
        if (packet.sequence_span > 0U &&
            !tcp_segments
                 .emplace(packet.tcp_sequence, packet.sequence_span)
                 .second) {
            ++retransmission_count;
        }
    }
};

FlowFeatures finish_live(const FlowKey& key, const RunningAggregate& agg) {
    FlowFeatures result;
    result.key = key;
    result.packet_count = agg.packet_count;
    result.first_seen_epoch_micros = agg.first_seen_epoch_micros;
    result.last_seen_epoch_micros = agg.last_seen_epoch_micros;
    result.fragment_count = agg.fragment_count;
    result.retransmission_count = agg.retransmission_count;
    result.truncated_packet_count = agg.truncated_packet_count;
    if (agg.packet_count == 0U) {
        return result;
    }
    const double count = static_cast<double>(agg.packet_count);
    result.ttl_mean = agg.ttl_sum / count;
    result.ttl_variance = std::max(
        0.0, agg.ttl_square_sum / count - result.ttl_mean * result.ttl_mean);
    result.payload_size_mean = agg.payload_sum / count;
    const double variance = std::max(
        0.0, agg.payload_square_sum / count -
                 result.payload_size_mean * result.payload_size_mean);
    result.payload_size_stddev = std::sqrt(variance);
    if (result.payload_size_stddev > 0.0) {
        const double third =
            agg.payload_cube_sum / count -
            3.0 * result.payload_size_mean * agg.payload_square_sum / count +
            2.0 * result.payload_size_mean * result.payload_size_mean *
                result.payload_size_mean;
        result.payload_size_skew =
            third / (result.payload_size_stddev * result.payload_size_stddev *
                     result.payload_size_stddev);
    }
    const double denominator = agg.window_count * agg.window_index_square_sum -
                               agg.window_index_sum * agg.window_index_sum;
    if (agg.window_count > 1.0 && denominator != 0.0) {
        result.tcp_window_trend =
            (agg.window_count * agg.window_index_value_sum -
             agg.window_index_sum * agg.window_value_sum) /
            denominator;
    }
    return result;
}

std::string json_escape_live(const std::string& value) {
    std::ostringstream escaped;
    for (const unsigned char c : value) {
        switch (c) {
        case '"':
            escaped << "\\\"";
            break;
        case '\\':
            escaped << "\\\\";
            break;
        default:
            if (c < 0x20U) {
                escaped << "\\u" << std::hex << std::setw(4)
                        << std::setfill('0') << static_cast<unsigned>(c)
                        << std::dec;
            } else {
                escaped << c;
            }
        }
    }
    return escaped.str();
}

} // namespace

struct LiveFeatureEmitter::Impl {
    std::uint64_t window_micros;
    PortScanConfig scan_config;
    LiveWindowCallback callback;
    std::map<FlowKey, RunningAggregate> flows;
    std::map<FlowKey, std::uint64_t> tcp_indices;
    PortScanDetector scans;
    bool anchored{false};
    std::uint64_t anchor_micros{};
    std::uint64_t current_window{};
    std::uint64_t next_window_end{};
    std::uint64_t emitted{};
    std::uint64_t observed{};

    explicit Impl(std::uint64_t window_seconds, PortScanConfig config)
        : window_micros(window_seconds * 1000000ULL),
          scan_config(config),
          scans(config) {}

    LiveFeatureWindow build(std::uint64_t index, std::uint64_t start,
                            std::uint64_t end) {
        LiveFeatureWindow window;
        window.window_index = index;
        window.window_start_epoch_micros = start;
        window.window_end_epoch_micros = end;
        window.flows.reserve(flows.size());
        for (const auto& entry : flows) {
            window.flows.push_back(finish_live(entry.first, entry.second));
        }
        window.port_scans = scans.results();
        return window;
    }

    void emit_current() {
        LiveFeatureWindow window =
            build(current_window, anchor_micros + current_window * window_micros,
                  anchor_micros + (current_window + 1U) * window_micros);
        ++emitted;
        flows.clear();
        tcp_indices.clear();
        scans.reset();
        ++current_window;
        next_window_end = anchor_micros + (current_window + 1U) * window_micros;
        if (callback) {
            callback(window);
        }
    }
};

LiveFeatureEmitter::LiveFeatureEmitter(std::uint64_t window_seconds,
                                       PortScanConfig scan_config)
    : impl_(new Impl(window_seconds, scan_config)) {
    if (window_seconds == 0U) {
        delete impl_;
        throw std::invalid_argument("window_seconds must be positive");
    }
}
LiveFeatureEmitter::~LiveFeatureEmitter() { delete impl_; }
LiveFeatureEmitter::LiveFeatureEmitter(LiveFeatureEmitter&& other) noexcept
    : impl_(other.impl_) {
    other.impl_ = nullptr;
}
LiveFeatureEmitter& LiveFeatureEmitter::operator=(
    LiveFeatureEmitter&& other) noexcept {
    if (this != &other) {
        delete impl_;
        impl_ = other.impl_;
        other.impl_ = nullptr;
    }
    return *this;
}

void LiveFeatureEmitter::set_callback(LiveWindowCallback callback) {
    impl_->callback = std::move(callback);
}

void LiveFeatureEmitter::observe(const LiveWindowPacket& packet) {
    if (packet.source_ip.empty() || packet.destination_ip.empty()) {
        return;
    }
    if (!impl_->anchored) {
        impl_->anchored = true;
        impl_->anchor_micros = packet.timestamp_micros;
        impl_->current_window = 0U;
        impl_->next_window_end =
            impl_->anchor_micros + impl_->window_micros;
    }
    while (packet.timestamp_micros >= impl_->next_window_end) {
        impl_->emit_current();
    }
    FlowKey key{packet.source_ip, packet.destination_ip, packet.source_port,
                packet.destination_port, packet.protocol};
    auto& aggregate = impl_->flows[key];
    std::uint64_t& tcp_index = impl_->tcp_indices[key];
    aggregate.add(packet, tcp_index);
    if (packet.is_tcp) {
        ++tcp_index;
    }
    FlowKey scan_key = key;
    impl_->scans.observe(scan_key);
    ++impl_->observed;
}

LiveFeatureWindow LiveFeatureEmitter::flush() {
    LiveFeatureWindow window = impl_->build(
        impl_->current_window,
        impl_->anchored ? impl_->anchor_micros +
                              impl_->current_window * impl_->window_micros
                        : 0U,
        impl_->anchored ? impl_->anchor_micros +
                              (impl_->current_window + 1U) * impl_->window_micros
                        : impl_->window_micros);
    if (!impl_->flows.empty()) {
        ++impl_->emitted;
        impl_->flows.clear();
        impl_->tcp_indices.clear();
        impl_->scans.reset();
        ++impl_->current_window;
        if (impl_->anchored) {
            impl_->next_window_end =
                impl_->anchor_micros +
                (impl_->current_window + 1U) * impl_->window_micros;
        }
    }
    return window;
}

std::uint64_t LiveFeatureEmitter::windows_emitted() const noexcept {
    return impl_->emitted;
}
std::uint64_t LiveFeatureEmitter::packets_observed() const noexcept {
    return impl_->observed;
}

std::string live_window_to_json(const LiveFeatureWindow& window) {
    std::ostringstream json;
    json << std::setprecision(12) << "{\"windowIndex\":" << window.window_index
         << ",\"windowStartEpochMicros\":" << window.window_start_epoch_micros
         << ",\"windowEndEpochMicros\":" << window.window_end_epoch_micros
         << ",\"flows\":[";
    for (std::size_t i = 0; i < window.flows.size(); ++i) {
        if (i != 0U) {
            json << ',';
        }
        const auto& f = window.flows[i];
        json << "{\"sourceIp\":\"" << json_escape_live(f.key.source_ip)
             << "\",\"destinationIp\":\"" << json_escape_live(f.key.destination_ip)
             << "\",\"sourcePort\":" << f.key.source_port
             << ",\"destinationPort\":" << f.key.destination_port
             << ",\"protocol\":" << static_cast<unsigned>(f.key.protocol)
             << ",\"packetCount\":" << f.packet_count
             << ",\"firstSeenEpochMicros\":" << f.first_seen_epoch_micros
             << ",\"lastSeenEpochMicros\":" << f.last_seen_epoch_micros
             << ",\"ttlMean\":" << f.ttl_mean << ",\"ttlVariance\":"
             << f.ttl_variance << ",\"tcpWindowTrend\":" << f.tcp_window_trend
             << ",\"fragmentCount\":" << f.fragment_count
             << ",\"retransmissionCount\":" << f.retransmission_count
             << ",\"truncatedPacketCount\":" << f.truncated_packet_count
             << ",\"payloadSizeMean\":" << f.payload_size_mean
             << ",\"payloadSizeStddev\":" << f.payload_size_stddev
             << ",\"payloadSizeSkew\":" << f.payload_size_skew << '}';
    }
    json << "],\"portScans\":[";
    for (std::size_t i = 0; i < window.port_scans.size(); ++i) {
        if (i != 0U) {
            json << ',';
        }
        const auto& s = window.port_scans[i];
        json << "{\"sourceIp\":\"" << json_escape_live(s.source_ip)
             << "\",\"observedPackets\":" << s.observed_packets
             << ",\"uniqueDestinationPorts\":" << s.unique_destination_ports
             << ",\"sequentialTransitionRatio\":" << s.sequential_transition_ratio
             << ",\"pattern\":\"" << to_string(s.pattern) << "\"}";
    }
    json << "]}";
    return json.str();
}

} // namespace networkwm
