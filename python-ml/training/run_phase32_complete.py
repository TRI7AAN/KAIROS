"""Complete the blocked Phase 32 loss, encoder, and rollout-horizon ablations.

The fixed 0.5 decision threshold is retained so all candidates are directly
comparable. Loss weights are selected with a security-oriented score that
rewards infiltration F1 and penalizes false-positive rate. K is an inference
horizon (not a training hyperparameter), so the winning encoder checkpoint is
evaluated at K=3/5/10 without redundant retraining.
"""

from __future__ import annotations

import json
import shutil
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

LOSS_CANDIDATES = (
    ("alpha075_050_3_3", 0.50, 3.0, 3.0, 0.75),
    ("alpha090_025_5_5", 0.25, 5.0, 5.0, 0.90),
    ("alpha0923_010_10_10", 0.10, 10.0, 10.0, 0.923),
    ("alpha097_010_10_3", 0.10, 10.0, 3.0, 0.97),
)
K_VALUES = (3, 5, 10)
THRESHOLD = 0.5


def security_score(result: dict) -> float:
    infiltration = result["infiltration"]
    return infiltration["f1"] - infiltration["fpr"]


def rollout_rank(result: dict) -> tuple[int, int, float]:
    attacks = result["rollout_attacks"]
    leads = [item["lead_windows"] for item in attacks
             if item["lead_windows"] is not None]
    curve_peaks = [
        max((point["mean_prob"] for point in item["curve"]), default=0.0)
        for item in attacks
    ]
    return (
        len(leads),
        sum(leads),
        sum(curve_peaks) / len(curve_peaks) if curve_peaks else 0.0,
    )


def main() -> int:
    node, edge, in_train, in_val, _, cross_val, split_report = build_splits()
    set_schema(node, edge)
    validation = [graph for day in in_val for graph in day]
    cross_day = [graph for day in cross_val for graph in day]
    loss_grid = []

    for tag, dynamics, infiltration, stage, alpha in LOSS_CANDIDATES:
        checkpoint_name = f"phase32_{tag}_gnn.pt"
        training = train_variant(
            tag,
            in_train,
            in_val,
            "gnn",
            checkpoint_name,
            f"Phase 32 loss/alpha: {dynamics}/{infiltration}/{stage}/{alpha}",
            dynamics_weight=dynamics,
            infiltration_weight=infiltration,
            stage_weight=stage,
            infiltration_alpha=alpha,
        )
        evaluation = evaluate_checkpoint(
            f"python-ml/weights/{checkpoint_name}",
            validation,
            10,
            5,
            "gnn",
            len(node),
            len(edge),
            threshold=THRESHOLD,
        )
        row = {
            "tag": tag,
            "loss_weights": {
                "dynamics": dynamics,
                "infiltration": infiltration,
                "stage": stage,
                "infiltration_alpha": alpha,
            },
            "training": training,
            "evaluation": evaluation,
            "security_score_f1_minus_fpr": security_score(evaluation),
        }
        loss_grid.append(row)
        metric = evaluation["infiltration"]
        print(
            f"{tag}: F1={metric['f1']:.4f} FPR={metric['fpr']:.4f} "
            f"AUC-ROC={metric['auc_roc']:.4f} "
            f"stage-F1={evaluation['stage']['macro_f1']:.4f}",
            flush=True,
        )

    loss_winner = max(
        loss_grid,
        key=lambda row: (
            row["security_score_f1_minus_fpr"],
            row["evaluation"]["infiltration"]["f1"],
            row["evaluation"]["stage"]["macro_f1"],
        ),
    )
    weights = loss_winner["loss_weights"]

    flat_training = train_variant(
        "flat_winning_loss",
        in_train,
        in_val,
        "flat",
        "phase32_flat_winning_loss.pt",
        "Phase 32 flat encoder with winning loss balance",
        dynamics_weight=weights["dynamics"],
        infiltration_weight=weights["infiltration"],
        stage_weight=weights["stage"],
        infiltration_alpha=weights["infiltration_alpha"],
    )
    flat_evaluation = evaluate_checkpoint(
        "python-ml/weights/phase32_flat_winning_loss.pt",
        validation,
        10,
        5,
        "flat",
        len(node),
        len(edge),
        threshold=THRESHOLD,
    )
    gnn_evaluation = loss_winner["evaluation"]
    encoders = {
        "gnn": {
            "training": loss_winner["training"],
            "evaluation": gnn_evaluation,
            "security_score_f1_minus_fpr": security_score(gnn_evaluation),
        },
        "flat": {
            "training": flat_training,
            "evaluation": flat_evaluation,
            "security_score_f1_minus_fpr": security_score(flat_evaluation),
        },
    }
    encoder_winner = max(
        encoders,
        key=lambda name: (
            encoders[name]["security_score_f1_minus_fpr"],
            encoders[name]["evaluation"]["infiltration"]["f1"],
            encoders[name]["evaluation"]["stage"]["macro_f1"],
        ),
    )
    winning_checkpoint = (
        loss_winner["training"]["checkpoint"]
        if encoder_winner == "gnn"
        else flat_training["checkpoint"]
    )

    k_results = {
        str(k): evaluate_checkpoint(
            winning_checkpoint,
            validation,
            10,
            k,
            encoder_winner,
            len(node),
            len(edge),
            threshold=THRESHOLD,
        )
        for k in K_VALUES
    }
    k_winner = max(K_VALUES, key=lambda value: (rollout_rank(k_results[str(value)]),
                                                -abs(value - 5)))

    cross_evaluation = evaluate_checkpoint(
        winning_checkpoint,
        cross_day,
        10,
        k_winner,
        encoder_winner,
        len(node),
        len(edge),
        threshold=THRESHOLD,
    )
    canonical = REPO_ROOT / "python-ml" / "weights" / "world_model_v1.pt"
    shutil.copy2(REPO_ROOT / winning_checkpoint, canonical)

    summary = {
        "artifact_version": "kairos.phase32.completed.v2",
        "methodology": {
            "threshold": THRESHOLD,
            "loss_selection": "maximize validation infiltration F1 minus FPR",
            "encoder_selection": "maximize F1 minus FPR, then F1, then stage macro-F1",
            "k_selection": "maximize detected rollout attacks, total lead, then mean peak probability; prefer K=5 on ties",
            "note": "Development-validation ablation; cross-day day0302 remains a secondary generalization stress test.",
        },
        "split_report": split_report,
        "loss_grid": loss_grid,
        "loss_winner": loss_winner["tag"],
        "encoder_comparison": encoders,
        "encoder_winner": encoder_winner,
        "k_ablation": k_results,
        "k_winner": k_winner,
        "winning_checkpoint_source": winning_checkpoint,
        "canonical_checkpoint": "python-ml/weights/world_model_v1.pt",
        "cross_day_generalization_secondary": cross_evaluation,
    }
    output = REPO_ROOT / "results" / "phase32_completed.json"
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(
        f"WINNER encoder={encoder_winner} K={k_winner} "
        f"loss={loss_winner['tag']} checkpoint={winning_checkpoint}",
        flush=True,
    )
    print(f"wrote {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
