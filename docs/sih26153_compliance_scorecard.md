# SIH26153 Compliance Scorecard — KAIROS Audit

## Step 1 — Literal PS Requirement Checklist

1. Represent network state using feature vectors or graphs.
2. Learn state-transition dynamics using sequence models (LSTM, Transformer), GNNs, latent state models, or other AI techniques.
3. Forecast future network states and estimate probability of attacker progression.
4. Map predicted behaviour to recognised MITRE ATT&CK phases (Reconnaissance, Initial Access, Lateral Movement, C2, Exfiltration).
5. Provide explainability via attention mechanisms, feature attribution, or equivalent — black-box outputs are explicitly NOT acceptable.
6. Use both flow-level (NetFlow/IPFIX: IPs/ports, TCP flags, protocol, bytes/packets, duration, IAT stats, bidirectional ratios) AND packet-level (PCAP-derived: TTL, TCP window size, fragment flags, payload size distribution, port-scan signatures, retransmission counts) features.
7. The core model must be a genuine world model learning P(S_t+1 | S_t) — not a static classifier — trained via supervised dynamics learning on labelled open-source datasets with ground-truth state transitions.
8. Must generalise to unseen attack patterns, not merely memorize training signatures.
9. Support K-step forward simulation from a current traffic snapshot, outputting: infiltration probability time-series, predicted MITRE stage, and driving/contributing features.
10. Feature extraction pipeline ingesting CIC-IDS2018/CTU-13 CSV and/or raw PCAP (via Scapy/PyShark), outputting a timestamped, normalized feature matrix with both feature levels.
11. A trained world model (LSTM/Transformer/GNN) with training scripts, model weights, and a reproducible training configuration included.
12. An infiltration prediction engine performing K-step forward simulation, outputting probability score + predicted MITRE stage + top contributing features.
13. Explainability output PER PREDICTION using SHAP or attention weights, identifying driving flags/ports/flow statistics — black-box outputs are unacceptable.
14. A working demonstration interface (Streamlit, Flask, or CLI) that accepts a PCAP or CSV file as input, runs world model inference, and displays the infiltration probability timeline, flagged flows, and attack stage annotations. Must run fully offline with no cloud API dependencies.
15. Benchmark results comparing model performance (F1, precision, recall, FPR) against a logistic regression baseline on the same features, demonstrating measurable improvement from the world model's temporal dynamics learning.

---

## Step 2 — Requirement Audit

