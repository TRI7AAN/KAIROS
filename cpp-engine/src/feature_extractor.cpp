#include "feature_extractor.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <map>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace networkwm {
namespace {

constexpr std::uint32_t kEthernetLinkType = 1;
constexpr std::uint32_t kRawIpv4LinkType = 101;
constexpr std::uint32_t kMaxCapturedPacketBytes = 64U * 1024U * 1024U;
constexpr std::uint64_t kAggregationWindowMicros = 10'000'000U;

std::uint16_t read_be16(const std::uint8_t* bytes) {
    return static_cast<std::uint16_t>((bytes[0] << 8U) | bytes[1]);
}

std::uint32_t read_be32(const std::uint8_t* bytes) {
    return (static_cast<std::uint32_t>(bytes[0]) << 24U) |
           (static_cast<std::uint32_t>(bytes[1]) << 16U) |
           (static_cast<std::uint32_t>(bytes[2]) << 8U) |
           static_cast<std::uint32_t>(bytes[3]);
}

std::uint16_t read_u16(const std::uint8_t* bytes, bool little_endian) {
    if (little_endian) {
        return static_cast<std::uint16_t>(bytes[0]) |
               static_cast<std::uint16_t>(bytes[1] << 8U);
    }
    return read_be16(bytes);
}

std::uint32_t read_u32(const std::uint8_t* bytes, bool little_endian) {
    if (little_endian) {
        return static_cast<std::uint32_t>(bytes[0]) |
               (static_cast<std::uint32_t>(bytes[1]) << 8U) |
               (static_cast<std::uint32_t>(bytes[2]) << 16U) |
               (static_cast<std::uint32_t>(bytes[3]) << 24U);
    }
    return read_be32(bytes);
}

std::string ipv4_string(const std::uint8_t* bytes) {
    std::ostringstream out;
    out << static_cast<unsigned>(bytes[0]) << '.'
        << static_cast<unsigned>(bytes[1]) << '.'
        << static_cast<unsigned>(bytes[2]) << '.'
        << static_cast<unsigned>(bytes[3]);
    return out.str();
}

struct FragmentKey {
    std::string source_ip;
    std::string destination_ip;
    std::uint8_t protocol{};
    std::uint16_t identification{};

    bool operator<(const FragmentKey& other) const noexcept {
        return std::tie(source_ip, destination_ip, protocol, identification) <
               std::tie(other.source_ip, other.destination_ip, other.protocol,
                        other.identification);
    }
};

struct WindowedFlowKey {
    FlowKey flow;
    std::uint64_t window_start_epoch_micros{};

    bool operator<(const WindowedFlowKey& other) const noexcept {
        if (flow < other.flow) {
            return true;
        }
        if (other.flow < flow) {
            return false;
        }
        return window_start_epoch_micros < other.window_start_epoch_micros;
    }
};

WindowedFlowKey windowed_key(
    FlowKey flow,
    std::uint64_t timestamp_micros) {
    return {
        std::move(flow),
        timestamp_micros / kAggregationWindowMicros
            * kAggregationWindowMicros,
    };
}

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

    void add(std::uint8_t ttl,
             bool fragmented,
             std::uint32_t payload_size,
             bool capture_truncated,
             bool is_tcp,
             std::uint16_t tcp_window,
             std::uint32_t tcp_sequence,
             std::uint32_t sequence_span,
             std::uint64_t timestamp_micros) {
        ++packet_count;
        if (first_seen_epoch_micros == 0U ||
            timestamp_micros < first_seen_epoch_micros) {
            first_seen_epoch_micros = timestamp_micros;
        }
        last_seen_epoch_micros = std::max(last_seen_epoch_micros, timestamp_micros);

        const double ttl_value = ttl;
        ttl_sum += ttl_value;
        ttl_square_sum += ttl_value * ttl_value;
        fragment_count += fragmented ? 1U : 0U;
        truncated_packet_count += capture_truncated ? 1U : 0U;

        const double payload_value = payload_size;
        payload_sum += payload_value;
        payload_square_sum += payload_value * payload_value;
        payload_cube_sum += payload_value * payload_value * payload_value;

        if (!is_tcp) {
            return;
        }

        const double index = window_count;
        const double window = tcp_window;
        window_count += 1.0;
        window_index_sum += index;
        window_value_sum += window;
        window_index_square_sum += index * index;
        window_index_value_sum += index * window;

        if (sequence_span > 0U &&
            !tcp_segments.emplace(tcp_sequence, sequence_span).second) {
            ++retransmission_count;
        }
    }
};

