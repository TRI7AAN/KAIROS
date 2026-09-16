#include "feature_extractor.hpp"

#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void require(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void append_le16(std::vector<std::uint8_t>& bytes, std::uint16_t value) {
    bytes.push_back(static_cast<std::uint8_t>(value));
    bytes.push_back(static_cast<std::uint8_t>(value >> 8U));
}

void append_le32(std::vector<std::uint8_t>& bytes, std::uint32_t value) {
    for (unsigned shift = 0U; shift < 32U; shift += 8U) {
        bytes.push_back(static_cast<std::uint8_t>(value >> shift));
    }
}

void append_be16(std::vector<std::uint8_t>& bytes, std::uint16_t value) {
    bytes.push_back(static_cast<std::uint8_t>(value >> 8U));
    bytes.push_back(static_cast<std::uint8_t>(value));
}

std::vector<std::uint8_t> udp_packet(std::uint8_t ttl,
                                     std::uint16_t destination_port,
                                     std::size_t payload_size) {
    const std::uint16_t udp_size = static_cast<std::uint16_t>(8U + payload_size);
    const std::uint16_t ip_size = static_cast<std::uint16_t>(20U + udp_size);
    std::vector<std::uint8_t> packet;
    packet.reserve(ip_size);
    packet.push_back(0x45U);
    packet.push_back(0U);
    append_be16(packet, ip_size);
    append_be16(packet, 1U);
    append_be16(packet, 0U);
    packet.push_back(ttl);
    packet.push_back(17U);
    append_be16(packet, 0U);
    packet.insert(packet.end(), {10U, 0U, 0U, 1U, 10U, 0U, 0U, 2U});
    append_be16(packet, 1234U);
    append_be16(packet, destination_port);
    append_be16(packet, udp_size);
    append_be16(packet, 0U);
    packet.insert(packet.end(), payload_size, 0xABU);
    return packet;
}

void append_record(std::vector<std::uint8_t>& capture,
                   const std::vector<std::uint8_t>& packet,
                   std::uint32_t timestamp) {
    append_le32(capture, timestamp);
    append_le32(capture, 0U);
    append_le32(capture, static_cast<std::uint32_t>(packet.size()));
    append_le32(capture, static_cast<std::uint32_t>(packet.size()));
    capture.insert(capture.end(), packet.begin(), packet.end());
}

std::filesystem::path write_known_capture() {
    std::vector<std::uint8_t> capture;
    append_le32(capture, 0xA1B2C3D4U);
    append_le16(capture, 2U);
    append_le16(capture, 4U);
    append_le32(capture, 0U);
    append_le32(capture, 0U);
    append_le32(capture, 65535U);
    append_le32(capture, 101U);
    append_record(capture, udp_packet(64U, 80U, 4U), 1U);
    append_record(capture, udp_packet(62U, 80U, 8U), 2U);

    const auto path = std::filesystem::temp_directory_path() /
        "kairos-known-feature-sample.pcap";
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    output.write(reinterpret_cast<const char*>(capture.data()),
                 static_cast<std::streamsize>(capture.size()));
    require(output.good(), "failed to write known PCAP fixture");
    return path;
}

void extractor_test() {
    const auto path = write_known_capture();
    networkwm::FeatureExtractor extractor;
    require(extractor.open(path.string()), extractor.last_error());
    const auto batch = extractor.extract_next_batch_analysis(32U, {2U, 0.7});
    require(batch.flows.size() == 1U, "expected one aggregated flow");
    const auto& flow = batch.flows.front();
    require(flow.key.source_ip == "10.0.0.1", "unexpected source IP");
    require(flow.key.destination_ip == "10.0.0.2", "unexpected destination IP");
    require(flow.key.destination_port == 80U, "unexpected destination port");
    require(flow.packet_count == 2U, "unexpected packet count");
    require(std::abs(flow.ttl_mean - 63.0) < 1e-12, "unexpected TTL mean");
    require(std::abs(flow.ttl_variance - 1.0) < 1e-12,
            "unexpected TTL variance");
    require(std::abs(flow.payload_size_mean - 6.0) < 1e-12,
            "unexpected payload mean");
    require(std::abs(flow.payload_size_stddev - 2.0) < 1e-12,
            "unexpected payload standard deviation");
    require(batch.port_scans.empty(), "duplicate port must not trigger a scan");
    std::filesystem::remove(path);
}

void detector_test() {
    networkwm::PortScanDetector detector({4U, 0.75});
    for (std::uint16_t port = 100U; port < 104U; ++port) {
        detector.observe({"192.0.2.10", "198.51.100.1", 40000U, port, 6U});
    }
    const auto results = detector.results();
    require(results.size() == 1U, "expected one scan result");
    require(results.front().pattern == networkwm::PortScanPattern::sequential,
            "expected sequential scan");
    require(std::abs(results.front().sequential_transition_ratio - 1.0) < 1e-12,
            "unexpected sequential ratio");
    detector.reset();
    require(detector.results(true).empty(), "reset did not clear detector state");
}

} // namespace

int main() {
    try {
        extractor_test();
        detector_test();
        std::cout << "feature extractor tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "feature extractor test failed: " << error.what() << '\n';
        return 1;
    }
}
