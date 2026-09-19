#include "feature_extractor.hpp"
#include "live_capture.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void generate_local_traffic(std::atomic<bool>& keep_running,
                            std::uint16_t port) {
    int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        return;
    }
    sockaddr_in destination{};
    destination.sin_family = AF_INET;
    destination.sin_port = htons(port);
    destination.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    std::string payload(120, 'k');
    while (keep_running.load()) {
        ::sendto(fd, payload.data(), payload.size(), 0,
                 reinterpret_cast<sockaddr*>(&destination),
                 sizeof(destination));
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    ::close(fd);
}

void enumeration_test() {
    std::string error;
    const auto interfaces =
        networkwm::LiveCaptureSession::list_interfaces(error);
    require(!interfaces.empty(), "expected at least one interface: " + error);
    bool loopback_found = false;
    for (const auto& info : interfaces) {
        require(!info.name.empty(), "interface name must not be empty");
        if (info.name == "lo") {
            loopback_found = true;
            require(info.loopback, "lo must be flagged loopback");
        }
    }
    require(loopback_found, "expected loopback interface 'lo' enumerated");
    std::cout << "interfaces enumerated: " << interfaces.size() << " (";
    for (std::size_t i = 0; i < interfaces.size(); ++i) {
        if (i != 0U) {
            std::cout << ",";
        }
        std::cout << interfaces[i].name;
    }
    std::cout << ")\n";
}

void unbounded_refused_test() {
    networkwm::LiveCaptureSession session;
    networkwm::CaptureSessionConfig config;
    config.interface_name = "lo";
    config.output_path = "/tmp/kairos-test-unbounded.pcap";
    require(!session.start(config),
            "unbounded capture must be refused");
    std::cout << "unbounded refusal ok: " << session.last_error() << "\n";
}

void unknown_interface_test() {
    networkwm::LiveCaptureSession session;
    networkwm::CaptureSessionConfig config;
    config.interface_name = "kairos-nonexistent0";
    config.duration_seconds = 2U;
    config.output_path = "/tmp/kairos-test-unknown.pcap";
    require(!session.start(config),
            "unknown interface must be refused");
    std::cout << "unknown-interface refusal ok: " << session.last_error()
              << "\n";
}

void bounded_capture_test() {
    const auto path = std::filesystem::temp_directory_path() /
                      "kairos-live-bounded-test.pcap";
    std::filesystem::remove(path);

    networkwm::LiveCaptureSession session;
    networkwm::CaptureSessionConfig config;
    config.interface_name = "lo";
    config.bpf_filter = "udp port 29841";
    config.duration_seconds = 5U;
    config.packet_limit = 0U;
    config.output_path = path.string();
    require(session.start(config),
            "bounded capture failed to start: " + session.last_error());

    std::atomic<bool> keep_running{true};
    std::thread generator(generate_local_traffic, std::ref(keep_running),
                          static_cast<std::uint16_t>(29841));
    const auto started = std::chrono::steady_clock::now();
    while (session.running() &&
           std::chrono::steady_clock::now() - started <
               std::chrono::seconds(12)) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    keep_running.store(false);
    generator.join();
    require(!session.running(), "bounded capture did not self-stop");
    require(session.wait_for_exit(5U), "capture did not exit cleanly");

    const auto counters = session.counters();
    std::cout << "bounded capture: received=" << counters.packets_received
              << " dropped=" << counters.packets_dropped << "\n";

    networkwm::FeatureExtractor extractor;
    require(extractor.open(path.string()), extractor.last_error());
    const auto batch = extractor.extract_next_batch_analysis(4096U);
    std::size_t loopback_packets = 0U;
    for (const auto& flow : batch.flows) {
        if (flow.key.source_ip == "127.0.0.1" &&
            flow.key.destination_ip == "127.0.0.1") {
            loopback_packets +=
                static_cast<std::size_t>(flow.packet_count);
        }
    }
    require(loopback_packets > 0U,
            "expected real loopback packets in bounded capture");
    std::cout << "bounded capture: loopback packets parsed=" << loopback_packets
              << "\n";
    std::filesystem::remove(path);
}

void packet_limit_capture_test() {
    const auto path = std::filesystem::temp_directory_path() /
                      "kairos-live-packetlimit-test.pcap";
    std::filesystem::remove(path);

    networkwm::LiveCaptureSession session;
    networkwm::CaptureSessionConfig config;
    config.interface_name = "lo";
    config.bpf_filter = "udp port 29842";
    config.duration_seconds = 60U;
    config.packet_limit = 4U;
    config.output_path = path.string();
    require(session.start(config),
            "packet-limit capture failed to start: " + session.last_error());

    std::atomic<bool> keep_running{true};
    std::thread generator(generate_local_traffic, std::ref(keep_running),
                          static_cast<std::uint16_t>(29842));
    const auto started = std::chrono::steady_clock::now();
    while (session.running() &&
           std::chrono::steady_clock::now() - started <
               std::chrono::seconds(20)) {
        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
    keep_running.store(false);
    generator.join();
    require(!session.running(),
            "packet-limit capture did not self-stop at the packet bound");
    require(session.wait_for_exit(5U), "capture did not exit cleanly");
    const auto counters = session.counters();
    std::cout << "packet-limit capture: received=" << counters.packets_received
              << " dropped=" << counters.packets_dropped << "\n";
    require(std::filesystem::exists(path), "capture file missing");
    require(std::filesystem::file_size(path) > 24U, "capture file empty");
    std::filesystem::remove(path);
}

} // namespace

int main() {
    try {
        enumeration_test();
        unbounded_refused_test();
        unknown_interface_test();
        bounded_capture_test();
        packet_limit_capture_test();
        std::cout << "live capture tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "live capture test failed: " << error.what() << '\n';
        return 1;
    }
}
