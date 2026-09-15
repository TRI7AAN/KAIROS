# Architecture Reference

This document is the standalone reference for the 4-layer architecture and the
inter-service communication contracts. It mirrors the relevant sections of
`README.md` for convenience during implementation.

## 4-Layer Stack

| Layer     | Language | Role |
|-----------|----------|------|
| cpp-engine | C++     | High-throughput packet-level feature extraction (TTL variance, TCP window size, frag flags, retransmission counts, port-scan signature detection). Per-packet loops over PCAPs benefit from native speed and direct memory access. |
| java-engine | Java   | Canonical ingestion and orchestration owner: CSV parsing, packet-feature merge, windowing, attack-stage labels, graph construction, public REST API, C++ bridge, Python client, and offline narrative generation. |
| python-ml  | Python | Deserializes the versioned Java graph contract into PyTorch Geometric objects; owns the GNN encoder, Temporal Transformer dynamics, K-step rollout, forecast heads, and SHAP/attention explainability. Exposed as a private Flask inference service. |
| react-ui   | React  | Dashboard consuming Java's public `/forecast` API: upload, probability timeline, flagged flows, stage annotations, and narrative panel. |
| Gemini API | (optional, via java-engine) | Enhanced SOC narrative available only in explicit online mode. The default local narrative keeps the complete demo offline. |

## Architecture Diagram

```
Raw PCAP / CSV
      |
      v
[C++ Packet Feature Extraction]  -- cpp-engine (libpcap)
      |                              TTL variance, TCP window size,
      |                              frag flags, retransmission counts,
      |                              port-scan signature detection
      v
[Java Ingestion Service]  -- java-engine
      |                        read PCAP/CSV, stream into time windows
      |                        (10s default; 5s/30s configs on standby)
      v
[Java Windowing + Graph Builder]  -- java-engine
      |                              per-window host-flow graph snapshots
      |                              (hosts=nodes, flows=edges with features)
      |                              ordered graph sequences + next-state labels
      v
[REST: POST /predict]  -- java-engine -> python-ml  (feature tensor JSON)
      |
      v
[python-ml World Model Service]  (Flask)
      |
      +-- [GNN Encoder: GraphSAGE/GAT]  -> per-window graph embedding
      |
      +-- [Temporal Dynamics: Transformer / LSTM]  learns P(S_t+1 | S_t)
      |
      +-- [K-Step Autoregressive Rollout]  t+1 .. t+K predicted states
      |
      +-- [Forecast Heads]
      |        +-- infiltration probability  (sigmoid)
      |        `-- MITRE ATT&CK stage        (softmax, 6 classes)
      |
      `-- [SHAP Explainer]  distilled surrogate model -> top features
      |
      v
[JSON response]  probability + predicted stage + SHAP features
      |
      v
[Java Narrative Service]  -- local rule-based generator by default
      |                        optional Gemini enhancement in online mode
      |                        structured output -> SOC analyst briefing
      v
[React Dashboard]  -- react-ui
      +-- Probability Timeline   (time series + alert threshold line)
      +-- Flagged Flows Table    (top-N per alerted window, from SHAP)
      +-- Stage Annotations      (color-coded by predicted MITRE stage)
      +-- Narrative Panel        (local or Gemini briefing, mode-indicated)
```

## Inter-Service Communication

### Java <-> C++ (cpp-engine)
- **Mechanism:** JNI or JNA, loading the native shared library produced by
  cpp-engine. For the prototype, a subprocess invocation of a C++ CLI wrapper
  is an acceptable fallback.
- **Calls (deferred to Phase 2/3):**
  - `FeatureExtractor::open(pcap_path)` — open a PCAP for reading.
  - `FeatureExtractor::extract_next_batch()` — read and aggregate the next
    batch of packets into flow-level feature records returned to Java.

### Java <-> Python (python-ml)
- **Mechanism:** HTTP REST. Java's `PythonMlClient` (OkHttp3) POSTs the
  versioned per-window host-flow graph snapshots to the python-ml Flask service.
- **Ownership:** Java constructs graph topology and attaches timeline-derived
  labels. Python validates/deserializes that contract into PyTorch Geometric
  objects; it does not independently reconstruct graphs from raw traffic.
- **Endpoint (deferred to Phase 3/4):**
  - `POST /predict` — request body carries the feature tensor (per-window
    graph snapshot); response body returns `{probability, predicted_stage,
    shap_features}` as JSON.

### React <-> Java (public API)
- **Endpoint:** `POST /forecast` accepts a PCAP or CSV upload and returns the
  complete timeline, stage, explanation, flagged-flow, and narrative response.
- The Python `/predict` endpoint is internal and is never called by the browser.

### Java narrative modes
- **Offline default:** a local deterministic template converts structured
  predictions into a SOC briefing without making a network call.
- **Optional online mode:** when `ONLINE_MODE=true` and `GEMINI_API_KEY` is
  present, `GeminiNarrativeService` may enrich the briefing through the Google
  Gen AI Java SDK. It supplements, and never replaces, SHAP/attention output.
