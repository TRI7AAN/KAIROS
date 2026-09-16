"""Phase 31 ablation training: one window size, same hyperparameters as 10s.

Usage:
    PYTHONPATH=python-ml python-ml/venv/bin/python \\
        python-ml/training/run_ablation_training.py <window_seconds> \\
        <contract_dir> <out_checkpoint> <out_prefix>

Example:
    ... run_ablation_training.py 5 data/processed/graphs_5s \\
        python-ml/weights/world_model_5s.pt results/ablation_5s

Writes <out_checkpoint>, <out_prefix>_config.json, <out_prefix>_history.json,
<out_prefix>_training_log.json, loss_curve_<ws>s.png into results/.
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

from model.world_model import NetworkWorldModel
from pipeline.graph_builder import load_graph_sequence
from training.world_model_trainer import (
    WorldModelTrainingConfig,
    train_world_model,
)

TRAIN_CONTRACTS = ["day14.json", "day15.json", "day28.json"]
VAL_CONTRACTS = ["day0302.json"]

EPOCHS = 5
CHUNK_LENGTH = 64
LEARNING_RATE = 1e-3
RANDOM_SEED = 42
ROLLOUT_K = 5


def main() -> int:
    window_seconds = int(sys.argv[1])
    contract_dir = Path(sys.argv[2])
    checkpoint = Path(sys.argv[3])
    out_prefix = Path(sys.argv[4])
    if not contract_dir.is_absolute():
        contract_dir = REPO_ROOT / contract_dir
    if not checkpoint.is_absolute():
        checkpoint = REPO_ROOT / checkpoint
    if not out_prefix.is_absolute():
        out_prefix = REPO_ROOT / out_prefix

    train_sequences = [load_graph_sequence(contract_dir / name)
                       for name in TRAIN_CONTRACTS]
    val_sequences = [load_graph_sequence(contract_dir / name)
                     for name in VAL_CONTRACTS]
    schemas = {(tuple(s.node_feature_names), tuple(s.edge_feature_names))
               for s in train_sequences + val_sequences}
    if len(schemas) != 1:
        raise SystemExit("feature schemas differ between contracts")
    node_features, edge_features = schemas.pop()
    train_graphs = [list(s.graphs) for s in train_sequences]
    val_graphs = [list(s.graphs) for s in val_sequences]
    print(f"window={window_seconds}s "
          f"train_windows={sum(len(g) for g in train_graphs)} "
          f"val_windows={sum(len(g) for g in val_graphs)}", flush=True)

    model = NetworkWorldModel(len(node_features), len(edge_features))
    config = WorldModelTrainingConfig(
        epochs=EPOCHS,
        chunk_length=CHUNK_LENGTH,
        learning_rate=LEARNING_RATE,
        random_seed=RANDOM_SEED,
    )
    started = time.time()
    history = train_world_model(
        model,
        train_graphs,
        val_graphs,
        config=config,
        checkpoint_path=checkpoint,
        config_path=out_prefix.parent / (out_prefix.name + "_config.json"),
        history_path=out_prefix.parent / (out_prefix.name + "_history.json"),
    )
    elapsed = time.time() - started
    print(f"window={window_seconds}s best val loss="
          f"{history.best_validation_loss:.6f} at epoch "
          f"{history.best_epoch + 1} ({elapsed:.1f}s)", flush=True)

    (out_prefix.parent / (out_prefix.name + "_training_log.json")).write_text(
        json.dumps({
            "window_size_seconds": window_seconds,
            "train_contracts": TRAIN_CONTRACTS,
            "validation_contracts": VAL_CONTRACTS,
            "contract_dir": str(contract_dir),
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
            "checkpoint": str(checkpoint.relative_to(REPO_ROOT)),
            "elapsed_seconds": elapsed,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    epochs = list(range(1, len(history.training_loss) + 1))
    plt.figure(figsize=(8, 5))
    plt.plot(epochs, list(history.training_loss), marker="o", label="train")
    plt.plot(epochs, list(history.validation_loss), marker="s", label="validation")
    plt.xlabel("epoch")
    plt.ylabel("loss")
    plt.title(f"KAIROS world-model training ({window_seconds}s windows)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_prefix.parent / f"loss_curve_{window_seconds}s.png", dpi=100)
    print(f"wrote {out_prefix.name}_training_log.json and "
          f"loss_curve_{window_seconds}s.png", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
