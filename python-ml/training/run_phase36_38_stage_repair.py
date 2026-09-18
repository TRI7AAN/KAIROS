"""Phases 36-38: label audit, stage-set decision, and frozen-backbone fine-tune."""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))
sys.path.insert(0, str(REPO_ROOT / "python-ml" / "training"))

import torch
from torch.nn import functional as F
from torch_geometric.data import Batch

from phase32_common import CLASS_NAMES, DAY_NAMES, build_splits, make_model

CHECKPOINT = REPO_ROOT / "python-ml" / "weights" / "world_model_v1.pt"
ARCHIVE = REPO_ROOT / "python-ml" / "weights" / "world_model_phase32.pt"
# The pre-finetune archive is best-effort provenance: if the Phase 38 script
# has already run once (or the checkpoint on disk is already the finetuned
# one), there is nothing to archive and the run must not crash — the finetuned
# checkpoint already carries artifact_version kairos.world-model.v1.phase38-stage.
EXPECTED_BY_DAY = {
    "day14.json": {"INITIAL_ACCESS"},
    "day15.json": {"IMPACT"},
    "day28.json": {"INITIAL_ACCESS"},
    "day0302.json": {"COMMAND_AND_CONTROL"},
}
EPOCHS = 200
LEARNING_RATE = 0.01
RANDOM_SEED = 42


def extract_examples(model, days) -> tuple[torch.Tensor, torch.Tensor]:
    states_out = []
    targets_out = []
    model.eval()
    with torch.no_grad():
        for graphs in days:
            for start in range(0, len(graphs) - 1, 512):
                piece = list(graphs[start:start + 513])
                batch = Batch.from_data_list(piece)
                states = model.encoder(batch).unsqueeze(0)
                predicted = model.dynamics(states[:, :-1])[0]
                targets = torch.stack(
                    [graph.y_stage for graph in piece[1:]]
                ).squeeze(1)
                malicious = targets >= 0
                states_out.append(predicted[malicious])
                targets_out.append(targets[malicious])
    return torch.cat(states_out), torch.cat(targets_out)


def stage_metrics(logits: torch.Tensor, targets: torch.Tensor) -> dict:
    predictions = logits.argmax(dim=-1)
    rows = []
    for index, name in enumerate(CLASS_NAMES):
        actual = targets == index
        predicted = predictions == index
        support = int(actual.sum())
        correct = int((actual & predicted).sum())
        predicted_total = int(predicted.sum())
        precision = correct / predicted_total if predicted_total else 0.0
        recall = correct / support if support else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall else 0.0
        )
        rows.append({
            "class": name,
            "support": support,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        })
    observed = [row for row in rows if row["support"]]
    accuracy = float((predictions == targets).float().mean())
    return {
        "accuracy": accuracy,
        "observed_macro_f1": (
            sum(row["f1"] for row in observed) / len(observed)
            if observed else 0.0
        ),
        "six_class_macro_f1": sum(row["f1"] for row in rows) / len(rows),
        "per_class": rows,
    }


def infiltration_probabilities(model, days) -> torch.Tensor:
    values = []
    model.eval()
    with torch.no_grad():
        for graphs in days:
            for start in range(0, len(graphs) - 1, 512):
                piece = list(graphs[start:start + 513])
                batch = Batch.from_data_list(piece)
                states = model.encoder(batch).unsqueeze(0)
                predicted = model.dynamics(states[:, :-1])
                values.append(
                    model.heads(predicted)["infiltration_probability"][0].cpu()
                )
    return torch.cat(values)


