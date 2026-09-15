package com.networkwm.ingestion;

/**
 * Ingestion service: windowing + graph construction.
 *
 * Intended responsibility (deferred to later phases):
 *   - Consume packet/flow feature records (from the C++ engine via JNI/JNA
 *     or from CSV uploads).
 *   - Bucket traffic into fixed time windows (e.g. 10s, with 5s/30s
 *     configs on standby).
 *   - Aggregate per-host statistics (byte totals, unique destination ports,
 *     SYN:ACK ratio).
 *   - Build per-window host-flow graph snapshots (hosts as nodes, flows as
 *     edges with feature vectors) and serialize ordered graph sequences with
 *     next-state labels.
 *
 * TODO: implement in Phase 3 (ingestion, windowing, graph construction).
 */
public class IngestionService {
    // TODO: implement in Phase 3.
}
