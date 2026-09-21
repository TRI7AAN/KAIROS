# KAIROS — SIH Judge Brief (PS 26153: AI-based Network Attack Forecasting)

> One line: KAIROS learns how network traffic *evolves* — P(S_t+1 | S_t) — rolls
> it K steps forward, and warns *before* compromise with stage + evidence.
> Fully offline, explainable, reproducible.

## 1. Does KAIROS align with the PS? — Yes, point by point

| PS requirement | KAIROS proof | Artifact |
|---|---|---|
| Represent state as feature vectors / graphs | Per-10s host-flow graph snapshots (`kairos.graph.v1`); CIC vector mode `__network__` + real CTU-13 topology | `GraphConstructionService.java`, `Ctu13PacketContractService.java`, `docs/graph-contract-v1.md` |
| Learn P(S_t+1\|S_t) with LSTM/Transformer/GNN/latent | GraphSAGE encoder + causal Transformer dynamics, teacher-forced MSE next-state loss | `model/encoder_gnn.py`, `model/dynamics_transformer.py`, `training/world_model_trainer.py` |
| Flow-level features (NetFlow/IPFIX) | 80 CICFlowMeter cols: IPs/ports, TCP flags, proto, bytes/pkts, duration, IAT mean/std/max, bidir ratios | `IngestionService.java`, `data/cic_ids_2018_manifest.yaml` |
| Packet-level features (PCAP) | TTL mean/var, TCP window trend, frag, retrans, payload mean/std/skew, seq-vs-rand port-scan | `cpp-engine/src/feature_extractor.cpp`, `Ctu13PacketContractService.java` |
| Train on labelled open data, transitions from timelines | 800K capped flows → 13,202 windows; stage labels from published CIC timelines | `CicGraphDatasetService.java`, `configs/train_config.yaml` |
| K-step rollout → infiltration probability time-series | `dynamics.rollout(states,K)` → `forecast_heads` sigmoid; timeline Now+T+1..T+K | `app.py:PredictionService.predict`, `ProbabilityTimeline.jsx` |
| MITRE stage mapping (Recon/IA/Lateral/C2/Exfil) | 6-class softmax head (5 PS stages + IMPACT); heuristic cross-check | `model/forecast_heads.py`, `results/phase34_mitre_crosscheck.json` |
| Explainability: attention / SHAP, no black box | Causal attention summary + TreeSHAP surrogate top-5, latency <2s | `explain/shap_explain.py`, `results/phase40_surrogate_metrics.json` |
| Open-source + weights + reproducible config | Weights committed, seed-42, exact yaml + history + load test | `weights/world_model_v1.pt`, `results/training_log.json`, `training/load_test_checkpoint.py` |
| Baseline comparison (F1/P/R/FPR) showing value | Same-feature LR vs deployed KAIROS head on identical 60s future task/test; external CTU stress test | `results/benchmark_table.json`, `baseline/logistic_regression.py` (tag `baseline-v1`) |
| Demo interface accepting PCAP/CSV, offline, no cloud | Java `/forecast/upload` accepts CSV/PCAP/PCAPNG + React console; Gemini optional-off | `ForecastController.java`, `react-ui/src/App.jsx`, `scripts/verify_offline.sh` |

Honest limits (stated, not hidden): only 3/6 stages appear in selected CIC
days; the external CTU Scenario-6-to-11 test has severe false positives even
though the primary same-task CIC benchmark improves every required binary
metric. Unsupported stages and absent CTU stage labels are never fabricated.

## 2. Why static classifiers fail (the PS core insight)

```
STATIC CLASSIFIER (what PS rejects):

  Flow A ──► label?      each flow judged alone
  Flow B ──► label?      order thrown away
  Flow C ──► label?      ──► reacts only AFTER malicious flow crossed wire

  Port scan (slow, 1 port/10s)  vs  benign burst  ──► look identical in isolation

WORLD MODEL (what KAIROS does):

  S_t ──► P(S_t+1|S_t) ──► S_t+1 ──► P(S_t+2|..) ──► S_t+2 ... ──► S_t+K
   │                                                              │
   └─ current graph ── causal history ──► converges to compromise? ──► WARN EARLY
```

Infiltration is a *process*: probe → exploit-shaped payloads → fan-out →
beaconing → exfil. A per-flow label sees none of the arrows. KAIROS learns the
arrows.

## 3. The core idea in one equation

