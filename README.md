# KAIROS — Network Attack World Model

KAIROS learns network-traffic state-transition dynamics — P(S_t+1 | S_t), the
probability distribution over future network states given the current state —
and forecasts attacker progression before compromise using K-step
autoregressive rollout of the learned dynamics, instead of classifying the
present. Current real scope: the static offline pipeline (file upload →
windowing → graph build → world-model inference → explanation → analyst
narrative → dashboard) is complete and verified end-to-end (Phases 0–63),
offline by default, with the baseline F1 gap honestly open (see Benchmark
Results). The passive live-capture tier (Phases 66–74, 76–77) is implemented
and verified on loopback (see Roadmap table and `docs/phase-status.md`);
authorized active probing (Phase 75) and the demo scenario (Phase 78) are
not started — Stop Gate 1 was never reached, so no active-probe code path
exists anywhere.

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
capture and no active probing. The implemented passive live-capture tier
(Phases 66–74, 76–77) captures packet headers on loopback/allowlisted local
interfaces only, under a consent gate with a default-empty allowlist, and
performs no active probing of any kind. Any future active-probe capability
(Phase 75, not started — Stop Gate 1 never reached) must only be used on
networks and hosts you own or are explicitly authorized to test. Active
probing in particular carries legal responsibility resting entirely with
the operator. The project maintainers are not responsible for misuse.

## Architecture Overview

Four-layer stack, one language per layer, plus an optional narrative layer.
A per-flow classifier sees each flow in isolation and can only react to
attacks already in progress; KAIROS instead models how network states evolve
and simulates future trajectories to score whether they converge toward
compromise — which is also why flow-level aggregates (right lens for
volumetric phenomena) and packet-level timing/sequencing features (right lens
for low-and-slow scans) are both required.

- **C++ (cpp-engine): packet-level feature extraction.** Parses PCAP/PCAPNG,
  aggregates flows, reconstructs logical payload lengths from retained
  headers, and runs a capture-level port-scan signature detector whose evidence is attached to matching-source windows (sequential
  vs. randomized). Exposed to Java via JNI (`libkairos_native.so`); a full
  3.28 GB scan completed without errors (17,412,467 supported packets,
  1,976,965 flow records). Live tier: `LiveCaptureSession` (real interface
  enumeration, bounded capture with dual autostop, backend-accounted
  packet/drop counters) and `LiveFeatureEmitter` (10s windows in the same
  flow schema); ctest 3/3.
- **Java (java-engine): orchestration engine and REST API.** CSV ingestion
  (header normalization, NaN/Infinity sanitization, timeline stage labels),
  10-second windowing, host-flow graph construction, the versioned
  `kairos.sequence.v1` JSON contract, the typed `PythonMlClient` REST
  client, narrative services, and the public `POST /forecast` and
  `POST /forecast/upload` endpoints (Spring Boot). Live tier
  (`com.networkwm.live`): `LiveSessionService` lifecycle supervisor,
  `ProcessCaptureBackend`, `ConsentGateService` (default-empty allowlist,
  DNS pinning, audit log), `LiveSequenceAdapter`, `LivePredictionService`,
  and `LiveCaptureController` (`/live` sessions/interfaces/windows/purge
  plus SSE event stream).
- **Python (python-ml): world-model inference service (Flask).** GraphSAGE
  encoder → causal Transformer dynamics → K-step rollout → infiltration
  and stage forecast heads → SHAP/attention explanation. Internal
  `POST /predict` endpoint (never called by the browser). Live tier: the
  same checkpoint serves live windows with no architecture fork; every
  response carries a reactive drift-guard `quality`
  (`ok`/`degraded`/`unreliable`, `live_drift.py`, reference
  `results/live_drift_reference.npz`).
- **React (react-ui): dashboard.** Upload form, probability timeline,
  flagged flows table, stage annotations, narrative panel with mode badge,
  and a sample-attack quick-load button. Calls Java at
  `POST /forecast/upload`. Live tier: `LiveDashboard` (start/stop on real
  `/live` sessions, SSE-driven counters/timeline/stage) with a prominent
  `QualityBadge`.
- **Narrative layer (Java, optional Gemini):** the **default is the
  offline-local rule-based generator** — deterministic templating, no
  network call. Gemini enhancement requires **both** `ONLINE_MODE=true`
  **and** an API key (`GEMINI_API_KEY` primary, `GOOGLE_API_KEY` accepted
  as a legacy fallback); any Gemini failure falls back to a local
  narrative. Gemini supplements and never replaces SHAP/attention output.

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
      |                        read CSV, stream into 10s time windows
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
      |                        optional: Gemini API (Google Gen AI Java SDK,
      |                        explicit opt-in only)
      |                        structured output -> natural-language
      |                        SOC analyst briefing (human-facing layer)
      v
