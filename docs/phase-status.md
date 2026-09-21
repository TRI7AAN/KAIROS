# Phase verification status

## Completed in the current implementation

- **2:** four complementary CIC-IDS2018 CSV attack days, verified by byte
  size, SHA-256, row count, and label distribution, plus the seeded (42)
  stratified 200K/day capping reference (`python-ml/pipeline/downsample_flows.py`,
  documented in `data/cic_ids_2018_manifest.yaml`).
- **3:** the official CTU-13 Scenario 6 truncated capture at the canonical
  path `data/raw/ctu13_pcap/scenario06_donbot/capture20110816.truncated.pcap`
  — 38,705,338 packets, 7749.87s (02:09:10), SHA-256-verified, excluded from
  zero-shot scoring.
- **7:** the typed Java bridge loads the native library and returns C++
  flow and port-scan records; surefire always passes
  `-Dkairos.native.library`, so `CppBridgeIntegrationTest` runs PASS (not
  SKIPPED).
- **9-11:** timestamped 10-second windows, host aggregation, flow/packet merge,
  graph construction, and a strictly validated Java-to-Python JSON contract.
- **12-16 (frozen, tag `baseline-v1`):** non-temporal logistic baselines with
  chronological splitting, train-only scaling, binary and six-stage models,
  metrics, confusion matrices, and serialized artifacts.
- **17-20:** edge-aware GraphSAGE, mean/attention pooling, overfit sanity check,
  and variable-size graph batching.
- **21-28:** causal temporal Transformer, next-state loss, whole-day validation,
  best-checkpoint training, autoregressive rollout, shared forecast heads, and
  focal joint loss.
- **29-30:** real four-day capped CIC export and end-to-end training with
  load-tested checkpoint, exact config, and loss history.
- **31:** window-size ablation finalized, winner 10s; stage macro-F1 diagnostic
  resolved as a coverage gap (val C2 disjoint from train IA/Impact;
  Recon/Lateral/Exfil nowhere), deferred to Phase 34.
- **32:** in-distribution per-day final-20%-time split adopted as the PRIMARY
  split (joined ~10,589 train / ~2,649 val across all 4 days); whole-day
  day0302 retained as a SECONDARY generalization stress test. Seeded
  loss/alpha, encoder (GNN winner), and rollout-K (K=3) ablations; frozen
  baseline re-evaluated on the identical in-dist split for a valid
  head-to-head (`results/baseline_metrics_indist.json`).
- **33:** rollout proof — K=3 gives 120s early alerts on both eligible
  validation attacks, but the probability-rise criterion did not pass, so
  Phase 33 is marked partial, not overstated.
- **34-38:** MITRE mapping cross-check (weak agreement; only IA/C2/Impact
  occur in the selected contracts), per-class error analysis, label audit
  (no ambiguous labels), stage-set decision
  (`retain_six_class_external_schema_no_merge` — no merge, no new labels),
  and frozen-backbone stage-head fine-tune (observed-macro 0.0667 → 0.3302),
  stamped into `world_model_v1.pt` (`artifact_version
  kairos.world-model.v1.phase38-stage`).
- **39-43:** causal Transformer attention extraction (mask + normalization
  checks pass), TreeSHAP surrogate over causal forecast-history features
  (fidelity R2 ~0.978, additivity error ~1e-15), Phase 42 explanation schema,
  and sub-2s latency (median ~108ms, p95 ~110ms).
- **44-50:** Flask `POST /predict` (graph load, GNN/Transformer inference,
  K-step rollout, attention, SHAP), typed Java `PythonMlClient`, public
  `POST /forecast` + `/forecast/upload` orchestration, deterministic
  offline-local narrative by default, optional Gemini mode behind
  `ONLINE_MODE` + API-key gate, and a MockMvc upload-to-response
  integration test (Python client mocked).
- **51-57:** React dashboard (upload wiring, probability timeline, flagged
  flows, stage annotations, narrative panel with mode badge, sample-attack
  quick-load) building cleanly via `npm run build`.
- **66:** live-capture architecture + threat/safety model
  (`docs/live_capture_threat_model.md`) — normative for Phases 67-77:
  `/live` API contracts, truncated-capture scope policy, local-only
  retention, IDLE→…→STOPPED/ERROR lifecycle, 8-row threat model.
- **67:** real interface enumeration (8 interfaces, `lo` flagged loopback)
  and bounded passive capture with dual autostop — 5s run captured 47 real
  loopback packets and self-stopped; packet-limit run self-stopped at 4;
  backend-accounted packet/drop counters (`ctest` live_capture_tests PASS).
- **68:** live feature-window emitter in the existing flow schema (10s
  windows) — 32s capture → 211 packets → 4 non-zero windows; live-shaped
  window passes the existing `load_graph_sequence` validator
  (`ctest` live_emitter_tests PASS).
