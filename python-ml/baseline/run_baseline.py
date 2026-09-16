"""Command-line runner for the reproducible KAIROS logistic baselines."""

from __future__ import annotations

import argparse
from pathlib import Path

from baseline.logistic_regression import run_baselines
from pipeline.graph_builder import load_graph_sequences


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("contracts", nargs="+", type=Path)
    parser.add_argument("--results", type=Path, default=Path("../results"))
    parser.add_argument("--weights", type=Path, default=Path("weights"))
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--max-iter", type=int, default=1000)
    arguments = parser.parse_args()

    sequence = load_graph_sequences(arguments.contracts)
    run = run_baselines(
        sequence,
        results_directory=arguments.results,
        weights_directory=arguments.weights,
        test_fraction=arguments.test_fraction,
        max_iter=arguments.max_iter,
    )
    print(
        f"trained on {run.split.x_train.shape[0]} windows; "
        f"tested on {run.split.x_test.shape[0]} windows; "
        f"binary F1={run.metrics['binary']['f1']:.4f}; "
        f"stage macro F1={run.metrics['stage']['macro_f1']:.4f}"
    )


if __name__ == "__main__":
    main()
