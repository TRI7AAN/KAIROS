# Implementation Plan — Network Attack World Model

Canonical 65-phase deliverable list. Each phase is a single deliverable with a
clear "done" state before moving on. Tackle one at a time.

> Stack: C++ (packet features) / Java (base engine) / Python (GNN+Transformer+SHAP)
> / Gemini API (optional narrative layer) / React (UI).
>
> **Compliance note:** the PS requires the demo to run fully offline with no cloud
> dependencies. Gemini is cloud-based, so it is built as an OPTIONAL toggle with a
> local rule-based fallback narrative generator — the core submission must pass
> fully offline; Gemini is a "bonus mode" for live demos with internet available
> (Phase 47–49).

## Progress

- **Phase 0: complete.** Repository skeleton, manifests, architecture and
  roadmap documentation, ignore rules, environment template, and service
  ownership decisions are present.
- **Phase 1: complete.** Clean C++17/CMake, Java/Maven Wrapper, Python
  3.12/PyTorch/PyTorch Geometric, and Node/React builds are verified; the
  offline environment template is present.
- **Phase 2: complete.** Four complementary CIC-IDS2018 CSV attack days are
  downloaded and verified by byte size, SHA-256, row count, and label
  distribution. Attack windows and known source anomalies are versioned in the
  dataset manifest.
- **Phase 3: in progress.** The matching raw objects are inventoried: 166.93 GiB
  compressed across four days, with the smallest full day at 37.17 GiB. Choose
  a storage/bandwidth-bounded capture strategy before downloading.
- **Phase 4: complete.** The dependency-free C++17 core parses classic PCAP
  Ethernet/raw-IPv4 traffic, aggregates directional TCP/UDP 5-tuples, and
  computes TTL, TCP-window, fragmentation, retransmission, and payload moments.
  A sanitizer-enabled deterministic synthetic-PCAP smoke test passes.
- **Phase 5: next.** Add the per-source port-scan signature detector.

---

**Phase 0 — Monorepo skeleton + README.** Create the 4-layer folder structure (cpp-engine/, java-engine/, python-ml/, react-ui/), stub files with docstrings only, populated dependency manifests (CMakeLists.txt, pom.xml, requirements.txt, package.json), .gitignore, and a README with full research writeup + architecture diagram.

**Phase 1 — Environment setup across all layers.** Verify C++17 compiler + CMake build, Java 17+ + Maven compile, Python venv + torch/torch-geometric compatibility, Node/React build, and provision `.env.example` for `GEMINI_API_KEY`.

**Phase 2 — CIC-IDS2018 acquisition.** Download processed CSVs via `aws s3 sync --no-sign-request`; select 3-4 attack days (brute-force, DoS/DDoS, infiltration, botnet) per the published schedule; verify row counts.

**Phase 3 — Raw PCAP subset pull.** Sync matching raw PCAP folders for the same selected days; confirm file sizes are reasonable before parsing.

**Phase 4 — C++ packet-level feature extractor core.** Implement `feature_extractor.cpp`/`.hpp`: parse PCAPs, compute TTL mean/variance, TCP window size trend, IP fragment flag count, retransmission count, payload size mean/std/skew per 5-tuple flow.

**Phase 5 — C++ port-scan signature detector.** Per src IP per window, count unique dst ports touched, classify sequential vs. randomized access pattern; expose as a callable function in the same C++ module.

**Phase 6 — C++ unit tests + shared library build.** Write unit tests for the feature extractor against a small known PCAP sample; build as a shared library (.so/.dll) ready for JNI/JNA linkage.

**Phase 7 — Java-to-C++ bridge (CppBridge.java).** Implement JNI or JNA bindings calling into the compiled C++ shared library; verify a round-trip call from Java returns correct feature values on a test PCAP.

**Phase 8 — Java flow CSV ingestion.** Implement flow-level CSV parsing in `IngestionService.java`: normalize CICFlowMeter headers, drop non-feature columns, clip/handle Infinity/NaN values, attach stage labels from published attack timelines.

**Phase 9 — Java windowing + host aggregation.** Bucket flows into time windows (10s default); aggregate per-host stats (byte totals, unique dst ports, SYN:ACK ratio); merge in C++-extracted packet-level features per window via the bridge.

