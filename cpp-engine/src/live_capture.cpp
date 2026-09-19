#include "live_capture.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <mutex>
#include <sstream>
#include <thread>

#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

namespace networkwm {
namespace {

constexpr const char* kDumpcapPath = "/usr/bin/dumpcap";
constexpr std::uint32_t kMaxDurationSeconds = 3600U;
constexpr std::uint64_t kMaxPacketLimit = 1000000ULL;

std::string run_command(const std::string& command) {
    std::string output;
    FILE* pipe = ::popen(command.c_str(), "r");
    if (pipe == nullptr) {
        return output;
    }
    std::array<char, 4096> buffer{};
    while (std::fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) !=
           nullptr) {
        output.append(buffer.data());
    }
    ::pclose(pipe);
    return output;
}

bool looks_like_interface_name(const std::string& name) {
    if (name.empty() || name.size() > 64U) {
        return false;
    }
    for (char c : name) {
        if (!(std::isalnum(static_cast<unsigned char>(c)) != 0 || c == '_' ||
              c == '-' || c == '.' || c == ':')) {
            return false;
        }
    }
    return true;
}

std::string json_unescape(const std::string& raw) {
    std::string out;
    for (std::size_t i = 0; i < raw.size(); ++i) {
        if (raw[i] == '\\' && i + 1 < raw.size()) {
            const char next = raw[i + 1];
            if (next == '"') {
                out.push_back('"');
            } else if (next == 'n') {
                out.push_back('\n');
            } else if (next == '\\') {
                out.push_back('\\');
            } else {
                out.push_back(next);
            }
            ++i;
        } else {
            out.push_back(raw[i]);
        }
    }
    return out;
}

bool known_interface(const std::vector<std::string>& names,
                     const std::string& wanted) {
    return std::find(names.begin(), names.end(), wanted) != names.end();
}

std::uint64_t parse_counter_after(const std::string& text,
                                  const std::string& marker) {
    const std::size_t pos = text.find(marker);
    if (pos == std::string::npos) {
        return 0U;
    }
    std::size_t i = pos + marker.size();
    while (i < text.size() &&
           !(std::isdigit(static_cast<unsigned char>(text[i])) != 0)) {
        ++i;
    }
    std::uint64_t value = 0U;
    bool any = false;
    while (i < text.size() &&
           std::isdigit(static_cast<unsigned char>(text[i])) != 0) {
        any = true;
        value = value * 10U +
                static_cast<std::uint64_t>(text[i] - '0');
        ++i;
    }
    return any ? value : 0U;
}

} // namespace

const char* to_string(CaptureStopReason reason) noexcept {
    switch (reason) {
    case CaptureStopReason::requested:
        return "requested";
    case CaptureStopReason::duration_limit:
        return "duration_limit";
    case CaptureStopReason::packet_limit:
        return "packet_limit";
    case CaptureStopReason::error:
        return "error";
    case CaptureStopReason::process_exit:
        return "process_exit";
    case CaptureStopReason::none:
    default:
        return "none";
    }
}

struct LiveCaptureSession::Impl {
    std::mutex mutex;
    pid_t child_pid{-1};
    int stderr_fd{-1};
    std::atomic<bool> running{false};
    std::atomic<bool> stop_requested{false};
    std::string stderr_text;
    std::string error;
    CaptureStopReason stop_reason{CaptureStopReason::none};
    CaptureSessionConfig config;
    std::chrono::steady_clock::time_point deadline{};
    bool has_deadline{false};
    std::thread reaper;

    ~Impl() {
        if (reaper.joinable()) {
            reaper.detach();
        }
    }

    void append_stderr(const std::string& chunk) {
        std::lock_guard<std::mutex> lock(mutex);
        stderr_text += chunk;
        if (stderr_text.size() > 65536U) {
            stderr_text.erase(0, stderr_text.size() - 65536U);
        }
    }