[React Dashboard]  -- react-ui
      +-- Probability Timeline   (time series + alert threshold line)
      +-- Flagged Flows Table    (top-N per alerted window, from SHAP)
      +-- Stage Annotations      (color-coded by predicted MITRE stage)
      +-- Narrative Panel        (local or Gemini briefing, mode-indicated)
```

Inter-service calls: Java→C++ via JNI (`CppBridge` loading the native
shared library); Java→Python via `PythonMlClient` (OkHttp) to the private
`POST /predict`; browser→Java at `POST /forecast` / `POST /forecast/upload`.
Endpoint-free CIC CSVs use an explicit `__network__` vector-mode node; host
identities are never invented.

## Quick Start (Offline Demo)

Real, tested commands only — this exact sequence was verified live (full
stack, network disabled, real CSV upload → narrative → JSON response, zero
errors, zero external calls; sample upload answered in 0.28–0.43s; cold
start ≈ Java boot ~1.4s + first inference ~0.3s, well under 30s).

Environment setup per layer (each command runs from the repo root):

```bash
# C++: C++17 compiler + CMake — builds libkairos_native.so
cmake -S cpp-engine -B cpp-engine/cmake-build-local \
  && cmake --build cpp-engine/cmake-build-local

# Java: JDK 17+, tested on JDK 21 — Maven via checked-in wrapper
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
(cd java-engine && ./mvnw -o test)   # 47 tests, 0 failures (1 pre-existing skip)

# Python: venv + pinned CPU-only requirements (tested on Python 3.13)
python3 -m venv python-ml/venv \
  && python-ml/venv/bin/pip install -r python-ml/requirements.txt
# Pins: torch==2.14.0+cpu, torch-geometric==2.8.0.post1, Flask==3.1.3,
# shap==0.52.0, scikit-learn==1.9.1

# React: Node 24.21.0 (.node-version), React 18, react-scripts ^5.0.1
(cd react-ui && npm ci && npm run build)   # verified: compiles successfully

# Offline env: ships ONLINE_MODE=false with an empty key
cp .env.example .env
# Ensure neither GEMINI_API_KEY nor GOOGLE_API_KEY is set.
```

Run the offline demo end to end. The documented command builds and explicitly loads `libkairos_native.so`, so both CSV and real PCAP/PCAPNG uploads use the same path:

```bash
./kairos.sh
```

Manual equivalent (three terminals, repo root):

```bash
# Terminal 1 — Python ML service (default port 5000)
ONLINE_MODE=false python-ml/venv/bin/python python-ml/app.py

# Terminal 2 — Java engine (default port 8080)
export JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
(cd java-engine && ONLINE_MODE=false ./mvnw spring-boot:run \
  -Dspring-boot.run.jvmArguments="-Dkairos.native.library=$PWD/../cpp-engine/build/libkairos_native.so")

# Terminal 3 — full-chain upload (verified live)
curl -X POST http://127.0.0.1:8080/forecast/upload \
  -F "file=@react-ui/public/sample-attack.csv;type=text/csv" \
  -F "rolloutSteps=3"