FlowFeatures finish(const FlowKey& key, const RunningAggregate& aggregate) {
    FlowFeatures result;
    result.key = key;
    result.packet_count = aggregate.packet_count;
    result.first_seen_epoch_micros = aggregate.first_seen_epoch_micros;
    result.last_seen_epoch_micros = aggregate.last_seen_epoch_micros;
    result.fragment_count = aggregate.fragment_count;
    result.retransmission_count = aggregate.retransmission_count;
    result.truncated_packet_count = aggregate.truncated_packet_count;

    if (aggregate.packet_count == 0U) {
        return result;
    }

    const double count = static_cast<double>(aggregate.packet_count);
    result.ttl_mean = aggregate.ttl_sum / count;
    result.ttl_variance = std::max(
        0.0, aggregate.ttl_square_sum / count - result.ttl_mean * result.ttl_mean);

    result.payload_size_mean = aggregate.payload_sum / count;
    const double payload_variance = std::max(
        0.0,
        aggregate.payload_square_sum / count -
            result.payload_size_mean * result.payload_size_mean);
    result.payload_size_stddev = std::sqrt(payload_variance);
    if (result.payload_size_stddev > 0.0) {
        const double third_central_moment =
            aggregate.payload_cube_sum / count -
            3.0 * result.payload_size_mean * aggregate.payload_square_sum / count +
            2.0 * result.payload_size_mean * result.payload_size_mean *
                result.payload_size_mean;
        result.payload_size_skew = third_central_moment /
            (result.payload_size_stddev * result.payload_size_stddev *
             result.payload_size_stddev);
    }

    const double denominator =
        aggregate.window_count * aggregate.window_index_square_sum -
        aggregate.window_index_sum * aggregate.window_index_sum;
    if (aggregate.window_count > 1.0 && denominator != 0.0) {
        result.tcp_window_trend =
            (aggregate.window_count * aggregate.window_index_value_sum -
             aggregate.window_index_sum * aggregate.window_value_sum) /
            denominator;
    }
    return result;
}

} // namespace

bool FlowKey::operator<(const FlowKey& other) const noexcept {
    return std::tie(source_ip, destination_ip, source_port, destination_port, protocol) <
           std::tie(other.source_ip, other.destination_ip, other.source_port,
                    other.destination_port, other.protocol);
}

const char* to_string(PortScanPattern pattern) noexcept {
    switch (pattern) {
    case PortScanPattern::sequential:
        return "sequential";
    case PortScanPattern::randomized:
        return "randomized";
    case PortScanPattern::none:
    default:
        return "none";
    }
}

struct PortScanDetector::Impl {
    struct SourceObservation {
        std::uint64_t observed_packets{};
        std::set<std::uint16_t> unique_ports;
        std::vector<std::uint16_t> first_seen_ports;
    };

    explicit Impl(PortScanConfig requested_config) : config(requested_config) {
        if (config.minimum_unique_ports < 2U) {
            throw std::invalid_argument(
                "minimum_unique_ports must be at least 2");
        }
        if (!std::isfinite(config.sequential_ratio_threshold) ||
            config.sequential_ratio_threshold < 0.0 ||
            config.sequential_ratio_threshold > 1.0) {
            throw std::invalid_argument(
                "sequential_ratio_threshold must be between 0 and 1");
        }
    }

    PortScanConfig config;
    std::map<std::string, SourceObservation> sources;
};

