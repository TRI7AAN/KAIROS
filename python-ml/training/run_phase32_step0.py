"""Phase 32 Step 0: in-distribution split training + before/after evaluation.

Trains the 10s/K=5/GNN control on the in-distribution split (per-day first
80% train, per-day last 20% val; 10,560 train / 2,642 val windows) with the
same hyperparameters as Fix 3 (lr 1e-3, 5 epochs, chunk 64, seed 42) and
overwrites python-ml/weights/world_model_v1.pt.

Then evaluates that checkpoint on BOTH:
  - in-distribution validation (PRIMARY): joined per-day tails, every
    val stage (IA/Impact/C2) seen in training;
  - cross-day whole-day0302 holdout (SECONDARY stress test, unchanged).

Writes results/phase32_step0.json. Fails loudly (exit 2) if in-distribution
F1 is still ~0.0, per the Step 0 stop gate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))
sys.path.insert(0, str(REPO_ROOT / "python-ml" / "training"))

from phase32_common import (
    build_splits,
    evaluate_checkpoint,
    set_schema,
    train_variant,
)

CHECKPOINT_NAME = "world_model_v1.pt"
TAG = "step0_indist_k5_gnn"


def main() -> int:
    node, edge, in_train, in_val, cross_train, cross_val, report = build_splits()
    set_schema(node, edge)
    train_windows = sum(len(g) for g in in_train)
    val_windows = sum(len(g) for g in in_val)
    print(f"in-dist split: train={train_windows} val={val_windows}", flush=True)
    print("per-day tails:", json.dumps(
        {k: {"train": v["train"], "val": v["val"]} for k, v in report.items()}),
        flush=True)

    log = train_variant(
        TAG, in_train, in_val, "gnn", CHECKPOINT_NAME,
        "KAIROS world-model training (in-distribution split, 10s, K=5, GNN)")
    print(f"train done: best val loss={log['best_validation_loss']:.6f} "
          f"at epoch {log['best_epoch'] + 1} ({log['elapsed_seconds']:.1f}s)",
          flush=True)

    ckpt = f"python-ml/weights/{CHECKPOINT_NAME}"
    in_val_graphs = [g for day in in_val for g in day]
    cross_val_graphs = [g for day in cross_val for g in day]
    indist = evaluate_checkpoint(ckpt, in_val_graphs, 10, 5, "gnn",
                                 len(node), len(edge))
    cross = evaluate_checkpoint(ckpt, cross_val_graphs, 10, 5, "gnn",
                                len(node), len(edge))
    summary = {
        "split_report": report,
        "training": log,
        "in_distribution_validation_primary": indist,
        "cross_day_generalization_secondary": cross,
    }
    (REPO_ROOT / "results" / "phase32_step0.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    inf = indist["infiltration"]
    st = indist["stage"]
    print(f"IN-DIST: F1={inf['f1']:.4f} P={inf['precision']:.4f} "
          f"R={inf['recall']:.4f} FPR={inf['fpr']:.4f} "
          f"AUC-ROC={inf['auc_roc']:.4f} AUC-PR={inf['auc_pr']:.4f} "
          f"stage-macro-F1={st['macro_f1']:.4f} "
          f"leads={[a['lead_windows'] for a in indist['rollout_attacks']]}",
          flush=True)
    cinf = cross["infiltration"]
    print(f"CROSS-DAY: F1={cinf['f1']:.4f} P={cinf['precision']:.4f} "
          f"R={cinf['recall']:.4f} FPR={cinf['fpr']:.4f} "
          f"AUC-ROC={cinf['auc_roc']:.4f} stage-macro-F1="
          f"{cross['stage']['macro_f1']:.4f} "
          f"leads={[a['lead_windows'] for a in cross['rollout_attacks']]}",
          flush=True)
    if inf["f1"] < 0.05:
        print("STOP GATE: in-distribution F1 still ~0.0; halting before ablations.",
              flush=True)
        return 2
    print("STOP GATE PASS: in-distribution F1 is non-zero and meaningful.",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
