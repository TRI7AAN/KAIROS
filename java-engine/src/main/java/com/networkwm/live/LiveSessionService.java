package com.networkwm.live;

import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.ReentrantLock;

/**
 * Phase 69: Java-side live capture session supervisor.
 *
 * Owns the Phase 66 lifecycle state machine
 * (IDLE -&gt; STARTING -&gt; CAPTURING -&gt; STOPPING -&gt; STOPPED / ERROR)
 * and delegates the actual bounded capture to a {@link CaptureBackend}.
 * The production backend ({@link ProcessCaptureBackend}) shells to the
 * file-capability dumpcap helper with dual autostop bounds
 * ({@code -a packets:N -a duration:N}); the Java supervisor enforces the
 * same bounds independently, so either mechanism stops the capture.
 *
 * Session data lives on local disk only under
 * {@code live-sessions/{sessionId}/} (capture.pcap, windows.jsonl,
 * predictions.jsonl). No external upload exists.
 */
@Service
public final class LiveSessionService {
    public static final long MAX_DURATION_SECONDS = 3600L;
    public static final long MAX_PACKET_LIMIT = 1_000_000L;
    public static final int MAX_SNAP_LENGTH = 262144;
    public static final int DEFAULT_SNAP_LENGTH = 256;

    public enum SessionState {
        STARTING,
        CAPTURING,
        STOPPING,
        STOPPED,
        ERROR
    }

    public enum StopReason {
        REQUESTED,
        DURATION_LIMIT,
        PACKET_LIMIT,
        ERROR,
        PROCESS_EXIT
    }

    public enum SessionMode {
        PASSIVE
    }

    private final CaptureBackend backend;
    private final Path sessionsRoot;
    private final ScheduledExecutorService scheduler;
    private final Map<String, LiveSession> sessions = new ConcurrentHashMap<>();

    public LiveSessionService() {
        this(new ProcessCaptureBackend(), defaultSessionsRoot());
    }

    public LiveSessionService(CaptureBackend backend, Path sessionsRoot) {
        this.backend = Objects.requireNonNull(backend, "backend");
        this.sessionsRoot = Objects.requireNonNull(sessionsRoot, "sessionsRoot");
        this.scheduler = Executors.newScheduledThreadPool(2, runnable -> {
            Thread thread = new Thread(runnable, "kairos-live-supervisor");
            thread.setDaemon(true);
            return thread;
        });
    }

    public record StartRequest(
            String interfaceName,
            String mode,
            Long durationSeconds,
            Long packetLimit,
            String bpfFilter) {
    }

    public record SessionView(
            String sessionId,
            String interfaceName,
            String mode,
            SessionState state,
            long packetCount,
            long dropCount,
            long windowCount,
            Instant startedAt,
            Instant stoppedAt,
            StopReason stopReason) {
    }

    public SessionView start(StartRequest request) throws IOException {
        Objects.requireNonNull(request, "request");
        String interfaceName = validateInterfaceName(request.interfaceName());
        SessionMode mode = validateMode(request.mode());
        long duration = validateDuration(request.durationSeconds());
        long packets = validatePacketLimit(request.packetLimit());
        if (duration <= 0 && packets <= 0) {
            throw new IllegalArgumentException(
                    "unbounded capture refused: set durationSeconds and/or packetLimit");
        }
        String filter = request.bpfFilter() == null ? "" : request.bpfFilter().trim();
        if (filter.length() > 4096) {
            throw new IllegalArgumentException("bpfFilter exceeds 4096 characters");
        }

        String sessionId = UUID.randomUUID().toString();
        Path sessionDir = sessionsRoot.resolve(sessionId);
        Files.createDirectories(sessionDir);
        Path captureFile = sessionDir.resolve("capture.pcap");

        LiveSession session = new LiveSession(
                sessionId, interfaceName, mode, duration, packets, filter,
                captureFile, Instant.now());
        sessions.put(sessionId, session);

        session.lock.lock();
        try {
            session.transition(SessionState.STARTING, SessionState.STARTING);
            try {
                backend.start(sessionId, interfaceName, filter, duration, packets,
                        DEFAULT_SNAP_LENGTH, captureFile);
            } catch (IOException | IllegalArgumentException error) {
                session.markError();
                throw error;
            }
            session.state = SessionState.CAPTURING;
            session.armSupervisor(duration, packets);
        } finally {
            session.lock.unlock();
        }
        return session.view();
    }

    public SessionView stop(String sessionId) throws IOException {
        LiveSession session = require(sessionId);
        session.lock.lock();
        try {
            if (session.state == SessionState.STOPPED
                    || session.state == SessionState.ERROR) {
                return session.view();
            }
            session.state = SessionState.STOPPING;
            session.stopReason = StopReason.REQUESTED;
            try {
                backend.stop(sessionId);
                backend.waitForExit(sessionId, Duration.ofSeconds(10));
            } catch (IOException error) {
                session.state = SessionState.ERROR;
                session.stopReason = StopReason.ERROR;
                session.stoppedAt = Instant.now();
                throw error;
            }
            session.countersFrom(backend.counters(sessionId));
            session.state = SessionState.STOPPED;
            session.stoppedAt = Instant.now();
            session.cancelSupervisor();
            return session.view();
        } finally {
            session.lock.unlock();
        }
    }