PortScanDetector::PortScanDetector(PortScanConfig config)
    : impl_(std::make_unique<Impl>(config)) {}
PortScanDetector::~PortScanDetector() = default;
PortScanDetector::PortScanDetector(PortScanDetector&&) noexcept = default;
PortScanDetector& PortScanDetector::operator=(PortScanDetector&&) noexcept = default;

void PortScanDetector::observe(const FlowKey& flow) {
    if ((flow.protocol != 6U && flow.protocol != 17U) ||
        flow.destination_port == 0U || flow.source_ip.empty()) {
        return;
    }
    auto& source = impl_->sources[flow.source_ip];
    ++source.observed_packets;
    if (source.unique_ports.insert(flow.destination_port).second) {
        source.first_seen_ports.push_back(flow.destination_port);
    }
}

std::vector<PortScanFeatures> PortScanDetector::results(
    bool include_below_threshold) const {
    std::vector<PortScanFeatures> detected;
    for (const auto& entry : impl_->sources) {
        const auto& source = entry.second;
        PortScanFeatures result;
        result.source_ip = entry.first;
        result.observed_packets = source.observed_packets;
        result.unique_destination_ports = source.unique_ports.size();

        if (source.first_seen_ports.size() > 1U) {
            std::size_t sequential_transitions = 0U;
            for (std::size_t index = 1U;
                 index < source.first_seen_ports.size(); ++index) {
                const int previous = source.first_seen_ports[index - 1U];
                const int current = source.first_seen_ports[index];
                sequential_transitions +=
                    std::abs(current - previous) == 1 ? 1U : 0U;
            }
            result.sequential_transition_ratio =
                static_cast<double>(sequential_transitions) /
                static_cast<double>(source.first_seen_ports.size() - 1U);
        }

        if (result.unique_destination_ports >=
            impl_->config.minimum_unique_ports) {
            result.pattern = result.sequential_transition_ratio >=
                    impl_->config.sequential_ratio_threshold
                ? PortScanPattern::sequential
                : PortScanPattern::randomized;
        }
        if (include_below_threshold ||
            result.pattern != PortScanPattern::none) {
            detected.push_back(std::move(result));
        }
    }
    return detected;
}

void PortScanDetector::reset() {
    impl_->sources.clear();
}

struct FeatureExtractor::Impl {
    std::ifstream stream;
    bool nanosecond_timestamps{};
    std::vector<double> interface_timestamp_units_per_second;
    bool little_endian{true};
    std::uint32_t link_type{};
    bool pcapng{};
    bool reached_eof{true};
    std::string error;
    std::vector<std::uint32_t> interface_link_types;
    std::vector<std::uint32_t> interface_snap_lengths;
    std::map<FragmentKey, WindowedFlowKey> fragment_flows;