| # | Requirement (short form) | Status | Evidence (file path / test / measured number) | Gap (if any) |
|---|---|---|---|---|
| 1 | Network state as feature vectors/graphs | **PASS** | `java-engine/.../graph/GraphConstructionService.java` builds `GraphSnapshot` (hosts=nodes, flows=edges); `python-ml/pipeline/graph_builder.py` loads into PyTorch Geometric `Data` objects; `java-engine/.../graph/CicGraphDatasetService.java` produces `__network__` vector-mode node for endpoint-free CSV. 13,202 timestamped windows in `data/processed/graph_contracts/`. | None |
| 2 | Learn state-transition dynamics via sequence models | **PASS** | `python-ml/model/dynamics_transformer.py` — `TemporalDynamicsModel`: causal Transformer, 2 layers, 4 heads, learns P(S_t+1\|S_t) via teacher-forced MSE (`next_state_loss()`). `python-ml/model/encoder_gnn.py` — GraphSAGE, 2-layer SAGEConv. `python-ml/model/world_model.py` — `NetworkWorldModel` composes encoder + dynamics + heads. No LSTM variant in code (README: "No LSTM variant exists"). | None |
| 3 | Forecast future network states / attacker progression | **PARTIAL** | K-step autoregressive rollout exists: `dynamics_transformer.py:rollout()` called from `app.py:future_states = model.dynamics.rollout(states, rollout_steps)`. Returns `rollout: {probabilities, predicted_stages, max_probability}`. BUT the primary infiltration probability used in the demo comes from the **separate** `ExtraTrees-temporal-forecast-component`, not the GNN-Transformer rollout. The rollout probability is surfaced as a "transition diagnostic," not the calibrated primary forecast. The GNN-Transformer core F1 is 0.3545 vs LR 0.6770. | World model rollout probabilities are diagnostic, not the primary calibrated forecast; the calibrated probability comes from a separate ExtraTrees component |
| 4 | Map to MITRE ATT&CK phases | **PARTIAL** | `java-engine/.../ingestion/IngestionService.java:cicIds2018Timelines()` maps only FTP-BruteForce & SSH-Bruteforce→INITIAL_ACCESS, DoS→IMPACT, Bot→COMMAND_AND_CONTROL. `python-ml/app.py:SUPPORTED_STAGE_INDICES = (1, 3, 5)`, `_supported_stage_index()` masks unsupported stages. README MITRE table: IA (697-699 val), C2 (113-114 val), IMPACT (206-207 val) supported. RECONNAISSANCE, LATERAL_MOVEMENT, EXFILTRATION have **zero** examples — F1 0.0, masked at runtime, never predicted. | 3/5 PS-mandated stages (Recon, Lateral Movement, Exfiltration) have zero training support; only 2/5 demonstrable |
| 5 | Explainability via attention/attribution, no black-box | **PASS** | `python-ml/model/dynamics_transformer.py:attention_weights()` — causal Transformer attention extraction. `python-ml/explain/shap_explain.py:explain_row()` — TreeSHAP surrogate (ExtraTrees, R2 0.9777, additivity error ~1e-15). `/predict` response includes `top_5_features[{feature, value, shap_value}]` and `attention_summary{top_context_for_final_query, causal_future_attention_mass}`. `java-engine/.../bridge/PythonMlClient.java:validate()` enforces non-null top_features and attention_summary. Phase 39: attention shape [2,1,4,64,64], zero future mass confirmed. | None |
| 6 | Both flow-level AND packet-level features, genuinely fused | **PASS** | Flow-level: CIC CSV via `IngestionService.java`. Packet-level: C++ `cpp-engine/src/feature_extractor.cpp` (TTL mean/variance, TCP window trend, frag count, retransmission count, payload size mean/std/skew, port-scan signatures). PCAP uploads are now genuinely fused in the demo path: `UploadGraphService.fromCapture()` derives flow-level summaries from the SAME extraction batch (`api/CaptureFlowDeriver.java`, `flow.*` prefix) and routes both lists through `WindowingService.windowAndMerge()` 5-tuple `FlowIdentity` matching → `GraphConstructionService` builds one combined edge per flow carrying real `flow.*` + `packet.*` values (`packetOnly=false`, `flowOnly=false`), with port-scan evidence threaded into host `packet.capture_scan_*` features. CSV-only uploads (endpoint-free CIC, no packet source) carry flow features only; packet evidence is then marked explicitly unavailable in the UI (`StageAnnotations.jsx`) instead of zero-filled. Packet→CIC projection (`pipeline/packet_projection.py`) lists every zero-filled model input in `inputProjectionDetail.unavailable_model_features`. Verified by `UploadGraphServiceTest.pcapUploadFusesRealFlowAndPacketFeaturesFromSameCapture` (real JNI extractor, both levels non-zero, `syn_count`/`ack_count` absent). | CSV-only uploads remain flow-level by necessity (no packet source exists); marked unavailable, not fused |
| 7 | Genuine world model learning P(S_t+1\|S_t), not classifier | **PASS** | `dynamics_transformer.py:TemporalDynamicsModel`: `forward()` computes next-state prediction; `next_state_loss()` computes teacher-forced MSE; `rollout()` autoregressively feeds each predicted state back (`generated = torch.cat((generated, next_state), dim=1)`) for K steps. `app.py:future_states = model.dynamics.rollout(states, rollout_steps)`. Genuine autoregressive rollout, not a static classifier. Verified against prior phase audit — code unchanged. | None |
| 8 | Generalise to unseen attack patterns | **PARTIAL** | CTU-13 zero-shot test (Phases 58-60) COMPLETE: Scenario 6 dev / Scenario 11 validate / Scenario 12 untouched holdout. `results/ctu13_unseen_scenario12.json`: h1 (10s) F1 0.3683→0.4746 (+0.1062), recall +0.2755, BUT FPR 0.7410→0.8249 (+0.0839, worse), ROC-AUC 0.3136→0.4579 (<0.5, worse than random), h3 F1 -0.1203 (regresses), h6 F1 -0.0324 (regresses). The below-random AUC was diagnosed as genuine, not a bug: one shared loader (`pipeline/ctu13_flow.py`, `label.startswith("flow=From-Botnet")`) encodes all three scenarios identically; both models score `predict_proba[:, 1]` through the same `_metrics`; the identical code yields above-random validation AUCs in 5/6 configs (LR h1 0.686/h3 0.749/h6 0.752, KAIROS h3 0.801/h6 0.669) — so S12 predictions genuinely anti-correlate with ground truth on the unseen NSIS.ay family. h3/h6 = 3/6 windows × 10s = 30s/60s-ahead horizons. Phase-status: "Limited generalization: F1/P/R improve but FPR worsens +0.0839 and ranking remains weak (<0.5)." | Zero-shot F1 improves but FPR worsens and AUC <0.5 (confirmed genuine anti-correlation, not a scoring bug); longer-horizon F1 regresses; domain shift NOT solved |
| 9 | K-step forward simulation: probability time-series + MITRE stage + contributing features | **PASS** | `app.py:predict()` calls `model.dynamics.rollout(states, rollout_steps)` producing `rollout.probabilities` (time-series), `rollout.predicted_stages`, and `top_5_features` (SHAP driving features). Rollout steps 1-10 configurable (default 3). `ForecastController.java` accepts `rolloutSteps` param 1-10. Java `ForecastResponse` includes `prediction.rollout`. Demo UI `ProbabilityTimeline.jsx` plots rollout probabilities. | None |
| 10 | Feature extraction pipeline: CIC-IDS2018/CTU-13 CSV + raw PCAP → timestamped normalized matrix | **PASS** | Java `IngestionService.java` ingests CIC CSV (header normalization, NaN/Inf sanitization, timeline stage labels); `CicGraphDatasetService.java` produces timestamped normalized graph contracts; C++ `feature_extractor.cpp` parses PCAP/PCAPNG; `Ctu13PacketContractService.java` adapts CTU-13 flows; `pipeline/graph_builder.py` validates contract→PyTorch Geometric. 13,202 ordered windows produced. | None |
| 11 | Trained world model with scripts, weights, reproducible config | **PASS** | `python-ml/weights/world_model_v1.pt` (603KB, `artifact_version kairos.world-model.v1.phase38-stage`). Training: `python-ml/training/run_world_model.py`, `world_model_trainer.py`, `dynamics_trainer.py`. Config: `python-ml/configs/train_config.yaml` (GNN: GraphSAGE 2-layer, 64 hidden; Transformer: 2-layer, 4-head, causal; 5 epochs, AdamW lr 1e-3, no weight decay/schedule, loss weights dyn 0.5/infilt 3.0/stage 3.0, focal α=0.75, seed 42). `load_test_checkpoint.py` → "LOAD TEST PASS". | None |
| 12 | Infiltration prediction engine: K-step sim + probability + stage + top features | **PASS** | `app.py:PredictionService.predict()` performs K-step rollout, outputs `immediate_probability` (sigmoid head), `predicted_stage` (softmax head), `top_5_features` (SHAP). `ForecastController.java:POST /forecast` and `POST /forecast/upload` orchestrate upload→ingestion→graph→Python→narrative→response. `PythonMlClient.java` validates schema. | None |
| 13 | Per-prediction explainability via SHAP or attention | **PASS** | Same as Item 5. Every `/predict` response includes `top_5_features` (SHAP TreeSHAP, `shap_explain.py:explain_row()`) and `attention_summary` (Transformer attention, `dynamics_transformer.py:attention_weights()`). SHAP surrogate: ExtraTrees, R2 0.9777, additivity error ~1e-15. Missing surrogate → HTTP 503 (not 500). Java client validates non-null. | None |
| 14 | Working demo interface (Streamlit/Flask/CLI) accepting PCAP/CSV, offline | **PASS** | Offline demo exists and works for CSV: React UI (`react-ui/src/App.jsx`) accepts `.csv/.pcap/.pcapng` drag-and-drop; `ForecastController.upload()` handles both; `kairos.sh` + `.env.example` set `ONLINE_MODE=false`; `ForecastUploadTest.java` tests CSV upload→offline-local narrative→JSON 200; `test_app.py` verifies `/health` returns `offline: True`; README claims verified live (network disabled, 0 errors, 0 external calls, 0.28-0.43s). PCAP path is now tested end-to-end with the REAL C++ extractor: `UploadGraphServiceTest.pcapUploadFusesRealFlowAndPacketFeaturesFromSameCapture` writes a synthetic 2-packet capture, extracts via JNI (`-Dkairos.native.library`, same as `CppBridgeIntegrationTest`), routes through the fused upload path, and asserts a validated `kairos.sequence.v1` contract with real flow+packet values — replacing the old mocked-`PacketExtractor` test. The file-upload path exists and was NOT removed in favor of live-capture. | PCAP full-chain inference (upload→live Python inference→UI pixels) remains manually verified, not committed as an automated test; the committed test covers real extractor→validated inference-ready contract |
| 15 | Benchmark vs LR baseline showing measurable world-model improvement | **PARTIAL** | `results/benchmark_table.csv`: same-feature LR F1 0.6770 vs ExtraTrees temporal F1 0.7390 (+0.0620), precision +0.0365, recall +0.0971, FPR -0.0092, ROC-AUC +0.0681 — improvement IS demonstrated on a fair matched comparison (identical backward-only temporal features from the shared `flatten_graph_sequence()` + `temporal_vector()`, identical future target, identical per-day 80/20 split, identical leave-one-day-out calibration for BOTH learners in `training/run_ps_aligned_benchmark.py`). BUT Case B diagnosed: the ExtraTrees head consumes raw graph-summary features with zero GNN-Transformer involvement (no rollout/latent/attention imports anywhere in `pipeline/temporal_forecaster.py` or the benchmark runner) — the gain comes from a stronger discriminative learner, NOT from learned world-model dynamics. The world model core itself: next-window diagnostic F1 0.3545 (fails to beat LR 0.6770 at same-task). Phase 63 retraining attempt (F1-selection) was honestly negative (raw F1 regressed 0.3132 vs canonical 0.3454), so no new tuning was attempted here. `temporal_ablation.json` confirms temporal history provides +0.0081 F1 / +0.0128 AUC over current-window-only (same ExtraTrees learner), evidencing temporal-dynamics value — but from feature history, not from the Transformer/GNN architecture. Table/JSON now carry an explicit `attribution` block (`improvement_from_world_model_core: False`) and README states the core-vs-separate-head numbers verbatim. | The world model (GNN-Transformer core) does NOT beat the baseline; improvement comes from a separate ExtraTrees temporal-forecast component. This is the single most consequential compliance gap — now framed honestly, not closed. |

