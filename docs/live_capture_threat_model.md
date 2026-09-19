# KAIROS live-capture architecture and threat/safety model (Phase 66)

Status: normative for Phases 67-77. Every later phase implements exactly what
is scoped here. If a later phase needs something not covered, stop and update
this document first. Phase 68 binds the feature schema by reference to the
existing static pipeline (no new schema is invented here).

Scope boundary: passive capture of locally generated traffic on
operator-owned interfaces only. Active probing is NOT implemented in this
session (Stop Gate 1, before Phase 75, was never reached — Phases 75-78 are
explicitly out of scope and undescribed beyond their existing README rows).

## 1. API contracts

Base path (Java Spring Boot, same origin as `/forecast`): `/live`. All bodies
are JSON. Errors are `{error: string}` with HTTP 400 (bad request), 403
(consent-gate denial), 404 (unknown session), or 409 (illegal transition).

### POST /live/sessions — start a capture session

Request schema (all required unless marked):

| Field | Type | Required | Meaning |
|---|---|---|---|
| `interfaceName` | string | yes | OS interface name as listed by `GET /live/interfaces` (e.g. `lo`). Arbitrary names are rejected. |
| `mode` | string | yes | Must be exactly `passive`. Any other value (including `active`) is rejected with 400 in this session — there is no active-probe code path. |
| `durationSeconds` | integer | one of the two bounds required | Wall-clock bound, 1-3600. Auto-stops the session when reached. |
| `packetLimit` | integer | one of the two bounds required | Packet-count bound, 1-1000000. Auto-stops the session when reached. |
| `bpfFilter` | string | no | BPF filter expression (default `""` = capture all). Validated by compiling it with the capture backend before start; a compile failure rejects the request. Example: `udp port 9999`. |

At least one of `durationSeconds` / `packetLimit` must be present and
positive. A request with neither is refused with 400 (`unbounded capture
refused`). When both are present they are two independent stopping
mechanisms: whichever fires first stops the capture.

Response 200 schema:

```json
{
  "sessionId": "3fa85f64-5717-4562-b3fd-2fc963996703",
  "interfaceName": "lo",
  "mode": "passive",
  "state": "CAPTURING",
  "durationSeconds": 5,
  "packetLimit": 1000,
  "bpfFilter": "udp port 9999"
}
```

`sessionId` is a server-generated UUID. The response `state` is the live
lifecycle state after start was accepted (`STARTING` or `CAPTURING`).

### POST /live/sessions/{id}/stop — stop a capture session

No request body. Response 200: `{sessionId, state: STOPPED}` plus final
`packetCount` / `dropCount` counters. Stopping an already-`STOPPED` session
returns its final record (idempotent). Stopping from any non-terminal state
moves it through `STOPPING` to `STOPPED` and terminates the backend capture.

### GET /live/sessions/{id} — session status

Response 200 schema:

```json
{
  "sessionId": "...", "interfaceName": "lo", "mode": "passive",
  "state": "CAPTURING", "packetCount": 42, "dropCount": 0,
  "windowCount": 1, "startedAt": "2026-09-19T11:00:00Z",
  "stoppedAt": null, "stopReason": null
}
```

`stopReason` is one of `requested | duration_limit | packet_limit | error |
process_exit` (null while running).

### GET /live/interfaces — enumerate capture interfaces

Response 200: `{interfaces: [{name, description, loopback, addresses[]}]}`.
The list is produced by real OS enumeration (libpcap `pcap_findalldevs`
semantics via the capture backend) — no hardcoded names. `lo` (loopback) is
always expected; anything else present is reported as found.

### GET /live/sessions/{id}/windows — emitted feature windows

Response 200: `{sessionId, windows: [...]}` where each window is a
`kairos.graph.v1` snapshot shaped exactly like one static-pipeline window
(see section 2 and Phase 68/71). This is a read convenience; the streaming
transport (Phase 74) is the primary live path.

### DELETE /live/sessions/{id} — purge a session's data

Response 200: `{sessionId, purged: true}`. Deletes the session's capture
file, buffered windows, and prediction records from local disk (see
section 3). Session metadata row is retained in the audit log with
`purged=true` (audit records are never deleted by purge).