    bool read_next_pcapng_packet(std::vector<std::uint8_t>& packet,
                                 std::uint32_t& original_size,
                                 std::uint32_t& packet_link_type,
                                 std::uint64_t& timestamp_micros) {
        while (true) {
            std::array<std::uint8_t, 8> block_header{};
            stream.read(reinterpret_cast<char*>(block_header.data()),
                        block_header.size());
            const std::streamsize header_bytes = stream.gcount();
            if (header_bytes == 0 && stream.eof()) {
                reached_eof = true;
                stream.clear();
                return false;
            }
            if (header_bytes != static_cast<std::streamsize>(block_header.size())) {
                error = "Truncated PCAPNG block header";
                reached_eof = true;
                return false;
            }

            const bool section_header =
                block_header[0] == 0x0AU && block_header[1] == 0x0DU &&
                block_header[2] == 0x0DU && block_header[3] == 0x0AU;
            if (section_header) {
                std::array<std::uint8_t, 4> byte_order_magic{};
                if (!stream.read(reinterpret_cast<char*>(byte_order_magic.data()),
                                 byte_order_magic.size())) {
                    error = "Truncated PCAPNG section header";
                    reached_eof = true;
                    return false;
                }
                if (byte_order_magic ==
                    std::array<std::uint8_t, 4>{0x4D, 0x3C, 0x2B, 0x1A}) {
                    little_endian = true;
                } else if (byte_order_magic ==
                           std::array<std::uint8_t, 4>{0x1A, 0x2B, 0x3C, 0x4D}) {
                    little_endian = false;
                } else {
                    error = "Invalid PCAPNG byte-order magic";
                    reached_eof = true;
                    return false;
                }
                const std::uint32_t block_size =
                    read_u32(block_header.data() + 4U, little_endian);
                if (block_size < 28U || block_size > kMaxCapturedPacketBytes) {
                    error = "Invalid PCAPNG section block size";
                    reached_eof = true;
                    return false;
                }
                std::vector<std::uint8_t> remainder(block_size - 12U);
                if (!stream.read(reinterpret_cast<char*>(remainder.data()),
                                 static_cast<std::streamsize>(remainder.size())) ||
                    read_u32(remainder.data() + remainder.size() - 4U,
                             little_endian) != block_size) {
                    error = "Corrupt PCAPNG section block";
                    reached_eof = true;
                    return false;
                }
                interface_link_types.clear();
                interface_snap_lengths.clear();
                interface_timestamp_units_per_second.clear();
                continue;
            }

            const std::uint32_t block_type =
                read_u32(block_header.data(), little_endian);
            const std::uint32_t block_size =
                read_u32(block_header.data() + 4U, little_endian);
            if (block_size < 12U || block_size > kMaxCapturedPacketBytes) {
                error = "Invalid PCAPNG block size";
                reached_eof = true;
                return false;
            }
            std::vector<std::uint8_t> body(block_size - 8U);
            if (!stream.read(reinterpret_cast<char*>(body.data()),
                             static_cast<std::streamsize>(body.size())) ||
                read_u32(body.data() + body.size() - 4U, little_endian) !=
                    block_size) {
                error = "Corrupt or truncated PCAPNG block";
                reached_eof = true;
                return false;
            }

            if (block_type == 1U) {
                if (body.size() < 12U) {
                    error = "Truncated PCAPNG interface block";
                    reached_eof = true;
                    return false;
                }
                interface_link_types.push_back(read_u16(body.data(), little_endian));
                interface_snap_lengths.push_back(
                    read_u32(body.data() + 4U, little_endian));
                double timestamp_units = 1.0e6;
                std::size_t option_offset = 8U;
                const std::size_t options_end = body.size() - 4U;
                while (option_offset + 4U <= options_end) {
                    const std::uint16_t option_code =
                        read_u16(body.data() + option_offset, little_endian);
                    const std::uint16_t option_size =
                        read_u16(body.data() + option_offset + 2U, little_endian);
                    option_offset += 4U;
                    if (option_code == 0U) {
                        break;
                    }
                    if (option_offset + option_size > options_end) {
                        error = "Invalid PCAPNG interface option";
                        reached_eof = true;
                        return false;
                    }
                    if (option_code == 9U && option_size >= 1U) {
                        const std::uint8_t resolution = body[option_offset];
                        const int exponent = resolution & 0x7FU;
                        timestamp_units = (resolution & 0x80U) != 0U
                            ? std::pow(2.0, exponent)
                            : std::pow(10.0, exponent);
                    }
                    option_offset += (option_size + 3U) & ~std::size_t{3U};
                }
                interface_timestamp_units_per_second.push_back(timestamp_units);
                continue;
            }

            if (block_type == 6U) {
                if (body.size() < 24U) {
                    error = "Truncated PCAPNG enhanced packet block";
                    reached_eof = true;
                    return false;
                }
                const std::uint32_t interface_id =
                    read_u32(body.data(), little_endian);
                const std::uint32_t captured_size =
                    read_u32(body.data() + 12U, little_endian);
                original_size = read_u32(body.data() + 16U, little_endian);
                if (interface_id >= interface_link_types.size() ||
                    interface_id >= interface_timestamp_units_per_second.size() ||
                    captured_size > body.size() - 24U) {
                    error = "Invalid PCAPNG enhanced packet metadata";
                    reached_eof = true;
                    return false;
                }
                const std::uint64_t raw_timestamp =
                    (static_cast<std::uint64_t>(
                         read_u32(body.data() + 4U, little_endian)) << 32U) |
                    read_u32(body.data() + 8U, little_endian);
                const long double timestamp_value =
                    static_cast<long double>(raw_timestamp) * 1.0e6L /
                    interface_timestamp_units_per_second[interface_id];
                timestamp_micros = timestamp_value >=
                        static_cast<long double>(
                            std::numeric_limits<std::uint64_t>::max())
                    ? std::numeric_limits<std::uint64_t>::max()
                    : static_cast<std::uint64_t>(timestamp_value);
                packet_link_type = interface_link_types[interface_id];
                packet.assign(body.begin() + 20,
                              body.begin() + 20 + captured_size);
                return true;
            }

            if (block_type == 3U) {
                if (body.size() < 8U || interface_link_types.empty()) {
                    error = "Invalid PCAPNG simple packet block";
                    reached_eof = true;
                    return false;
                }
                original_size = read_u32(body.data(), little_endian);
                const std::uint32_t captured_size = std::min(
                    original_size, interface_snap_lengths.front());
                if (captured_size > body.size() - 8U) {
                    error = "Invalid PCAPNG simple packet metadata";
                    reached_eof = true;
                    return false;
                }
                packet_link_type = interface_link_types.front();
                timestamp_micros = 0U;
                packet.assign(body.begin() + 4,
                              body.begin() + 4 + captured_size);
                return true;
            }
        }
    }