---

## Overall Count

| Status | Count |
|--------|-------|
| **PASS** | 9/15 |
| **PARTIAL** | 6/15 |
| **FAIL** | 0/15 |

---

## Step 3 — Specific Risk Area Verification

### Item 7 — Genuine world model (not classifier): VERIFIED
The autoregressive rollout was re-verified against current code. The exact code path:
- `python-ml/model/dynamics_transformer.py:TemporalDynamicsModel.rollout()` (lines ~70-85 in current file): iterates `steps` times, each iteration calls `self(generated)[:, -1:, :]` to predict the next state, then feeds it back via `torch.cat((generated, next_state), dim=1)`. This is a genuine autoregressive world model: each predicted state becomes the context for the next prediction.
- `python-ml/app.py:PredictionService.predict()`: `future_states = model.dynamics.rollout(states, rollout_steps)` followed by `future_outputs = model.heads(future_states)` produces rollout probabilities and stages.
- The dynamics model learns via `next_state_loss()` (teacher-forced MSE), and the rollout method is `@torch.no_grad()` (inference-only, no teacher forcing).
- **Conclusion**: Code was not altered since prior verification; the rollout is genuine K-step autoregressive, not a static classifier. PASS confirmed.

### Item 8 — Generalization to unseen attacks: VERIFIED (bug check: genuine)
CTU-13 zero-shot testing (Phases 58-60) was run. Evidence:
- `results/ctu13_unseen_scenario12.json` — full results for Scenario 12 (untouched holdout)
- `data/ctu13_scenario6_manifest.yaml` — Scenario 6 development capture
- Protocol: Scenario 6 dev / Scenario 11 validate (threshold selection) / Scenario 12 holdout (untouched)
- h1: F1 +0.1062, precision +0.0586, recall +0.2755, but FPR +0.0839, AUC 0.4579 (<0.5)
- h3: F1 -0.1203 (regresses), h6: F1 -0.0324 (regresses)
- Bug check (no bug found): label polarity identical across scenarios (single shared `load_ctu13_windows`, positive = window containing ≥1 `From-Botnet` flow); score direction identical for both models (`predict_proba[:, 1]` = P(malicious), standard `roc_auc_score`, correct `tn, fp, fn, tp` unpack); the SAME code yields above-random validation AUCs in 5/6 configs (LR h1 0.686 / h3 0.749 / h6 0.752; KAIROS h3 0.801 / h6 0.669) — a systematic inversion would flip validation too. Both independent learners anti-correlate on S12 (a data property, not a model bug), and KAIROS h3/h6 holdout AUCs are actually >0.5 (0.547/0.511) while LR stays ~0.3 — inconsistent with any uniform scoring bug. h3/h6 = 3/6-window (30s/60s-ahead) horizons; the F1 regression is threshold-dependent.
- Phase-status explicitly states: "Limited generalization: F1/P/R improve but FPR worsens +0.0839 and ranking remains weak (<0.5)."
- **Conclusion**: Zero-shot test WAS run, the below-random AUC was bug-checked and confirmed genuine anti-correlation on the NSIS.ay family. This is a genuine gap, reported as PARTIAL, not an omission.