- **69:** Java live-session bridge (`com.networkwm.live`: supervisor +
  backend) — start → windows → stop with no orphaned backend post-stop;
  real 5s `lo` capture with real counters (`LiveSessionServiceTest` 6/6).
- **70:** target resolver + consent gate — default-empty allowlist, DNS
  pinning, append-only audit; allow-path and deny-path tested
  (`ConsentGateServiceTest` 7/7; enforced at `POST /live/sessions`, 403).
- **71:** sequence adapter — live windows validate as `kairos.sequence.v1`,
  malformed input rejected with `live window N` errors
  (`LiveSequenceAdapterTest` 4/4).
- **72:** same-checkpoint live inference + reactive drift guard
  (`ok`/`degraded`/`unreliable` via `python-ml/live_drift.py`,
  `results/live_drift_reference.npz` + `results/live_drift_calibration.json`;
  real window `ok`, 25σ-shifted `unreliable`, NaN `unreliable`;
  `tests.test_live_drift` 3/3).
- **73-74:** React `LiveDashboard` + `QualityBadge` on real `/live`
  sessions; genuine SSE `text/event-stream` (`LiveControllerTest` 7/7).
- **75 (active probing):** NOT STARTED — Stop Gate 1 never reached; no
  active-probe code path exists (`mode` must be exactly `passive`).
- **76:** offline + safety regression (`results/phase76_regression.md`) —
  netns-isolated passive capture works; active refused fresh 3/3
  (`Phase76ActiveRefusalTest`).
- **77:** performance + packet-loss validation
  (`results/live_capture_performance.md`) — 55/204/785 pps zero-loss;
  662,520-packet burst, 0 drops; RSS flat at 4116 kB; backpressure verified.
- **78 (demo scenario + docs):** NOT STARTED.
- **58-60 (CTU-13 adaptation/zero-shot):** COMPLETE. Scenario 6 (DonBot) is
  development, Scenario 11 (RBot) is external validation, and Scenario 12
  (NSIS.ay) is the untouched holdout. At 10s KAIROS improves holdout F1
  0.3683 -> 0.4746 and recall 0.5816 -> 0.8571, while FPR worsens
  0.7410 -> 0.8249; the domain-shift gap remains explicit.
- **63 (retraining attempt, Option A):** genuine attempt, honestly negative.
  Diagnosis: validation loss anti-correlates with F1 (dynamics-MSE ~95% of
  joint loss); added dropout/weight-decay/cosine and aggressive loss
  rebalancing all accelerate infiltration-head collapse; per-epoch F1 peaks
  at ep1 (0.5671 @FPR 0.87) then collapses (max prob < 0.5 from ep8).
  F1-selection probe (same recipe, 6 epochs, `results/phase63_retrain.json`)
  picked ep3: F1 0.3132 / FPR 0.1424 vs canonical 0.3454 / 0.1694 — raw F1
  REGRESSED, so the canonical checkpoint was KEPT (pre-attempt archive:
  `world_model_v1_pretune_baseline_loss.pt`). The temporal architecture's
  value proposition rests on explainability/stage-mapping/rollout, not raw
  legacy next-window-head superiority. The separate deployed ExtraTrees 60s temporal forecasting component now beats
  same-feature LR on F1, precision, recall, FPR, and ROC-AUC.

## Real-data evidence

| Dataset day | Capped flows in | 10-second windows | Malicious stage |
|---|---:|---:|---|
| 2018-02-14 | 200,001 | 3,253 | Initial Access |
| 2018-02-15 | 200,000 | 3,413 | Impact |
| 2018-02-28 | 200,000 | 3,393 | Initial Access |
| 2018-03-02 | 200,000 | 3,143 | Command and Control |
| **Total** | **800,001** | **13,202** | three observed classes |

The JNI round-trip test passes without skips (surefire supplies the native
library). Native extractor tests, all Java unit tests, and all Python tests pass.
Current totals: Java 60 tests / 0 failures (1 pre-existing skip
`RealCicCsvIntegrationTest`), Python 35 (unittest discover) + 3 PS-alignment
guards, C++ ctest 3/3.

## Current measured results (task-aligned PRIMARY benchmark v2)

PRIMARY — CIC per-day final-20% untouched test, 60s future-window task
(`results/ps_aligned_benchmark.json` h6, `results/benchmark_table.json:v2`):
same backward-only temporal features, same future target, same split and
leave-one-source-day-out calibration for both models (10545 dev / 2649 test,
6420 features, ExtraTrees 150 trees, seed 42).

- Same-feature logistic baseline: F1 **0.6770**, precision **0.6331**, recall
  **0.7275**, FPR **0.2640**, ROC-AUC **0.7923**, observed-stage macro **0.9990**.
- Separate ExtraTrees temporal forecasting component (deployed `ps_aligned_temporal_forecaster.joblib`):
  F1 **0.7390**, precision **0.6696**, recall **0.8245**, FPR **0.2548**,
  ROC-AUC **0.8604**, observed-stage macro **1.0000**.
  Improvement: **+0.0620 F1, +0.0365 P, +0.0971 R, −0.0092 FPR, +0.0681 AUC**.
