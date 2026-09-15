# Architecture Reference

This document is the standalone reference for the 4-layer architecture and the
inter-service communication contracts. It mirrors the relevant sections of
`README.md` for convenience during implementation.

## 4-Layer Stack

| Layer     | Language | Role |
|-----------|----------|------|
| cpp-engine | C++     | High-throughput packet-level feature extraction (TTL variance, TCP window size, frag flags, retransmission counts, port-scan signature detection). Per-packet loops over PCAPs benefit from native speed and direct memory access. |
| java-engine | Java   | Base orchestration: ingestion service, windowing, graph construction, REST API server; JNI/JNA bridge to cpp-engine; REST client to python-ml service; Gemini narrative service via the Google Gen AI Java SDK. |
| python-ml  | Python | GNN encoder (GraphSAGE/GAT) + Temporal Transformer dynamics model + K-step autoregressive rollout + forecast heads (sigmoid infiltration probability, softmax MITRE stage) + SHAP explainability via distilled surrogate. Exposed as a Flask REST service. |
| react-ui   | React  | Dashboard consuming the java-engine REST API: probability timeline, flagged flows table, stage annotations, Gemini narrative panel. |
| Gemini API | (via java-engine) | Natural-language SOC analyst briefing from the structured ML output. Human-facing layer; never a replacement for SHAP/attention explainability. |

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
[Java Narrative Service]  -- Gemini API (Google Gen AI Java SDK)
      |                        structured output -> natural-language
      |                        SOC analyst briefing (human-facing layer)
      v
[React Dashboard]  -- react-ui
      +-- Probability Timeline   (time series + alert threshold line)
      +-- Flagged Flows Table    (top-N per alerted window, from SHAP)
      +-- Stage Annotations      (color-coded by predicted MITRE stage)
      +-- Narrative Panel        (Gemini-generated briefing)
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
  per-window feature tensor to the python-ml Flask service.
- **Endpoint (deferred to Phase 3/4):**
  - `POST /predict` — request body carries the feature tensor (per-window
    graph snapshot); response body returns `{probability, predicted_stage,
    shap_features}` as JSON.

### Java <-> Gemini API
- **Mechanism:** Google Gen AI Java SDK from the `GeminiNarrativeService`.
- **Behavior (deferred to Phase 5):** builds a structured prompt from the
  python-ml response (probability, stage, top SHAP features) and returns a
  natural-language SOC analyst briefing. This output is rendered in the
  React dashboard's NarrativePanel; it supplements, and never replaces, the
  mandatory SHAP/attention explainability required by the problem statement.