### Streaming (Phase 74)

`GET /live/sessions/{id}/events` with `Accept: text/event-stream` opens a
Server-Sent Events stream emitting `window`, `prediction`, `counter`, and
`state` events. SSE (not polling, not WebSocket) is the specified transport;
reconnect uses `Last-Event-ID`. Closing the connection never stops the
capture by itself (explicit stop required), but a session with zero
connected listeners for longer than its duration bound still self-stops via
its time bound.

## 2. Scope policy

### 2.1 What is captured

- Packet headers only, under the existing truncated-capture convention:
  snap length 256 bytes (`-s 256`), matching the CTU-13
  privacy-preserving "headers retained, payload removed" precedent.
- The C++ feature extractor recovers logical payload *lengths* from IPv4 /
  transport length headers (as the static pipeline already does) — lengths
  are statistics, never payload bytes.
- Link types supported: Ethernet (with up to 2 VLAN tags) and raw IPv4;
  protocols IPv4 TCP/UDP/ICMP. Anything else is skipped, counted as
  unsupported, and never fails the capture.

### 2.2 What is immediately discarded

- Payload bytes beyond the 256-byte snap (never written; the snap is a
  capture-time truncation, not a post-filter).
- Non-IPv4 frames (ARP, IPv6, etc.) — skipped at parse time.
- Malformed/unsupported packets — skipped safely, extractor error string
  set, capture continues.
- BPF-filtered-out packets — dropped by the kernel filter before userspace.

### 2.3 Auto-stop triggers (any one stops the capture)

