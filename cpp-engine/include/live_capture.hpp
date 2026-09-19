#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace networkwm {

struct NetworkInterfaceInfo {
    std::string name;
    std::string description;
    bool loopback{};
    std::vector<std::string> addresses;
};

struct CaptureBounds {
    std::uint32_t duration_seconds{};
    std::uint64_t packet_limit{};
};

struct CaptureSessionConfig {
    std::string interface_name;
    std::string bpf_filter;
    std::uint32_t duration_seconds{};
    std::uint64_t packet_limit{};
    std::string output_path;
    std::uint32_t snap_length{256};
};

enum class CaptureStopReason {
    none,
    requested,
    duration_limit,
    packet_limit,
    error,
    process_exit,
};

const char* to_string(CaptureStopReason reason) noexcept;

struct CaptureCounters {
    std::uint64_t packets_captured{};
    std::uint64_t packets_received{};
    std::uint64_t packets_dropped{};
};

struct CaptureSessionResult {
    bool started{};
    std::string error;
    CaptureCounters counters;
    CaptureStopReason stop_reason{CaptureStopReason::none};
};

/**
 * Phase 67: real interface enumeration and bounded passive capture.
 *
 * Enumeration shells to `dumpcap -D -M` (libpcap-backed enumeration, the same
 * device list libpcap's pcap_findalldevs reports) and parses the
 * machine-readable TSV lines (Wireshark 4.x; JSON accepted when present);
 * no interface name is hardcoded.
 *
 * Capture shells to the file-capability dumpcap helper (`/usr/bin/dumpcap`,
 * cap_net_admin+cap_net_raw) so unprivileged operators can capture on
 * allowlisted local interfaces. Every capture is bounded: at least one of
 * duration_seconds / packet_limit must be positive, enforced both by this
 * wrapper (validation + supervisor stop conditions) and by the backend
 * autostop flags (-a duration:N / packets:N). Counters are read from the
 * backend's own accounting (`Packets captured` / `Packets received/dropped`
 * on interface lines), never simulated.
 */
class LiveCaptureSession {
public:
    LiveCaptureSession();
    ~LiveCaptureSession();

    LiveCaptureSession(const LiveCaptureSession&) = delete;
    LiveCaptureSession& operator=(const LiveCaptureSession&) = delete;
    LiveCaptureSession(LiveCaptureSession&&) noexcept;
    LiveCaptureSession& operator=(LiveCaptureSession&&) noexcept;

    static std::vector<NetworkInterfaceInfo> list_interfaces(
        std::string& error);

    bool start(const CaptureSessionConfig& config);
    bool request_stop();
    bool wait_for_exit(std::uint32_t timeout_seconds);
    bool running() const noexcept;
    CaptureCounters counters() const;
    CaptureStopReason stop_reason() const noexcept;
    const std::string& last_error() const noexcept;

private:
    struct Impl;
    Impl* impl_;
};

} // namespace networkwm