    bool parse_packet(const std::vector<std::uint8_t>& packet,
                      std::uint32_t packet_link_type,
                      bool capture_truncated,
                      std::uint64_t timestamp_micros,
                      std::map<WindowedFlowKey, RunningAggregate>& flows,
                      PortScanDetector& scan_detector) {
        std::size_t ip_offset = 0;
        if (packet_link_type == kEthernetLinkType) {
            if (packet.size() < 14U) {
                return false;
            }
            std::size_t ether_type_offset = 12U;
            std::uint16_t ether_type = read_be16(packet.data() + ether_type_offset);
            ip_offset = 14U;
            for (int tag = 0; tag < 2 &&
                 (ether_type == 0x8100U || ether_type == 0x88A8U); ++tag) {
                if (packet.size() < ip_offset + 4U) {
                    return false;
                }
                ether_type = read_be16(packet.data() + ip_offset + 2U);
                ip_offset += 4U;
            }
            if (ether_type != 0x0800U) {
                return false;
            }
        } else if (packet_link_type != kRawIpv4LinkType) {
            return false;
        }

        if (packet.size() < ip_offset + 20U) {
            return false;
        }
        const std::uint8_t* ip = packet.data() + ip_offset;
        if ((ip[0] >> 4U) != 4U) {
            return false;
        }
        const std::size_t ip_header_size = (ip[0] & 0x0FU) * 4U;
        if (ip_header_size < 20U || packet.size() < ip_offset + ip_header_size) {
            return false;
        }

        const std::uint16_t declared_ip_size = read_be16(ip + 2U);
        if (declared_ip_size < ip_header_size) {
            return false;
        }
        const std::size_t captured_ip_size =
            std::min<std::size_t>(declared_ip_size, packet.size() - ip_offset);
        const std::size_t logical_transport_size = declared_ip_size - ip_header_size;
        const std::uint16_t fragment_field = read_be16(ip + 6U);
        const bool more_fragments = (fragment_field & 0x2000U) != 0U;
        const std::uint16_t fragment_offset = fragment_field & 0x1FFFU;
        const bool fragmented = more_fragments || fragment_offset != 0U;
        const std::uint8_t protocol = ip[9];

        FlowKey key;
        key.source_ip = ipv4_string(ip + 12U);
        key.destination_ip = ipv4_string(ip + 16U);
        key.protocol = protocol;
        const FragmentKey fragment_key{
            key.source_ip, key.destination_ip, protocol, read_be16(ip + 4U)};

        const std::uint8_t* transport = ip + ip_header_size;
        const std::size_t captured_transport_size =
            captured_ip_size - ip_header_size;
        std::uint32_t payload_size =
            static_cast<std::uint32_t>(logical_transport_size);
        bool is_tcp = false;
        std::uint16_t tcp_window = 0U;
        std::uint32_t tcp_sequence = 0U;
        std::uint32_t sequence_span = 0U;

        if (fragment_offset != 0U) {
            const auto existing_flow = fragment_flows.find(fragment_key);
            if (existing_flow == fragment_flows.end()) {
                return false;
            }
            const WindowedFlowKey aggregate_key = existing_flow->second;
            flows[aggregate_key].add(
                           ip[8], true, payload_size, capture_truncated,
                           false, 0U, 0U, 0U, timestamp_micros);
            if (!more_fragments) {
                fragment_flows.erase(existing_flow);
            }
            return true;
        }

        if (protocol == 6U) {
            if (captured_transport_size < 20U) {
                return false;
            }
            is_tcp = true;
            key.source_port = read_be16(transport);
            key.destination_port = read_be16(transport + 2U);
            tcp_sequence = read_be32(transport + 4U);
            const std::size_t tcp_header_size = (transport[12] >> 4U) * 4U;
            if (tcp_header_size < 20U ||
                captured_transport_size < tcp_header_size ||
                logical_transport_size < tcp_header_size) {
                return false;
            }
            tcp_window = read_be16(transport + 14U);
            payload_size = static_cast<std::uint32_t>(
                logical_transport_size - tcp_header_size);
            const bool syn = (transport[13] & 0x02U) != 0U;
            const bool fin = (transport[13] & 0x01U) != 0U;
            sequence_span = payload_size + (syn ? 1U : 0U) + (fin ? 1U : 0U);
        } else if (protocol == 17U) {
            if (captured_transport_size < 8U) {
                return false;
            }
            key.source_port = read_be16(transport);
            key.destination_port = read_be16(transport + 2U);
            const std::uint16_t udp_size = read_be16(transport + 4U);
            if (udp_size < 8U) {
                return false;
            }
            if (more_fragments) {
                payload_size = static_cast<std::uint32_t>(
                    logical_transport_size - 8U);
            } else {
                if (logical_transport_size < udp_size) {
                    return false;
                }
                payload_size = static_cast<std::uint32_t>(udp_size - 8U);
            }
        } else if (protocol == 1U) {
            constexpr std::size_t icmp_header_size = 8U;
            if (captured_transport_size < icmp_header_size ||
                logical_transport_size < icmp_header_size) {
                return false;
            }
            payload_size = static_cast<std::uint32_t>(
                logical_transport_size - icmp_header_size);
        } else {
            return false;
        }

        if (more_fragments) {
            fragment_flows[fragment_key] = windowed_key(key, timestamp_micros);
        }
        flows[windowed_key(key, timestamp_micros)].add(
                       ip[8], fragmented, payload_size, capture_truncated,
                       is_tcp, tcp_window, tcp_sequence, sequence_span,
                       timestamp_micros);
        scan_detector.observe(key);
        return true;
    }
};