### Item 14 — Offline demo: VERIFIED (PCAP real-extractor test now committed)
Verified from code evidence (cannot run full stack in this environment):
- `.env.example`: `ONLINE_MODE=false`, `GEMINI_API_KEY=` (empty) — default is offline ✓
- `app.py:/health` returns `{"offline": true}` ✓
- `ForecastUploadTest.java:uploadProducesForecastWithOfflineNarrative()` — CSV upload → mock Python → `narrative.mode` = `offline-local` → JSON 200 ✓
- `test_app.py:test_health_is_offline_and_does_not_load_model()` ✓
- `PythonMlClient.java:configuredBaseUrl()` defaults to `http://127.0.0.1:5000` ✓
- `app.py:predict_route()` never makes external calls ✓
- React `client.js:resolveApiBase()` defaults to `http://127.0.0.1:8080` ✓
- `ForecastController.java:forecastUpload()` handles CSV + PCAP via `UploadGraphService` ✓
- Live capture is a separate `LiveDashboard.jsx` section; the upload path is primary and was NOT removed ✓
- **PCAP path (fixed this session)**: the old mocked-`PacketExtractor` test (`convertsUploadedPcapIntoPacketNativeWindows`) is REPLACED by `UploadGraphServiceTest.pcapUploadFusesRealFlowAndPacketFeaturesFromSameCapture` — synthetic 2-packet capture → real JNI extraction → fused upload path → validated `kairos.sequence.v1` contract with real flow+packet values (runs, not skipped: surefire passes `-Dkairos.native.library`). The C++ extractor itself has real tests (`feature_extractor_test.cpp`, JNI round-trip in `CppBridgeIntegrationTest`). Residual: full-chain PCAP inference→UI remains manually verified.

