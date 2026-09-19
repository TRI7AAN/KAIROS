package com.networkwm.live;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.networkwm.live.LiveSessionService.SessionState;
import com.networkwm.live.LiveSessionService.SessionView;
import com.networkwm.live.LiveSessionService.StartRequest;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Phases 69/70/73/74: public live-capture REST boundary.
 *
 * <ul>
 *   <li>Every start passes through the Phase 70 {@link ConsentGateService}
 *   first: a DENIED decision returns 403 and no capture is spawned.</li>
 *   <li>Start/stop/status call the real {@link LiveSessionService} (real
 *   backend session, auditable via the consent-gate log).</li>
 *   <li>{@code GET /live/sessions/{id}/events} is a genuine
 *   Server-Sent Events stream (Phase 74): one persistent connection per
 *   subscriber, fed by {@link LivePredictionService} fan-out plus session
 *   state/counter heartbeats. No polling loop exists on either side.</li>
 * </ul>
 */
@RestController
@CrossOrigin(origins = {
        "http://localhost:3000",
        "http://127.0.0.1:3000"
})
@RequestMapping("/live")
public final class LiveCaptureController {
    private static final ObjectMapper JSON = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    private final LiveSessionService sessions;
    private final ConsentGateService consent;
    private final LivePredictionService predictions;
    private final ExecutorService ssePool = Executors.newCachedThreadPool(runnable -> {
        Thread thread = new Thread(runnable, "kairos-live-sse");
        thread.setDaemon(true);
        return thread;
    });

    public LiveCaptureController(
            LiveSessionService sessions,
            ConsentGateService consent,
            LivePredictionService predictions) {
        this.sessions = Objects.requireNonNull(sessions, "sessions");
        this.consent = Objects.requireNonNull(consent, "consent");
        this.predictions = Objects.requireNonNull(predictions, "predictions");
    }

    @GetMapping("/interfaces")
    public InterfacesResponse interfaces() {
        return new InterfacesResponse(
                new ProcessCaptureBackend().listInterfaces());
    }

    @PostMapping("/sessions")
    public SessionView start(
            @RequestBody StartRequest request,
            @RequestHeader(value = "X-Operator-Id", required = false)
                    String operatorId) {
        if (request == null || request.interfaceName() == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "interfaceName is required");
        }
        ConsentGateService.GateDecision decision = consent.check(
                request.interfaceName(), request.mode(), operatorId);
        if (decision.decision() != ConsentGateService.Decision.ALLOWED) {
            throw new ResponseStatusException(
                    HttpStatus.FORBIDDEN,
                    "capture refused by consent gate: " + decision.reason());
        }
        try {
            return sessions.start(request);
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, error.getMessage(), error);
        } catch (IOException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY,
                    "capture backend failed to start: " + error.getMessage(),
                    error);
        }
    }

    @PostMapping("/sessions/{id}/stop")
    public SessionView stop(@PathVariable("id") String sessionId) {
        try {
            return sessions.stop(sessionId);
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, error.getMessage(), error);
        } catch (IOException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, error.getMessage(), error);
        }
    }

    @GetMapping("/sessions/{id}")
    public SessionView status(@PathVariable("id") String sessionId) {
        try {
            return sessions.status(sessionId);
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, error.getMessage(), error);
        }
    }

    @GetMapping("/sessions")
    public List<SessionView> list() {
        return sessions.list();
    }

    @DeleteMapping("/sessions/{id}")
    public PurgeResponse purge(@PathVariable("id") String sessionId) {
        try {
            return new PurgeResponse(sessionId, sessions.purge(sessionId));
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, error.getMessage(), error);
        } catch (IllegalStateException error) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT, error.getMessage(), error);
        } catch (IOException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, error.getMessage(), error);
        }
    }

    @PostMapping("/sessions/{id}/windows")
    public LivePredictionService.LivePrediction ingestWindow(
            @PathVariable("id") String sessionId,
            @RequestBody WindowIngestRequest request) {
        if (request == null || request.windowJson() == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "windowJson is required");
        }
        try {
            return predictions.predict(sessionId, request.windowJson());
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, error.getMessage(), error);
        } catch (IllegalStateException error) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY, error.getMessage(), error);
        }
    }

    @GetMapping(
            path = "/sessions/{id}/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter events(@PathVariable("id") String sessionId) {
        try {
            sessions.status(sessionId);
        } catch (IllegalArgumentException error) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, error.getMessage(), error);
        }
        SseEmitter emitter = new SseEmitter(0L);
        Runnable unsubscribe = predictions.subscribe(
                sessionId, event -> send(emitter, "prediction", event));
        emitter.onCompletion(unsubscribe::run);
        emitter.onTimeout(unsubscribe::run);
        emitter.onError(ignored -> unsubscribe.run());
        ssePool.execute(() -> {
            try {
                send(emitter, "state", sessions.status(sessionId));
                long deadline = System.currentTimeMillis() + 3_600_000L;
                while (System.currentTimeMillis() < deadline) {
                    Thread.sleep(2000);
                    SessionView live = sessions.status(sessionId);
                    send(emitter, "counter", new CounterEvent(
                            live.sessionId(),
                            live.state().name(),
                            live.packetCount(),
                            live.dropCount(),
                            live.windowCount()));
                    if (live.state() == SessionState.STOPPED
                            || live.state() == SessionState.ERROR) {
                        send(emitter, "state", live);
                        break;
                    }
                }
                emitter.complete();
            } catch (Exception error) {
                emitter.completeWithError(error);
            } finally {
                unsubscribe.run();
            }
        });
        return emitter;
    }

    private static void send(SseEmitter emitter, String name, Object payload) {
        try {
            String encoded = JSON.writeValueAsString(payload);
            emitter.send(SseEmitter.event()
                    .name(name)
                    .data(encoded,
                            MediaType.APPLICATION_JSON));
        } catch (IOException error) {
            try {
                emitter.completeWithError(error);
            } catch (IllegalStateException alreadyCompleted) {
                // Emitter already finished (client disconnect); fall through.
            }
            throw new IllegalStateException("subscriber disconnected", error);
        }
    }

    public record InterfacesResponse(
            List<NetworkInterfaceInfo> interfaces) {
    }

    public record PurgeResponse(String sessionId, boolean purged) {
    }

    public record WindowIngestRequest(String windowJson) {
    }

    public record CounterEvent(
            String sessionId,
            String state,
            long packetCount,
            long dropCount,
            long windowCount) {
    }
}