**Phase 10 — Java graph construction.** Build per-window host-flow graph structures (nodes=hosts, edges=flows with combined flow+packet feature vectors) in Java; this becomes the state representation handed to Python.

**Phase 11 — Java-Python serialization contract.** Define and implement a JSON/Parquet schema for serializing graph snapshots + labels from Java; write the corresponding Python-side loader stub; verify one full window round-trips correctly.

**Phase 12 — Python baseline feature flattening.** Flatten the Java-exported per-window graphs into non-temporal feature rows for the logistic regression baseline.

**Phase 13 — Python time-based split + scaling.** Apply `StandardScaler`; split train/test strictly by time, never randomly shuffled across windows.

**Phase 14 — Python multinomial logistic regression.** Train on the 6-class MITRE stage label; log training time and convergence behavior.

**Phase 15 — Python binary logistic regression.** Train a second LR for binary infiltration-vs-not for direct comparison metrics.

**Phase 16 — Baseline evaluation + freeze.** Compute F1/precision/recall/FPR, save confusion matrices, log to `results/baseline_metrics.json`, git-tag `baseline-v1`, freeze this code.

**Phase 17 — Python GNN encoder skeleton.** Implement 2-3 layer GraphSAGE over each per-window graph loaded from the Java-exported format.

**Phase 18 — Pooling layer.** Implement mean/attention pooling compressing each graph into a fixed-size embedding per timestep.

**Phase 19 — Encoder overfit sanity test.** Overfit encoder + trivial linear head on ~50 windows; confirm loss drops near-zero before scaling up.

**Phase 20 — Batch pipeline integration.** Wire the encoder into a `torch_geometric` DataLoader batching variable-sized graphs across a full attack day.

**Phase 21 — Temporal dynamics model skeleton.** Implement Transformer (4-head, 2-layer) or LSTM fallback with temporal positional encoding.

**Phase 22 — Next-state training objective.** Teacher-forced next-embedding prediction using MSE/contrastive loss against the true next embedding.

**Phase 23 — Dynamics training loop.** Implement training loop with checkpointing, gradient clipping, validation split by day.

**Phase 24 — Loss curve verification.** Run several epochs; confirm the model learns transitions, not memorization.

**Phase 25 — Autoregressive rollout.** Implement K-step rollout feeding the model's own predictions back in as input for subsequent steps.

**Phase 26 — Infiltration probability head.** Sigmoid head on top of rolled-forward latent states.

**Phase 27 — MITRE stage head.** Softmax head (6 classes) sharing the same rolled-forward latents.

**Phase 28 — Joint loss + class imbalance handling.** Combine dynamics + head losses with tunable weights; use focal loss for classification heads.

**Phase 29 — Full dataset training run.** Train end-to-end on selected CIC-IDS2018 days, splitting train/val by day.

**Phase 30 — Checkpointing + config logging.** Save `weights/world_model_v1.pt` and exact training config for reproducibility.

**Phase 31 — Ablation: window size.** Compare 5s/10s/30s windows by validation F1.

**Phase 32 — Ablation: K and GNN-vs-flat.** Test K=3/5/10 and GNN vs. flattened-vector encoder; pick best combo.

**Phase 33 — Rollout proof-of-concept check.** Plot rollout probability curves for sample attacks, confirming rise before true attack timestamp; compare against frozen baseline.

**Phase 34 — MITRE heuristic cross-check.** Compare stage-head predictions against the manual mapping table.

**Phase 35 — Per-class error analysis.** Identify which ATT&CK stages the model confuses most.

**Phase 36 — Label relabeling pass.** Manually correct ambiguous timeline-derived labels.

**Phase 37 — Stage-set decision.** Decide whether to merge weak stages (e.g., Lateral Movement into Initial Access); document rationale.

**Phase 38 — Stage head fine-tune.** Retrain stage head only (freeze dynamics + encoder) with corrected labels.

**Phase 39 — Attention extraction.** Pull attention weights from Transformer/GAT layers into a heatmap format.

**Phase 40 — SHAP surrogate model.** Train a distilled gradient-boosted tree/shallow MLP approximating the world model's forecast output.

