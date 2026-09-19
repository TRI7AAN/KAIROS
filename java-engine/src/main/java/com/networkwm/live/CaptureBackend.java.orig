package com.networkwm.live;

import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;

/**
 * Phase 69: capture-backend SPI behind {@link LiveSessionService}.
 *
 * The production implementation ({@link ProcessCaptureBackend}) spawns the
 * file-capability dumpcap helper with dual {@code -a} autostop bounds.
 * Tests substitute a fake that generates synthetic traffic without
 * touching the network.
 */
public interface CaptureBackend {
    void start(
            String sessionId,
            String interfaceName,
            String bpfFilter,
            long durationSeconds,
            long packetLimit,
            int snapLength,
            Path captureFile) throws IOException;

    void stop(String sessionId) throws IOException;

    void waitForExit(String sessionId, Duration timeout) throws IOException;

    boolean isRunning(String sessionId);

    CaptureCounters counters(String sessionId);

    List<NetworkInterfaceInfo> listInterfaces();

    record CaptureCounters(long captured, long received, long dropped) {
    }
}
