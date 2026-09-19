# KAIROS — Final Hardcore Regression + Audit Review

Date (UTC): 2026-09-19
Scope: full audit (Phases 0–78) + full regression (C++, Java, Python, React, checkpoint).
Method: everything re-ran fresh today; every value re-read from disk. No summaries from memory.

---

## A. Final regression (all green)

| Layer | Command | Result (today) |
|---|---|---|
| Checkpoint | `/home/mystic/KAIROS/.venv/bin/python training/load_test_checkpoint.py` (workdir `python-ml/`) | **PASS** — `epoch=1 val_loss=3.915369`, forward mean -0.0567, K=5 rollout ok |
| Python | `/home/mystic/KAIROS/.venv/bin/python -m unittest tests.test_app tests.test_explainability tests.test_phase32_metrics tests.test_live_drift` (workdir `python-ml/`) | **15/15 OK** |
| C++ | `/home/mystic/KAIROS/.venv/bin/ctest --output-on-failure` (workdir `cpp-engine/build`) | **3/3 PASS** — feature 0.01s, live_capture 6.3s, live_emitter 32.6s |
| Java | `./mvnw -o test` with `JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64` (workdir `java-engine/`) | **59 run, 0 fail, 1 skipped, BUILD SUCCESS** (only skip: `RealCicCsvIntegrationTest`) |
| React | `npm run build` (workdir `react-ui/`) | **Compiled successfully** |
| Baseline freeze | `git diff baseline-v1 -- python-ml/baseline/ \| wc -l` | **0 lines = untouched** |

Note: this session fixed two real Wireshark-4.2.2 incompatibilities that blocked C++ live tests:

1. `dumpcap -D -M` emits TSV, not JSON — added TSV fallback in `cpp-engine/src/live_capture.cpp:221-304` and `java-engine/src/main/java/com/networkwm/live/ProcessCaptureBackend.java:281-435`.
2. `dumpcap` no longer accepts `-F pcap` — switched all 8 `execl` branches to `-P` (`cpp-engine/src/live_capture.cpp:479-518`).

Effect: C++ went 1/3 → 3/3; Java live-session test went from skipped to actually running (59/1 skip vs prior 59/2).

---

## B. Phase verdicts 0–78

**Complete (verified with artifacts):** 0–32, 34–49, 51–57, 63, 66–74, 76, 77.

**Partial:**

- 33 — `proof_status: "partial"` (`results/phase33_rollout_proof.json:10-13`): 2/2 attacks × 120s lead but 0 material near-onset rise.
- 50 — MockMvc upload-to-response test exists (`ForecastUploadTest.java:14-19`) but Python client is mocked (per `docs/phase-status.md:56-57`).
- 58 — docs contradict; adapter code exists only untracked (see Section C.7).
- 61 — `results/benchmark_table.csv` exists (5 rows, threshold 0.5) but CTU-13 row pending.
- 62 — README rewritten (570 lines) but `docs/architecture.md:42,44` stale (GAT/LSTM).
- 65 — verified in-place only; roadmap admits "no clean-clone" (`README.md:475`).

**Not started (correctly absent):** 59, 60, 64, 75, 78.

### Phase table 0–65 (one-line evidence each)