    public SessionView status(String sessionId) {
        LiveSession session = require(sessionId);
        session.lock.lock();
        try {
            session.pollBackend();
            return session.view();
        } finally {
            session.lock.unlock();
        }
    }

    public Optional<SessionView> find(String sessionId) {
        LiveSession session = sessions.get(sessionId);
        if (session == null) {
            return Optional.empty();
        }
        session.lock.lock();
        try {
            session.pollBackend();
            return Optional.of(session.view());
        } finally {
            session.lock.unlock();
        }
    }

    public List<SessionView> list() {
        return sessions.values().stream()
                .sorted(Comparator.comparing(LiveSession::startedAt))
                .map(session -> {
                    session.lock.lock();
                    try {
                        session.pollBackend();
                        return session.view();
                    } finally {
                        session.lock.unlock();
                    }
                })
                .toList();
    }

    public boolean purge(String sessionId) throws IOException {
        LiveSession session = require(sessionId);
        session.lock.lock();
        try {
            if (session.state == SessionState.CAPTURING
                    || session.state == SessionState.STARTING
                    || session.state == SessionState.STOPPING) {
                throw new IllegalStateException(
                        "stop the session before purging its data");
            }
            session.purged = true;
            deleteRecursively(session.sessionDir);
            return true;
        } finally {
            session.lock.unlock();
        }
    }

    public void sweepOrphans() {
        for (LiveSession session : sessions.values()) {
            session.lock.lock();
            try {
                if (session.state == SessionState.CAPTURING
                        || session.state == SessionState.STARTING
                        || session.state == SessionState.STOPPING) {
                    if (!backend.isRunning(session.sessionId)) {
                        session.countersFrom(backend.counters(session.sessionId));
                        session.state = SessionState.ERROR;
                        session.stopReason = StopReason.PROCESS_EXIT;
                        session.stoppedAt = Instant.now();
                        session.cancelSupervisor();
                    }
                }
            } finally {
                session.lock.unlock();
            }
        }
    }

    public void recordWindow(String sessionId, String windowJson) throws IOException {
        LiveSession session = require(sessionId);
        session.lock.lock();
        try {
            if (session.state != SessionState.CAPTURING) {
                throw new IllegalStateException(
                        "session is not capturing: " + session.state);
            }
            Path windows = session.sessionDir.resolve("windows.jsonl");
            String line = (windowJson == null ? "{}" : windowJson.strip()) + "\n";
            Files.writeString(windows,
                    line,
                    java.nio.file.StandardOpenOption.CREATE,
                    java.nio.file.StandardOpenOption.APPEND);
            session.windowCount.incrementAndGet();
        } finally {
            session.lock.unlock();
        }
    }

    public void shutdown() {
        scheduler.shutdownNow();
    }

    private LiveSession require(String sessionId) {
        LiveSession session = sessions.get(Objects.requireNonNull(sessionId, "sessionId"));
        if (session == null) {
            throw new IllegalArgumentException("unknown session: " + sessionId);
        }
        return session;
    }

    private static String validateInterfaceName(String name) {
        if (name == null || name.isBlank() || name.length() > 64
                || !name.matches("[A-Za-z0-9_.:\\-]+")) {
            throw new IllegalArgumentException("invalid interfaceName");
        }
        String trimmed = name.trim();
        boolean known = false;
        for (NetworkInterfaceInfo info : new ProcessCaptureBackend().listInterfaces()) {
            if (info.name().equals(trimmed)) {
                known = true;
                break;
            }
        }
        if (!known) {
            throw new IllegalArgumentException(
                    "unknown interface '" + trimmed + "': not reported by interface enumeration");
        }
        return trimmed;
    }

    private static SessionMode validateMode(String mode) {
        if (mode == null || !"passive".equalsIgnoreCase(mode.trim())) {
            throw new IllegalArgumentException(
                    "mode must be exactly 'passive' (active probing is not implemented)");
        }
        return SessionMode.PASSIVE;
    }

    private static long validateDuration(Long duration) {
        if (duration == null) {
            return 0L;
        }
        if (duration <= 0 || duration > MAX_DURATION_SECONDS) {
            throw new IllegalArgumentException(
                    "durationSeconds must be within 1.." + MAX_DURATION_SECONDS);
        }
        return duration;
    }

    private static long validatePacketLimit(Long packets) {
        if (packets == null) {
            return 0L;
        }
        if (packets <= 0 || packets > MAX_PACKET_LIMIT) {
            throw new IllegalArgumentException(
                    "packetLimit must be within 1.." + MAX_PACKET_LIMIT);
        }
        return packets;
    }

    private static Path defaultSessionsRoot() {
        String configured = System.getProperty("kairos.live.dir");
        if (configured != null && !configured.isBlank()) {
            return Path.of(configured);
        }
        return Path.of("live-sessions");
    }