```
Learn:  P(S_t+1 | S_t)   distribution over NEXT network state given current

Roll:   S_t → M(S_t) → Ŝ_t+1 → M(Ŝ_t+1) → Ŝ_t+2 ... → Ŝ_t+K   (autoregressive,
        feeding own predictions back — no teacher forcing at inference)

Score:  infiltration head σ(Ŝ) per step → timeline [p_now, p_T+1 ... p_T+K]
        stage head softmax(Ŝ) → [INITIAL_ACCESS ... IMPACT]
```

`M` = GNN encoder (space: who talks to whom) + Transformer (time: what leads
to what). Training is supervised dynamics: timelines tell us which windows are
IA/IMPACT/C2, so next-state + head losses have ground truth.

## 4. Two-level features — why both are required

```
FLOW-LEVEL (aggregate, NetFlow/IPFIX — sees floods):
  5-tuple, TCP flags SYN/ACK/FIN/RST/PSH/URG, proto, bytes/pkts, duration,
  IAT mean/std/max, TotLen fwd/bwd, Down/Up ratio
  Example: SYN flood = huge SYN count + SYN:ACK ratio spike in one window

PACKET-LEVEL (timing/sequence, PCAP — sees low-and-slow):
  TTL mean/variance, TCP window trend (slope), frag count, retrans count
  (dup seq), payload mean/std/skew from header lens, truncated count,
  port-scan: unique dst ports/srcIP + sequential-ratio (|p_i − p_{i-1}|==1)
  Example: recon scan = 1 SYN/10s to sequential ports, TTL stable, window flat
  → invisible to flow thresholds, visible to packet sequence
```

C++ does per-packet loops natively (17.4M packets scanned); Java merges
flow+packet per 5-tuple per window.

## 5. System architecture (4 layers, offline by default)

```
Raw PCAP (3.1GB CTU-13) / CSV (4 CIC days, 800K capped flows)
        │
        ▼
[C++ cpp-engine] packet features + port-scan ──JNI──►
        │  FlowFeatures{ttl, window_trend, frag, retrans, payload stats}
        ▼
[Java java-engine] ingest → 10s windows → host-flow graphs → kairos.sequence.v1
        │  IngestionService → WindowingService → GraphConstructionService
        │  POST /predict {contract, rolloutSteps} ──OkHttp──►
        ▼
[Python python-ml Flask]  GNN encode → Transformer dynamics → K-rollout
        │  → sigmoid infiltration + softmax 6-stage + TreeSHAP top-5 + attention
        │  JSON {probability, predicted_stage, top_5_features, attention, rollout}
        ▼
[Java narrative]  offline-local DEFAULT (deterministic template)
                  gemini-online ONLY if ONLINE_MODE=true AND key present
        │  POST /forecast, POST /forecast/upload (CSV 750MiB cap)
        ▼
[React react-ui]  timeline (Now+T+1..T+5 + 60% alert) + flagged table
                  + stage overlay + narrative badge (Local/Gemini)
```

Browser never calls Python directly. Python never touches raw traffic — Java owns
graphs. Gemini never touches prediction — narrative only.

## 6. What is a "state"? (graph snapshot)

```
CIC vector mode (CSVs lack IPs — honest fallback):
  nodes: [__network__ {flow_count, bytes, uniq_ports, syn/ack, topo=0}]
  edges: [__network__ → __network__ {80 CIC feats × mean/std/max/sum}]
  topologyAvailable=false — never invent IPs

CTU-13 packet mode (pcap retains headers — real topology):
  nodes: [147.32.84.165 {..., topo=1}, 10.0.0.5 {...}, ... 443 hosts]
  edges: [hostA → hostB {packet.*: count, ttl, window_trend, payload...}]
  topologyAvailable=true

Bounded sample: 20k packets → 1263 flows → 443 hosts / 1 window
```

Same 8 node features in both modes; edge schema differs by design — the loader
rejects mismatches instead of mis-scoring (see §8).

## 7. Live walkthrough (real numbers from this repo)

```
Input:  react-ui/public/sample-attack.csv (10 CIC rows, benign→Infiltration)
Java:   CicDatasetExporter → /tmp/sample-contract.json (10 windows, 10s each)
Python: PredictionService.predict(contract, K=5)
        encoder(Batch 10 graphs) → [1,10,64] → dynamics → heads
        immediate p=0.590 stage=COMMAND_AND_CONTROL
        rollout p=[0.59,0.44,0.46,0.47,0.47] stages=[C2,IA,IA,IA,IA] max=0.59
        attention: 10 ctx, top idx 9/8/5..., future_mass=0.0 (causal ✓)
        SHAP (ExtraTrees R2 0.9746): top drivers + latency 187–219ms (<2000ms ✓)
Java:   LocalNarrative → "High risk: 59.0% ... next state command and control.
        Primary drivers were ... The 5-window rollout peaked at 59.0%..."
React:  risk stamp 59.0%, Below threshold (60%), peak 59.0%, 219ms,
        blue trajectory Now→T+5, stage chips, evidence table (↑/↓), green badge
        "Local · offline"
```

