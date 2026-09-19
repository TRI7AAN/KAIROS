package com.networkwm.live;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * Phase 69: production capture backend.
 *
 * Spawns {@code /usr/bin/dumpcap} (file capabilities
 * cap_net_admin+cap_net_raw, so unprivileged operators can capture on
 * allowlisted local interfaces) with the truncated-capture convention
 * ({@code -s 256}, headers only) and dual autostop bounds
 * ({@code -a packets:N -a duration:N}). Enumerates interfaces via
 * {@code dumpcap -D -M} (libpcap's device list, machine-readable JSON) with
 * no hardcoded names. Counters come from the backend's own stderr
 * accounting, never simulated.
 */
public final class ProcessCaptureBackend implements CaptureBackend {
    static final String DUMPCAP = "/usr/bin/dumpcap";

    private final Map<String, RunningCapture> processes = new ConcurrentHashMap<>();

    @Override
    public void start(
            String sessionId,
            String interfaceName,
            String bpfFilter,
            long durationSeconds,
            long packetLimit,
            int snapLength,
            Path captureFile) throws IOException {
        Objects.requireNonNull(sessionId, "sessionId");
        Objects.requireNonNull(interfaceName, "interfaceName");
        Objects.requireNonNull(captureFile, "captureFile");
        if (processes.containsKey(sessionId)) {
            throw new IllegalStateException("session already capturing: " + sessionId);
        }
        if (!Files.exists(Path.of(DUMPCAP))) {
            throw new IOException("capture helper not found: " + DUMPCAP);
        }
        List<String> command = new ArrayList<>();
        command.add(DUMPCAP);
        command.add("-i");
        command.add(interfaceName);
        command.add("-F");
        command.add("pcap");
        command.add("-s");
        command.add(String.valueOf(snapLength));
        command.add("-w");
        command.add(captureFile.toAbsolutePath().toString());
        command.add("-q");
        if (bpfFilter != null && !bpfFilter.isBlank()) {
            command.add("-f");
            command.add(bpfFilter);
        }
        if (packetLimit > 0) {
            command.add("-a");
            command.add("packets:" + packetLimit);
        }
        if (durationSeconds > 0) {
            command.add("-a");
            command.add("duration:" + durationSeconds);
        }
        Process process;
        try {
            process = new ProcessBuilder(command)
                    .redirectOutput(ProcessBuilder.Redirect.DISCARD)
                    .redirectErrorStream(false)
                    .start();
        } catch (IOException error) {
            throw new IOException("failed to spawn capture backend", error);
        }
        RunningCapture running =
                new RunningCapture(process, new ByteArrayOutputStream(), Instant.now());
        processes.put(sessionId, running);
        Thread drainer = new Thread(
                () -> drain(process.getErrorStream(), running),
                "kairos-capture-" + sessionId);
        drainer.setDaemon(true);
        drainer.start();

        try {
            Thread.sleep(400);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        }
        if (!process.isAlive()) {
            processes.remove(sessionId);
            String detail = running.stderrText();
            int exit = process.exitValue();
            throw new IOException(
                    "capture backend exited immediately (status " + exit + "): " + detail);
        }
    }

    @Override
    public void stop(String sessionId) throws IOException {
        RunningCapture running = processes.get(sessionId);
        if (running == null) {
            return;
        }
        Process process = running.process();
        process.destroy();
        try {
            if (!process.waitFor(5, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                if (!process.waitFor(5, TimeUnit.SECONDS)) {
                    throw new IOException(
                            "capture backend refused to terminate: " + sessionId);
                }
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IOException("interrupted while stopping capture", interrupted);
        }
    }

    @Override
    public void waitForExit(String sessionId, Duration timeout) throws IOException {
        RunningCapture running = processes.get(sessionId);
        if (running == null) {
            return;
        }
        try {
            boolean exited = running.process()
                    .waitFor(timeout.toMillis(), TimeUnit.MILLISECONDS);
            if (!exited) {
                running.process().destroyForcibly();
                throw new IOException(
                        "capture backend did not exit within " + timeout);
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IOException("interrupted while waiting for capture", interrupted);
        } finally {
            if (!running.process().isAlive()) {
                processes.remove(sessionId);
            }
        }
    }

    @Override
    public boolean isRunning(String sessionId) {
        RunningCapture running = processes.get(sessionId);
        if (running == null) {
            return false;
        }
        if (running.process().isAlive()) {
            return true;
        }
        processes.remove(sessionId);
        return false;
    }

    @Override
    public CaptureCounters counters(String sessionId) {
        RunningCapture running = processes.get(sessionId);
        String text = running == null ? "" : running.stderrText();
        return parseCounters(text);
    }

    @Override
    public List<NetworkInterfaceInfo> listInterfaces() {
        try {
            Process process = new ProcessBuilder(DUMPCAP, "-D", "-M")
                    .redirectErrorStream(false)
                    .start();
            String output;
            try (InputStream stream = process.getInputStream()) {
                output = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            }
            boolean finished = process.waitFor(10, TimeUnit.SECONDS);
            if (!finished || output.isBlank()) {
                return List.of();
            }
            return parseInterfaces(output);
        } catch (IOException | InterruptedException error) {
            if (error instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            return List.of();
        }
    }

    static CaptureCounters parseCounters(String stderrText) {
        if (stderrText == null || stderrText.isBlank()) {
            return new CaptureCounters(0, 0, 0);
        }
        long captured = counterAfter(stderrText, "Packets captured:");
        long received = 0;
        int anchor = stderrText.lastIndexOf("Packets received/dropped on interface");
        if (anchor >= 0) {
            received = leadingNumber(stderrText, anchor);
            int slash = stderrText.indexOf('/', anchor);
            long dropped = slash >= 0 ? leadingNumber(stderrText, slash + 1) : 0;
            if (received == 0 && captured > 0) {
                received = captured;
            }
            return new CaptureCounters(captured, received, dropped);
        }
        long packets = counterAfter(stderrText, "Packets:");
        if (received == 0) {
            received = Math.max(packets, captured);
        }
        return new CaptureCounters(captured, received, 0);
    }

    private static long counterAfter(String text, String marker) {
        int index = text.indexOf(marker);
        if (index < 0) {
            return 0;
        }
        return leadingNumber(text, index + marker.length());
    }

    private static long leadingNumber(String text, int from) {
        int i = from;
        while (i < text.length() && !Character.isDigit(text.charAt(i))) {
            i++;
        }
        long value = 0;
        boolean any = false;
        while (i < text.length() && Character.isDigit(text.charAt(i))) {
            any = true;
            value = value * 10 + (text.charAt(i) - '0');
            i++;
        }
        return any ? value : 0;
    }

    static List<NetworkInterfaceInfo> parseInterfaces(String json) {
        List<NetworkInterfaceInfo> interfaces = new ArrayList<>();
        int arrayStart = json.indexOf('[');
        if (arrayStart < 0) {
            return interfaces;
        }
        int cursor = arrayStart;
        while (true) {
            int open = json.indexOf('{', cursor);
            if (open < 0) {
                break;
            }
            int close = json.indexOf('}', open);
            if (close < 0) {
                break;
            }
            String block = json.substring(open, close + 1);
            cursor = close + 1;
            int keyStart = block.indexOf('"');
            if (keyStart < 0) {
                continue;
            }
            int keyEnd = block.indexOf('"', keyStart + 1);
            if (keyEnd < 0) {
                continue;
            }
            String name = block.substring(keyStart + 1, keyEnd);
            if (name.isBlank() || name.length() > 64
                    || !name.matches("[A-Za-z0-9_.:\\-]+")) {
                continue;
            }
            boolean duplicate = false;
            for (NetworkInterfaceInfo info : interfaces) {
                if (info.name().equals(name)) {
                    duplicate = true;
                    break;
                }
            }
            if (duplicate) {
                continue;
            }
            boolean loopback = block.contains("\"loopback\":true");
            List<String> addresses = new ArrayList<>();
            int addrPos = block.indexOf("\"addrs\":[");
            if (addrPos >= 0) {
                int addrEnd = block.indexOf(']', addrPos + 9);
                if (addrEnd >= 0) {
                    String list = block.substring(addrPos + 9, addrEnd);
                    int q = 0;
                    while (true) {
                        int qs = list.indexOf('"', q);
                        if (qs < 0) {
                            break;
                        }
                        int qe = list.indexOf('"', qs + 1);
                        if (qe < 0) {
                            break;
                        }
                        addresses.add(list.substring(qs + 1, qe));
                        q = qe + 1;
                    }
                }
            }
            String description = "";
            String friendlyKey = "\"friendly_name\":\"";
            int friendly = block.indexOf(friendlyKey);
            if (friendly >= 0) {
                int start = friendly + friendlyKey.length();
                int end = block.indexOf('"', start);
                if (end > start) {
                    description = block.substring(start, end);
                }
            }
            interfaces.add(new NetworkInterfaceInfo(
                    name, description, loopback, addresses));
        }
        return interfaces;
    }

    private static void drain(
            InputStream stream, RunningCapture running) {
        try (InputStream owned = stream) {
            byte[] buffer = new byte[4096];
            int read;
            while ((read = owned.read(buffer)) >= 0) {
                running.append(buffer, read);
            }
        } catch (IOException ignored) {
            // Backend stderr closed with the process; counters parsed so far stand.
        }
    }

    private record RunningCapture(
            Process process,
            ByteArrayOutputStream stderr,
            Instant startedAt) {
        private synchronized void append(byte[] chunk, int length) {
            if (stderr.size() > 65536) {
                stderr.reset();
            }
            stderr.write(chunk, 0, length);
        }

        private synchronized String stderrText() {
            return stderr.toString(StandardCharsets.UTF_8);
        }
    }
}
