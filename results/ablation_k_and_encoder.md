# Phase 32 — Split-design fix + K/encoder ablation

## Step 0 — Split fix: rationale

Phase 31's whole-day holdout (train day14/15/28, validate whole day0302)
validates on Command-and-Control, a stage entirely absent from training
(train stages: IA + Impact; val stage: C2 only). Infiltration AUC-ROC
~0.48 (chance) and stage macro-F1 0.0 on every window variant showed the
same unseen-class problem hits detection too — no architecture choice can
win on that split. The fix, matching the frozen baseline's strategy
(`results/baseline_metrics.json`: joined final-20%-time holdout), is a
**second, in-distribution split**: per day, train on the first 80% of the
time-ordered windows and hold out the **last 20% of each day's time
range** for validation. The whole-day holdout is KEPT as a separate,
clearly labeled **cross-day generalization stress test** — never mixed
into the primary numbers.

Per-day in-distribution split (canonical 10s contracts, ceil(20%) tails):

| Day | Total | Train (first 80%) | Val (last 20%) | Train stages | Val stages |
|---|---|---:|---:|---|---|
| day14 | 3,253 | 2,602 | 651 | benign 2,373 + IA 229 | IA 346 + benign 305 |
| day15 | 3,413 | 2,730 | 683 | benign 2,606 + Impact 124 | Impact 204 + benign 479 |
| day28 | 3,393 | 2,714 | 679 | benign 2,613 + IA 101 | IA 349 + benign 330 |
| day0302 | 3,143 | 2,514 | 629 | benign 2,147 + C2 367 | C2 114 + benign 515 |
| **Total** | **13,202** | **10,560** | **2,642** | IA 330 / Impact 124 / C2 367 | IA 695 / Impact 204 / C2 114 |

Every val stage (IA, Impact, C2) is seen in training. (Recon/Lateral/Exfil
appear in none of the four selected days — unchanged, out of scope.)

## Step 0 — Before/after (same 10s / K=5 / GNN, same hyperparameters:
## lr 1e-3, 5 epochs, chunk 64, seed 42)

| Metric | Before: whole-day-only val (Phase 31 10s row) | After: in-distribution val (PRIMARY) | After: cross-day val (SECONDARY stress) |
|---|---|---|---|
| Split | train 10,059 / val whole day0302 3,143 | train 10,560 / val joined tails 2,642 | same checkpoint, val whole day0302 3,143 |
| Infiltration F1@0.5 (P/R/FPR) | 0.0000 (0/0/0) | **0.0000** (0/0/0) | 0.0000 (0/0/0) |
| Infiltration AUC-ROC / AUC-PR | 0.4838 / 0.1595 | 0.5074 / 0.3895 | 0.5014 / 0.1560 |
| Prob operating point (mean/std/max) | ~0.16 / 0.059 / low | 0.241 / 0.034 / **0.325** | 0.241 / 0.035 / 0.324 |
| Stage macro-F1 | 0.0000 | 0.0138 | 0.0443 |
| Rollout lead (K=5, 0.5 thresh) | none (flat ~0.16) | none (max rollout prob < 0.5) | none |
| Training time | 9.8s | 9.9s | — (same checkpoint) |
| Train loss (ep1-5) | 0.2647, 0.1222, 0.1032, 0.0883, 0.0845 | 0.2475, 0.1473, 0.1283, 0.1180, 0.1102 | — |
| Val loss (ep1-5) | 0.6115, 0.6836, 0.6784, 0.8365, 0.8864 (best ep1) | 1.8567, 1.6779, 1.7460, 0.9462, **0.8119 (best ep5)** | — |

Raw JSON: `results/phase32_step0.json`. Checkpoint `world_model_v1.pt`
now stores the in-distribution run (best epoch 5 of 5). Training log:
`results/phase32_step0_indist_k5_gnn_training_log.json`; loss curve:
`results/loss_curve_phase32_step0_indist_k5_gnn.png`.

**STOP gate verdict: TRIPPED.** In-distribution F1 is still 0.0 (max
predicted probability 0.325 never reaches the 0.5 threshold), so per the
phase instructions the K and encoder ablations below are **NOT run as
architecture comparisons** — every variant would read ~0.0 and the
comparison would be meaningless. The blocker was diagnosed instead
(see next section); this is a deeper modeling problem beyond split
design, exactly the case the stop gate exists for.

## Stop-gate diagnosis — joint-loss dynamics dominance (evidence, not guess)

1. **Raw features are separable.** Frozen-baseline logic re-run on the
   IDENTICAL in-distribution windows: binary F1 **0.6745** (P 0.6215,
   R 0.7374, FPR 0.2793), stage macro-F1 **0.4828** (IA 681/695 correct,
   C2 114/114, Impact 196/204) — `results/baseline_metrics_indist.json`
   (+ `comparison` notes in `results/baseline_metrics.json`; frozen
   values untouched, `git diff baseline-v1 -- python-ml/baseline/`
   empty). Data carries signal; the world model does not use it.
2. **Signal survives the encoder at init, training destroys it.**
   LR probe on encoder states (current-window labels): untrained 0.3931
   → trained 0.2032. Dynamics-output probe (next-step): untrained
   0.1614 → trained **0.0215**. Stage path: edge-projection-only probe
   0.4466 at init — the GNN input path sees the signal, joint training
   erases it.