    CaptureCounters parse_counters() {
        std::lock_guard<std::mutex> lock(mutex);
        CaptureCounters counters;
        counters.packets_captured =
            parse_counter_after(stderr_text, "Packets captured:");
        counters.packets_received =
            parse_counter_after(stderr_text, "Packets received/dropped on interface");
        if (counters.packets_received == 0U) {
            counters.packets_received =
                parse_counter_after(stderr_text, "Packets:");
        }
        const std::size_t slash = stderr_text.rfind('/');
        if (slash != std::string::npos) {
            std::size_t i = slash + 1;
            while (i < stderr_text.size() && stderr_text[i] == ' ') {
                ++i;
            }
            std::uint64_t drops = 0U;
            bool any = false;
            while (i < stderr_text.size() &&
                   std::isdigit(static_cast<unsigned char>(stderr_text[i])) != 0) {
                any = true;
                drops = drops * 10U +
                        static_cast<std::uint64_t>(stderr_text[i] - '0');
                ++i;
            }
            if (any) {
                counters.packets_dropped = drops;
            }
        }
        if (counters.packets_captured > 0U && counters.packets_received == 0U) {
            counters.packets_received = counters.packets_captured;
        }
        return counters;
    }
};

LiveCaptureSession::LiveCaptureSession() : impl_(new Impl()) {}
LiveCaptureSession::~LiveCaptureSession() {
    if (impl_->reaper.joinable()) {
        request_stop();
        wait_for_exit(5U);
        impl_->reaper.join();
    }
    delete impl_;
}
LiveCaptureSession::LiveCaptureSession(LiveCaptureSession&& other) noexcept
    : impl_(other.impl_) {
    other.impl_ = nullptr;
}
LiveCaptureSession& LiveCaptureSession::operator=(
    LiveCaptureSession&& other) noexcept {
    if (this != &other) {
        delete impl_;
        impl_ = other.impl_;
        other.impl_ = nullptr;
    }
    return *this;
}