1. `durationSeconds` wall-clock bound reached (enforced by the Java session
   supervisor, independent of the capture backend's own autostop).
2. `packetLimit` reached (enforced by the backend autostop `packets:N` AND
   re-checked by the supervisor from the counter stream).
3. Backend process exit or error (interface removed, filter invalid at
   runtime, backend crash) → state `ERROR`, `stopReason` set.
4. Explicit `POST .../stop` (user request) → `STOPPED`, `stopReason:
   requested`.
5. Abnormal termination (JVM crash, host reboot, interface down): on
   restart the supervisor marks any non-terminal session `ERROR` with
   `stopReason: process_exit`, kills any orphaned backend process for that
   session, and deletes its partial capture file only if it is corrupt
   (valid partial data is retained and marked truncated).

No always-on capture exists: unbounded start requests are refused, and every
running session has at least one live bound.

## 3. Retention policy

- Location: local disk only, under the server working directory
  (`live-sessions/{sessionId}/capture.pcap` + `windows.jsonl` +
  `predictions.jsonl`). No external upload exists anywhere in this design —
  live data never leaves the host; the Python `/predict` call is
  `127.0.0.1`-local like the static pipeline.
- Lifetime: session data persists until the operator deletes it via
  `DELETE /live/sessions/{id}` or deletes the directory manually. There is
  no automatic expiry beyond the capture auto-stop (stopped sessions keep
  their data for review).
- Purge: `DELETE /live/sessions/{id}` removes the session directory
  (capture file, buffered windows, predictions). The audit-log row
  (section 5, control 5) is retained with `purged=true` — audit records are
  append-only and survive purge by design.
- Predictions derived from live windows are subject to the same purge
  (they live in the session directory).

## 4. Interface lifecycle (normative state machine)

States: `IDLE → STARTING → CAPTURING → STOPPING → STOPPED`, plus `ERROR`
reachable from `STARTING`, `CAPTURING`, or `STOPPING`.

```
IDLE --(POST /live/sessions, consent-gate ALLOW)--> STARTING
STARTING --(backend capture confirmed running)--> CAPTURING
STARTING --(consent DENY | backend spawn failure | invalid filter)--> ERROR
CAPTURING --(POST .../stop)--> STOPPING --> STOPPED
CAPTURING --(duration bound | packet bound)--> STOPPING --> STOPPED
CAPTURING --(backend exit/error | interface down)--> ERROR
STOPPING --(backend terminated, counters flushed)--> STOPPED
STOPPING --(backend kill timeout / termination failure)--> ERROR
STOPPED, ERROR: terminal. No transitions out (a new sessionId is required
for a new capture).
```

Transition rules:

- `IDLE` exists only as the pre-creation state; sessions are created by
  the start endpoint (there is no explicit IDLE record).
- `STARTING` spawns the backend capture process and compiles the BPF. Any
  failure lands in `ERROR` with `stopReason: error` — never silently back
  to `IDLE`.
- `CAPTURING` is the only state in which packets are read and windows are
  emitted. Counters (`packetCount`, `dropCount`) advance only here.
- `STOPPING` terminates the backend process (SIGTERM, then SIGKILL after a
  5s grace), flushes final counters and the trailing partial window, then
  records `STOPPED`.
- `STOPPED` / `ERROR` are terminal and observable via `GET
  /live/sessions/{id}` forever (or until purge, which keeps the audit row).
- Abnormal termination: a supervisor sweep on startup finds sessions
  recorded as `STARTING`/`CAPTURING`/`STOPPING` with no live backend
  process, marks them `ERROR` (`stopReason: process_exit`), and kills any
  stray backend process holding the session's capture file (verified by
  Phase 69's no-orphan check).

Java-side session state is a mirror of this machine: the Java
`LiveSessionService` holds exactly one authoritative state per sessionId
and every JNI/backend callback is applied as a guarded transition — an
illegal transition throws rather than silently coercing state.

## 5. Threat model

| # | Misuse / failure scenario | Control (implemented, not advisory) |
|---|---|---|
| 1 | Capturing on an unauthorized interface (e.g. operator typo `eth0` instead of `lo`, or a hostile request smuggled to the API) | Phase 70 consent gate: default-empty operator allowlist; `interfaceName` must exactly match an allowlisted entry AND a real enumerated interface, else 403 + deny audit record. |
| 2 | Targeting a network the operator doesn't own (future active-probe target, or a crafted interface/address parameter) | Same consent gate: allowlist holds only operator-configured interfaces/CIDRs; URL/IP validation + DNS pinning (resolve once, pin for session, re-validate on long sessions) blocks TOCTOU allowlist bypass; active mode additionally disabled by default with a separate flag (Phase 75, out of scope this session). |
| 3 | Accidental always-on capture (forgotten session recording indefinitely) | Mandatory bounds (§1: at least one of duration/packet limit, maxima enforced) + dual independent stopping mechanisms (backend autostop AND Java supervisor bound); no unbounded-start code path exists. |
| 4 | Credential/PII exposure in captured headers (cookies, auth tokens, hostnames visible in header bytes) | Truncated capture (§2.1: 256-byte snap, payload never written) + local-disk-only retention (§3: no external upload) + purge endpoint (§3). Headers can still contain hostnames/IPs — documented residual risk, mitigated by allowlist scoping and purge. |
| 5 | Repudiation / unnoticed misuse (operator denies starting a capture, or a denied attempt goes unlogged) | Append-only audit record for EVERY session attempt (allowed or denied): timestamp, requested target, mode, allowlist decision, operator/user id if available. Purge never deletes audit rows. |
| 6 | Orphaned capture surviving session stop (background process keeps recording after the UI says stopped) | Phase 69 verified clean termination: stop kills the backend process group, stop endpoint returns only after process exit confirmed, and a test asserts no backend process remains post-stop. Startup sweep reaps strays (§4). |
| 7 | Malformed live data poisoning downstream inference (crafted traffic producing NaN/Inf features, schema drift) | Phase 71 adapter validates every window against the `kairos.sequence.v1` contract (finite numerics, declared names, ordered timestamps) and rejects/logs malformed windows; Phase 72 drift guard emits ok/degraded/unreliable quality beside every prediction. |
| 8 | Disconnect abuse (browser tab closed, capture runs forever with no listener) | SSE transport (§1): closing the stream does not stop capture, but the duration bound always does — a listener-less session still self-stops. Reconnect resumes via Last-Event-ID without duplicating backend state. |

Residual risks accepted and documented: header metadata (IPs/hostnames)
remains sensitive even after truncation; the consent gate is only as good
as the operator's allowlist configuration (empty default is safe but
requires deliberate setup); BPF filters are operator-supplied strings and
are compile-validated but not semantically sandboxed beyond the allowlist.