### Item 15 — Baseline comparison: VERIFIED (Case B — honestly reframed, not closed)
`results/benchmark_table.csv` and `results/benchmark_table.json` (v2) contain current numbers.
Case determination (code evidence, not assumption):
- The ExtraTrees head trains in `training/run_ps_aligned_benchmark.py:_fit_models` on `development["x"]` where each row is `temporal_vector(block)` over `flatten_graph_sequence()` rows — the SAME flatten function, SAME feature matrix, SAME future target, SAME per-day 80/20 split, SAME leave-one-day-out calibration as the LR baseline (both prototypes go through `_out_of_day_probabilities` + `_select_threshold`).
- Neither `pipeline/temporal_forecaster.py` nor the benchmark runner imports anything from `model/` — no rollout, latent, or attention features exist in this path. **Case B confirmed.**
- **Result**: improvement IS demonstrated on the PS-aligned 60s forecast task (F1 +0.0620, AUC +0.0681), but from a separate discriminative head, not from world-model dynamics. The world model core underperforms the baseline (0.3545 vs 0.6770).
- Remediation applied (reframe branch — Phase 63 already did the genuine retrain attempt with a negative result, so no new tuning): `benchmark_table.json` now carries an explicit `attribution` block (`improvement_from_world_model_core: False`); row notes state the core-vs-head numbers; README states them verbatim; no "world model beats baseline" claim remains in README/demo/pitch-adjacent copy (React copy already separated: "plus a separate world-model transition diagnostic").
- `results/temporal_ablation.json`: same ExtraTrees learner (50 trees), history-6 F1 0.6871 vs current-only 0.6790 (+0.0081 F1). This shows temporal history provides measurable improvement, but not from the GNN-Transformer architecture.
- `results/baseline_metrics_indist.json`: the identical-split LR baseline (F1 0.7097 at threshold 0.5).
- Phase 63 retraining attempt: honestly negative, canonical checkpoint kept.
- **Conclusion**: Fair matched comparison, honestly attributed. The world model core underperforms the baseline — PARTIAL retained deliberately.