- Legacy GNN-Transformer transition core (retained for rollout/attention, not
  the headline comparison): next-window F1 **0.3545**, P 0.5027, R 0.2738,
  FPR 0.1694, AUC 0.5813, threshold 0.5 (`results/phase32_completed.json`).
  The old LR (current-window) vs transition-head (future-window) comparison
  was apples-to-oranges and is superseded.
- Caveats (do not omit in demo): thresholds are development-calibrated
  (LR 0.0148, KAIROS 0.1031 at h6) under prevalence shift dev 7.7%
  (819/10545) vs test 38.5% (1020/2649) — fair (same protocol) but absolute
  values are prevalence-sensitive; stage 0.999→1.0 reflects near-trivial
  separability on selected CIC days (future stage ≈ current for long blocks),
  not general stage reasoning; `trees:150` is recorded in weights artifact
  and `python-ml/weights/README.md`.

EXTERNAL — CTU-13 S6 develop / S11 validate / S12 untouched holdout, 10s
(`results/ctu13_unseen_scenario12.json` h1; 770 dev / 92 val / 862 refit /
613 holdout): LR F1 **0.3683** P 0.2695 R 0.5816 FPR 0.7410 AUC 0.3136;
KAIROS F1 **0.4746** P 0.3281 R 0.8571 FPR 0.8249 AUC 0.4579.
Limited generalization: F1/P/R improve but FPR worsens +0.0839 and ranking
remains weak (<0.5). Longer horizons regress and are disclosed here, not
hidden: h3 F1 −0.1203 (LR 0.4960 vs KAIROS 0.3756), h6 F1 −0.0324
(LR 0.4840 vs KAIROS 0.4516). Official CTU labels carry no MITRE stages,
so none are fabricated.

SECONDARY — whole-day cross-generalization stress test (train
day14+day15+day28, validate whole day0302, unseen C2 dynamics):

- World model: F1 **0.1489**, precision **0.1334**, recall **0.1684**, FPR
  **0.1977**, AUC-ROC 0.471. Tracked separately and labeled as such; the gap
  vs in-dist is the honest generalization limitation.
- Early warning (Phase 33, partial): K=3 crosses the alert threshold 120s
  before onset on both eligible validation attacks, but without a material
  near-onset probability rise — early alerting, not a calibrated
  rising-risk trajectory.

The legacy pre-Phase-32 whole-day-only baseline (binary F1 0.3096 on the
strict final-20%-of-joined-sequence holdout, stage macro-F1 0.0 on 481
C2-only holdout windows) is superseded by the identical-split comparison
above and retained in `results/baseline_metrics.json` for provenance only.

The epoch-1 checkpoint (`python-ml/weights/world_model_v1.pt`, 603KB)
passes the forward + K=5 rollout load test (`LOAD TEST PASS`).

## Known limitations and next phase

Endpoint IPs are preserved as graph topology IDs whenever present
(`IngestionService:sourceIp/destinationIp` → `GraphConstructionService:endpoints`,
packet IPs preferred when flow IPs are blank; ports/protocol preserved as edge
features). Raw IPs are excluded from numeric ML features by design (to avoid
memorizing addresses). The official processed CIC CSVs omit endpoint IPs, so
they exercise vector mode through the explicit `__network__` fallback, while
real host topology is available for PCAP/enriched-flow input. PS flow-level
coverage: ports/protocol/bytes/packets/duration/IAT/bidir and SYN/ACK counts
preserved; FIN/RST/PSH/URG survive as generic numeric edge summaries.
PS packet-level coverage (C++): TTL mean/variance, TCP window trend, frag and
retransmission counts, payload mean/std/skew, sequential vs randomized
port-scan signatures.
PS MITRE mapping: the 6-class schema retains IA/C2/IMPACT with real support;
RECONNAISSANCE, LATERAL_MOVEMENT and EXFILTRATION have zero support in the
selected CIC days (F1 0.0) and are masked, never fabricated — so only 2/5
PS-mandated stages (IA, C2) are demonstrable plus IMPACT as CIC-extra.
Unsupported stages are not fabricated.
CTU-13 Phases 58-60 use Scenario 6 for development, Scenario 11 for
external validation/threshold selection, and official Scenario 12 (NSIS.ay)
as the untouched final holdout; no Scenario 12 row influences fitting,
preprocessing, model choice, or threshold selection. See `results/benchmark_table.csv` for the full
model-vs-baseline comparison.
Live-tier limits: verified on loopback only (non-loopback behavior
unmeasured); drift guard flags 9/400 real day0302 windows as
degraded/unreliable (documented tail behavior); Phase 75 (active probing)
and Phase 78 (demo) not started — neither Stop Gate confirmation occurred.
