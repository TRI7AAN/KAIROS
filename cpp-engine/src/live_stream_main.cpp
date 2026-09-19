#include "live_capture.hpp"
#include "live_emitter.hpp"

#include <arpa/inet.h>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

std::atomic<bool> stop_requested{false};

void request_stop(int) { stop_requested.store(true); }

std::uint16_t be16(const std::uint8_t* bytes) {
    return static_cast<std::uint16_t>((bytes[0] << 8U) | bytes[1]);
}

std::uint32_t be32(const std::uint8_t* bytes) {
    return (static_cast<std::uint32_t>(bytes[0]) << 24U) |
           (static_cast<std::uint32_t>(bytes[1]) << 16U) |
           (static_cast<std::uint32_t>(bytes[2]) << 8U) |
           static_cast<std::uint32_t>(bytes[3]);
}

bool parse_ipv4(const std::uint8_t* ip, std::size_t captured,
                std::uint64_t timestamp_micros,
                networkwm::LiveWindowPacket& out) {
    if (captured < 20U || (ip[0] >> 4U) != 4U) {
        return false;
    }
    const std::size_t ip_header = (ip[0] & 0x0FU) * 4U;
    if (ip_header < 20U || captured < ip_header) {
        return false;
    }
    const std::uint16_t declared = be16(ip + 2U);
    if (declared < ip_header) {
        return false;
    }
    char source[INET_ADDRSTRLEN]{};
    char destination[INET_ADDRSTRLEN]{};
    if (::inet_ntop(AF_INET, ip + 12U, source, sizeof(source)) == nullptr ||
        ::inet_ntop(AF_INET, ip + 16U, destination,
                    sizeof(destination)) == nullptr) {
        return false;
    }
    out.source_ip = source;
    out.destination_ip = destination;
    out.protocol = ip[9];
    out.ttl = ip[8];
    out.timestamp_micros = timestamp_micros;
    out.capture_truncated = captured < declared;
    const std::uint16_t fragment = be16(ip + 6U);
    out.fragmented =
        (fragment & 0x2000U) != 0U || (fragment & 0x1FFFU) != 0U;

    const std::uint8_t* transport = ip + ip_header;
    const std::size_t captured_transport = captured - ip_header;
    const std::size_t declared_transport = declared - ip_header;
    if (out.protocol == 17U) {
        if (captured_transport < 8U || declared_transport < 8U) {
            return false;
        }
        out.source_port = be16(transport);
        out.destination_port = be16(transport + 2U);
        const std::uint16_t udp_length = be16(transport + 4U);
        out.payload_size =
            udp_length >= 8U ? static_cast<std::uint32_t>(udp_length - 8U) : 0U;
        return true;
    }
    if (out.protocol == 6U) {
        if (captured_transport < 20U || declared_transport < 20U) {
            return false;
        }
        const std::size_t tcp_header = (transport[12] >> 4U) * 4U;
        if (tcp_header < 20U || captured_transport < tcp_header) {
            return false;
        }
        out.is_tcp = true;
        out.source_port = be16(transport);
        out.destination_port = be16(transport + 2U);
        out.tcp_sequence = be32(transport + 4U);
        out.tcp_window = be16(transport + 14U);
        out.sequence_span = declared_transport >= tcp_header
                                ? static_cast<std::uint32_t>(
                                      declared_transport - tcp_header)
                                : 0U;
        out.payload_size = out.sequence_span;
        return true;
    }
    if (out.protocol == 1U) {
        if (captured_transport < 8U || declared_transport < 8U) {
            return false;
        }
        out.payload_size =
            static_cast<std::uint32_t>(declared_transport - 8U);
        return true;
    }
    return false;
}

class GrowingPcapReader {
public:
    explicit GrowingPcapReader(const std::filesystem::path& path)
        : stream_(path, std::ios::binary) {
        if (!stream_) {
            throw std::runtime_error("cannot open growing capture");
        }
        std::uint8_t header[24]{};
        stream_.read(reinterpret_cast<char*>(header), sizeof(header));
        if (stream_.gcount() != static_cast<std::streamsize>(sizeof(header))) {
            throw std::runtime_error("capture header is incomplete");
        }
        const std::uint8_t* magic = header;
        if (magic[0] == 0xd4 && magic[1] == 0xc3 &&
            magic[2] == 0xb2 && magic[3] == 0xa1) {
            little_endian_ = true;
            nanosecond_ = false;
        } else if (magic[0] == 0x4d && magic[1] == 0x3c &&
                   magic[2] == 0xb2 && magic[3] == 0xa1) {
            little_endian_ = true;
            nanosecond_ = true;
        } else if (magic[0] == 0xa1 && magic[1] == 0xb2 &&
                   magic[2] == 0xc3 && magic[3] == 0xd4) {
            little_endian_ = false;
            nanosecond_ = false;
        } else if (magic[0] == 0xa1 && magic[1] == 0xb2 &&
                   magic[2] == 0x3c && magic[3] == 0x4d) {
            little_endian_ = false;
            nanosecond_ = true;
        } else {
            throw std::runtime_error("live helper requires classic PCAP");
        }
        link_type_ = u32(header + 20U);
    }

