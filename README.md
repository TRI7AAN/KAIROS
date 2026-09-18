# KAIROS — Network Attack World Model

KAIROS learns network-traffic state-transition dynamics — P(S_t+1 | S_t), the
probability distribution over future network states given the current state —
and forecasts attacker progression before compromise using K-step
autoregressive rollout of the learned dynamics, instead of classifying the
present. The static offline pipeline (file upload → windowing → graph build →
world-model inference → explanation → analyst narrative → dashboard) is
complete and verified end-to-end (Phases 0–63), runs fully offline by default,
and currently trails a non-temporal logistic-regression baseline on raw
in-distribution F1 while offering rollout-based early warning, MITRE-stage
mapping, and SHAP/attention explainability the baseline cannot provide. A
live-capture and authorized active-probe extension (Phases 66–78) is planned
as a separate, higher-risk tier and has not started.

## Table of Contents

- [Safety and Legal Notice](#safety-and-legal-notice)
- [Architecture Overview](#architecture-overview)
- [Quick Start (Offline Demo)](#quick-start-offline-demo)
- [Datasets](#datasets)
- [Model Architecture and Training](#model-architecture-and-training)
- [Benchmark Results](#benchmark-results)
- [Explainability](#explainability)
- [MITRE ATT\&CK Stage Mapping](#mitre-attck-stage-mapping)
- [Offline Mode and Gemini Narrative Mode](#offline-mode-and-gemini-narrative-mode)
- [Known Limitations](#known-limitations)
- [Roadmap — Live-Capture and Active-Probe Extension (Phases 66–78)](#roadmap--live-capture-and-active-probe-extension-phases-66-78)
- [Reproducibility](#reproducibility)
- [Contribution / License / Acknowledgments](#contribution--license--acknowledgments)

## Safety and Legal Notice

This project is a research/hackathon prototype. The verified static pipeline
analyzes files you provide (PCAP/CSV upload) only — it performs no network
capture and no active probing. Any future live-capture or active-probe
capability (Phases 66–78, not started) must only be used on networks and
hosts you own or are explicitly authorized to test. Active probing in
particular carries legal responsibility resting entirely with the operator.
The project maintainers are not responsible for misuse.

## Architecture Overview

Four-layer stack, one language per layer, plus an optional narrative layer:

- **C++ (cpp-engine): packet-level feature extraction.** Parses PCAP/PCAPNG,
  aggregates flows, reconstructs logical payload lengths from retained
  headers, and runs a per-window port-scan signature detector (sequential vs.
  randomized). Exposed to Java via JNI (`libkairos_native.so`).
- **Java (java-engine): orchestration engine and REST API.** CSV ingestion,
  10-second windowing, host-flow graph construction, the versioned
  `kairos.sequence.v1` contract, the typed `PythonMlClient` REST client,
  narrative services, and the public `POST /forecast` and
  `POST /forecast/upload` endpoints (Spring Boot).
- **Python (python-ml): world-model inference service (Flask).** GraphSAGE
  encoder → causal Transformer dynamics → K-step rollout → infiltration and
  stage forecast heads → SHAP/attention explanation. Internal
  `POST /predict` endpoint (never called by the browser).
- **React (react-ui): dashboard.** Upload form, probability timeline, flagged
  flows table, stage annotations, narrative panel with mode badge, and a
  sample-attack quick-load button. Calls Java at `POST /forecast/upload`.
- **Narrative layer (Java, optional Gemini):** the **default is the
  offline-local rule-based generator** — deterministic templating, no network
  call. Gemini enhancement requires **both** `ONLINE_MODE=true` **and** a
  `GEMINI_API_KEY` (with `GOOGLE_API_KEY` accepted as a legacy fallback);
  any Gemini failure falls back to a local narrative. Gemini supplements and
  never replaces SHAP/attention output.

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
      |                        (10s windows)
      v
[Java Windowing + Graph Builder]  -- java-engine
      |                              per-window host-flow graph snapshots
      |                              ordered graph sequences + next-state labels
      v
[REST: POST /predict]  -- java-engine -> python-ml  (feature tensor JSON)
      |
      v
[python-ml World Model Service]  (Flask)
      |
      +-- [GNN Encoder: GraphSAGE]  -> per-window graph embedding
      |
      +-- [Temporal Dynamics: Transformer]  learns P(S_t+1 | S_t)
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
[Java Narrative Service]  -- default: local rule-based generator (offline)
      |                        optional: Gemini API (Google Gen AI Java SDK)
      |                        structured output -> natural-language
      |                        SOC analyst briefing (human-facing layer)
      v
[React Dashboard]  -- react-ui
      +-- Probability Timeline   (time series + alert threshold line)
      +-- Flagged Flows Table    (top-N per alerted window, from SHAP)
      +-- Stage Annotations      (color-coded by predicted MITRE stage)
      +-- Narrative Panel        (local or Gemini briefing, mode-indicated)
```

Inter-service calls: Java→C++ via JNI (`CppBridge`); Java→Python via
`PythonMlClient` (OkHttp) to the private `POST /predict`; browser→Java at
`POST /forecast` / `POST /forecast/upload`. The Python endpoint is internal
and is never called by the browser.

## Quick Start (Offline Demo)

This is the exact command sequence verified live (full stack, network
disabled, real CSV upload → narrative → JSON response, zero errors, zero
external calls; sample upload answered in 0.28–0.43s; cold start ≈ Java
boot ~1.4s + first inference ~0.3s, well under 30s).

Prerequisites per layer (all verified):

- **C++:** C++17 compiler + CMake. Build the native library:
  `cmake -S cpp-engine -B cpp-engine/cmake-build-local && cmake --build cpp-engine/cmake-build-local`
  (the JNI round-trip test passes against the built `libkairos_native.so`).
- **Java:** JDK 17 or newer — tested with JDK 21
  (`export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64`). Maven is
  supplied by the checked-in wrapper (`./mvnw`); the full suite passes
  offline (`./mvnw -o test`: 20 tests, 0 failures).
- **Python:** `python3 -m venv python-ml/venv &&
  python-ml/venv/bin/pip install -r python-ml/requirements.txt` (pinned,
  CPU-only: `torch==2.14.0+cpu`, `torch-geometric==2.8.0.post1`,
  `Flask==3.1.3`, `shap==0.52.0`, `scikit-learn==1.9.1`). Tested with
  Python 3.13.
- **React:** Node (`.node-version` pins 24.21.0), React 18
  (`react-scripts ^5.0.1`): `cd react-ui && npm ci && npm run build`
  (verified: compiles successfully).
- **Offline env:** `cp .env.example .env` (ships `ONLINE_MODE=false` with
  an empty key). Ensure neither `GEMINI_API_KEY` nor `GOOGLE_API_KEY` is
  set in the environment.

Run the offline demo (three terminals, repo root):

```bash
# Terminal 1 — Python ML service (default port 5000)
ONLINE_MODE=false python-ml/venv/bin/python python-ml/app.py

# Terminal 2 — Java engine (default port 8080; JDK 21)
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
cd java-engine && ONLINE_MODE=false ./mvnw spring-boot:run

# Terminal 3 — upload the bundled sample through the full chain
curl -X POST http://127.0.0.1:8080/forecast/upload \
  -F "file=@react-ui/public/sample-attack.csv;type=text/csv" \
  -F "rolloutSteps=3"
```

Expected: HTTP 200 with `{artifactVersion, prediction, narrative}`, where
`prediction.probability` ≈ 0.59, `predicted_stage` is a MITRE stage, and
`narrative.mode` is `offline-local`. (Verified live: probability 0.5901,
stage `COMMAND_AND_CONTROL`, mode `offline-local`.) The React dashboard
(`react-ui`, served from `npm run build` output) posts to the same
`/forecast/upload` endpoint via its "Load sample attack" button.

## Datasets

**CSE-CIC-IDS2018 (primary training data)** — exactly four days are used:
2018-02-14, 2018-02-15, 2018-02-28, and 2018-03-02. Each day is capped to
200,000 flows with seed 42 via `python-ml/pipeline/downsample_flows.py`
(stratified, class-ratio-preserving; see `data/cic_ids_2018_manifest.yaml`),
then exported to 10-second graph contracts
(`data/processed/graph_contracts/day14/day15/day28/day0302.json`): 3,253 +
3,413 + 3,393 + 3,143 = 13,202 ordered windows. Raw and processed data
directories are gitignored (local `data/` ≈ 4.7G); manifests are tracked.

**CTU-13 Scenario 6 / DonBot (capture 47)** — reserved for packet-level
feature development ONLY: the official privacy-preserving truncated
complete-traffic capture (602,748,112-byte `.bz2`, SHA-256-verified;
38,705,338 packets, 7749.87s / 02:09:10, headers retained, payload
removed) at `data/raw/ctu13_pcap/scenario06_donbot/`, documented in
`data/ctu13_scenario6_manifest.yaml`. It is **explicitly excluded from any
zero-shot generalization test** — the Phases 58–60 test must use a
different CTU-13 scenario to preserve the leakage-free claim.

## Model Architecture and Training

- **GNN encoder:** edge-aware GraphSAGE, 2 layers, hidden dim 64, state dim
  64, attention pooling, dropout 0.1 (`python-ml/model/encoder_gnn.py`).
- **Temporal dynamics:** causal Transformer, 2 layers, 4 heads, sinusoidal
  positional encoding, dropout 0.1 (`python-ml/model/dynamics_transformer.py`).
- **Rollout:** K-step autoregressive feeding of predicted states; K=3 is the
  selected horizon (ablated K=3/5/10). Services accept rollout steps 1–10.
- **Forecast heads:** sigmoid infiltration-probability head and 6-class
  softmax MITRE-stage head sharing the rolled-forward latents; focal
  classification losses plus dynamics MSE, gradient clipping
  (`python-ml/model/forecast_heads.py`).
- **Current canonical checkpoint** (`python-ml/weights/world_model_v1.pt`,
  603KB, `artifact_version kairos.world-model.v1.phase38-stage`): trained on
  the PRIMARY in-distribution split (per-day first-80% train / last-20% val,
  joined ≈10,589 train / 2,649 val windows), 5 epochs, chunk length 64,
  AdamW lr 1e-3 with **no weight decay and no LR schedule**, loss weights
  dynamics 0.5 / infiltration 3.0 / stage 3.0 with focal alpha 0.75, seed
  42, **checkpoint selected by validation loss** (best epoch 1,
  val_loss 3.915), followed by the frozen-backbone Phase 38 stage-head
  fine-tune (stage observed-macro 0.0667 → 0.3302 as recorded; infiltration
  probabilities provably unchanged, max delta 0.0). The losing Phase 32
  encoder (flat, F1 0.0) and loss-grid variants are reproducible via
  `python-ml/training/run_phase32_complete.py`; the pre-Phase-63 archive is
  kept at `python-ml/weights/world_model_v1_pretune_baseline_loss.pt`.
- **Phase 63 retraining attempt (NOT promoted):** same proven recipe, 6
  epochs, checkpoint selected by validation F1 instead of loss
  (`python-ml/training/run_phase63_retrain.py`, full trajectory in
  `results/phase63_retrain.json`). Added dropout/weight-decay/cosine
  schedules and aggressive loss rebalancing were all trialed first and
  rejected by evidence (each accelerated infiltration-head collapse).

## Benchmark Results

Source: `results/benchmark_table.csv` (threshold 0.5 throughout).

| Model | Split | F1 | Precision | Recall | FPR | AUC-ROC | Stage macro-F1 | Early-warning lead time |
|---|---|---|---|---|---|---|---|---|
| Logistic Regression (frozen `baseline-v1`) | In-distribution (identical 10,589/2,649 windows) | 0.7097 | 0.6535 | 0.7765 | 0.2578 | — | 0.4983 | N/A (non-temporal) |
| World Model (canonical checkpoint) | In-distribution (same windows) | 0.3454 | 0.5027 | 0.2738 | 0.1694 | 0.5813 | 0.0335 pre-finetune; 0.244 post-Phase-38 | 120s on both eligible validation attacks (Phase 33: partial — threshold crossed, no material near-onset rise) |
| World Model (Phase 63 F1-selection attempt, NOT promoted) | In-distribution (same windows) | 0.3132 | 0.4989 | 0.2283 | 0.1424 | 0.5843 | 0.2397 | — |
| World Model (canonical checkpoint) | Cross-day whole-day-03-02 stress test (different methodology) | 0.1489 | 0.1334 | 0.1684 | 0.1977 | 0.4714 | 0.0386 | — |
| World Model (CTU-13 zero-shot) | Pending Phases 58–60 — no run yet | — | — | — | — | — | — | — |

Stated plainly: **the world model trails the baseline on in-distribution F1
(0.3454 vs. 0.7097), and Phase 63's genuine retraining attempt did not close
the gap** (F1-selection picked a lower-FPR operating point but regressed raw
F1 to 0.3132, so the canonical checkpoint was kept). The one-line rationale:
validation loss anti-correlates with F1 on this task because the
dynamics-MSE term (~95% of the joint loss at init) dominates checkpoint
selection, and the infiltration head's probability mass collapses below the
0.5 threshold with further training while ranking quality (AUC ≈ 0.55–0.60)
barely moves. The temporal architecture's value therefore rests on
early-warning rollout, stage mapping, and explainability — not raw F1
superiority. The cross-day row uses a different, harder methodology
(unseen-C2 whole-day generalization) and must not be compared directly
against the in-distribution rows.

## Explainability

- **Attention visualization:** causal Transformer attention is extracted over
  a real 64-window pre-attack validation context by
  `python-ml/explain/attention_viz.py` (canonical implementation;
  `training/run_phase39_attention.py` is a thin runner). Verified live:
  shape [2 layers, 1 batch, 4 heads, 64, 64], zero future (non-causal) mass,
  row-sum error 1.2e-07. Outputs: `results/phase39_attention_heatmap.png`,
  `results/phase39_attention_summary.json`, and the tracked
  `results/phase39_attention_weights.pt`.
- **SHAP surrogate:** ExtraTrees regressor (100 trees, max depth 18) trained
  on causal forecast-history features, saved at
  `python-ml/weights/shap_surrogate_v1.joblib` (~28MB, tracked). Fidelity on
  its seeded teacher-output holdout (10,555 train / 2,639 val rows, 1,289
  features): **R2 0.9777**, Pearson 0.9894, MAE 0.00934, TreeSHAP additivity
  error ~1.3e-15. This measures surrogate-to-teacher fidelity only — not
  attack-detection or generalization performance.
- **Explanation JSON schema** (every `/predict` response):
  `{probability, predicted_stage, top_5_features[{feature, value,
  shap_value}], attention_summary}` plus `rollout`, `surrogate`, `latency_ms`,
  and `artifact_version: kairos.prediction.v1`.
- **Latency (real end-to-end figures):** TreeSHAP attribution + JSON
  construction median 108.2ms / p95 110.3ms / max 111.3ms (30 runs, target
  <2s — passes); live HTTP `POST /predict` on a real 8-window contract
  149.9ms total; live full-chain `/forecast/upload` 0.28–0.43s. If the
  surrogate file is missing or corrupt, `/predict` returns a clean HTTP 503
  (`explainability service unavailable`), never a 500.

## MITRE ATT&CK Stage Mapping

Per the Phase 37 decision (`retain_six_class_external_schema_no_merge` —
no stages merged, no new labels sourced), the six-class schema is retained
end to end, but only three stages have real training support in the
selected CIC-IDS2018 days:

- **Supported:** INITIAL_ACCESS, COMMAND_AND_CONTROL, IMPACT (live
  per-class F1 ≈ 0.56 / 0.42 / 0.48 on the in-distribution split).
- **Explicitly unsupported — do not present as working:**
  RECONNAISSANCE, LATERAL_MOVEMENT, and EXFILTRATION have zero examples in
  the selected contracts (F1 0.0 with zero support), so no validated
  performance may be claimed for them. The demo must identify this coverage
  limitation rather than imply full six-stage capability.

## Offline Mode and Gemini Narrative Mode

Two separate operating modes:

- **Offline-local (default).** Deterministic template narrative, no network
  call of any kind. Active unless *both* gating conditions below hold — and
  it is the automatic fallback (`offline-local-fallback`) if Gemini throws.
  Verified via the network-disabled full-stack test: real CSV upload
  through Java → Python → narrative → UI with zero errors and zero external
  calls (service logs contain no Gemini/Google API references).
- **Gemini-enhanced (optional opt-in).** Requires explicit `ONLINE_MODE=true`
  **and** an API key (`GEMINI_API_KEY` primary, `GOOGLE_API_KEY` legacy
  fallback; optional `GEMINI_MODEL`, default `gemini-flash-latest`). With a
  key present but `ONLINE_MODE` unset/false, the system stays offline. With
  no key, Gemini is never invoked (unit-tested: offline-by-default and
  failure-fallback cases pass). Gemini output is capped, plain-text-only,
  and instructed to use only facts present in the prediction JSON.

## Known Limitations

- **Baseline gap is open:** world-model in-distribution F1 0.3454 vs.
  frozen baseline 0.7097 on identical windows; Phase 63 attempt reached
  0.3132 and was not promoted. See Benchmark Results for the rationale.
- **Three MITRE stages unsupported:** Reconnaissance, Lateral Movement,
  Exfiltration have no training examples; no performance claimed.
- **CTU-13 zero-shot (Phases 58–60) not run:** no generalization numbers
  exist; Scenario 6 must not be reused for it.
- **Phase 33 is PARTIAL:** K=3 crosses the alert threshold 120s before
  onset on both eligible attacks, but the probability-rise criterion did
  not pass — early alerting, not a calibrated rising-risk trajectory.
- **Cross-day generalization is weak:** F1 0.1489 on the whole-day-03-02
  stress test (unseen C2 dynamics), tracked separately by design.
- **Threshold dependence:** reported F1 values use the fixed 0.5 decision
  threshold retained for comparability; lower thresholds raise F1 at steep
  FPR cost (e.g. 0.55 F1 at FPR 0.97 for threshold 0.3).

## Roadmap — Live-Capture and Active-Probe Extension (Phases 66–78)

> The phases below extend KAIROS from static file analysis (PCAP/CSV upload)
> to live network capture and, optionally, authorized active probing. This is
> a distinct, higher-risk capability tier. Live passive capture and active
> probing are NOT part of the verified, complete static pipeline described
> above — they are planned/in-progress work, gated behind explicit
> authorization, and must only be used on networks and hosts you own or are
> explicitly authorized to test. Active probing in particular carries legal
> responsibility resting entirely with the operator.

| Phase | Deliverable | Exit Criterion |
|---|---|---|
| 66 | Live-capture architecture and threat/safety model | API contracts, scope policy, retention policy, interface lifecycle documented |
| 67 | C++ interface enumeration and passive capture | Lists interfaces; captures a bounded local session with BPF filter and packet/drop counters |
| 68 | C++ live feature-window emitter | Emits the existing packet and flow feature schema every 10 seconds from live packets |
| 69 | Java JNI live-session bridge | Java starts/stops C++ capture and receives validated window events |
| 70 | Java target resolver and consent gate | URL/IP validation, DNS pinning, allowlist/lab policy, audit session record |
| 71 | Java sequence adapter | Live windows convert into kairos.sequence.v1 and pass schema validation |
| 72 | Python live inference and drift guard | Same model accepts live sequence windows and emits score/stage/XAI plus quality state |
| 73 | React live dashboard | Start/stop controls, live timeline, counters, stage/XAI panel |
| 74 | Streaming transport | WebSocket/SSE live updates without full-page polling |
| 75 | Authorized probe-and-observe mode | Conservative, explicitly gated discovery with an auditable safe profile |
| 76 | Offline and safety regression tests | Passive mode works with network disabled after traffic generation; active mode requires explicit authorization flag |
| 77 | Performance and packet-loss validation | Measured throughput, drop-rate behaviour, bounded memory, capture backpressure tested |
| 78 | Demo scenario and docs | Local Docker/lab attack simulation, evidence screenshots, scope/limitations documentation |

Status: not yet started — none of Phases 66–78 has begun, and no capability
from this table is working. Do not describe any capability from this table
as working until its own phase-specific exit criterion has been met and
independently verified.

## Reproducibility

All commands below were verified live (Python suite 12/12, Java suite 20
tests / 0 failures, checkpoint load test `LOAD TEST PASS`, offline upload
matrix HTTP 200 with `offline-local` narrative):

```bash
# 1. Reload the canonical checkpoint + rollout load test
python-ml/venv/bin/python python-ml/training/load_test_checkpoint.py

# 2. Reproduce the identical-split baseline (frozen logic; rewrites
#    results/baseline_metrics_indist.json + weights — restore with
#    `git checkout -- results python-ml/weights` afterwards if unwanted)
python-ml/venv/bin/python python-ml/training/run_phase32_baseline_indist.py

# 3. Reproduce the Phase 63 trajectory + comparison (promotes nothing;
#    restores the canonical checkpoint automatically)
python-ml/venv/bin/python python-ml/training/run_phase63_retrain.py

# 4. Regenerate attention + surrogate artifacts
python-ml/venv/bin/python python-ml/explain/attention_viz.py
python-ml/venv/bin/python python-ml/training/run_phase40_43_explainability.py

# 5. Rerun the offline demo (see Quick Start), then the test suites
cd python-ml && ./venv/bin/python -m unittest tests.test_app tests.test_explainability tests.test_phase32_metrics
cd ../java-engine && ./mvnw -o test
cd ../react-ui && npm run build
```

The benchmark table (`results/benchmark_table.csv`) is committed; its rows
trace to `results/baseline_metrics_indist.json` (baseline),
`results/phase32_completed.json` + live evaluation (canonical world model),
`results/phase63_retrain.json` (attempt row), and the cross-day live
evaluation. Tracked weights follow the size-gated policy in
`.gitignore`/`python-ml/weights/README.md` (final artifacts committed;
regenerable intermediates documented, not committed).

## Contribution / License / Acknowledgments

No license file is currently committed; contributions follow the existing
per-layer conventions (typed, tested, offline-first) and must keep
`git diff baseline-v1 -- python-ml/baseline/` empty. Data acknowledgments:
CSE-CIC-IDS2018 (Registry of Open Data on AWS) for primary training data;
the Stratosphere Laboratory CTU-13 dataset for the Scenario 6 development
capture (CC-BY). Results, manifests, and phase-status records in
`results/` and `docs/phase-status.md` are the authoritative references —
this README summarizes them and must not be cited over them where they
differ.
