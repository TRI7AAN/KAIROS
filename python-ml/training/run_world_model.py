"""Train KAIROS world model with whole-day validation."""

from __future__ import annotations

import argparse
from pathlib import Path

from model.world_model import NetworkWorldModel
from pipeline.graph_builder import load_graph_sequence
from training.world_model_trainer import (
    WorldModelTrainingConfig,
    train_world_model,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("contracts", nargs="+", type=Path)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--chunk-length", type=int, default=64)
    parser.add_argument("--checkpoint", type=Path, default=Path("weights/world_model_v1.pt"))
    parser.add_argument(
        "--config", type=Path, default=Path("../results/world_model_config.json")
    )
    parser.add_argument(
        "--history", type=Path, default=Path("../results/world_model_history.json")
    )
    arguments = parser.parse_args()
    if len(arguments.contracts) < 2:
        parser.error("provide at least one training day and one validation day")

    sequences = [load_graph_sequence(path) for path in arguments.contracts]
    schema = (
        sequences[0].node_feature_names,
        sequences[0].edge_feature_names,
    )
    if any(
        (sequence.node_feature_names, sequence.edge_feature_names) != schema
        for sequence in sequences[1:]
    ):
        parser.error("all contracts must use identical feature schemas")

    model = NetworkWorldModel(len(schema[0]), len(schema[1]))
    config = WorldModelTrainingConfig(
        epochs=arguments.epochs,
        chunk_length=arguments.chunk_length,
    )
    history = train_world_model(
        model,
        [sequence.graphs for sequence in sequences[:-1]],
        [sequences[-1].graphs],
        config=config,
        checkpoint_path=arguments.checkpoint,
        config_path=arguments.config,
        history_path=arguments.history,
    )
    print(
        f"best validation loss={history.best_validation_loss:.6f} "
        f"at epoch {history.best_epoch + 1}"
    )


if __name__ == "__main__":
    main()