Threshold 0.6 is UI escalation only — model outputs raw probability.

## 8. Benchmarks (task-aligned and reproducible)

```
Primary CIC 60-second future-window task (same features/target/test):
  Logistic LR   F1 0.6770  P 0.6331 R 0.7275 FPR 0.2640 AUC 0.7923
  KAIROS head   F1 0.7390  P 0.6696 R 0.8245 FPR 0.2548 AUC 0.8604

Absolute KAIROS improvement:
  F1 +0.0620, precision +0.0365, recall +0.0971,
  FPR reduction 0.0092, ROC-AUC +0.0681.

Temporal proves itself (same learner, history vs no-history, fixed 0.5):
  current-only  F1 0.6790  AUC 0.8466  (1284 feats)
  history-6     F1 0.6871  AUC 0.8594  (6420 feats)
  -> +0.0081 F1, +0.0128 AUC from history alone (50 trees;
     results/temporal_ablation.json; full 150-tree calibrated:
     +0.0620/+0.0681 above).

External zero-shot: train S6, validate S11, final untouched S12 (10s):
  Logistic LR   F1 0.3683  P 0.2695 R 0.5816 FPR 0.7410
  KAIROS head   F1 0.4746  P 0.3281 R 0.8571 FPR 0.8249
  Longer horizons regress (disclosed): h3 F1 -0.1203, h6 F1 -0.0324.
```

Two-component forecasting architecture: GNN-Transformer learns P(S_t+1|S_t) for K-step rollout
(120s early-alert, partial — threshold-cross not rising trajectory) and causal
attention; calibrated infiltration probability comes from a separate ExtraTrees temporal forecasting component on
the same backward-only summaries (ExtraTrees 150, seed 42). Legacy
next-window GNN head (F1 0.3545) retained as rollout/attention diagnostic.
The primary benchmark uses backward-only histories, per-day final-20%
untouched tests, and leave-one-source-day-out development calibration. The
external result shows limited generalization: KAIROS improves F1,
precision, and recall but over-alerts. Scenario 12 is never used for fitting,
preprocessing, model choice, or threshold selection. Prevalence shift
(dev 7.7% vs test 38.5%) and near-trivial CIC stage separability (0.999→1.0)
are disclosed. See `results/benchmark_table.json`,
`results/ps_aligned_benchmark.json`,
`results/ctu13_unseen_scenario12.json`, and
`results/temporal_ablation.json`.

## 9. Explainability (no black box)

```
Per prediction:
  top_5_features: [{feature, value, shap_value}]  e.g. forecast_history.last
  attention_summary: {context_windows, top_context_for_final_query
    [{context_index, windows_before, seconds_before, weight}], 
    causal_future_attention_mass=0.0}
  UI: SHAP table (↑ raises / ↓ lowers, never "causes") + attention heatmap
      artifact results/phase39_attention_heatmap.png, phase41_shap_global_importance.png
```

SHAP comes from a distilled ExtraTrees surrogate (fidelity R2 0.9777 — surrogate
≈ teacher, not detector ≈ truth). Attention is causal-masked; future mass must
be 0 — tested. SHAP scope is teacher-fidelity only; attention scope is temporal
attribution over prior latents, not causal proof.

## 10. How to run the offline demo (3 terminals)

```bash
# 1. Python ML (private, :5000)
PYTHONPATH=python-ml .venv/bin/python python-ml/app.py
# 2. Java engine (public, :8080)
(cd java-engine && ./mvnw spring-boot:run)
# 3. React (dev, :3000) — use `npm start`, there is no `npm run dev`
(cd react-ui && npm start)   # or serve build: npx serve -s build
# Upload react-ui/public/sample-attack.csv → timeline + evidence + local briefing
# Offline proof: ONLINE_MODE=false ./scripts/verify_offline.sh
```

Cold-start + full tests: `ctest` (C++ 1/1), `./mvnw test` (Java 30),
`PYTHONPATH=python-ml pytest` (Python 23), all green; baseline freeze
`git diff baseline-v1 -- python-ml/baseline/` empty.