FeatureExtractor::FeatureExtractor() : impl_(std::make_unique<Impl>()) {}
FeatureExtractor::~FeatureExtractor() = default;
FeatureExtractor::FeatureExtractor(FeatureExtractor&&) noexcept = default;
FeatureExtractor& FeatureExtractor::operator=(FeatureExtractor&&) noexcept = default;

bool FeatureExtractor::open(const std::string& pcap_path) {
    impl_->stream.close();
    impl_->stream.clear();
    impl_->error.clear();
    impl_->reached_eof = true;
    impl_->link_type = 0U;
    impl_->pcapng = false;
    impl_->nanosecond_timestamps = false;
    impl_->interface_timestamp_units_per_second.clear();
    impl_->interface_link_types.clear();
    impl_->interface_snap_lengths.clear();
    impl_->fragment_flows.clear();
    impl_->stream.open(pcap_path, std::ios::binary);
    if (!impl_->stream) {
        impl_->error = "Unable to open PCAP file: " + pcap_path;
        return false;
    }

    std::array<std::uint8_t, 12> probe{};
    if (!impl_->stream.read(reinterpret_cast<char*>(probe.data()), probe.size())) {
        impl_->error = "Capture header is missing or truncated";
        return false;
    }
    const std::array<std::uint8_t, 4> probe_magic{
        probe[0], probe[1], probe[2], probe[3]};
    if (probe_magic ==
        std::array<std::uint8_t, 4>{0x0A, 0x0D, 0x0D, 0x0A}) {
        const std::array<std::uint8_t, 4> byte_order_magic{
            probe[8], probe[9], probe[10], probe[11]};
        if (byte_order_magic !=
                std::array<std::uint8_t, 4>{0x4D, 0x3C, 0x2B, 0x1A} &&
            byte_order_magic !=
                std::array<std::uint8_t, 4>{0x1A, 0x2B, 0x3C, 0x4D}) {
            impl_->error = "Invalid PCAPNG byte-order magic";
            return false;
        }
        impl_->stream.clear();
        impl_->stream.seekg(0);
        impl_->pcapng = true;
        impl_->reached_eof = false;
        return true;
    }

    impl_->stream.clear();
    impl_->stream.seekg(0);
    std::array<std::uint8_t, 24> header{};
    if (!impl_->stream.read(reinterpret_cast<char*>(header.data()), header.size())) {
        impl_->error = "PCAP global header is missing or truncated";
        return false;
    }

    const std::array<std::uint8_t, 4> magic{header[0], header[1], header[2], header[3]};
    if (magic == std::array<std::uint8_t, 4>{0xD4, 0xC3, 0xB2, 0xA1} ||
        magic == std::array<std::uint8_t, 4>{0x4D, 0x3C, 0xB2, 0xA1}) {
        impl_->little_endian = true;
    } else if (magic == std::array<std::uint8_t, 4>{0xA1, 0xB2, 0xC3, 0xD4} ||
               magic == std::array<std::uint8_t, 4>{0xA1, 0xB2, 0x3C, 0x4D}) {
        impl_->little_endian = false;
    } else {
        impl_->error = "Unsupported capture format: expected classic PCAP";
        return false;
    }
    impl_->nanosecond_timestamps =
        magic == std::array<std::uint8_t, 4>{0x4D, 0x3C, 0xB2, 0xA1} ||
        magic == std::array<std::uint8_t, 4>{0xA1, 0xB2, 0x3C, 0x4D};


    impl_->link_type = read_u32(header.data() + 20U, impl_->little_endian);
    if (impl_->link_type != kEthernetLinkType &&
        impl_->link_type != kRawIpv4LinkType) {
        impl_->error = "Unsupported PCAP link type: " +
                       std::to_string(impl_->link_type);
        return false;
    }

    impl_->reached_eof = false;
    return true;
}