**Phase 41 — SHAP integration.** Run KernelSHAP/TreeSHAP on the surrogate; validate plausibility of top features.

**Phase 42 — Explanation object schema.** Standardize output JSON: `{probability, predicted_stage, top_5_features, attention_summary}` — this is the contract Java will consume.

**Phase 43 — Explainability latency check.** Confirm full explanation generation runs under 2 seconds per window.

**Phase 44 — Python Flask /predict endpoint.** Wrap the full inference chain (graph load -> rollout -> heads -> explain) behind a single REST endpoint returning the Phase 42 JSON schema.

**Phase 45 — Java PythonMlClient integration.** Implement the REST client calling `/predict`, parsing the JSON response into Java objects.

**Phase 46 — Java ForecastController REST API.** Expose a `/forecast` endpoint for React, orchestrating C++ extraction -> windowing/graph build -> Python inference in one request.

**Phase 47 — Local fallback narrative generator (offline-compliant).** Implement a rule-based/template narrative generator in Java (no external API) that converts the Phase 42 JSON into a readable sentence — this satisfies the PS's offline requirement as the default mode.

**Phase 48 — Gemini narrative service (optional mode).** Implement `GeminiNarrativeService.java` using the Google Gen AI Java SDK, sending the structured prediction JSON to Gemini (e.g. `gemini-2.5-flash-lite`) for a richer analyst briefing; gate behind a config flag/env check so it's skipped entirely when offline or no API key is present.

**Phase 49 — Narrative mode toggle wiring.** Wire `ForecastController` to use the Phase 47 local generator by default, switching to Phase 48's Gemini service only if `GEMINI_API_KEY` is present and a `--online-mode` flag is set.

**Phase 50 — End-to-end backend integration test.** Full chain test: PCAP/CSV upload -> C++ parse -> Java windowing/graph -> Python inference -> narrative (local or Gemini) -> single JSON API response.

**Phase 51 — React app skeleton + upload wiring.** Build file upload component calling the Java `/forecast` endpoint.

**Phase 52 — React probability timeline chart.** Render the infiltration-probability time series with an alert threshold line.

**Phase 53 — React flagged flows table.** Display top-N contributing flows per alerted window from the SHAP output.

**Phase 54 — React stage annotations overlay.** Color-code the timeline by predicted MITRE stage per window.

**Phase 55 — React narrative panel.** Display the local or Gemini-generated narrative text, with a visible indicator of which mode produced it.

**Phase 56 — Offline compliance verification.** Disable network access entirely, confirm full pipeline (upload -> timeline -> table -> annotations -> local narrative) works with zero errors and zero external calls.

**Phase 57 — Demo polish.** Add a "load sample attack" quick-load button pre-populated with a known test file; cold-restart test of the full stack.

**Phase 58 — CTU-13 pipeline adaptation.** Adapt Java ingestion + C++ extraction to compute CTU-13 features into the same schema.

**Phase 59 — CTU-13 zero-shot inference.** Run the frozen, already-trained world model on CTU-13 via the full pipeline (no retraining).

**Phase 60 — CTU-13 metrics + generalization analysis.** Compute F1/precision/recall/FPR on CTU-13; compare against CIC-IDS2018 results; note the generalization gap honestly.

**Phase 61 — Benchmark table finalization.** Compile the full comparison table: Logistic Regression vs. World Model (CIC-IDS2018) vs. World Model (CTU-13), across F1/Precision/Recall/FPR/early-warning lead time.

**Phase 62 — Documentation completion.** Finalize README and `docs/architecture.md` with reproducibility instructions, results, explainability screenshots, offline-vs-Gemini mode explanation, and limitations.

**Phase 63 — Demo video recording.** Record a 2-3 minute walkthrough covering both offline mode and the Gemini-enhanced narrative mode.

**Phase 64 — Pitch deck build.** Problem -> 4-layer architecture rationale -> benchmark results -> CII-applicability angle (offline-by-default, explainable, optional AI-narrative enhancement).

**Phase 65 — Final end-to-end reproducibility check.** Clean-clone the repo, rebuild all four toolchains from scratch, rerun training from saved config, confirm near-identical metrics, confirm the full offline demo launches with documented commands.
