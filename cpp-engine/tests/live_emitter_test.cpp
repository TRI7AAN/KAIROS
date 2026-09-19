#include "feature_extractor.hpp"
#include "live_capture.hpp"
#include "live_emitter.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

std::uint16_t read_be16(const std::uint8_t* bytes) {
    return static_cast<std::uint16_t>((bytes[0] << 8U) | bytes[1]);
}

bool parse_live_packet(const std::uint8_t* ip, std::size_t size,
                       std::uint64_t timestamp_micros,
                       networkwm::LiveWindowPacket& out) {
    if (size < 20U || (ip[0] >> 4U) != 4U) {
        return false;
    }
    const std::size_t header = (ip[0] & 0x0FU) * 4U;
    if (header < 20U || size < header) {
        return false;
    }
    const std::uint16_t declared = read_be16(ip + 2U);
    if (declared < header) {
        return false;
    }
    const std::uint16_t frag_field = read_be16(ip + 6U);
    out.fragmented =
        ((frag_field & 0x2000U) != 0U) || ((frag_field & 0x1FFFU) != 0U);
    out.protocol = ip[9];
    out.ttl = ip[8];
    char src[16]{};
    char dst[16]{};
    std::snprintf(src, sizeof(src), "%u.%u.%u.%u", ip[12], ip[13], ip[14],
                  ip[15]);
    std::snprintf(dst, sizeof(dst), "%u.%u.%u.%u", ip[16], ip[17], ip[18],
                  ip[19]);
    out.source_ip = src;
    out.destination_ip = dst;
    out.timestamp_micros = timestamp_micros;
    out.capture_truncated = true;
    const std::size_t transport_size = declared - header;
    const std::uint8_t* transport = ip + header;
    if (out.protocol == 17U) {
        if (transport_size < 8U) {
            return false;
        }
        out.source_port = read_be16(transport);
        out.destination_port = read_be16(transport + 2U);
        const std::uint16_t udp_size = read_be16(transport + 4U);
        out.payload_size =
            udp_size >= 8U ? static_cast<std::uint32_t>(udp_size - 8U) : 0U;
    } else if (out.protocol == 6U) {
        if (transport_size < 20U) {
            return false;
        }
        out.is_tcp = true;
        out.source_port = read_be16(transport);
        out.destination_port = read_be16(transport + 2U);
        out.tcp_sequence =
            (static_cast<std::uint32_t>(transport[4]) << 24U) |
            (static_cast<std::uint32_t>(transport[5]) << 16U) |
            (static_cast<std::uint32_t>(transport[6]) << 8U) |
            transport[7];
        out.tcp_window = read_be16(transport + 14U);
        const std::size_t tcp_header = (transport[12] >> 4U) * 4U;
        out.sequence_span =
            transport_size >= tcp_header
                ? static_cast<std::uint32_t>(transport_size - tcp_header)
                : 0U;
        out.payload_size = out.sequence_span;
    } else if (out.protocol == 1U) {
        if (transport_size < 8U) {
            return false;
        }
        out.payload_size =
            static_cast<std::uint32_t>(transport_size - 8U);
    } else {
        return false;
    }
    return true;
}

struct PcapReader {
    std::ifstream stream;
    bool little_endian{true};
    bool nanosecond{true};
    std::uint64_t base_micros{};
    bool first{true};

    explicit PcapReader(const std::string& path) {
        stream.open(path, std::ios::binary);
        require(static_cast<bool>(stream), "cannot open capture for replay");
        char header[24]{};
        stream.read(header, 24);
        require(stream.gcount() == 24, "bad pcap header");
        const std::uint32_t magic =
            static_cast<std::uint32_t>(static_cast<unsigned char>(header[0])) |
            (static_cast<std::uint32_t>(
                 static_cast<unsigned char>(header[1]))
             << 8U) |
            (static_cast<std::uint32_t>(
                 static_cast<unsigned char>(header[2]))
             << 16U) |
            (static_cast<std::uint32_t>(
                 static_cast<unsigned char>(header[3]))
             << 24U);
        nanosecond = (magic == 0xA1B23C4DU);
    }

    bool next(networkwm::LiveWindowPacket& packet) {
        char record[16]{};
        while (true) {
            stream.read(record, 16);
            if (stream.gcount() == 0 && stream.eof()) {
                return false;
            }
            require(stream.gcount() == 16, "truncated record header");
            const auto u32 = [&](int off) {
                return static_cast<std::uint32_t>(
                           static_cast<unsigned char>(record[off])) |
                       (static_cast<std::uint32_t>(
                            static_cast<unsigned char>(record[off + 1]))
                        << 8U) |
                       (static_cast<std::uint32_t>(
                            static_cast<unsigned char>(record[off + 2]))
                        << 16U) |
                       (static_cast<std::uint32_t>(
                            static_cast<unsigned char>(record[off + 3]))
                        << 24U);
            };
            const std::uint32_t incl = u32(8);
            std::vector<std::uint8_t> bytes(incl);
            stream.read(reinterpret_cast<char*>(bytes.data()),
                        static_cast<std::streamsize>(incl));
            require(static_cast<std::size_t>(stream.gcount()) == incl,
                    "truncated packet");
            const std::uint64_t fraction = u32(4);
            const std::uint64_t micros = static_cast<std::uint64_t>(u32(0)) *
                                             1000000ULL +
                                         (nanosecond ? fraction / 1000ULL
                                                     : fraction);
            if (first) {
                base_micros = micros;
                first = false;
            }
            std::uint64_t replay_time =
                base_micros + (micros - base_micros);
            if (bytes.size() < 14U) {
                continue;
            }
            if (parse_live_packet(bytes.data() + 14U, bytes.size() - 14U,
                                  replay_time, packet)) {
                return true;
            }
        }
    }
};

