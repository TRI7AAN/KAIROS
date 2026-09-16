# Phase verification status

## Completed in the current implementation

- **9-11:** timestamped 10-second windows, host aggregation, flow/packet merge,
  graph construction, and a strictly validated Java-to-Python JSON contract.
- **12-16:** non-temporal logistic baselines with chronological splitting,
  train-only scaling, binary and six-stage models, metrics, confusion matrices,
  and serialized artifacts.
- **17-20:** edge-aware GraphSAGE, mean/attention pooling, overfit sanity check,
  and variable-size graph batching.
- **21-28:** causal temporal Transformer, next-state loss, whole-day validation,
  best-checkpoint training, autoregressive rollout, shared forecast heads, and
  focal joint loss.
- **29-30:** real four-day CIC export and end-to-end training with frozen
  checkpoint, exact config, and loss history.

## Real-data evidence

| Dataset day | Emitted flows | 10-second windows | Malicious stage |
|---|---:|---:|---|
| 2018-02-14 | 1,048,575 | 3,260 | Initial Access |
| 2018-02-15 | 1,048,575 | 3,429 | Impact |
| 2018-02-28 | 613,071 | 3,406 | Initial Access |
| 2018-03-02 | 1,048,575 | 3,143 | Command and Control |
| **Total** | **3,758,796** | **13,238** | three observed classes |

The real JNI fixture and the 613,104-row infiltration CSV test both pass without
skips when their paths are supplied. Native extractor tests, all Java unit tests,
and all Python tests pass.

## Current measured results

The converged logistic baseline uses the final 20% of windows as a future
holdout: binary F1 **0.4723**, precision **0.5854**, recall **0.3959**, and false
positive rate **0.0629**. Its stage macro-F1 is **0.0** because all 485 malicious
holdout windows are Command-and-Control, a class not present in the prior
training period. This is a meaningful generalization failure, not a parsing bug.

The end-to-end world-model run uses the first three full days for training and
2 March for validation. Training loss is `[0.2751, 0.1219, 0.0987]`; validation
loss is `[0.4084, 0.5035, 0.5971]`. The epoch-1 checkpoint is retained.

## Known limitations and next phase

The official processed CIC CSVs omit endpoint IPs. They therefore exercise
vector mode through the explicit `__network__` fallback, while real host
topology is available for PCAP/enriched-flow input. The selected days contain
only three of six stage classes; unsupported stages are not fabricated.
Phase 31 should compare 5/10/30-second windows, followed by Phase 32's rollout-K
and GNN-vs-flat ablation. The Git tag for the baseline should be created only
after the current changes are reviewed and committed.
