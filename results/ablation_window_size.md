# Phase 31 — Window-size ablation (5s / 10s / 30s)

Same data (capped day14/day15/day28 train, whole day0302 validation), same
hyperparameters (`train_config.yaml`: lr 1e-3, 5 epochs, chunk 64, K=5,
seed 42). Only the window size varies. Contracts: `data/processed/graphs_5s/`,
`data/processed/graph_contracts/` (10s control), `data/processed/graphs_30s/`.

## Window counts

| Window | Train windows | Val windows | Total |
|---|---|---:|---:|
| 5s | 19,974 | 6,285 | 26,259 (~1.99x control) |
| 10s (control) | 10,059 | 3,143 | 13,202 |
| 30s | 3,369 | 1,048 | 4,417 (~0.33x control) |

Counts match expectation (~2x at 5s, ~1/3 at 30s).

## Training

| Window | Train loss (ep1-5) | Val loss (ep1-5) | Best | Time |
|---|---|---|---|---|
| 5s | 0.1829, 0.0912, 0.0625, 0.0522, 0.0537 | 0.3469, 0.3692, 0.4139, 0.6187, 0.6823 | ep1, 0.3469 | 20.6s |
| 10s | 0.2647, 0.1222, 0.1032, 0.0883, 0.0845 | 0.6115, 0.6836, 0.6784, 0.8365, 0.8864 | ep1, 0.6115 | 9.8s |
| 30s | 0.6966, 0.3270, 0.2663, 0.2130, 0.2062 | 0.5716, 0.7138, 0.8188, 0.5769, 0.5583 | ep5, 0.5583 | 3.7s |

Checkpoints: `python-ml/weights/world_model_{5s,v1,30s}.pt` (603KB each).
Loss curves: `results/loss_curve{,_5s,_30s}.png`; logs: `results/{training_log,ablation_5s_training_log,ablation_30s_training_log}.json`.

## Evaluation (held-out day0302, C2-only — see diagnostic below)

| Window | Inf AUC-ROC | Inf AUC-PR | Inf F1@0.5 (P/R/FPR) | Stage macro-F1 | Rollout lead (0.5 thresh) | Prob trace |
|---|---|---|---|---|---|---|
| 5s | 0.4804 | 0.1594 | 0.0000 (0/0/0) | 0.0000 | none (flat ~0.25) | std 0.044, flat |
| 10s | 0.4838 | 0.1595 | 0.0000 (0/0/0) | 0.0000 | none (flat ~0.16) | std 0.059, varies |
| 30s | 0.4349 | 0.1853 | 0.0000 (0/0/0) | 0.0000 | none (flat ~0.13) | std 0.056, varies |

Val base rate: 481/3143 malicious at 10s (~15%). Full JSON:
`results/ablation_eval.json`; rollout curves: `results/rollout_*s_attack*.png`.

## Step 0 diagnostic (stage macro-F1 = 0.0) — data coverage, not modeling

The 10s training run used **all four selected days** (not one): train =
day14 + day15 + day28 (10,059 windows), val = whole day0302 (3,143 windows).

Per-stage window counts (`NONE/-1` = benign):

- day14: benign 2,678, Initial Access 575 (rest 0)
- day15: benign 3,085, Impact 328 (rest 0)
- day28: benign 2,943, Initial Access 450 (rest 0)
- day0302: benign 2,662, Command-and-Control 481 (rest 0)
- Train total: benign 8,706, IA 1,025, Impact 328; C2 **0**
- Val total: benign 2,662, C2 **481**; IA/Impact **0**

Three of six stages (Reconnaissance, Lateral Movement, Exfiltration) appear
**nowhere**; the validation stage (C2) is **entirely absent from training**,
and the training stages (IA, Impact) are **entirely absent from validation**.
The stage head therefore cannot score above 0.0 macro-F1 on this split, and
the infiltration head's AUC-ROC ~0.48 (chance) shows the same unseen-class
problem affects detection too — the model never saw C2 dynamics. The rollout
curves are flat because predicted probabilities never approach 0.5 for any
variant. This is a data-split artifact, not a window-size effect, and it hits
all three variants equally — so the ablation comparison remains fair
like-for-like, but **no window size can win on detection quality here**.
Deferred to Phase 34 (multi-day/stage-coverage fix: stratified or
multi-day validation containing seen stages), per recommendation (a).

## Decision — winner: 10s (retain control)

No variant demonstrates infiltration detection (all AUC-ROC <= 0.49, all
F1@0.5 = 0.0, all rollout leads none). With detection tied at zero, the
choice falls back to training dynamics and cost:

- 5s doubles windows (26,259) and time (20.6s) for no gain (AUC 0.4804).
- 30s trains fastest (3.7s) but has the worst ranking (AUC 0.4349) and the
  coarsest early-warning granularity (each window = 30s of traffic).
- 10s matches 5s on ranking (0.4838 vs 0.4804), keeps the finest useful
  granularity among the viable options, and is the existing control —
  keeping it avoids needless churn before Phase 32.

**Winner: 10s.** Keep `data/processed/graph_contracts/` as canonical.
Kept for the record: all three `.pt` files, all loss curves/logs, and this doc.
Deleted after evaluation: `data/processed/graphs_5s/`, `data/processed/graphs_30s/`.
