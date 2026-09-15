#include "feature_extractor.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <tuple>
#include <utility>

namespace networkwm {
namespace {

constexpr std::uint32_t kEthernetLinkType = 1;
constexpr std::uint32_t kRawIpv4LinkType = 101;
constexpr std::uint32_t kMaxCapturedPacketBytes = 64U * 1024U * 1024U;

std::uint16_t read_be16(const std::uint8_t* bytes) {
    return static_cast<std::uint16_t>((bytes[0] << 8U) | bytes[1]);
}

std::uint32_t read_be32(const std::uint8_t* bytes) {
    return (static_cast<std::uint32_t>(bytes[0]) << 24U) |
           (static_cast<std::uint32_t>(bytes[1]) << 16U) |
           (static_cast<std::uint32_t>(bytes[2]) << 8U) |
           static_cast<std::uint32_t>(bytes[3]);
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

struct RunningAggregate {
    std::uint64_t packet_count{};
    double ttl_sum{};
    double ttl_square_sum{};
    std::uint64_t fragment_count{};
    std::uint64_t retransmission_count{};
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
             bool is_tcp,
             std::uint16_t tcp_window,
             std::uint32_t tcp_sequence,
             std::uint32_t sequence_span) {
        ++packet_count;
        const double ttl_value = ttl;
        ttl_sum += ttl_value;
        ttl_square_sum += ttl_value * ttl_value;
        fragment_count += fragmented ? 1U : 0U;

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
    result.fragment_count = aggregate.fragment_count;
    result.retransmission_count = aggregate.retransmission_count;

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

struct FeatureExtractor::Impl {
    std::ifstream stream;
    bool little_endian{true};
    std::uint32_t link_type{};
    bool reached_eof{true};
    std::string error;
    std::map<FragmentKey, FlowKey> fragment_flows;

    bool parse_packet(const std::vector<std::uint8_t>& packet,
                      std::map<FlowKey, RunningAggregate>& flows) {
        std::size_t ip_offset = 0;
        if (link_type == kEthernetLinkType) {
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
        } else if (link_type != kRawIpv4LinkType) {
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
        const std::size_t transport_size = captured_ip_size - ip_header_size;
        std::uint32_t payload_size = static_cast<std::uint32_t>(transport_size);
        bool is_tcp = false;
        std::uint16_t tcp_window = 0U;
        std::uint32_t tcp_sequence = 0U;
        std::uint32_t sequence_span = 0U;

        if (fragment_offset != 0U) {
            const auto existing_flow = fragment_flows.find(fragment_key);
            if (existing_flow == fragment_flows.end()) {
                return false;
            }
            key = existing_flow->second;
            flows[key].add(ip[8], true, payload_size, false, 0U, 0U, 0U);
            if (!more_fragments) {
                fragment_flows.erase(existing_flow);
            }
            return true;
        }

        if (protocol == 6U) {
            if (transport_size < 20U) {
                return false;
            }
            is_tcp = true;
            key.source_port = read_be16(transport);
            key.destination_port = read_be16(transport + 2U);
            tcp_sequence = read_be32(transport + 4U);
            const std::size_t tcp_header_size = (transport[12] >> 4U) * 4U;
            if (tcp_header_size < 20U || transport_size < tcp_header_size) {
                return false;
            }
            tcp_window = read_be16(transport + 14U);
            payload_size = static_cast<std::uint32_t>(transport_size - tcp_header_size);
            const bool syn = (transport[13] & 0x02U) != 0U;
            const bool fin = (transport[13] & 0x01U) != 0U;
            sequence_span = payload_size + (syn ? 1U : 0U) + (fin ? 1U : 0U);
        } else if (protocol == 17U) {
            if (transport_size < 8U) {
                return false;
            }
            key.source_port = read_be16(transport);
            key.destination_port = read_be16(transport + 2U);
            payload_size = static_cast<std::uint32_t>(transport_size - 8U);
        } else if (protocol != 6U && protocol != 17U) {
            return false;
        }

        if (more_fragments) {
            fragment_flows[fragment_key] = key;
        }
        flows[key].add(ip[8], fragmented, payload_size, is_tcp, tcp_window,
                       tcp_sequence, sequence_span);
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
    impl_->fragment_flows.clear();
    impl_->stream.open(pcap_path, std::ios::binary);
    if (!impl_->stream) {
        impl_->error = "Unable to open PCAP file: " + pcap_path;
        return false;
    }

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

std::vector<FlowFeatures> FeatureExtractor::extract_next_batch_features(
    std::size_t max_packets) {
    std::vector<FlowFeatures> results;
    if (!impl_->stream.is_open() || impl_->reached_eof || max_packets == 0U) {
        return results;
    }

    std::map<FlowKey, RunningAggregate> flows;
    std::size_t records_read = 0U;
    while (records_read < max_packets) {
        std::array<std::uint8_t, 16> record_header{};
        impl_->stream.read(reinterpret_cast<char*>(record_header.data()),
                           record_header.size());
        const std::streamsize header_bytes = impl_->stream.gcount();
        if (header_bytes == 0 && impl_->stream.eof()) {
            impl_->reached_eof = true;
            impl_->stream.clear();
            break;
        }
        if (header_bytes != static_cast<std::streamsize>(record_header.size())) {
            impl_->error = "Truncated PCAP packet header";
            impl_->reached_eof = true;
            break;
        }

        const std::uint32_t captured_size =
            read_u32(record_header.data() + 8U, impl_->little_endian);
        if (captured_size > kMaxCapturedPacketBytes) {
            impl_->error = "PCAP packet exceeds the 64 MiB safety limit";
            impl_->reached_eof = true;
            break;
        }

        std::vector<std::uint8_t> packet(captured_size);
        if (!impl_->stream.read(reinterpret_cast<char*>(packet.data()),
                                static_cast<std::streamsize>(packet.size()))) {
            impl_->error = "Truncated PCAP packet payload";
            impl_->reached_eof = true;
            break;
        }
        ++records_read;
        impl_->parse_packet(packet, flows);
    }

    results.reserve(flows.size());
    for (const auto& entry : flows) {
        results.push_back(finish(entry.first, entry.second));
    }
    return results;
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
             << ",\"ttl_mean\":" << value.ttl_mean
             << ",\"ttl_variance\":" << value.ttl_variance
             << ",\"tcp_window_trend\":" << value.tcp_window_trend
             << ",\"fragment_count\":" << value.fragment_count
             << ",\"retransmission_count\":" << value.retransmission_count
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