| Ph | Verdict | Evidence |
|---|---|---|
| 0 | Complete | 4-layer skeleton (`cpp-engine/ java-engine/ python-ml/ react-ui/` + `.gitignore` + `.env.example`); `docs/implementationplan.md:17-19`, `README.md:410` |
| 1 | Complete | Toolchain pins: JDK 21, Python 3.13 (`torch==2.14.0+cpu`), Node 24.21.0 — `README.md:170,172-179,411` |
| 2 | Complete | 4 CIC days capped 200K/day seed 42 via `python-ml/pipeline/downsample_flows.py`, manifest `data/cic_ids_2018_manifest.yaml`; `docs/phase-status.md:5-8` |
| 3 | Complete | Scenario 6 truncated capture 38,705,338 pkts / 7749.87s SHA-verified, excluded from scoring; `docs/phase-status.md:9-12` |
| 4 | Complete | `cpp-engine/src/feature_extractor.cpp:1` parses PCAP/PCAPNG; 17,412,467-packet scan clean per `README.md:60-61` |
| 5 | Complete | `PortScanPattern::sequential/randomized` at `cpp-engine/src/feature_extractor.cpp:195-203` |
| 6 | Complete | ctest 3/3 + `libkairos_native.so`; `README.md:64`, `docs/phase-status.md:126` |
| 7 | Complete | `java-engine/.../bridge/CppBridge.java:15,19-31` typed JNI bridge; `CppBridgeIntegrationTest.java` exists |
| 8 | Complete | `IngestionService.java:155` timelines + NaN/Inf sanitize `:118-120,:247-272` |
| 9 | Complete | 10s windowing via `WindowingService`/`CicGraphDatasetService.java:54-71`; 10s won ablation (`results/ablation_window_size.md:67-79`) |
| 10 | Complete | Host-flow snapshots (`GraphConstructionService`, `CicGraphDatasetService`); contract nodes/edges per `docs/graph-contract-v1.md:7-16` |
| 11 | Complete | `CONTRACT_VERSION="kairos.sequence.v1"` at `GraphContractService.java:25` and `python-ml/pipeline/graph_builder.py:15-16` |
| 12 | Complete | Flattening (`flatten_graph` in `python-ml/explain/shap_explain.py`, used `app.py:133`; flat 1,284-d encoder `python-ml/model/encoder_flat.py`) |
| 13 | Complete | `StandardScaler` train-only + chronological split at `python-ml/baseline/logistic_regression.py:103-132` (`random_state 42`) |
| 14 | Complete | 6-class stage LR artifacts `python-ml/weights/baseline_stage_lr*.joblib`; metrics `results/baseline_metrics_indist.json:53-121` |
| 15 | Complete | Binary LR artifacts `baseline_binary_lr*.joblib`; binary block `results/baseline_metrics_indist.json:30-52` (F1 0.7096774193548387) |
| 16 | Complete | Tag `baseline-v1` exists; `git diff baseline-v1 -- python-ml/baseline/` is empty (verified live) |
| 17 | Complete | GraphSAGE 2-layer `SAGEConv` at `python-ml/model/encoder_gnn.py:45-47`; no GAT anywhere in `python-ml/` |
| 18 | Complete | Mean/attention pooling at `python-ml/model/encoder_gnn.py:96-101` |
| 19 | Complete | `test_encoder_and_linear_head_can_overfit_small_sanity_set` at `python-ml/tests/test_encoder_gnn.py:54` |
| 20 | Complete | Variable-size batching via `Batch.from_data_list` (`python-ml/training/evaluate_ablation.py:63`, `load_test_checkpoint.py:63`) |
| 21 | Complete | Causal Transformer 2L/4H at `python-ml/model/dynamics_transformer.py:39-64`; no LSTM in `python-ml/` |
| 22 | Complete | Teacher-forced MSE `next_state_loss` at `dynamics_transformer.py:108-113` |
| 23 | Complete | 5-epoch checkpointed runs w/ grad-clip (`train_config.yaml:50-60`; per-config logs `results/phase32_*_training_log.json`) |
| 24 | Complete | Loss curves committed (`results/loss_curve*.png`); val diverges after ep1 (`phase32_completed.json:95-101`: 5.18→3.915→3.94→4.49→5.98) |
| 25 | Complete | `rollout()` at `dynamics_transformer.py:116-128`; K=3 selected (`phase32_completed.json:2167` `"k_winner": 3`) |
| 26 | Complete | Sigmoid infiltration head at `forecast_heads.py:17,24-25` |
| 27 | Complete | 6-class softmax stage head at `forecast_heads.py:18,27` (`stage_count 6`, `train_config.yaml:47`) |
| 28 | Complete | Focal joint loss, weights 0.5/3.0/3.0 α=0.75 at `forecast_heads.py:39-107`; winner tag `alpha075_050_3_3` (`phase32_completed.json:1062`) |
| 29 | Complete | End-to-end 5-epoch run on capped 4-day data (10.78s, `phase32_completed.json:105`); canonical split 10589/2649 (`:76-77`) |
| 30 | Complete | `python-ml/weights/world_model_v1.pt` (617,725 B ≈ 603 KB) + loader asserts `kairos.world-model.v1` (`load_test_checkpoint.py:24,35-37`). Config record stale (see Section C) |
| 31 | Complete | 5s/10s/30s ablation, winner 10s; coverage-gap diagnosis (`ablation_window_size.md:67-81`, step-0 table `:31-35` all F1 0.0) |
| 32 | Complete | Loss/K/encoder ablations in `phase32_completed.json` (4 loss-grid entries, `encoder_winner: gnn :1549`, GNN F1 0.3545 vs flat 0.0 `:1347-1355`); checkpoint ep1 val_loss 3.9153693893621133 (`:94-102`) |
| 33 | Partial | `proof_status: "partial"` (`phase33_rollout_proof.json:12`): 2/2 × 120s lead but `attacks_with_material_probability_rise: 0` (`:10-13`), deltas −0.0017/−0.0009 (`:44,114`) |
| 34 | Complete | `result: "weak_agreement"` (`phase34_mitre_crosscheck.json:80`); observed IA/C2/Impact only (`:70-74`), observed-macro 0.06672571597283732 (`:68`) |
| 35 | Complete | Confusions IA→C2 697, Impact→C2 206 (`phase35_class_error_analysis.json:111-122`); `worst_supported_class: INITIAL_ACCESS` (`:123`) |
| 36 | Complete | `corrections_applied: 0`, `ambiguous_or_mismatched_windows: []` (`phase36_label_audit.json:36-39`) |
| 37 | Complete | `decision: retain_six_class_external_schema_no_merge` (`phase37_stage_set_decision.json:3`); unsupported = Recon/Lateral/Exfil (`:9-13`) |
| 38 | Complete | Frozen-backbone fine-tune observed-macro 0.0667→0.330210463368684, best ep7 (`phase38_stage_finetune.json:92,141,188`); infiltration Δ 0.0 (`:1391`); stamped `world_model_v1.pt` (`:1392`) |
| 39 | Complete | Shape `[2,1,4,64,64]` (`phase39_attention_summary.json:3-9`), future mass 0.0 (`:75`), row-err 1.19e-07 (`:76`) |
| 40 | Complete | ExtraTrees R² 0.9777148326649993, MAE 0.009340423584263647 (`phase40_surrogate_metrics.json:17-18`); 10,555/2,639 rows (`:12-13`) |
| 41 | Complete | TreeSHAP max additivity err 1.27675647831893e-15 (`phase41_shap_validation.json:5`); top feature `forecast_history.last_probability` (`:7-10`) |
| 42 | Complete | Schema `{probability, predicted_stage, top_5_features, attention_summary}` + `artifact_version: kairos.prediction.v1` (`phase44_predict_smoke.json:3-69`; built `app.py:160-165`) |
| 43 | Complete | 30 runs: median 108.24588299965399 ms / p95 110.2707369498603 ms / max 111.327 ms < 2s (`phase43_explainability_latency.json:1-9`) |
| 44 | Complete | `POST /predict` at `app.py:222-235` (steps 1–10 validated `:80-85`); missing/corrupt surrogate → HTTP 503 (`:210-212`, `SurrogateUnavailableError :41-42`) |
| 45 | Complete | `PythonMlClient.java:25` real OkHttp client w/ typed `PredictionResponse` |
| 46 | Complete | `@RequestMapping("/forecast")` at `ForecastController.java:28` + `/forecast/upload` (client posts it, `react-ui/src/api/client.js:12`) |
| 47 | Complete | Deterministic local narrative, mode `offline-local` (`LocalNarrativeService.java:50`) |
| 48 | Complete | Gemini service key-gated (`GeminiNarrativeService.java:51,96` requires `GEMINI_API_KEY`) |
| 49 | Complete | `ONLINE_MODE`+key toggle w/ `offline-local-fallback` (`NarrativeModeService.java:42-52`) |
| 50 | Partial | MockMvc upload-to-response test exists (`ForecastUploadTest.java:14-19`) but Python client is mocked — not a live full-chain test |
| 51 | Complete | Upload wiring posts `/forecast/upload` (`react-ui/src/api/client.js:12`) |
| 52 | Complete | `react-ui/src/components/ProbabilityTimeline.jsx:16` |
| 53 | Complete | `react-ui/src/components/FlaggedFlowsTable.jsx:7` (wired `App.jsx:253` to SHAP `topFeatures`) |
| 54 | Complete | `react-ui/src/components/StageAnnotations.jsx:13` (wired `App.jsx:251`) |
| 55 | Complete | `NarrativePanel.jsx:3` w/ mode badge (wired `App.jsx:252` to `result.narrative`) |
| 56 | Complete | Network-disabled full-stack upload verified per docs (`README.md:156-159,349-350`); evidence documentary |
| 57 | Complete | `Load sample attack` button (`App.jsx:209`) loading `react-ui/public/sample-attack.csv` (exists) |
| 58 | Partial | Docs contradict; code untracked (see Section C.7) |
| 59 | Not started | No frozen-model zero-shot inference on non-Scenario-6 data; CSV CTU-13 row all-null (`benchmark_table.csv:6`) |
| 60 | Not started | No CTU-13 F1/precision/recall/FPR anywhere (explicitly null) |
| 61 | Partial | `benchmark_table.csv` (5 rows, threshold 0.5) exists but CTU-13 row pending; untracked `benchmark_table.json` stale and divergent |
| 62 | Partial | README rewritten (570 lines, verified commands `README.md:513-549`); `docs/architecture.md:42,44` still stale (`GraphSAGE/GAT`, `Transformer / LSTM`) |
| 63 | Complete | Negative result, tag `phase63-complete` exists; ep3 F1 0.31322033898305085 < canonical, checkpoint KEPT, archive `world_model_v1_pretune_baseline_loss.pt` (`phase63_retrain.json:100-109,707-708`) |
| 64 | Not started | No pitch-deck file anywhere (only stray untracked `docs/KAIROS_Judge_Brief.pdf` + `sih_judge_brief.md`) |
| 65 | Partial | Verified in-place only; roadmap admits "no clean-clone" (`README.md:475`) |