    private static void deleteRecursively(Path root) throws IOException {
        if (!Files.exists(root)) {
            return;
        }
        try (var stream = Files.walk(root)) {
            List<Path> paths = stream.sorted(Comparator.reverseOrder()).toList();
            for (Path path : paths) {
                Files.deleteIfExists(path);
            }
        }
    }

    final class LiveSession {
        private final ReentrantLock lock = new ReentrantLock();
        private final String sessionId;
        private final String interfaceName;
        private final SessionMode mode;
        private final long durationSeconds;
        private final long packetLimit;
        private final String bpfFilter;
        private final Path sessionDir;
        private final Path captureFile;
        private final Instant startedAt;
        private final AtomicLong packetCount = new AtomicLong();
        private final AtomicLong dropCount = new AtomicLong();
        private final AtomicLong windowCount = new AtomicLong();
        private volatile SessionState state = SessionState.STARTING;
        private volatile StopReason stopReason;
        private volatile Instant stoppedAt;
        private volatile boolean purged;
        private volatile ScheduledFuture<?> supervisorTask;

        private LiveSession(
                String sessionId,
                String interfaceName,
                SessionMode mode,
                long durationSeconds,
                long packetLimit,
                String bpfFilter,
                Path captureFile,
                Instant startedAt) {
            this.sessionId = sessionId;
            this.interfaceName = interfaceName;
            this.mode = mode;
            this.durationSeconds = durationSeconds;
            this.packetLimit = packetLimit;
            this.bpfFilter = bpfFilter;
            this.captureFile = captureFile;
            this.sessionDir = captureFile.getParent();
            this.startedAt = startedAt;
        }

        private void transition(SessionState from, SessionState to) {
            if (state != from && !(from == SessionState.STARTING && state == SessionState.STARTING)) {
                throw new IllegalStateException(
                        "illegal session transition: " + state + " -> " + to);
            }
            state = to;
        }

        private void markError() {
            state = SessionState.ERROR;
            stopReason = StopReason.ERROR;
            stoppedAt = Instant.now();
        }

        private void armSupervisor(long duration, long packets) {
            cancelSupervisor();
            supervisorTask = scheduler.scheduleAtFixedRate(
                    () -> supervise(duration, packets),
                    500, 500, TimeUnit.MILLISECONDS);
        }

        private void supervise(long duration, long packets) {
            lock.lock();
            try {
                if (state != SessionState.CAPTURING) {
                    return;
                }
                pollBackend();
                if (state != SessionState.CAPTURING) {
                    return;
                }
                boolean durationHit = duration > 0
                        && Duration.between(startedAt, Instant.now()).getSeconds()
                                >= duration;
                boolean packetsHit = packets > 0
                        && packetCount.get() >= packets;
                if ((durationHit || packetsHit) && state == SessionState.CAPTURING) {
                    state = SessionState.STOPPING;
                    stopReason = durationHit
                            ? StopReason.DURATION_LIMIT : StopReason.PACKET_LIMIT;
                    try {
                        backend.stop(sessionId);
                        backend.waitForExit(sessionId, Duration.ofSeconds(10));
                        countersFrom(backend.counters(sessionId));
                        state = SessionState.STOPPED;
                    } catch (IOException error) {
                        state = SessionState.ERROR;
                        stopReason = StopReason.ERROR;
                    } finally {
                        stoppedAt = Instant.now();
                        cancelSupervisor();
                    }
                } else if (!backend.isRunning(sessionId)) {
                    countersFrom(backend.counters(sessionId));
                    state = SessionState.ERROR;
                    stopReason = StopReason.PROCESS_EXIT;
                    stoppedAt = Instant.now();
                    cancelSupervisor();
                }
            } finally {
                lock.unlock();
            }
        }

        private void pollBackend() {
            if (state == SessionState.CAPTURING) {
                countersFrom(backend.counters(sessionId));
                if (!backend.isRunning(sessionId)) {
                    state = SessionState.STOPPED;
                    if (stopReason == null) {
                        stopReason = StopReason.PROCESS_EXIT;
                    }
                    stoppedAt = Instant.now();
                    cancelSupervisor();
                }
            }
        }

        private void countersFrom(CaptureBackend.CaptureCounters counters) {
            if (counters != null) {
                packetCount.set(counters.received());
                dropCount.set(counters.dropped());
            }
        }

        private void cancelSupervisor() {
            ScheduledFuture<?> task = supervisorTask;
            supervisorTask = null;
            if (task != null) {
                task.cancel(false);
            }
        }

        private Instant startedAt() {
            return startedAt;
        }

        private SessionView view() {
            return new SessionView(
                    sessionId,
                    interfaceName,
                    mode.name().toLowerCase(java.util.Locale.ROOT),
                    state,
                    packetCount.get(),
                    dropCount.get(),
                    windowCount.get(),
                    startedAt,
                    stoppedAt,
                    stopReason);
        }
    }
}