3. **Scale audit at init (all-attack chunk):** dynamics MSE 4.75 vs
   infiltration focal 0.026 vs stage focal 2.25; encoder-input grad
   norms — dynamics-only 9.53, stage-only 10.67, infiltration-only
   **0.41**. The infiltration head gets ~1/25th the gradient of the
   other terms. The encoder minimizes next-state MSE by collapsing
   states (trained state std 0.24 vs 1.73 at init; trained MSE 0.069
   looks "good" only because targets collapsed), starving the heads.
4. **Mechanism proof (/tmp pilots, not tracked):** LayerNorm-wrapped
   encoder, same weights otherwise — still F1 0.0 (not a pure scale
   bug). Loss reweighting dyn 0.1 / inf 10 / stage 10 — head unlocks:
   F1 **0.5287** (P 0.4179, R 0.7194, max prob 0.85; FPR 0.62 —
   fires, poorly calibrated). Two milder points: dyn 1 / inf+stage 3 —
   F1 0.0; dyn 0.5 / inf+stage 3 — F1 0.2626. The operating point lives
   in loss-balance space, not in K or encoder space.
5. **Not a graph-topology artifact per se:** all 13,202 windows are
   single-node/single-self-loop vector-mode graphs (endpoint-free CIC
   CSVs), so the GNN is effectively an MLP — but the same compressed
   features drive an MLP to F1 0.47 in one epoch and the frozen LR to
   0.67. Topology degeneracy costs little here; loss balance costs
   everything.

## Step 1 — K ablation (K=3/5/10): NOT RUN (blocked by stop gate)

No K variants were trained. Rationale: the control (K=5) scores F1 0.0
with max prob 0.325 — threshold, ranking (AUC 0.51), and rollout-lead
metrics are all degenerate, so K=3/10 would compare noise, not rollout
depth. The rollout-K question is meaningful only after the head fires.
Re-run this table after the loss-balance fix lands (recommended grid:
same in-dist split, same 1:1:1-vs-balanced comparison first, then
K=3/5/10 on the winning loss setting).

| K | In-dist F1 (P/R/FPR) | Stage macro-F1 | Rollout lead | Train time | Cross-day F1 |
|---|---|---|---|---|---|
| 3 | — not run — | — | — | — | — |
| 5 (control) | 0.0000 (0/0/0) | 0.0138 | none | 9.9s | 0.0000 |
| 10 | — not run — | — | — | — | — |

## Step 2 — GNN-vs-flat ablation: NOT RUN (blocked by stop gate)

The flat encoder (`python-ml/model/encoder_flat.py`: baseline-identical
mean/std/max/sum aggregation → 1,284-d → 64-d, drop-in for GraphEncoder,
same Transformer + heads) is implemented and unit-plausible
(untrained-state probe F1 0.19 vs GNN 0.39), but no flat-control training
was run: with the joint loss starving every head, GNN-vs-flat would read
0.0-vs-0.0 regardless of architecture merit. Run it after the
loss-balance fix; the interesting comparison is flat-vs-GNN under the
WINNING loss weights, since single-node graphs make this a fair fight.

| Encoder (winning K) | In-dist F1 (P/R/FPR) | Stage macro-F1 | Rollout lead | Train time |
|---|---|---|---|---|
| GNN GraphSAGE-2L/64 (control) | 0.0000 (0/0/0) | 0.0138 | none | 9.9s |
| Flat vector → same Transformer | — not run — | — | — | — |

## Final recommended configuration

- **Window size: 10s** (stands, Phase 31).
- **K: 5 (unchanged default)** — no evidence to move; K ablation
  deferred, not decided.
- **Encoder: GNN (unchanged default)** — no evidence to move;
  encoder ablation deferred, not decided.
- **Split: in-distribution per-day-tail split is now the PRIMARY
  training/validation split** (`world_model_v1.pt` trained on it);
  whole-day-0302 is retained as a SECONDARY cross-day generalization
  stress test. Baseline↔world-model head-to-head is now apples-to-apples
  on identical windows (baseline F1 0.6745 vs world-model control F1
  0.0 — the gap is the modeling bug above, stated plainly).
- **Next (Phase 33 pre-work, not Phase 33): loss-balance fix.** The
  /tmp pilots point at dynamics-weight reduction + head-weight increase
  (dyn 0.5 / inf+stage 3 gives F1 0.26 with FPR 0.11; dyn 0.1 /
  inf+stage 10 gives F1 0.53 with FPR 0.62). A proper small grid +
  threshold/calibration tuning + re-run of the K and encoder ablations
  on the winning setting is the correct next step. No checkpoint beyond
  the same-hyperparameter control is committed — the reweight pilots
  live in /tmp only, deliberately.

## Artifact map

- `results/phase32_step0.json` — split report + both-split eval of control.
- `results/phase32_step0_indist_k5_gnn_{config,history,training_log}.json`,
  `results/loss_curve_phase32_step0_indist_k5_gnn.png` — control run.
- `results/baseline_metrics_indist.json`,
  `baseline_{binary,stage}_confusion_matrix_indist.csv` — identical-split
  baseline; `comparison` notes appended to `results/baseline_metrics.json`.
- `python-ml/training/phase32_common.py`, `run_phase32_step0.py`,
  `run_phase32_baseline_indist.py` — split/eval/training harness (kept;
  Steps 1–2 reuse it).
- `python-ml/model/encoder_flat.py` — flat encoder (kept for the
  deferred Step 2).