### Phase table 66–78 (one-line evidence each)

| Ph | Verdict | Evidence |
|---|---|---|
| 66 | Complete | `docs/live_capture_threat_model.md:1-227` normative; API `13-105`, lifecycle `169-208`, 8-row model `212-221` |
| 67 | Complete | `cpp-engine/src/live_capture.cpp:212-405` TSV fallback + `479-518` all `-P`; fresh 8 ifaces / 47 pkts / limit-4 exit 0; bounds `407-449`, counters `152-186`, dual `-a` + `wait_for_exit:615-635` |
| 68 | Complete | `cpp-engine/src/live_emitter.cpp:212-261` observe/flush, `270-312` same-schema JSON; fresh 212 replayed → 4 windows; `live_emitter_test.cpp:267-297` 10s + `ttlMean` checks pass |
| 69 | Complete | `LiveSessionService.java:425-474` supervisor dual-bound, `152-180` stop, `ProcessCaptureBackend.java:60-110` helper spawn; no-orphan assert `LiveSessionServiceTest.java:56-57`, real 5s `lo` `157-207` |
| 70 | Complete | `ConsentGateService.java:162-167` empty-deny, `153-158` active-deny, `223-240` audit, `242-275` resolve/pin; `ConsentGateServiceTest` 7/7 per surefire |
| 71 | Complete | `LiveSequenceAdapter.java:62-138` snapshot + `live window N` rejects `64-107,186-229`; `LiveSequenceAdapterTest` 4/4 |
| 72 | Complete | `python-ml/live_drift.py:38-41` 12/2% + 20/5%, `71-120` assess; `app.py:29,140,169-176` same-checkpoint + quality wiring; `.npz` 1284 feats, `live_drift_calibration.json:7-13` 391/8/1; pytest 3/3 |
| 73 | Complete | `LiveDashboard.jsx:52-87,106,115` start/stop + quality + badge; `QualityBadge.jsx:3-10,16` ok/degraded/unreliable; `client.js:52` `mode:'passive'` |
| 74 | Complete | `LiveCaptureController.java:169-212` `TEXT_EVENT_STREAM`, `214-229` `data:` frames; `LiveControllerTest.java:172-195` asserts `data:` + content-type; `client.js:70-81` `EventSource` |
| 75 | Not started | Zero code path: grep nmap/masscan/syn-scan hits only refusal string `LiveSessionService.java:324`; triple `passive` refusal; `Phase76ActiveRefusalTest.java:3` 3/3 |
| 76 | Complete | `results/phase76_regression.md:1-27` netns 4/4 `8-9`, refusals 3/3 `19-25` |
| 77 | Complete | `results/live_capture_performance.md:9-15` 55/204/785 pps zero-loss, `19-31` 662520/0 burst, `35-38` RSS 4116 kB flat, `42-53` backpressure via parsed `received/dropped` |
| 78 | Not started | `README.md:505` + `docs/phase-status.md:97` both `Not started`; no demo file exists |

