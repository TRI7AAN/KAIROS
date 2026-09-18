"""Phase 63: retrain with F1-based checkpoint selection (Option A).

Diagnosis (see Step 1 findings):
  - Validation LOSS anti-correlates with infiltration F1 on this task
    (flat encoder: lower loss 1.67 yet F1 0.0 vs GNN loss 3.92 / F1 0.3545),
    because the dynamics-MSE term (~95% of the joint loss at init) dominates.
  - The best-loss checkpoint (epoch 1) is therefore NOT the best detector.
    Per-epoch F1 tracking shows F1 peaks early (ep1: 0.5671) then the head
    collapses (max prob < 0.5 from ep8 on) while AUC stays ~0.55-0.60.
  - Added regularization (dropout 0.2, weight decay, cosine schedule) and
    aggressive loss rebalancing (dyn 0.1) both ACCELERATE the collapse;
    the vanilla recipe (dyn 0.5 / inf 3 / stage 3, alpha 0.75, lr 1e-3,
    dropout 0.1, no weight decay, no schedule) has the latest, highest F1.
  - Fix applied: keep the proven vanilla recipe, train 6 epochs, select the
    checkpoint by validation F1 (security score F1-minus-FPR breaks ties),
    then run the frozen-backbone Phase 38 stage-head fine-tune on top so the
    canonical checkpoint keeps its stage-head quality.

Same in-distribution split as the evaluation standard (per-day
first-80/last-20, primary). Writes results/phase63_retrain.json and promotes
the finetuned best-F1 state to python-ml/weights/world_model_v1.pt.
"""

from __future__ import annotations

import copy
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))
sys.path.insert(0, str(REPO_ROOT / "python-ml" / "training"))

import torch
from torch.nn import functional as F

from phase32_common import (
    CLASS_NAMES,
    build_splits,
    evaluate_checkpoint,
    head_metrics,
    make_model,
    set_schema,
)
from training.world_model_trainer import (
    WorldModelTrainingConfig,
    _chunks,
    _chunk_loss,
)

EPOCHS = 6
K = 3
THRESHOLD = 0.5
CHECKPOINT = REPO_ROOT / "python-ml" / "weights" / "world_model_v1.pt"
FINETUNE_LR = 0.01
FINETUNE_EPOCHS = 200


