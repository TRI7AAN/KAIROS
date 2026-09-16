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

## Current measured results

The converged logistic baseline (frozen, `results/baseline_metrics.json`) uses
the strict final 20% of the joined 13,202-window sequence as a future holdout
(10,561 train / 2,641 test): binary F1 **0.3096**, precision **0.5730**,
recall **0.2121**, and false positive rate **0.0352**. Its stage macro-F1 is
**0.0** because all 481 malicious holdout windows are Command-and-Control, a
class not present in the prior training period. This is a meaningful
generalization failure, not a parsing bug.

The end-to-end world-model run uses the first three capped days for training
(10,059 windows) and 2 March for validation (3,143 windows). Training loss is
`[0.2647, 0.1222, 0.1032, 0.0883, 0.0845]`; validation loss is
`[0.6115, 0.6836, 0.6784, 0.8365, 0.8864]`. The epoch-1 checkpoint
(`python-ml/weights/world_model_v1.pt`, 603KB) is retained and passes the
forward + K=5 rollout load test (`LOAD TEST PASS`).

## Known limitations and next phase

The official processed CIC CSVs omit endpoint IPs. They therefore exercise
vector mode through the explicit `__network__` fallback, while real host
topology is available for PCAP/enriched-flow input. The selected days contain
only three of six stage classes; unsupported stages are not fabricated.
Phase 31 should compare 5/10/30-second windows, followed by Phase 32's rollout-K
and GNN-vs-flat ablation.