---

## C. Numbers traceability (exact measured values)

### C.1 Canonical in-distribution world model

`results/phase32_completed.json:113-127`: tp 279 / fp 276 / fn 740 / tn 1353, precision 0.5027027027027027, recall 0.27379784102060845, **F1 0.35451080050825917**, FPR 0.1694290976058932, AUC-ROC 0.5813406540313539, threshold 0.5. K=3 and K=10 curves identical F1.

`results/benchmark_table.csv:3` reports **0.3454** / 0.5027 / 0.2738 / 0.1694 / 0.5813.

**Discrepancy:** 2·0.5027·0.2738/(0.5027+0.2738) = **0.3545**, so the CSV/phase-status/README canonical F1 **0.3454 matches no JSON and contradicts its own P/R**; raw JSON value is 0.3545. Further, `docs/phase-status.md:134` prints recall **0.2638** / FPR **0.1639**, contradicting CSV+JSON 0.2738/0.1694.

### C.2 Baseline identical-split

`results/baseline_metrics_indist.json:30-52,62-65`: F1 0.7096774193548387, P 0.6534653465346535, R 0.7764705882352941, FPR 0.2578268876611418, stage macro-F1 0.4983119471782733, 10589/2649 windows, confusion [[1209,420],[228,792]], training 12.26s, converged.