### Item 6 — Both feature levels, genuinely fused: VERIFIED (fixed this session)
- Flow-level features: from CIC CSV via `IngestionService.java` (IPs/ports, protocol, bytes/packets, duration, IAT, bidirectional, SYN/ACK counts) ✓
- Packet-level features: from C++ `feature_extractor.cpp` (TTL mean/variance, TCP window trend, fragment count, retransmission count, payload size mean/std/skew, port-scan signatures) ✓
- **Fusion (fixed)**: `UploadGraphService.fromCapture()` now derives `flow.*` summaries from the same extraction (`api/CaptureFlowDeriver.java`) and routes both lists through `WindowingService.windowAndMerge()` (exact 5-tuple `FlowIdentity` match) into `GraphConstructionService`, which emits one combined edge per flow (`packetOnly=false`, `flowOnly=false`) plus per-host `packet.capture_scan_*` evidence. Port-scan batches ride the new `windowAndMerge(records, batch, size)` overload.
- Verified by `UploadGraphServiceTest.pcapUploadFusesRealFlowAndPacketFeaturesFromSameCapture` (real extractor): `packet.packet_count=2.0`, `packet.ttl_mean=63.0`, `flow.packet_count=2.0`, `flow.duration_micros=1e6`, `flow.payload_bytes_estimate=12.0` from the same 2-packet capture; `syn_count`/`ack_count` absent (not fabricated).
- CSV-only uploads stay flow-level (endpoint-free CIC has no packet source and no IPs for 5-tuple matching); the UI marks packet evidence explicitly unavailable, and `unavailable_model_features` names every zero-filled model input.
- **Conclusion**: Both feature levels are genuinely fused into the same state representation wherever both sources exist; unavailability is explicit elsewhere. PASS.

### Item 4 — MITRE stage mapping: VERIFIED
Precisely which stages have real training support:
- **Supported (3 of 6 classes, 2 of 5 PS-mandated):**
  - `INITIAL_ACCESS` — 697-699 val examples (FTP-BruteForce, SSH-Bruteforce, Infiltration)
  - `COMMAND_AND_CONTROL` — 113-114 val examples (Bot)
  - `IMPACT` — 206-207 val examples (DoS GoldenEye/Slowloris) — CIC-extra, NOT PS-mandated
- **Unsupported (3 of 6 classes, 3 of 5 PS-mandated):**
  - `RECONNAISSANCE` — 0 examples
  - `LATERAL_MOVEMENT` — 0 examples
  - `EXFILTRATION` — 0 examples
- Enforcement: `app.py:_supported_stage_index()` only selects from `SUPPORTED_STAGE_INDICES = (1, 3, 5)`. Unsupported argmax entries are masked, never predicted. `GraphBuilder` labels: `NONE → -1`, only stages present in CIC data get labels.

---

## Step 4 — Core PS Scope vs Bonus Live-Capture Scope

### Core PS-required scope (file-upload demo): PASS with caveat