    bool next(networkwm::LiveWindowPacket& packet) {
        const std::streampos record_start = stream_.tellg();
        std::uint8_t header[16]{};
        stream_.read(reinterpret_cast<char*>(header), sizeof(header));
        if (stream_.gcount() != static_cast<std::streamsize>(sizeof(header))) {
            retry(record_start);
            return false;
        }
        const std::uint32_t included = u32(header + 8U);
        if (included > 16U * 1024U * 1024U) {
            throw std::runtime_error("capture record exceeds safety bound");
        }
        std::vector<std::uint8_t> frame(included);
        stream_.read(reinterpret_cast<char*>(frame.data()),
                     static_cast<std::streamsize>(included));
        if (stream_.gcount() != static_cast<std::streamsize>(included)) {
            retry(record_start);
            return false;
        }
        const std::uint64_t fraction = u32(header + 4U);
        const std::uint64_t timestamp =
            static_cast<std::uint64_t>(u32(header)) * 1000000ULL +
            (nanosecond_ ? fraction / 1000ULL : fraction);
        std::size_t offset = 0U;
        if (link_type_ == 1U) {
            if (frame.size() < 14U) {
                return false;
            }
            std::uint16_t ether_type = be16(frame.data() + 12U);
            offset = 14U;
            if ((ether_type == 0x8100U || ether_type == 0x88a8U) &&
                frame.size() >= 18U) {
                ether_type = be16(frame.data() + 16U);
                offset = 18U;
            }
            if (ether_type != 0x0800U) {
                return false;
            }
        } else if (link_type_ == 101U) {
            offset = 0U;
        } else if (link_type_ == 113U) {
            if (frame.size() < 16U || be16(frame.data() + 14U) != 0x0800U) {
                return false;
            }
            offset = 16U;
        } else if (link_type_ == 276U) {
            if (frame.size() < 20U || be16(frame.data()) != 0x0800U) {
                return false;
            }
            offset = 20U;
        } else {
            return false;
        }
        return parse_ipv4(frame.data() + offset, frame.size() - offset,
                          timestamp, packet);
    }

private:
    std::ifstream stream_;
    bool little_endian_{true};
    bool nanosecond_{false};
    std::uint32_t link_type_{};

    std::uint32_t u32(const std::uint8_t* value) const {
        if (little_endian_) {
            return static_cast<std::uint32_t>(value[0]) |
                   (static_cast<std::uint32_t>(value[1]) << 8U) |
                   (static_cast<std::uint32_t>(value[2]) << 16U) |
                   (static_cast<std::uint32_t>(value[3]) << 24U);
        }
        return be32(value);
    }

    void retry(std::streampos position) {
        stream_.clear();
        stream_.seekg(position);
    }
};

struct Arguments {
    std::string interface_name;
    std::string filter;
    std::string output;
    std::uint64_t duration{};
    std::uint64_t packets{};
    std::uint32_t snap_length{256U};
    std::uint64_t window_seconds{10U};
};

Arguments parse_arguments(int argc, char** argv) {
    Arguments args;
    for (int index = 1; index < argc; ++index) {
        const std::string key = argv[index];
        if (index + 1 >= argc) {
            throw std::invalid_argument("missing value for " + key);
        }
        const std::string value = argv[++index];
        if (key == "--interface") args.interface_name = value;
        else if (key == "--filter") args.filter = value;
        else if (key == "--output") args.output = value;
        else if (key == "--duration") args.duration = std::stoull(value);
        else if (key == "--packets") args.packets = std::stoull(value);
        else if (key == "--snap-length") args.snap_length = std::stoul(value);
        else if (key == "--window-seconds") args.window_seconds = std::stoull(value);
        else throw std::invalid_argument("unknown argument: " + key);
    }
    if (args.interface_name.empty() || args.output.empty()) {
        throw std::invalid_argument("--interface and --output are required");
    }
    if (args.duration == 0U && args.packets == 0U) {
        throw std::invalid_argument("unbounded capture refused");
    }
    return args;
}

} // namespace

int main(int argc, char** argv) {
    try {
        const Arguments args = parse_arguments(argc, argv);
        std::signal(SIGINT, request_stop);
        std::signal(SIGTERM, request_stop);

        networkwm::LiveCaptureSession capture;
        networkwm::CaptureSessionConfig config;
        config.interface_name = args.interface_name;
        config.bpf_filter = args.filter;
        config.duration_seconds = args.duration;
        config.packet_limit = args.packets;
        config.snap_length = args.snap_length;
        config.output_path = args.output;
        if (!capture.start(config)) {
            std::cerr << capture.last_error() << '\n';
            return 2;
        }

        networkwm::LiveFeatureEmitter emitter(args.window_seconds);
        emitter.set_callback([](const networkwm::LiveFeatureWindow& window) {
            std::cout << networkwm::live_window_to_json(window) << '\n'
                      << std::flush;
        });

        std::unique_ptr<GrowingPcapReader> reader;
        while (capture.running() && !stop_requested.load()) {
            if (!reader && std::filesystem::exists(args.output) &&
                std::filesystem::file_size(args.output) >= 24U) {
                reader = std::make_unique<GrowingPcapReader>(args.output);
            }
            if (reader) {
                networkwm::LiveWindowPacket packet;
                while (reader->next(packet)) {
                    emitter.observe(packet);
                }
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
        if (stop_requested.load() && capture.running()) {
            capture.request_stop();
        }
        capture.wait_for_exit(10U);
        if (reader) {
            networkwm::LiveWindowPacket packet;
            while (reader->next(packet)) {
                emitter.observe(packet);
            }
        }
        if (emitter.packets_observed() > 0U) {
            const auto final_window = emitter.flush();
            if (!final_window.flows.empty()) {
                std::cout << networkwm::live_window_to_json(final_window)
                          << '\n' << std::flush;
            }
        }
        const auto counters = capture.counters();
        std::cerr << "Packets captured: " << counters.packets_captured << '\n'
                  << "Packets received/dropped on interface: "
                  << counters.packets_received << '/' << counters.packets_dropped
                  << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "kairos_live_stream: " << error.what() << '\n';
        return 2;
    }
}