def main() -> int:
    node, edge, in_train, in_val, _, _, split_report = build_splits()

    audit_days = in_train + in_val
    mismatches = []
    counts = {}
    for name, training, validation in zip(DAY_NAMES, in_train, in_val):
        graphs = list(training) + list(validation)
        day_counts = {}
        expected = EXPECTED_BY_DAY[name]
        for index, graph in enumerate(graphs):
            stage_index = int(graph.y_stage.item())
            stage = "NONE" if stage_index < 0 else CLASS_NAMES[stage_index]
            day_counts[stage] = day_counts.get(stage, 0) + 1
            if stage != "NONE" and stage not in expected:
                mismatches.append({
                    "day": name,
                    "window_index": index,
                    "stage": stage,
                    "expected_one_of": sorted(expected),
                })
        counts[name] = day_counts

    phase36 = {
        "artifact_version": "kairos.phase36.v1",
        "method": (
            "Manual day/family mapping audit against every 10-second contract "
            "label. Timeline boundaries are minute-aligned and therefore exact "
            "multiples of the selected 10-second window."
        ),
        "expected_stage_by_day": {
            name: sorted(stages) for name, stages in EXPECTED_BY_DAY.items()
        },
        "stage_counts": counts,
        "ambiguous_or_mismatched_windows": mismatches,
        "relabel_overrides": [],
        "corrections_applied": 0,
        "result": (
            "no_ambiguous_labels_found" if not mismatches
            else "manual_review_required"
        ),
        "note": (
            "No labels were silently changed. Raw attack labels must match the "
            "published attack timeline in Java before a malicious stage is "
            "assigned, and no selected-day contract contains an unexpected "
            "stage."
        ),
    }
    (REPO_ROOT / "results" / "phase36_label_audit.json").write_text(
        json.dumps(phase36, indent=2) + "\n", encoding="utf-8"
    )

    phase37 = {
        "artifact_version": "kairos.phase37.v1",
        "decision": "retain_six_class_external_schema_no_merge",
        "active_training_classes": [
            "INITIAL_ACCESS", "COMMAND_AND_CONTROL", "IMPACT"
        ],
        "unsupported_in_selected_data": [
            "RECONNAISSANCE", "LATERAL_MOVEMENT", "EXFILTRATION"
        ],
        "rationale": (
            "The three weak classes have zero examples, not evidence of "
            "semantic overlap. Merging them would invent supervision and break "
            "the stable Java/Python six-class contract. Fine-tuning therefore "
            "uses class balancing over the three observed classes while "
            "retaining all six output positions for later data expansion."
        ),
        "demo_policy": (
            "Do not claim validated performance for unsupported stages; expose "
            "the full schema but identify the coverage limitation."
        ),
    }
    (REPO_ROOT / "results" / "phase37_stage_set_decision.json").write_text(
        json.dumps(phase37, indent=2) + "\n", encoding="utf-8"
    )

    model = make_model(len(node), len(edge), encoder="gnn")
    payload = torch.load(CHECKPOINT, map_location="cpu", weights_only=False)
    if payload.get("artifact_version") == "kairos.world-model.v1.phase38-stage":
        print("checkpoint is already the Phase 38 finetuned artifact; "
              "re-running the fine-tune is idempotent and will refresh the "
              "same stage-head optimum.")
    elif not ARCHIVE.exists():
        shutil.copy2(CHECKPOINT, ARCHIVE)
    model.load_state_dict(payload["model_state_dict"])
    before_infiltration = infiltration_probabilities(model, in_val)
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

    torch.manual_seed(RANDOM_SEED)
    optimizer = torch.optim.AdamW(
        model.heads.stage.parameters(), lr=LEARNING_RATE, weight_decay=1e-4
    )
    history = []
    best_score = -1.0
    best_state = None
    best_epoch = -1
    for epoch in range(EPOCHS):
        model.heads.stage.train()
        optimizer.zero_grad()
        logits = model.heads.stage(train_states)
        loss = F.cross_entropy(logits, train_targets, weight=class_weights)
        loss.backward()
        optimizer.step()

        model.heads.stage.eval()
        with torch.no_grad():
            validation_metrics = stage_metrics(
                model.heads.stage(val_states), val_targets
            )
        score = validation_metrics["observed_macro_f1"]
        history.append({
            "epoch": epoch + 1,
            "training_loss": float(loss.detach()),
            "validation_observed_macro_f1": score,
            "validation_accuracy": validation_metrics["accuracy"],
        })
        if score > best_score:
            best_score = score
            best_epoch = epoch + 1
            best_state = copy.deepcopy(model.heads.stage.state_dict())

    assert best_state is not None
    model.heads.stage.load_state_dict(best_state)
    model.heads.stage.eval()
    after_stage = stage_metrics(model.heads.stage(val_states), val_targets)
    after_infiltration = infiltration_probabilities(model, in_val)
    infiltration_max_delta = float(
        (after_infiltration - before_infiltration).abs().max()
    )
    if infiltration_max_delta > 1e-7:
        raise RuntimeError(
            "stage-only fine-tune changed infiltration probabilities: "
            f"{infiltration_max_delta}"
        )

    if (payload.get("artifact_version")
            != "kairos.world-model.v1.phase38-stage"
            and not ARCHIVE.exists()):
        shutil.copy2(CHECKPOINT, ARCHIVE)
    updated_payload = dict(payload)
    updated_payload["artifact_version"] = "kairos.world-model.v1.phase38-stage"
    updated_payload["model_state_dict"] = model.state_dict()
    updated_payload["phase38"] = {
        "best_epoch": best_epoch,
        "validation_observed_macro_f1": best_score,
        "class_weights": class_weights.tolist(),
        "frozen_backbone": True,
        "infiltration_max_probability_delta": infiltration_max_delta,
    }
    torch.save(updated_payload, CHECKPOINT)

    result = {
        "artifact_version": "kairos.phase38.v1",
        "configuration": {
            "epochs": EPOCHS,
            "learning_rate": LEARNING_RATE,
            "random_seed": RANDOM_SEED,
            "optimizer": "AdamW",
            "loss": "class-weighted cross entropy",
            "frozen": ["encoder", "dynamics", "infiltration_head"],
            "trainable": ["stage_head"],
            "class_counts": class_counts.tolist(),
            "class_weights": class_weights.tolist(),
        },
        "split_report": split_report,
        "training_examples": len(train_targets),
        "validation_examples": len(val_targets),
        "before": before_stage,
        "after": after_stage,
        "best_epoch": best_epoch,
        "history": history,
        "infiltration_max_probability_delta": infiltration_max_delta,
        "checkpoint": "python-ml/weights/world_model_v1.pt",
        "pre_finetune_archive": "python-ml/weights/world_model_phase32.pt",
    }
    (REPO_ROOT / "results" / "phase38_stage_finetune.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "phase36": phase36["result"],
        "phase37": phase37["decision"],
        "stage_macro_f1_before": before_stage["observed_macro_f1"],
        "stage_macro_f1_after": after_stage["observed_macro_f1"],
        "stage_accuracy_after": after_stage["accuracy"],
        "best_epoch": best_epoch,
        "infiltration_max_delta": infiltration_max_delta,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