std::vector<NetworkInterfaceInfo> LiveCaptureSession::list_interfaces(
    std::string& error) {
    std::vector<NetworkInterfaceInfo> interfaces;
    const std::string output =
        run_command(std::string(kDumpcapPath) + " -D -M 2>/dev/null");
    if (output.empty()) {
        error = "interface enumeration produced no output";
        return interfaces;
    }
    // Wireshark 4.x `dumpcap -D -M` emits machine-readable TSV lines, not
    // JSON, e.g.:
    //   3. lo\t\tLoopback\t0\t127.0.0.1,::1\tloopback\t
    // Older dev notes assumed a JSON shape; accept JSON when present but
    // fall back to the line-based TSV/plain format actually observed.
    std::size_t array_start = output.find('[');
    if (array_start != std::string::npos) {
        std::size_t pos = array_start;
        while ((pos = output.find('{', pos)) != std::string::npos) {
        const std::size_t block_end = output.find('}', pos);
        if (block_end == std::string::npos) {
            break;
        }
        const std::string block = output.substr(pos, block_end - pos + 1);
        pos = block_end + 1;
        const std::size_t key_start = block.find('"');
        if (key_start == std::string::npos) {
            continue;
        }
        const std::size_t key_end = block.find('"', key_start + 1);
        if (key_end == std::string::npos) {
            continue;
        }
        const std::string candidate =
            block.substr(key_start + 1, key_end - key_start - 1);
        if (candidate.empty() || candidate.size() > 64U) {
            continue;
        }
        bool plausible = true;
        for (char c : candidate) {
            if (!(std::isalnum(static_cast<unsigned char>(c)) != 0 ||
                  c == '_' || c == '-' || c == '.' || c == ':')) {
                plausible = false;
                break;
            }
        }
        if (!plausible) {
            continue;
        }
        if (std::any_of(interfaces.begin(), interfaces.end(),
                        [&](const NetworkInterfaceInfo& info) {
                            return info.name == candidate;
                        })) {
            continue;
        }
        NetworkInterfaceInfo info;
        info.name = candidate;
        if (block.find("\"loopback\":true") != std::string::npos) {
            info.loopback = true;
        }
        const std::size_t addr_pos = block.find("\"addrs\":[");
        if (addr_pos != std::string::npos) {
            const std::size_t addr_end = block.find(']', addr_pos + 9);
            if (addr_end != std::string::npos) {
                const std::string list =
                    block.substr(addr_pos + 9, addr_end - addr_pos - 9);
                std::size_t q = 0;
                while ((q = list.find('"', q)) != std::string::npos) {
                    const std::size_t qe = list.find('"', q + 1);
                    if (qe == std::string::npos) {
                        break;
                    }
                    info.addresses.push_back(
                        json_unescape(list.substr(q + 1, qe - q - 1)));
                    q = qe + 1;
                }
            }
        }
        const std::string friendly_key = "\"friendly_name\":\"";
        const std::size_t friendly = block.find(friendly_key);
        if (friendly != std::string::npos) {
            const std::size_t fs = friendly + friendly_key.size();
            const std::size_t fe = block.find('"', fs);
            if (fe != std::string::npos) {
                info.description =
                    json_unescape(block.substr(fs, fe - fs));
            }
        }
        interfaces.push_back(std::move(info));
        }
    }
    if (!interfaces.empty()) {
        return interfaces;
    }
    // Line-based fallback: `dumpcap -D [-M]` prints one interface per line:
    //   "1. eth0" (plain) or "3. lo\t\tLoopback\t0\t127.0.0.1\tloopback\t"
    // (TSV machine-readable). Parse "<idx>. <name><tab/space>...".
    {
        std::istringstream lines(output);
        std::string line;
        while (std::getline(lines, line)) {
            if (!line.empty() && line.back() == '\r') {
                line.pop_back();
            }
            std::size_t dot = line.find('.');
            if (dot == std::string::npos || dot == 0U || dot > 6U) {
                continue;
            }
            bool idx_ok = true;
            for (std::size_t i = 0; i < dot; ++i) {
                if (!std::isdigit(static_cast<unsigned char>(line[i]))) {
                    idx_ok = false;
                    break;
                }
            }
            if (!idx_ok) {
                continue;
            }
            std::size_t name_begin = dot + 1;
            while (name_begin < line.size() &&
                   (line[name_begin] == ' ' || line[name_begin] == '\t')) {
                ++name_begin;
            }
            std::size_t name_end = name_begin;
            while (name_end < line.size() && line[name_end] != ' ' &&
                   line[name_end] != '\t' && line[name_end] != '(') {
                ++name_end;
            }
            std::string candidate = line.substr(name_begin, name_end - name_begin);
            while (!candidate.empty() &&
                   (candidate.back() == ' ' || candidate.back() == '\t')) {
                candidate.pop_back();
            }
            if (!looks_like_interface_name(candidate)) {
                continue;
            }
            if (std::any_of(interfaces.begin(), interfaces.end(),
                            [&](const NetworkInterfaceInfo& info) {
                                return info.name == candidate;
                            })) {
                continue;
            }
            NetworkInterfaceInfo info;
            info.name = candidate;
            std::string lower_rest = line.substr(name_end);
            for (char& c : lower_rest) {
                c = static_cast<char>(
                    std::tolower(static_cast<unsigned char>(c)));
            }
            if (candidate == "lo" || lower_rest.find("loopback") != std::string::npos) {
                info.loopback = true;
            }
            // Heuristic addresses: tab/comma separated tokens containing
            // '.' or ':' that look like IPs.
            std::string rest = line.substr(name_end);
            for (char& c : rest) {
                if (c == '\t' || c == ',') {
                    c = ' ';
                }
            }
            std::istringstream toks(rest);
            std::string tok;
            while (toks >> tok) {
                if (tok.size() < 3U || tok.size() > 64U) {
                    continue;
                }
                const bool has_dot = tok.find('.') != std::string::npos;
                const bool has_colon = tok.find(':') != std::string::npos;
                if (!has_dot && !has_colon) {
                    if (info.description.empty() && tok.size() > 1U &&
                        tok != "network" && tok != "0") {
                        info.description = tok;
                    }
                    continue;
                }
                bool ip_like = true;
                for (char c : tok) {
                    if (!(std::isalnum(static_cast<unsigned char>(c)) != 0 ||
                          c == '.' || c == ':' || c == '/')) {
                        ip_like = false;
                        break;
                    }
                }
                if (ip_like) {
                    info.addresses.push_back(tok);
                }
            }
            interfaces.push_back(std::move(info));
        }
    }
    if (interfaces.empty()) {
        error = "no interfaces parsed from enumeration output";
    }
    return interfaces;
}