The core file-upload demo required by Item 14 exists and is functional:
- `react-ui/src/App.jsx` — main upload form accepts CSV/PCAP/PCAPNG via drag-and-drop
- `java-engine/.../api/ForecastController.java` — `@PostMapping("/upload")` with `UploadGraphService`
- `java-engine/.../api/UploadGraphService.java` — handles both CSV (`fromCsv`) and PCAP (`fromCapture`)
- `react-ui/src/components/ProbabilityTimeline.jsx` — displays 10/30/60s forecast timeline
- `react-ui/src/components/FlaggedFlowsTable.jsx` — displays SHAP-ranked flagged flows
- `react-ui/src/components/StageAnnotations.jsx` — displays predicted MITRE stage annotations
- `react-ui/src/components/NarrativePanel.jsx` — displays analyst narrative with offline mode badge
- Verified by `ForecastUploadTest.java` (CSV path) and offline tests (`test_app.py`)

**The file-upload demo was NOT removed or deprioritized.** It remains the primary entry point in the React UI (`App.jsx` renders the upload panel first; `LiveDashboard.jsx` is a separate section below).

### Bonus live-capture scope: implemented and verified on loopback

The passive live-capture tier (Phases 66-74, 76-77) is implemented and verified on loopback only:
- `docs/live_capture_threat_model.md` — full threat/safety model
- `cpp-engine/src/live_capture.cpp` — real interface enumeration + bounded passive capture via dumpcap
- `cpp-engine/src/live_emitter.cpp` — 10s feature windows in existing flow schema
- `java-engine/.../live/` — 6 Java classes for session supervision, consent gate, adapter, drift guard
- `react-ui/src/components/LiveDashboard.jsx` + `QualityBadge.jsx` — SSE-driven live dashboard
- Verified by `live_capture_test.cpp` (ctest), `LiveControllerTest` (7/7), `LiveSessionServiceTest` (6/6), `ConsentGateServiceTest` (7/7), `LiveSequenceAdapterTest` (4/4), `Phase76ActiveRefusalTest` (3/3)
- **Note**: Live capture requires dumpcap + loopback; non-loopback behavior is unmeasured per phase-status.

### Active probing (Phase 75): NOT started
`mode` must be exactly `passive`; any other value is rejected at the consent gate, session service, and REST boundary. `Phase76ActiveRefusalTest` confirms fresh 3/3 refusal.

---

## Prioritized Gap List (most threatening to judging)

Ordered by severity. Items 7, 8, 14, 15 weighted most heavily per instructions.

### 1. Item 15 — World model core does not beat the LR baseline (CRITICAL, reframed honestly)

The PS asks to "demonstrate measurable improvement from the world model's temporal dynamics learning." Post-fix status (Case B diagnosed by code evidence):
- The GNN-Transformer world model core (next-window diagnostic) has **F1 0.3545** — it does NOT beat the LR baseline (0.6770 / 0.7097).
- The improvement that IS demonstrated (F1 +0.0620, AUC +0.0681 at 60s, fair same-task/same-split/same-calibration comparison) comes from a **separate** ExtraTrees classifier on hand-crafted temporal summaries — verified to consume no rollout/latent/attention features.
- The world's value proposition rests on rollout (120s early-alert), attention, and explainability — not on the headline infiltration metric.
- Phase 63 retraining attempt was honestly negative; no new tuning attempted (reframe branch).
- **Remediation**: `benchmark_table.json` attribution block, honest row notes, README core-vs-head numbers verbatim, no "world model beats baseline" claim in README/demo. A judge checking this sees PARTIAL with the gap stated, not an overstatement.
- **Impact**: A judge checking whether the "world model" beats the baseline will see F1 0.3545 < 0.6770 and conclude the core gap remains — but will also see it disclosed, not hidden. Item stays PARTIAL by design.

### 2. Item 6 — Flow-level and packet-level features NOW genuinely fused (was HIGH, now PASS)

Post-fix: PCAP uploads fuse capture-derived `flow.*` summaries with native `packet.*` features from the same capture via `windowAndMerge()` 5-tuple matching (verified by a real-extractor test asserting both levels non-zero and unobservable fields absent). CSV-only uploads stay flow-level by necessity and are marked unavailable in the UI; projection lists zero-filled inputs explicitly. Residual: CSV inputs cannot fuse (no packet source exists) — documented, not hidden.

### 3. Item 8 — Generalization is limited, not solved (HIGH, bug-checked)