CSV row matches (0.7097/0.6535/0.7765/0.2578/0.4983). **But** `docs/phase-status.md:138-140` prints **0.6745/0.6215/0.7374/0.2793/0.4828** — identical to the superseded step-0 memo (`ablation_k_and_encoder.md:61-67`), contradicting current JSON. Legacy frozen row (`baseline_metrics.json:2-13`): 10561/2641, F1 0.3095599393019727, stage macro 0.0 — retained for provenance.

### C.3 Stage numbers

Pre-finetune six-class macro 0.033539276257722864 (phase32); observed-macro 0.06672571597283732 (phase34, phase38-before). Post-finetune observed **0.330210463368684** / six-class **0.165105231684342**, best ep7 (phase38). Per-class after: IA 0.3195402298850575 (support 697), C2 0.35359116022099446 (support 113), Impact 0.3175 (support 206); Recon/Lateral/Exfil support 0, F1 0.0.

**Provenance gap:** CSV/README/phase-status claim post-38 **0.244** (per-class IA 0.5612 / C2 0.4238 / Impact 0.4819) — **no JSON contains 0.244 or those per-class values**. Untraced live re-evaluation.

### C.4 Cross-day secondary

phase32 cross-day: F1 0.14545454545454545, P 0.13008130081300814, R 0.16494845360824742, FPR 0.20135491155438465, AUC 0.4749768167338561, stage macro 0.16666666666666666.

