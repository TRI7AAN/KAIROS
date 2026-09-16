"""End-to-end world-model training on the real day-split contracts (Fix 3).

Train: day14 + day15 + day28 (10,059 windows). Validate: whole held-out day0302
(3,143 windows). 10s windows, chunk_length 64, lr 1e-3, 5 epochs, seed 42 —
matching python-ml/configs/train_config.yaml.

Writes:
  python-ml/weights/world_model_v1.pt
  results/world_model_config.json
  results/world_model_history.json
  results/training_log.json
  results/loss_curve.png
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml

from model.world_model import NetworkWorldModel
from pipeline.graph_builder import load_graph_sequence
from training.world_model_trainer import (
    WorldModelTrainingConfig,
    train_world_model,
)

TRAIN_CONTRACTS = ["day14.json", "day15.json", "day28.json"]
VAL_CONTRACTS = ["day0302.json"]
ROLLOUT_K = 5

EPOCHS = 5
CHUNK_LENGTH = 64
LEARNING_RATE = 1e-3
RANDOM_SEED = 42


def main() -> int:
    with open(REPO_ROOT / "python-ml" / "configs" / "train_config.yaml") as handle:
        train_yaml = yaml.safe_load(handle)
    print(f"train_config window_size_seconds="
          f"{train_yaml['data']['window_size_seconds']}")

    contract_dir = REPO_ROOT / "data" / "processed" / "graph_contracts"
    train_sequences = [load_graph_sequence(contract_dir / name)
                       for name in TRAIN_CONTRACTS]
    val_sequences = [load_graph_sequence(contract_dir / name)
                     for name in VAL_CONTRACTS]
    schemas = {(tuple(s.node_feature_names), tuple(s.edge_feature_names))
               for s in train_sequences + val_sequences}
    if len(schemas) != 1:
        raise SystemExit("feature schemas differ between contracts")
    node_features, edge_features = schemas.pop()
    print(f"node_features={len(node_features)} "
          f"edge_features={len(edge_features)}")
    train_graphs = [list(s.graphs) for s in train_sequences]
    val_graphs = [list(s.graphs) for s in val_sequences]
    print(f"train_windows={sum(len(g) for g in train_graphs)} "
          f"val_windows={sum(len(g) for g in val_graphs)}")

    model = NetworkWorldModel(len(node_features), len(edge_features))
    config = WorldModelTrainingConfig(
        epochs=EPOCHS,
        chunk_length=CHUNK_LENGTH,
        learning_rate=LEARNING_RATE,
        random_seed=RANDOM_SEED,
    )
    checkpoint = REPO_ROOT / "python-ml" / "weights" / "world_model_v1.pt"
    config_path = REPO_ROOT / "results" / "world_model_config.json"
    history_path = REPO_ROOT / "results" / "world_model_history.json"
    started = time.time()
    history = train_world_model(
        model,
        train_graphs,
        val_graphs,
        config=config,
        checkpoint_path=checkpoint,
        config_path=config_path,
        history_path=history_path,
    )
    elapsed = time.time() - started
    print(f"best validation loss={history.best_validation_loss:.6f} "
          f"at epoch {history.best_epoch + 1} "
          f"({elapsed:.1f}s total)")

    results_dir = REPO_ROOT / "results"
    training_log = {
        "train_contracts": TRAIN_CONTRACTS,
        "validation_contracts": VAL_CONTRACTS,
        "window_size_seconds": 10,
        "train_windows": sum(len(g) for g in train_graphs),
        "validation_windows": sum(len(g) for g in val_graphs),
        "epochs": EPOCHS,
        "chunk_length": CHUNK_LENGTH,
        "learning_rate": LEARNING_RATE,
        "random_seed": RANDOM_SEED,
        "rollout_k": ROLLOUT_K,
        "training_loss": list(history.training_loss),
        "validation_loss": list(history.validation_loss),
        "best_epoch": history.best_epoch,
        "best_validation_loss": history.best_validation_loss,
        "checkpoint": "python-ml/weights/world_model_v1.pt",
        "elapsed_seconds": elapsed,
    }
    (results_dir / "training_log.json").write_text(
        json.dumps(training_log, indent=2) + "\n", encoding="utf-8"
    )

    epochs = list(range(1, len(history.training_loss) + 1))
    plt.figure(figsize=(8, 5))
    plt.plot(epochs, list(history.training_loss), marker="o", label="train")
    plt.plot(epochs, list(history.validation_loss), marker="s", label="validation")
    plt.xlabel("epoch")
    plt.ylabel("loss")
    plt.title("KAIROS world-model training (train: 3 days, val: 2018-03-02)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(results_dir / "loss_curve.png", dpi=100)
    print("wrote results/training_log.json and results/loss_curve.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