bool LiveCaptureSession::start(const CaptureSessionConfig& config) {
    if (impl_->running.load()) {
        impl_->error = "capture session is already running";
        return false;
    }
    if (!looks_like_interface_name(config.interface_name)) {
        impl_->error = "invalid interface name";
        return false;
    }
    if (config.duration_seconds == 0U && config.packet_limit == 0U) {
        impl_->error = "unbounded capture refused: set duration_seconds "
                       "and/or packet_limit";
        return false;
    }
    if (config.duration_seconds > kMaxDurationSeconds) {
        impl_->error = "duration_seconds exceeds the 3600s maximum";
        return false;
    }
    if (config.packet_limit > kMaxPacketLimit) {
        impl_->error = "packet_limit exceeds the 1000000 maximum";
        return false;
    }
    if (config.output_path.empty()) {
        impl_->error = "output_path is required";
        return false;
    }
    if (config.snap_length == 0U || config.snap_length > 262144U) {
        impl_->error = "snap_length must be within 1..262144";
        return false;
    }
    std::string enum_error;
    std::vector<NetworkInterfaceInfo> devices =
        list_interfaces(enum_error);
    std::vector<std::string> names;
    for (const auto& device : devices) {
        names.push_back(device.name);
    }
    if (!known_interface(names, config.interface_name)) {
        impl_->error = "unknown interface '" + config.interface_name +
                       "': not reported by interface enumeration" +
                       (enum_error.empty() ? "" : " (" + enum_error + ")");
        return false;
    }

    int pipefd[2];
    if (::pipe(pipefd) != 0) {
        impl_->error = "failed to create capture log pipe";
        return false;
    }
    const pid_t pid = ::fork();
    if (pid < 0) {
        ::close(pipefd[0]);
        ::close(pipefd[1]);
        impl_->error = "failed to fork capture process";
        return false;
    }
    if (pid == 0) {
        ::dup2(pipefd[1], STDERR_FILENO);
        ::close(pipefd[0]);
        ::close(pipefd[1]);
        ::close(STDOUT_FILENO);
        const std::string snap = std::to_string(config.snap_length);
        const std::string packets =
            config.packet_limit > 0U
                ? "packets:" + std::to_string(config.packet_limit)
                : std::string();
        const std::string duration =
            config.duration_seconds > 0U
                ? "duration:" + std::to_string(config.duration_seconds)
                : std::string();
        const bool has_filter = !config.bpf_filter.empty();
        if (!has_filter && packets.empty() && duration.empty()) {
            ::execl(kDumpcapPath, "dumpcap", "-i",
                    config.interface_name.c_str(), "-P", "-s",
                    snap.c_str(), "-w", config.output_path.c_str(), "-q",
                    nullptr);
        } else if (!has_filter && !packets.empty() && duration.empty()) {
            ::execl(kDumpcapPath, "dumpcap", "-i",
                    config.interface_name.c_str(), "-P", "-s",
                    snap.c_str(), "-w", config.output_path.c_str(), "-q", "-a",
                    packets.c_str(), nullptr);
        } else if (!has_filter && packets.empty() && !duration.empty()) {
            ::execl(kDumpcapPath, "dumpcap", "-i",
                    config.interface_name.c_str(), "-P", "-s",
                    snap.c_str(), "-w", config.output_path.c_str(), "-q", "-a",
                    duration.c_str(), nullptr);
        } else if (!has_filter && !packets.empty() && !duration.empty()) {
            ::execl(kDumpcapPath, "dumpcap", "-i",
                    config.interface_name.c_str(), "-P", "-s",
                    snap.c_str(), "-w", config.output_path.c_str(), "-q", "-a",
                    packets.c_str(), "-a", duration.c_str(), nullptr);
        } else if (has_filter && packets.empty() && duration.empty()) {
            ::execl(kDumpcapPath, "dumpcap", "-i",
                    config.interface_name.c_str(), "-P", "-s",
                    snap.c_str(), "-w", config.output_path.c_str(), "-q", "-f",
                    config.bpf_filter.c_str(), nullptr);
        } else if (has_filter && !packets.empty() && duration.empty()) {
            ::execl(kDumpcapPath, "dumpcap", "-i",
                    config.interface_name.c_str(), "-P", "-s",
                    snap.c_str(), "-w", config.output_path.c_str(), "-q", "-f",
                    config.bpf_filter.c_str(), "-a", packets.c_str(), nullptr);
        } else if (has_filter && packets.empty() && !duration.empty()) {
            ::execl(kDumpcapPath, "dumpcap", "-i",
                    config.interface_name.c_str(), "-P", "-s",
                    snap.c_str(), "-w", config.output_path.c_str(), "-q", "-f",
                    config.bpf_filter.c_str(), "-a", duration.c_str(), nullptr);
        } else {
            ::execl(kDumpcapPath, "dumpcap", "-i",
                    config.interface_name.c_str(), "-P", "-s",
                    snap.c_str(), "-w", config.output_path.c_str(), "-q", "-f",
                    config.bpf_filter.c_str(), "-a", packets.c_str(), "-a",
                    duration.c_str(), nullptr);
        }
        _exit(127);
    }
    ::close(pipefd[1]);
    impl_->stderr_fd = pipefd[0];
    impl_->child_pid = pid;
    impl_->config = config;
    impl_->stop_requested.store(false);
    impl_->stop_reason = CaptureStopReason::none;
    {
        std::lock_guard<std::mutex> lock(impl_->mutex);
        impl_->stderr_text.clear();
        impl_->error.clear();
    }
    if (config.duration_seconds > 0U) {
        impl_->deadline = std::chrono::steady_clock::now() +
                          std::chrono::seconds(config.duration_seconds + 5U);
        impl_->has_deadline = true;
    } else {
        impl_->has_deadline = false;
    }
    impl_->running.store(true);

    std::this_thread::sleep_for(std::chrono::milliseconds(400));
    int status = 0;
    const pid_t probe = ::waitpid(pid, &status, WNOHANG);
    if (probe == pid) {
        char buf[4096];
        std::string early;
        ssize_t n = ::read(impl_->stderr_fd, buf, sizeof(buf) - 1);
        if (n > 0) {
            buf[n] = '\0';
            early = buf;
        }
        ::close(impl_->stderr_fd);
        impl_->stderr_fd = -1;
        impl_->child_pid = -1;
        impl_->running.store(false);
        impl_->stop_reason = CaptureStopReason::error;
        {
            std::lock_guard<std::mutex> lock(impl_->mutex);
            impl_->stderr_text = early;
            if (WIFEXITED(status) && WEXITSTATUS(status) != 0) {
                impl_->error = "capture backend exited immediately (status " +
                               std::to_string(WEXITSTATUS(status)) + "): " +
                               early;
            } else {
                impl_->error =
                    "capture backend failed to start: " + early;
            }
        }
        return false;
    }

    impl_->reaper = std::thread([impl = impl_]() {
        char buf[4096];
        while (true) {
            ssize_t n = ::read(impl->stderr_fd, buf, sizeof(buf) - 1);
            if (n <= 0) {
                break;
            }
            buf[n] = '\0';
            impl->append_stderr(std::string(buf, static_cast<std::size_t>(n)));
        }
        int status = 0;
        if (impl->child_pid > 0) {
            ::waitpid(impl->child_pid, &status, 0);
        }
        ::close(impl->stderr_fd);
        impl->stderr_fd = -1;
        impl->child_pid = -1;
        impl->running.store(false);
        if (impl->stop_requested.load()) {
            impl->stop_reason = CaptureStopReason::requested;
        } else if (impl->stop_reason == CaptureStopReason::none) {
            impl->stop_reason = CaptureStopReason::process_exit;
        }
    });
    impl_->reaper.detach();
    return true;
}