ExtractionBatch FeatureExtractor::extract_next_batch_analysis(
    std::size_t max_packets,
    PortScanConfig scan_config) {
    ExtractionBatch batch;
    if (!impl_->stream.is_open() || impl_->reached_eof || max_packets == 0U) {
        return batch;
    }

    std::map<WindowedFlowKey, RunningAggregate> flows;
    PortScanDetector scan_detector(scan_config);
    std::size_t records_read = 0U;
    while (records_read < max_packets) {
        std::vector<std::uint8_t> packet;
        std::uint32_t captured_size = 0U;
        std::uint32_t original_size = 0U;
        std::uint32_t packet_link_type = impl_->link_type;

        std::uint64_t timestamp_micros = 0U;
        if (impl_->pcapng) {
            if (!impl_->read_next_pcapng_packet(
                    packet, original_size, packet_link_type, timestamp_micros)) {
                break;
            }
            captured_size = static_cast<std::uint32_t>(packet.size());
        } else {
            std::array<std::uint8_t, 16> record_header{};
            impl_->stream.read(reinterpret_cast<char*>(record_header.data()),
                               record_header.size());
            const std::streamsize header_bytes = impl_->stream.gcount();
            if (header_bytes == 0 && impl_->stream.eof()) {
                impl_->reached_eof = true;
                impl_->stream.clear();
                break;
            }
            if (header_bytes !=
                static_cast<std::streamsize>(record_header.size())) {
                impl_->error = "Truncated PCAP packet header";
                impl_->reached_eof = true;
                break;
            }
            captured_size =
                read_u32(record_header.data() + 8U, impl_->little_endian);
            const std::uint64_t seconds =
                read_u32(record_header.data(), impl_->little_endian);
            const std::uint64_t fraction =
                read_u32(record_header.data() + 4U, impl_->little_endian);
            timestamp_micros = seconds * 1'000'000U +
                (impl_->nanosecond_timestamps ? fraction / 1'000U : fraction);

            original_size =
                read_u32(record_header.data() + 12U, impl_->little_endian);
            if (captured_size > kMaxCapturedPacketBytes) {
                impl_->error = "PCAP packet exceeds the 64 MiB safety limit";
                impl_->reached_eof = true;
                break;
            }
            packet.resize(captured_size);
            if (!impl_->stream.read(
                    reinterpret_cast<char*>(packet.data()),
                    static_cast<std::streamsize>(packet.size()))) {
                impl_->error = "Truncated PCAP packet payload";
                impl_->reached_eof = true;
                break;
            }
        }
        ++records_read;
        impl_->parse_packet(packet, packet_link_type,
                            captured_size < original_size, timestamp_micros, flows,
                            scan_detector);
    }

    batch.flows.reserve(flows.size());
    for (const auto& entry : flows) {
        batch.flows.push_back(finish(entry.first.flow, entry.second));
    }
    batch.port_scans = scan_detector.results();
    return batch;
}

std::vector<FlowFeatures> FeatureExtractor::extract_next_batch_features(
    std::size_t max_packets) {
    return extract_next_batch_analysis(max_packets).flows;
}

std::vector<std::uint8_t> FeatureExtractor::extract_next_batch() {
    const auto features = extract_next_batch_features();
    std::ostringstream json;
    json << std::setprecision(12) << '[';
    for (std::size_t index = 0; index < features.size(); ++index) {
        if (index != 0U) {
            json << ',';
        }
        const auto& value = features[index];
        json << "{\"source_ip\":\"" << value.key.source_ip
             << "\",\"destination_ip\":\"" << value.key.destination_ip
             << "\",\"source_port\":" << value.key.source_port
             << ",\"destination_port\":" << value.key.destination_port
             << ",\"protocol\":" << static_cast<unsigned>(value.key.protocol)
             << ",\"packet_count\":" << value.packet_count
             << ",\"first_seen_epoch_micros\":" << value.first_seen_epoch_micros
             << ",\"last_seen_epoch_micros\":" << value.last_seen_epoch_micros
             << ",\"ttl_mean\":" << value.ttl_mean
             << ",\"ttl_variance\":" << value.ttl_variance
             << ",\"tcp_window_trend\":" << value.tcp_window_trend
             << ",\"fragment_count\":" << value.fragment_count
             << ",\"retransmission_count\":" << value.retransmission_count
             << ",\"truncated_packet_count\":" << value.truncated_packet_count
             << ",\"payload_size_mean\":" << value.payload_size_mean
             << ",\"payload_size_stddev\":" << value.payload_size_stddev
             << ",\"payload_size_skew\":" << value.payload_size_skew << '}';
    }
    json << ']';
    const std::string encoded = json.str();
    return {encoded.begin(), encoded.end()};
}

bool FeatureExtractor::eof() const noexcept {
    return impl_->reached_eof;
}

const std::string& FeatureExtractor::last_error() const noexcept {
    return impl_->error;
}

} // namespace networkwm