CTU-13 zero-shot testing was completed and honestly reported; the below-random AUC (0.4579) was additionally bug-checked (shared loader, same scoring path, above-random validation AUCs) and confirmed as genuine anti-correlation on the NSIS.ay family — documented plainly in README and the benchmark row note:
- h1 F1 improves but FPR worsens (+0.0839) and ROC-AUC <0.5 (0.4579)
- h3 and h6 F1 regress
- **Impact**: The PS requires generalization to unseen patterns; current results show limited generalization with significant domain shift. Honestly documented as PARTIAL.

### 4. Item 14 — PCAP real-extractor upload test committed (was MEDIUM, now PASS)

Post-fix: `pcapUploadFusesRealFlowAndPacketFeaturesFromSameCapture` runs the real JNI extractor through the fused upload path and asserts a validated inference-ready contract — replacing the mocked-`PacketExtractor` test. Residual: full-chain PCAP inference→UI remains manually verified (same `/predict` + UI path as CSV).

### 5. Item 4 — 3/5 PS-mandated MITRE stages have zero training support (HIGH)

The PS mandates mapping to all five: Recon, Initial Access, Lateral Movement, C2, Exfiltration.
- Only 2/5 (Initial Access, C2) are demonstrable
- 3/5 (Recon, Lateral Movement, Exfiltration) have zero training examples in CIC-IDS2018
- These are masked at runtime, never predicted
- **Impact**: A judge checking MITRE coverage will see 3/5 stages unsupported.

### 6. Item 3 — Rollout probability is diagnostic, not primary (MEDIUM)

The K-step rollout produces future infiltration probabilities, but these are surfaced as "transition diagnostics" in the UI, not as the calibrated primary forecast. The calibrated probability comes from the ExtraTrees temporal head.
- **Impact**: PS Item 9 requires the demo to "output infiltration probability time-series, predicted MITRE stage, and driving/contributing features" from the K-step simulation. The rollout does output these, but the primary timeline shown to users comes from a different component.

### 7. Item 14 — Feature extraction mentions Scapy/PyShisk but uses C++/libpcap (LOW)

PS Item 10 mentions "via Scapy/PyShark" for PCAP ingestion. The actual implementation uses a C++ PCAP parser (`feature_extractor.cpp` with libpcap-compatible parsing) plus Java JNI bridge. Scapy/PyShark are not used.
- **Impact**: Minor — the approach is arguably superior (native speed) but doesn't match the PS's suggested toolchain.

---

## Step 5 — Recommendation for Fix-Prioritization

### Closed this session (compliance remediation):

1. **Item 15 / 1 — Case B diagnosed; benchmark narrative aligned with the world model core.** Code evidence proved the ExtraTrees head consumes no world-model representations; `benchmark_table.json` now carries an explicit `attribution` block, row notes state core 0.3545 vs baseline 0.6770, and README/demo make no "world model beats baseline" claim. Stays PARTIAL honestly.

2. **Item 6 / 2 — Packet-level features merged into flow-level graph edges for PCAP uploads.** `UploadGraphService.fromCapture()` derives `flow.*` summaries from the same extraction and routes both through `WindowingService.windowAndMerge()`; CSV-only uploads mark packet evidence unavailable in the UI; projection lists zero-filled inputs. Now PASS.

3. **Item 8 / 3 — Domain-shift limitation bug-checked and stated plainly.** Below-random AUC confirmed genuine anti-correlation (not a polarity/score bug); README + benchmark row state it verbatim. Stays PARTIAL honestly.

4. **Item 14 — Real-extractor PCAP upload test committed.** Mocked-`PacketExtractor` test replaced with a real-JNI fused-path test asserting a validated inference-ready contract. Now PASS (full-chain inference→UI still manually verified).

### Document as known limitations (do not attempt to close):

4. **Item 4 — 3/5 MITRE stages unsupported.** This is a data limitation (CIC-IDS2018 simply contains no Recon/Lateral/Exfil examples). Cannot be fixed without acquiring new training data. Document prominently in README and pitch deck as a structural coverage gap.

5. **Item 14 — PCAP end-to-end without committed sample.** Building a committed small PCAP end-to-end test requires either a real capture dataset or a synthetic PCAP generator. Document as a known limitation; the mocked-extractor test validates the pipeline structure. If a small PCAP can be committed, add it as a regression.

6. **Item 7 — Active probing (Phase 75).** Not started (Stop Gate 1 never reached). Leave as-is; the threat model document and Phase 76 refusal tests already demonstrate safe-by-design scoping.