bool LiveCaptureSession::request_stop() {
    if (!impl_->running.load()) {
        return true;
    }
    impl_->stop_requested.store(true);
    if (impl_->stop_reason == CaptureStopReason::none) {
        impl_->stop_reason = CaptureStopReason::requested;
    }
    if (impl_->child_pid > 0) {
        ::kill(impl_->child_pid, SIGTERM);
    }
    return true;
}

bool LiveCaptureSession::wait_for_exit(std::uint32_t timeout_seconds) {
    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::seconds(timeout_seconds);
    while (impl_->running.load()) {
        if (impl_->has_deadline &&
            std::chrono::steady_clock::now() > impl_->deadline) {
            if (impl_->child_pid > 0) {
                ::kill(impl_->child_pid, SIGKILL);
            }
            impl_->stop_reason = CaptureStopReason::duration_limit;
        }
        if (std::chrono::steady_clock::now() > deadline) {
            if (impl_->child_pid > 0) {
                ::kill(impl_->child_pid, SIGKILL);
            }
            return false;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    return true;
}

bool LiveCaptureSession::running() const noexcept {
    return impl_->running.load();
}

CaptureCounters LiveCaptureSession::counters() const {
    return impl_->parse_counters();
}

CaptureStopReason LiveCaptureSession::stop_reason() const noexcept {
    return impl_->stop_reason;
}

const std::string& LiveCaptureSession::last_error() const noexcept {
    return impl_->error;
}

} // namespace networkwm