```

Expected (verified live): HTTP 200 with
`{artifactVersion, prediction, narrative}` — probability ≈ 0.59, stage
`COMMAND_AND_CONTROL`, `narrative.mode` = `offline-local`. The React
dashboard posts to the same `/forecast/upload` endpoint via its "Load
sample attack" button. The first dependency installation requires internet
access; runtime inference and the complete demo work offline.

## Datasets

- **CSE-CIC-IDS2018 (primary training data)** — exactly four days are used:
  2018-02-14, 2018-02-15, 2018-02-28, and 2018-03-02. Each day is capped to
  200,000 flows with seed 42 via `python-ml/pipeline/downsample_flows.py`
  (stratified, class-ratio-preserving; see
  `data/cic_ids_2018_manifest.yaml`), then exported to 10-second graph
  contracts (`data/processed/graph_contracts/day14/day15/day28/day0302.json`):
  3,253 + 3,413 + 3,393 + 3,143 = 13,202 ordered windows. Raw and processed
  data directories are gitignored (local `data/` ≈ 4.7G); manifests are
  tracked. Download and verify the slice with
  `./scripts/download_cic_ids_2018.sh`.
- **CTU-13 Scenario 6 / DonBot (capture 47)** — reserved for packet-level
  feature development ONLY: the official privacy-preserving truncated
  complete-traffic capture (602,748,112-byte `.bz2`, SHA-256-verified;
  38,705,338 packets, 7749.87s / 02:09:10, headers retained, payload
  removed) at `data/raw/ctu13_pcap/scenario06_donbot/`, documented in
  `data/ctu13_scenario6_manifest.yaml`. **Explicitly excluded from any
  zero-shot generalization test** — the Phases 58–60 test must use a
  different CTU-13 scenario to preserve the leakage-free claim. Download
  with `./scripts/download_ctu13_scenario6.sh`.

## Model Architecture and Training

- **GNN encoder:** edge-aware GraphSAGE, 2 layers, hidden dim 64, state dim
  64, attention pooling, dropout 0.1
  (`python-ml/model/encoder_gnn.py`). No GAT variant exists in code.
- **Temporal dynamics:** causal Transformer, 2 layers, 4 heads, sinusoidal
  positional encoding, dropout 0.1
  (`python-ml/model/dynamics_transformer.py`). No LSTM variant exists.
- **Rollout:** K-step autoregressive feeding of predicted states; K=3
  selected (K=3/5/10 ablated; 10s windows won the 5s/10s/30s ablation).
  Services accept rollout steps 1–10.
- **Forecast heads:** sigmoid infiltration-probability head and 6-class
  softmax MITRE-stage head sharing the rolled-forward latents; focal
  classification losses plus dynamics MSE, gradient clipping
  (`python-ml/model/forecast_heads.py`).
- **Current canonical checkpoint** (`python-ml/weights/world_model_v1.pt`,
  603KB, `artifact_version kairos.world-model.v1.phase38-stage`): trained
  on the PRIMARY in-distribution split (per-day first-80% train / last-20%
  val, joined ≈10,589 train / 2,649 val windows), 5 epochs, chunk length
  64, AdamW lr 1e-3 with **no weight decay and no LR schedule**, loss
  weights dynamics 0.5 / infiltration 3.0 / stage 3.0, focal alpha 0.75,
  seed 42, **checkpoint selected by validation loss** (best epoch 1,
  val_loss 3.915), followed by the frozen-backbone Phase 38 stage-head
  fine-tune (stage observed-macro 0.0667 → 0.3302 as recorded;
  infiltration probabilities provably unchanged, max delta 0.0). Full
  settings in `python-ml/configs/train_config.yaml`. The pre-Phase-63
  archive is kept at
  `python-ml/weights/world_model_v1_pretune_baseline_loss.pt`; losing Phase
  32 variants (flat encoder, loss-grid checkpoints) are reproducible via
  `python-ml/training/run_phase32_complete.py` and recorded in
  `results/phase32_completed.json`.
- **Phase 63 retraining attempt (NOT promoted):** same proven recipe, 6
  epochs, checkpoint selected by validation F1 instead of loss
  (`python-ml/training/run_phase63_retrain.py`, full trajectory in
  `results/phase63_retrain.json`). Added dropout/weight-decay/cosine
  schedules and aggressive loss rebalancing were trialed first and rejected
  by evidence — each accelerated infiltration-head collapse.

## Benchmark Results

Canonical source: `results/benchmark_table.json`, generated by
`python-ml/training/generate_benchmark_table.py`. Both primary models receive
the same backward-only temporal features, predict the same future label, and
use the same per-day final-20% untouched test windows. Thresholds are selected
from leave-one-source-day-out predictions inside development data only.

| Model | Forecast task | F1 | Precision | Recall | FPR | ROC-AUC | Observed-stage macro-F1 |
|---|---|---:|---:|---:|---:|---:|---:|
| Logistic Regression | 60s future window | 0.6770 | 0.6331 | 0.7275 | 0.2640 | 0.7923 | 0.9990 |
| **ExtraTrees temporal forecasting component (separate from GNN-Transformer)** | **60s future window** | **0.7390** | **0.6696** | **0.8245** | **0.2548** | **0.8604** | **1.0000** |
| GNN-Transformer transition core | Legacy next-window diagnostic | 0.3545 | 0.5027 | 0.2738 | 0.1694 | 0.5813 | 0.067 observed / 0.0335 six-class |
| CTU-13 Scenario 12 LR | S6 train, S11 validate, S12 zero-shot, 10s | 0.3683 | 0.2695 | 0.5816 | 0.7410 | 0.3136 | N/A |
| CTU-13 Scenario 12 KAIROS | S6 train, S11 validate, S12 zero-shot, 10s | 0.4746 | 0.3281 | 0.8571 | 0.8249 | 0.4579 | N/A |

On the PS-aligned 60-second CIC forecast, a separate temporal-feature
classifier (ExtraTrees) improves over the same-feature logistic baseline by
**+0.0620 F1, +0.0365 precision, +0.0971 recall, -0.0092 FPR, and +0.0681
ROC-AUC**. The older comparison was invalid as a headline result because
logistic regression classified the current window while the transition head
predicted a future window. Stated plainly (Case B finding): the core
world-model architecture (GNN-Transformer) currently underperforms the
baseline on raw F1 (0.3545 vs 0.6770); a separate temporal-feature classifier
(ExtraTrees) shows improvement (+0.0620 F1) but runs as a separate
discriminative head outside the GNN-Transformer rollout path — it consumes
no rollout, latent, or attention features, so this is not evidence that the
world model's learned temporal dynamics beat the baseline. The Phase 63
retraining attempt (F1-selected checkpoint, raw F1 0.3132 vs canonical
0.3454) was honestly negative, so the canonical checkpoint was kept.
Two-component forecasting architecture (honest): the GNN-Transformer learns `P(S_t+1|S_t)` for
K-step rollout (120s early-alert) and causal attention; the calibrated
infiltration probability comes from the temporal forecast head on the same
backward-only temporal summaries (ExtraTrees 150 trees, seed 42). History
matters: same-learner temporal-vs-static ablation at fixed 0.5
(`results/temporal_ablation.json`, 50 trees for speed) gives history-6
F1 0.6871/AUC 0.8594 vs current-only 0.6790/0.8466 (+0.0081 F1, +0.0128 AUC);
the full 150-tree calibrated benchmark shows the larger +0.0620/+0.0681 above.
Caveats: thresholds development-calibrated under prevalence shift (dev 7.7%
vs test 38.5%; LR 0.0148, KAIROS 0.1031 at h6); stage 0.999→1.0 reflects
near-trivial CIC separability, not general stage reasoning.

The external CTU row is deliberately retained: Scenario 6 is development,
Scenario 11 is external validation, and Scenario 12 is untouched until final
scoring. At 10 seconds the KAIROS temporal head improves F1 (+0.1062), precision (+0.0586), and
recall (+0.2755) over LR, but FPR worsens by 0.0839 and ranking is
below-random (AUC 0.4579). This below-random AUC was investigated as a
possible label-polarity or score-direction bug and confirmed genuine: the
positive class (From-Botnet windows) is encoded by one shared loader for all
three scenarios, both models score `P(malicious)` via the same
`predict_proba[:, 1]` path, and the identical code yields above-random
validation AUCs (5/6 configs, e.g. LR h3 0.749, KAIROS h3 0.801) — so the
model's predictions are anti-correlated with ground truth on this specific
unseen botnet family (NSIS.ay), suggesting the learned features do not
transfer to this attack pattern. Longer horizons regress on F1 and are
disclosed: h3 F1 −0.1203, h6 F1 −0.0324 (h = horizon in 10s windows, i.e.
30s/60s ahead; see `docs/phase-status.md`). This is limited generalization, not a claim that domain shift is solved. Official CTU labels do not contain
MITRE stages, so no stage metric is fabricated.

## Explainability

- **Attention visualization:** causal Transformer attention extracted over a
  real 64-window pre-attack validation context by
  `python-ml/explain/attention_viz.py` (canonical implementation;
  `training/run_phase39_attention.py` is a thin runner). Verified live:
  shape [2 layers, 1 batch, 4 heads, 64, 64], zero future (non-causal)
  mass, row-sum error 1.2e-07. Outputs:
  `results/phase39_attention_heatmap.png`,
  `results/phase39_attention_summary.json`, and the tracked
  `results/phase39_attention_weights.pt` (148KB).
- **SHAP surrogate:** ExtraTrees regressor (100 trees, max depth 18) trained
  on causal forecast-history features, saved at
  `python-ml/weights/shap_surrogate_v1.joblib` (~28MB, tracked), 1,289
  features. Fidelity on its seeded teacher-output holdout (10,555 train /
  2,639 val rows): **R2 0.9777**, Pearson 0.9894, MAE 0.00934, TreeSHAP
  additivity error ~1.3e-15. This measures surrogate-to-teacher fidelity
  only — not attack-detection or generalization performance.
- **Explanation JSON schema** (every `/predict` response):
  `{probability, predicted_stage, top_5_features[{feature, value,
  shap_value}], attention_summary}` plus `rollout`, `surrogate`,
  `latency_ms`, and `artifact_version: kairos.prediction.v1`.
- **Latency (real end-to-end figures, not isolated component timing):**
  TreeSHAP attribution + JSON construction median 108.2ms / p95 110.3ms /
  max 111.3ms (30 runs, target <2s — passes); live HTTP `POST /predict` on
  a real 8-window contract 149.9ms total; live full-chain
  `/forecast/upload` 0.28–0.43s. If the surrogate file is missing or
  corrupt, `/predict` returns a clean HTTP 503 (`explainability service
  unavailable`), never a 500.

## MITRE ATT&CK Stage Mapping

Per the Phase 37 decision (`retain_six_class_external_schema_no_merge` — no
stages merged, no new labels sourced), the six-class schema is retained end
to end, but only three stages have real training support in the selected
CIC-IDS2018 days. PS-26153 mandates Reconnaissance, Initial Access, Lateral
Movement, Command & Control, Exfiltration (IMPACT is CIC-extra, not PS-listed):

| PS-mandated stage | KAIROS class | Support in selected days | Status |
|---|---|---:|---|
| Reconnaissance | RECONNAISSANCE | 0 | **Unsupported — masked, never predicted** |
| Initial Access | INITIAL_ACCESS | 697–699 val | Supported |
| Lateral Movement | LATERAL_MOVEMENT | 0 | **Unsupported — masked, never predicted** |
| Command & Control | COMMAND_AND_CONTROL | 113–114 val | Supported |
| Exfiltration | EXFILTRATION | 0 | **Unsupported — masked, never predicted** |
| (CIC-extra) | IMPACT | 206–207 val | Supported (DoS GoldenEye/Slowloris) |

- **Supported:** INITIAL_ACCESS, COMMAND_AND_CONTROL, IMPACT.
  Runtime enforces this via `_supported_stage_index` (`python-ml/app.py`):
  unsupported argmax entries are masked, so `predicted_stage` and
  `predicted_stage_if_attack` can never be Recon/Lateral/Exfil.
- **Explicitly unsupported — do not present as working:**
  RECONNAISSANCE, LATERAL_MOVEMENT, and EXFILTRATION have zero examples in
  the selected contracts (F1 0.0 with zero support), so no validated
  performance may be claimed for them. The demo must identify this coverage
  limitation rather than imply full five-stage PS capability. Only 2/5
  PS-mandated stages are demonstrable.

## Offline Mode and Gemini Narrative Mode

Two separate operating modes:

- **Offline-local (default).** Deterministic template narrative, no network
  call of any kind. Active unless *both* Gemini conditions below hold — and
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

Configure via a local `.env` (never committed; see `.env.example`):

```
ONLINE_MODE=false
GEMINI_API_KEY=
```

The Java service owns ingestion, windowing, stage-label attachment, and
graph construction; Python owns training and inference on the versioned
contract. The browser calls Java at `POST /forecast`; Java calls the
private Python endpoint at `POST /predict`.

## Known Limitations

- **Core world-model benchmark — most consequential open gap (Item 15):**
  The GNN-Transformer core (F1 0.3545) currently trails the logistic
  regression baseline (F1 0.6770) on the in-distribution split. A separate
  ExtraTrees classifier shows improvement (+0.0620 F1) but is
  architecturally independent of the world model's rollout/latent states
  (Case B, confirmed: it consumes no rollout, latent, or attention
  features) — do not read that second model's result as validating the
  core architecture. Closing this requires further training investment on
  the core objective, not reframing.
- **Three MITRE stages unsupported (Item 4):** only 2 of the 5 PS-named
  stages (Initial Access, Command & Control) plus one CIC-specific extra
  (Impact) have real training support from the selected datasets;
  Reconnaissance, Lateral Movement, and Exfiltration are structurally
  unsupported and masked in output (`_supported_stage_index`), never
  predicted. Closing this requires additional labeled data covering those
  stages, not a code fix.
- **Cross-domain generalization (Item 8):** CTU-13 Scenario 12 zero-shot
  testing shows genuine, bug-checked anti-correlation (AUC 0.4579, below
  0.5) against the NSIS.ay botnet family specifically — the model does
  not currently transfer to this specific unseen attack family — with FPR
  increasing (0.7410→0.8249) and longer rollout horizons (h3/h6)
  regressing further (see phase-status). Closing this requires
  cross-family training data or domain-adaptation work, not tuning.
- **Rollout calibration status (Item 3):** the K-step autoregressive
  rollout is genuine and verified (not a static classifier), but its
  output is currently presented as a diagnostic transition-probability
  signal rather than a calibrated primary forecast (K=3 crosses the alert
  threshold 120s before onset on both eligible validation attacks, but
  the probability-rise criterion did not pass — early alerting, not a
  calibrated rising-risk trajectory; rollout `max_probability` is a
  threshold-cross signal). Promoting it to the primary forecast would
  require calibration evidence (e.g., reliability diagrams, Brier score
  validation) not yet produced.
- **Cross-day generalization is weak:** F1 0.1489 on the whole-day-03-02
  stress test (unseen C2 dynamics), tracked separately by design.
- **Threshold dependence:** legacy rows use fixed 0.5; v2 primary rows use
  development-calibrated thresholds (LR 0.0148, KAIROS 0.1031 at h6) under
  prevalence shift — same protocol for both, absolute values sensitive.
- **Explainability scope:** SHAP = surrogate→teacher fidelity (R2 0.9777),
  not detection; attention = temporal attribution over prior latents, not
  causal proof or raw-feature attribution. Both supplement, never replace,
  analyst verification.
- **Topology scope:** endpoint IPs preserved as node IDs when present, excluded
  from numeric features by design; endpoint-free CIC uses `__network__`
  fallback. PCAP upload bounded at 2M packets; the upload path fuses
  capture-derived flow summaries (`flow.*`) with native packet features
  (`packet.*`) from the same capture via `WindowingService.windowAndMerge()`
  5-tuple matching (verified by a real-extractor upload test, both levels
  non-zero, unobservable fields absent rather than zero-filled). CSV-only
  uploads remain flow-level by necessity (endpoint-free, no packet source);
  packet-level evidence is then marked explicitly unavailable in the UI, and
  packet-to-CIC projection lists every zero-filled model input in
  `inputProjectionDetail.unavailable_model_features`.
- **Live tier verified on loopback only:** passive capture, windowing,
  inference, and SSE streaming are proven against locally generated
  loopback traffic (see `results/live_capture_performance.md`,
  `results/phase76_regression.md`); behavior on busy non-loopback
  interfaces is unmeasured. The drift guard flags 9/400 real day0302
  windows as degraded/unreliable (see `results/live_drift_calibration.json`) —
  expected tail behavior, not a defect.
- **Active probing does not exist:** Phase 75 was not started (Stop Gate 1
  never reached); `mode` must be exactly `passive` and any other value is
  refused at the consent gate, session service, and REST boundary.

## Roadmap — Live-Capture and Active-Probe Extension (Phases 66–78)

Full project history first (Phases 0–65, summarized from
`docs/implementationplan.md` with actual completion status from the
audits), then the live-capture tier (66–78, passive half implemented).

### Static pipeline history (Phases 0–65)

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Monorepo skeleton + README (4-layer structure, manifests, .gitignore, arch diagram) | Complete |
| 1 | Environment setup across all layers (C++17, JDK 17+, Python venv + torch/geometric, Node/React, `.env.example`) | Complete (verified: JDK 21, Python 3.13, Node 24.21.0) |
| 2 | CIC-IDS2018 acquisition (02-14, 02-15, 02-28, 03-02; 13,202 windows) | Complete |
| 3 | CTU-13 Scenario 6 / DonBot truncated capture (dev-only) | Complete (excluded from zero-shot) |
| 4 | C++ packet-level feature extractor core | Complete (17.4M-packet scan, no errors) |
| 5 | C++ port-scan signature detector (sequential vs. randomized) | Complete |
| 6 | C++ unit tests + `libkairos_native.so` shared library | Complete |
| 7 | Java-to-C++ bridge (`CppBridge.java`, JNI round-trip) | Complete |
| 8 | Java flow CSV ingestion (header normalization, NaN/Inf sanitize, stage labels) | Complete |
| 9 | Java 10s windowing + host aggregation | Complete (10s won 5s/10s/30s) |
| 10 | Java graph construction (host-flow snapshots) | Complete |
| 11 | Java↔Python serialization contract (`kairos.sequence.v1`, JSON) | Complete |
| 12 | Python baseline feature flattening | Complete |
| 13 | Python time-based split + `StandardScaler` | Complete |
| 14 | Python multinomial logistic regression (6-class stage) | Complete |
| 15 | Python binary logistic regression (infiltration) | Complete |
| 16 | Baseline evaluation + freeze (`baseline-v1` tag; code must stay untouched) | Complete |
| 17 | GraphSAGE GNN encoder skeleton | Complete (no GAT in code) |
| 18 | Mean/attention pooling to fixed-size embedding | Complete |
| 19 | Encoder overfit sanity test (~50 windows, near-zero loss) | Complete |
| 20 | Variable-size graph batch pipeline | Complete |
| 21 | Temporal dynamics skeleton (Transformer, 2 layers, 4 heads) | Complete (no LSTM in code) |
| 22 | Teacher-forced next-state objective (MSE) | Complete |
| 23 | Dynamics training loop (checkpointing, grad clipping, day split) | Complete |
| 24 | Loss-curve verification | Complete (val diverges after epoch 1) |
| 25 | K-step autoregressive rollout | Complete (K=3 selected of 3/5/10) |
| 26 | Infiltration probability head (sigmoid) | Complete |
| 27 | MITRE stage head (6-class softmax) | Complete |
| 28 | Joint loss + focal class-imbalance handling (0.5/3/3, α=0.75) | Complete |
| 29 | Full end-to-end training run (in-distribution split) | Complete |
| 30 | Checkpoint + config logging (`world_model_v1.pt`) | Complete |
| 31 | Window-size ablation (5s/10s/30s) | Complete (10s wins; coverage-gap diagnosis) |
| 32 | K + GNN-vs-flat ablation | Complete (GNN F1 0.3454; flat 0.0) |
| 33 | Rollout proof-of-concept (120s early alert) | Partial (threshold crossed; no probability rise) |
| 34 | MITRE heuristic cross-check | Complete (weak agreement) |
| 35 | Per-class error analysis | Complete |
| 36 | Label audit | Complete (no ambiguous labels) |
| 37 | Stage-set decision (`retain_six_class_external_schema_no_merge`) | Complete |
| 38 | Stage-head-only fine-tune (frozen backbone) | Complete (observed-macro 0.0667→0.3302) |
| 39 | Causal attention extraction + heatmap | Complete ([2,1,4,64,64], causal) |
| 40 | SHAP surrogate (ExtraTrees, R2 0.9777) | Complete |
| 41 | TreeSHAP integration (additivity err ~1e-15) | Complete |
| 42 | Explanation JSON schema (`kairos.prediction.v1`) | Complete |
| 43 | Explainability latency check (<2s) | Complete (108ms median) |
| 44 | Flask `POST /predict` endpoint (clean 503 on missing surrogate) | Complete |
| 45 | Java `PythonMlClient` (real HTTP, typed parsing) | Complete |
| 46 | `ForecastController` (`/forecast`, `/forecast/upload`) | Complete |
| 47 | Local fallback narrative (offline default) | Complete |
| 48 | Gemini narrative service (key-gated) | Complete |
| 49 | Narrative mode toggle (`ONLINE_MODE` + key, local fallback) | Complete |
| 50 | Backend end-to-end integration test (MockMvc) | Complete |
| 51 | React app skeleton + upload wiring | Complete |
| 52 | Probability timeline chart | Complete |
| 53 | Flagged flows table (SHAP evidence) | Complete |
| 54 | Stage annotations overlay | Complete |
| 55 | Narrative panel (mode badge) | Complete |
| 56 | Offline compliance verification (network disabled, 0 errors) | Complete |
| 57 | Sample-attack quick-load button (<30s cold start) | Complete |
| 58 | Packet/flow adaptation (loss-aware CIC projection + CTU flow adapter) | Complete |
| 59 | CTU-13 zero-shot inference (S6 develop, S11 validate, S12 holdout) | Complete |
| 60 | CTU-13 metrics + generalization-gap analysis | Complete (gap remains documented) |
| 61 | Canonical benchmark table generation | Complete (task-aligned CIC + CTU external rows) |
| 62 | Documentation completion | Complete for implementation/status/judge brief + architecture/train-config staleness fixed; temporal ablation + PS-5 mapping disclosed (clean-clone still open, see 65) |
| 63 | Retraining attempt, Option A (redefined from demo video; F1-selection probe, canonical kept) | Complete — negative result, tag `phase63-complete` |
| 64 | Pitch deck | Not started |
| 65 | Clean-clone end-to-end reproducibility check | Partial (verified in-place, no clean-clone) |

### Live-capture and active-probe extension (Phases 66–78)

> The phases below extend KAIROS from static file analysis (PCAP/CSV
> upload) to live network capture and, optionally, authorized active
> probing. This is a distinct, higher-risk capability tier. The passive
> live-capture half (Phases 66–74, 76–77) is implemented and verified on
> loopback (see table statuses and `docs/phase-status.md`) — it is gated
> behind explicit authorization and must only be used on networks and
> hosts you own or are explicitly authorized to test. Active probing
> (Phase 75) is NOT implemented and must not be described as working;
> Stop Gate 1 was never reached, so no active-probe code path exists.
> Active probing in particular carries legal responsibility resting
> entirely with the operator.

| Phase | Deliverable | Status |
|---|---|---|
| 66 | Live-capture architecture and threat/safety model (`docs/live_capture_threat_model.md`) | Complete — API contracts, scope/retention policy, interface lifecycle, 8-row threat model documented |
| 67 | C++ interface enumeration and passive capture (`live_capture.hpp/cpp`) | Complete — 8 real interfaces enumerated; 5s bounded run captured 47 real loopback packets and self-stopped; packet-limit run self-stopped at 4 |
| 68 | C++ live feature-window emitter (`live_emitter.hpp/cpp`) | Complete — 32s capture → 211 packets → 4 windows, same flow schema, live-shaped window passes existing validator |
| 69 | Java live-session bridge (`com.networkwm.live`: supervisor + backend) | Complete — start→windows→stop, no orphaned backend after stop; real 5s `lo` capture with real counters |
| 70 | Java target resolver and consent gate | Complete — default-empty allowlist, DNS pinning, audit log; deny-path and allow-path tested |
| 71 | Java sequence adapter | Complete — live windows validate as `kairos.sequence.v1`; malformed input rejected |
| 72 | Python live inference and drift guard | Complete — same checkpoint serves live windows; reactive `ok`/`degraded`/`unreliable` quality |
| 73 | React live dashboard (`LiveDashboard`, `QualityBadge`) | Complete — real session start/stop, SSE counters/timeline/stage, prominent quality badge |
| 74 | Streaming transport | Complete — genuine SSE (`text/event-stream`, async, `data:` frames), persistent connection with disconnect handling |
| 75 | Authorized probe-and-observe mode | Not started — Stop Gate 1 never reached; no active-probe code exists |
| 76 | Offline and safety regression tests (`results/phase76_regression.md`) | Complete — netns-isolated passive capture works; active mode refused fresh 3/3 |
| 77 | Performance and packet-loss validation (`results/live_capture_performance.md`) | Complete — 55/204/785 pps zero-loss; 662,520-packet burst, 0 drops; flat 4116 kB RSS; backpressure verified |
| 78 | Demo scenario and docs | Not started |

> Note: Phases 64–65 in the table above (pitch deck, clean-clone check) are
> still open from the original 65-phase plan; Phases 66–78 below are a
> separate live-capture tier and do not depend on them. Neither Stop Gate
> confirmation occurred in this session (no Stop Gate 1 scope was agreed,
> so Phase 75 was correctly not implemented).

## Reproducibility

Exact commands, all verified live (Python suite 12/12 static + 3/3 drift
guard, Java suite 47 tests / 0 failures — 1 pre-existing skip, C++ ctest
3/3, checkpoint load test `LOAD TEST PASS`, offline upload matrix HTTP 200
with `offline-local` narrative):

```bash
# Reload the canonical checkpoint + rollout load test
python-ml/venv/bin/python python-ml/training/load_test_checkpoint.py