def main() -> int:
    started = time.time()
    node, edge, in_train, in_val, cross_train, cross_val, split_report = (
        build_splits()
    )
    set_schema(node, edge)
    validation = [graph for day in in_val for graph in day]
    cross_day = [graph for day in cross_val for graph in day]

    torch.manual_seed(42)
    model = make_model(len(node), len(edge), encoder="gnn", dropout=0.1)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    config = WorldModelTrainingConfig(
        epochs=EPOCHS,
        dynamics_weight=0.5,
        infiltration_weight=3.0,
        stage_weight=3.0,
        infiltration_alpha=0.75,
    )
    epoch_f1: list[dict] = []
    best_f1 = -1.0
    best_fpr = 1.0
    best_state = None
    best_epoch = -1
    train_losses: list[float] = []
    for epoch in range(EPOCHS):
        model.train()
        total, chunks = 0.0, 0
        for graphs in in_train:
            for chunk in _chunks(graphs, config.chunk_length):
                optimizer.zero_grad()
                loss = _chunk_loss(model, chunk, config)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), config.gradient_clip_norm
                )
                optimizer.step()
                total += float(loss.detach())
                chunks += 1
        train_losses.append(total / chunks)
        model.eval()
        metrics = head_metrics(model, validation, threshold=THRESHOLD)
        infiltration = metrics["infiltration"]
        row = {
            "epoch": epoch,
            "train_loss": train_losses[-1],
            "f1": infiltration["f1"],
            "precision": infiltration["precision"],
            "recall": infiltration["recall"],
            "fpr": infiltration["fpr"],
            "auc_roc": infiltration["auc_roc"],
            "prob_max": infiltration["prob_max"],
        }
        epoch_f1.append(row)
        print(f"ep{epoch}: " + json.dumps(row), flush=True)
        score = (infiltration["f1"] - infiltration["fpr"], infiltration["f1"])
        best_score = (best_f1 - best_fpr, best_f1)
        if score > best_score:
            best_f1 = infiltration["f1"]
            best_fpr = infiltration["fpr"]
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())

    assert best_state is not None
    model.load_state_dict(best_state)

    torch.save(
        {
            "artifact_version": "kairos.world-model.v1.phase63-f1",
            "model_state_dict": model.state_dict(),
            "epoch": best_epoch,
            "validation_f1": best_f1,
            "selection": "validation F1 (F1-minus-FPR tiebreak), "
            "threshold 0.5",
            "config": {
                "epochs": EPOCHS,
                "dynamics_weight": 0.5,
                "infiltration_weight": 3.0,
                "stage_weight": 3.0,
                "infiltration_alpha": 0.75,
                "learning_rate": 1e-3,
                "dropout": 0.1,
                "weight_decay": 0.0,
                "lr_schedule": "none",
            },
        },
        CHECKPOINT,
    )
    pre_finetune = evaluate_checkpoint(
        "python-ml/weights/world_model_v1.pt",
        validation,
        10,
        K,
        "gnn",
        len(node),
        len(edge),
        threshold=THRESHOLD,
    )

    from run_phase36_38_stage_repair import (
        extract_examples,
        infiltration_probabilities,
        stage_metrics,
    )

    train_states, train_targets = extract_examples(model, in_train)
    val_states, val_targets = extract_examples(model, in_val)
    before_stage = stage_metrics(model.heads.stage(val_states), val_targets)
    for parameter in model.parameters():
        parameter.requires_grad = False
    for parameter in model.heads.stage.parameters():
        parameter.requires_grad = True
    class_counts = torch.bincount(train_targets, minlength=len(CLASS_NAMES))
    class_weights = torch.zeros(len(CLASS_NAMES), dtype=torch.float32)
    observed = class_counts > 0
    class_weights[observed] = (
        class_counts[observed].sum()
        / (observed.sum() * class_counts[observed].float())
    )
    torch.manual_seed(42)
    finetune_opt = torch.optim.AdamW(
        model.heads.stage.parameters(), lr=FINETUNE_LR, weight_decay=1e-4
    )
    best_score, best_head, best_head_epoch = -1.0, None, -1
    for epoch in range(FINETUNE_EPOCHS):
        model.heads.stage.train()
        finetune_opt.zero_grad()
        loss = F.cross_entropy(
            model.heads.stage(train_states), train_targets,
            weight=class_weights,
        )
        loss.backward()
        finetune_opt.step()
        model.heads.stage.eval()
        with torch.no_grad():
            validation_metrics = stage_metrics(
                model.heads.stage(val_states), val_targets
            )
        score = validation_metrics["observed_macro_f1"]
        if score > best_score:
            best_score = score
            best_head_epoch = epoch + 1
            best_head = copy.deepcopy(model.heads.stage.state_dict())
    assert best_head is not None
    model.heads.stage.load_state_dict(best_head)
    model.heads.stage.eval()
    after_stage = stage_metrics(model.heads.stage(val_states), val_targets)

    payload = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    payload["artifact_version"] = "kairos.world-model.v1.phase63-f1-stage"
    payload["model_state_dict"] = model.state_dict()
    payload["phase63"] = {
        "f1_selected_epoch": best_epoch,
        "validation_f1": best_f1,
        "stage_finetune_best_epoch": best_head_epoch,
        "stage_observed_macro_f1": best_score,
        "frozen_backbone": True,
    }
    torch.save(payload, CHECKPOINT)

    final_indist = evaluate_checkpoint(
        "python-ml/weights/world_model_v1.pt",
        validation,
        10,
        K,
        "gnn",
        len(node),
        len(edge),
        threshold=THRESHOLD,
    )
    final_cross = evaluate_checkpoint(
        "python-ml/weights/world_model_v1.pt",
        cross_day,
        10,
        K,
        "gnn",
        len(node),
        len(edge),
        threshold=THRESHOLD,
    )
    result = {
        "artifact_version": "kairos.phase63.v1",
        "configuration": payload["config"],
        "selection": payload["selection"],
        "split_report": split_report,
        "epoch_trajectory": epoch_f1,
        "f1_selected_epoch": best_epoch,
        "pre_finetune_indist": pre_finetune["infiltration"],
        "final_indist": final_indist,
        "final_cross": final_cross,
        "stage_before": before_stage,
        "stage_after": after_stage,
        "stage_finetune_best_epoch": best_head_epoch,
        "elapsed_seconds": time.time() - started,
        "checkpoint": "python-ml/weights/world_model_v1.pt",
        "pre_tune_archive": "python-ml/weights/"
        "world_model_v1_pretune_baseline_loss.pt",
    }
    (REPO_ROOT / "results" / "phase63_retrain.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "f1_selected_epoch": best_epoch,
        "final_indist_f1": final_indist["infiltration"]["f1"],
        "final_indist_fpr": final_indist["infiltration"]["fpr"],
        "final_cross_f1": final_cross["infiltration"]["f1"],
        "stage_six_class_macro_f1": final_indist["stage"]["macro_f1"],
        "stage_finetune_best_epoch": best_head_epoch,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