CSV/phase-status report **0.1489/0.1334/0.1684/0.1977/0.4714/0.0386** — **no JSON contains these values** (nearest: phase63 final_cross F1 0.13399014778325125). Methodology labeling ("different methodology… must not be compared directly") is consistent.

### C.5 Phase 63

Trajectory `phase63_retrain.json:69-130`: ep0 F1 0.555027 → ep1 **0.567128946591915 @FPR 0.8692449355432781** → ep3 **0.31322033898305085** / P 0.49892008639308855 / R 0.22826086956521738 / FPR 0.14241866175567833 / AUC 0.5843214756258235 (selected) → final stage macro 0.23970775859294793. **Split mismatch:** phase63 split 3253/3413/3393/3143 = 13202 with 10560/2642 vs canonical 10589/2649 — CSV "same windows" is false.

### C.6 Splits, thresholds, checkpoint

- Window totals: canonical docs 3253+3413+3393+3143 = **13202** vs phase32 JSON 3260+3429+3406+3143 = **13238** vs legacy whole-day 10059/3143 (`train_config.yaml:37-38`, `training_log.json`) and legacy joined 10561/2641 (`baseline_metrics.json:4-5`). Surrogate rows 10555/2639 match neither split.
- Per-class support drifts with regeneration: IA 698 vs 697 vs 694/693; C2 114 vs 113; Impact 207 vs 206 vs 204/203; malicious 1019 vs 1016.
- Checkpoint: winner `alpha075_050_3_3`, GNN, K=3, thr 0.5, loss-selected ep1, val_loss 3.9153693893621133. `world_model_v1.pt` 617,725 B; `world_model_v1_pretune_baseline_loss.pt` 617,725 B.
- Threshold 0.5 fixed everywhere. K=3 earned (2×120s lead vs K=5's 120s+50s vs K=10 none).
- Unsupported Recon/Lateral/Exfil: zero support and F1 0.0 in every JSON — consistent, correctly undisclosed as working.

### C.7 CTU-13 contradiction

`docs/implementationplan.md:56-58` claims Phase 58 "complete w/ lossy adapter" vs `README.md:468` + `docs/phase-status.md:98-100` + `benchmark_table.csv:6` = not-started/no-run. Reality: adapter code exists **only untracked** (`Ctu13PacketContractService.java:32`, `Ctu13PacketExporter.java:10`, `packet_projection.py:92`, `run_ctu13_zero_shot.py:4-6`) plus untracked dev-smoke `results/ctu13_zero_shot_attempt.json` (artifact `kairos.ctu13-development-smoke.v2`, 1 window, 443 nodes / 1263 edges, p=0.5479, quality unreliable, F1 null by design). Nothing tracked, no metric. Correct wording is "no zero-shot metric yet", not "no inference executed".

### C.8 Stale configs and hygiene

- `python-ml/configs/train_config.yaml:61-63` weights 1.0/1.0/1.0 vs actual 0.5/3.0/3.0; `:76` `k_steps: 5` vs K=3; `:28-38` whole-day-0302 validation + 10059/3143 vs primary indist split.
- `results/world_model_config.json:6-8` weights 1.0/1.0/1.0; `training_log.json` / `world_model_history.json` record the old whole-day run.
- `docs/architecture.md:42,44` still says `GraphSAGE/GAT`, `Transformer / LSTM` — neither GAT nor LSTM exists in `python-ml/`.
- Untracked `results/benchmark_table.json` stale and divergent (0.3545/0.1455/0.1666 vs CSV 0.3454/0.1489/0.244-post-38).
- Spurious tag `list` exists (points at HEAD — accidental `git tag list`).
- `git status`: 17 modified tracked files + ~35 untracked, of which 19 are `.orig` backups plus untracked CTU-13 dev files, `benchmark_table.json`, `world_model_phase32.pt`, `ctu13_zero_shot_attempt.json`.

---

## D. Live tier safety gaps (measured, non-blocking)

- **BPF wording overstates code:** `docs/live_capture_threat_model.md:29,189,226-227` claims "compile before start"; code has only length check (`LiveSessionService.java:119-121`) + `dumpcap -f` passthrough + early-exit detect. No `pcap_compile` / `dumpcap -d` pre-check exists.
- **Audit durability best-effort:** `ConsentGateService.java:237-239` swallows `IOException`; purge-safe by sibling path but file loss is silent.
- **DNS revalidation dead code:** `ConsentGateService.java:186-199` (`DNS_REVALIDATION_SECONDS:43`) has zero callers.
- **Test-count drift:** `docs/phase-status.md:75` + `results/phase76_regression.md:13-15` claim `LiveSessionServiceTest` 6/6; file has 7 `@Test`, surefire confirms 7. Totals `phase-status.md:125-126` (Java 47) stale vs current 59.
- **Lenient quality default:** `LivePredictionService.java:118-124` blanks → `"ok"`, `LiveDashboard.jsx:106` fallback `'ok'`; missing Python quality renders as ok rather than unknown.
- **Cosmetic:** `live_emitter_test.cpp:233-236` duplicated `dumpcap` SKIP block (unreachable position); emitter fresh count 212 vs doc'd 211 (1-packet loopback variance).
- **Accepted residual (documented):** header IPs/hostnames survive 256B snap, allowlist quality operator-dependent, loopback-only verification — all stated in `threat_model.md:223-227`.

Safety gates confirmed: default-empty allowlist deny (`ConsentGateService.java:162-167`), triple `mode==passive` refusal (controller 403 → gate deny → service 400), no active-probe code path (grep across all four language trees returns only refusal strings), `Phase76ActiveRefusalTest` 3/3.

---

## E. Final verdict

- **Code: GREEN.** Static pipeline + passive live tier work on loopback; all suites pass; baseline frozen; no active-probe path exists.
- **Docs/numbers: NOT GREEN.** Do not present 0.3454, 0.244, per-class triple, or 0.1489 row as measured until re-evaluated or corrected to JSON values (0.3545, 0.1651/0.3302, 0.1455/0.1667). Fix `train_config.yaml`, `world_model_config.json`, `architecture.md` GAT/LSTM lines, Phase-58 contradiction, CTU-13 wording, `phase-status` stale numbers/test counts, `benchmark_table.json` staleness. Delete spurious `list` tag + 19 `.orig` files; commit or remove untracked CTU-13/helper artifacts intentionally.
- **Scope to preserve in any demo:** loopback-only verification, 120s threshold-cross (not rising-risk trajectory), 3 unsupported MITRE stages with zero support, weak cross-day generalization, threshold-0.5 dependence, header-IP sensitivity despite `-s 256`, operator-owned allowlist required.

---

## Appendix: artifact inventory (today)

Weights (`python-ml/weights/`): `world_model_v1.pt` 604K (canonical), `world_model_v1_pretune_baseline_loss.pt` 604K, `world_model_phase32.pt` 604K, `phase32_alpha075_050_3_3_gnn.pt` 604K, `phase32_alpha090_025_5_5_gnn.pt` 604K, `phase32_alpha0923_010_10_10_gnn.pt` 604K, `phase32_alpha097_010_10_3_gnn.pt` 604K, `phase32_flat_winning_loss.pt` 745K, `world_model_5s.pt` 603K, `world_model_30s.pt` 603K, `shap_surrogate_v1.joblib` 27M, baseline `*_indist.joblib` pairs.

Results: 81 files incl. `benchmark_table.csv`, `baseline_metrics_indist.json`, `phase32_completed.json`, `phase33_rollout_proof.json`, `phase38_stage_finetune.json`, `phase39_attention_summary.json` + `weights.pt` (148K), `phase40_surrogate_metrics.json`, `phase41_shap_validation.json`, `phase43_explainability_latency.json`, `phase63_retrain.json`, `live_drift_reference.npz` (1284 feats), `live_drift_calibration.json`, `phase76_regression.md`, `live_capture_performance.md`, `ctu13_zero_shot_attempt.json` (untracked dev smoke).

Tags: `baseline-v1`, `list` (spurious), `phase63-complete`. Baseline diff empty.