void generate_local_traffic(std::atomic<bool>& keep_running,
                            std::uint16_t port) {
    const int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        return;
    }
    sockaddr_in destination{};
    destination.sin_family = AF_INET;
    destination.sin_port = htons(port);
    destination.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    const std::string payload(120, 'e');
    while (keep_running.load()) {
        ::sendto(fd, payload.data(), payload.size(), 0,
                 reinterpret_cast<sockaddr*>(&destination),
                 sizeof(destination));
        std::this_thread::sleep_for(std::chrono::milliseconds(150));
    }
    ::close(fd);
}

} // namespace

int main() {
    try {
        const auto path = std::filesystem::temp_directory_path() /
                          "kairos-live-emitter-test.pcap";
        std::filesystem::remove(path);

        networkwm::LiveCaptureSession session;
        networkwm::CaptureSessionConfig config;
        config.interface_name = "lo";
        config.bpf_filter = "udp port 29843";
        config.duration_seconds = 32U;
        config.packet_limit = 0U;
        config.output_path = path.string();
        require(session.start(config),
                "capture failed to start: " + session.last_error());

        std::atomic<bool> keep_running{true};
        std::thread generator(generate_local_traffic, std::ref(keep_running),
                              static_cast<std::uint16_t>(29843));
        const auto started = std::chrono::steady_clock::now();
        while (session.running() &&
               std::chrono::steady_clock::now() - started <
                   std::chrono::seconds(40)) {
            std::this_thread::sleep_for(std::chrono::milliseconds(200));
        }
        keep_running.store(false);
        generator.join();
        require(!session.running(), "capture did not self-stop");
        require(session.wait_for_exit(5U), "capture did not exit");

        networkwm::LiveFeatureEmitter emitter(10U);
        std::vector<networkwm::LiveFeatureWindow> emitted;
        std::mutex emitted_mutex;
        emitter.set_callback(
            [&](const networkwm::LiveFeatureWindow& window) {
                std::lock_guard<std::mutex> lock(emitted_mutex);
                emitted.push_back(window);
            });

        PcapReader reader(path.string());
        networkwm::LiveWindowPacket packet;
        std::uint64_t replayed = 0U;
        while (reader.next(packet)) {
            emitter.observe(packet);
            ++replayed;
        }
        {
            std::lock_guard<std::mutex> lock(emitted_mutex);
            networkwm::LiveFeatureWindow tail = emitter.flush();
            if (!tail.flows.empty()) {
                emitted.push_back(tail);
            }
        }
        std::cout << "replayed packets: " << replayed << "\n";
        std::cout << "windows emitted: " << emitted.size() << "\n";
        require(replayed > 0U, "expected replayed packets");
        require(emitted.size() >= 2U,
                "expected at least 2 windows from 30s+ capture, got " +
                    std::to_string(emitted.size()));
        std::uint64_t total_flow_packets = 0U;
        for (const auto& window : emitted) {
            require(!window.flows.empty(), "emitted window has no flows");
            require(window.window_end_epoch_micros >
                        window.window_start_epoch_micros,
                    "window has non-positive duration");
            require(window.window_end_epoch_micros -
                            window.window_start_epoch_micros ==
                        10000000ULL,
                    "window is not 10 seconds");
            bool nonzero = false;
            for (const auto& flow : window.flows) {
                total_flow_packets += flow.packet_count;
                if (flow.payload_size_mean > 0.0 ||
                    flow.ttl_mean > 0.0) {
                    nonzero = true;
                }
            }
            require(nonzero, "window has no plausible non-zero features");
            const std::string encoded =
                networkwm::live_window_to_json(window);
            require(encoded.find("\"ttlMean\"") != std::string::npos,
                    "window JSON missing existing-schema ttlMean");
            require(encoded.find("\"payloadSizeMean\"") != std::string::npos,
                    "window JSON missing existing-schema payloadSizeMean");
        }
        require(total_flow_packets == replayed,
                "flow packet accounting mismatch");
        std::cout << "total flow packets: " << total_flow_packets << "\n";
        std::filesystem::remove(path);
        std::cout << "live emitter tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "live emitter test failed: " << error.what() << '\n';
        return 1;
    }
}