# Reproduce the identical-split baseline (frozen logic; rewrites the
# indist artifacts — restore with `git checkout -- results python-ml/weights`
# afterwards if unwanted)
python-ml/venv/bin/python python-ml/training/run_phase32_baseline_indist.py

# Reproduce the Phase 63 trajectory + comparison (promotes nothing;
# restores the canonical checkpoint automatically)
python-ml/venv/bin/python python-ml/training/run_phase63_retrain.py

# Regenerate attention + surrogate artifacts
python-ml/venv/bin/python python-ml/explain/attention_viz.py
python-ml/venv/bin/python python-ml/training/run_phase40_43_explainability.py

# Test suites + UI build (C++ live tests take ~40s: bounded captures)
cmake -S cpp-engine -B cpp-engine/cmake-build-local && cmake --build cpp-engine/cmake-build-local
(cd cpp-engine/cmake-build-local && ctest)   # 3/3 (static + live capture + live emitter)
cd python-ml && ./venv/bin/python -m unittest tests.test_app \
  tests.test_explainability tests.test_phase32_metrics tests.test_live_drift
cd ../java-engine && ./mvnw -o test
cd ../react-ui && npm run build

# Live-capture evidence (regenerate; results/ holds the measured output)
python-ml/venv/bin/python python-ml/pipeline/make_drift_reference.py

# Offline demo: see Quick Start above.
```

The benchmark table (`results/benchmark_table.csv`) is committed; its rows
trace to `results/baseline_metrics_indist.json` (baseline),
`results/phase32_completed.json` + live evaluation (canonical world model),
`results/phase63_retrain.json` (attempt row), and the cross-day live
evaluation. Tracked weights follow the size-gated policy in `.gitignore` /
`python-ml/weights/README.md` (final artifacts committed; regenerable
intermediates documented, not committed). `results/` and
`docs/phase-status.md` are authoritative — this README summarizes them and
must not be cited over them where they differ. Phase history lives in
`docs/implementationplan.md` (65-phase static-pipeline plan) and
`docs/phase-status.md` (measured results).

## Contribution / License / Acknowledgments

No license file is currently committed. Contributions follow the existing
per-layer conventions (typed, tested, offline-first) and must keep
`git diff baseline-v1 -- python-ml/baseline/` empty. Data acknowledgments:
CSE-CIC-IDS2018 (Registry of Open Data on AWS) for primary training data;
the Stratosphere Laboratory CTU-13 dataset for the Scenario 6 development
capture (CC-BY).
