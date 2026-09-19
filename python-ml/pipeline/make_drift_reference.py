"""Regenerate results/live_drift_reference.npz (Phase 72 provenance).

Samples every 10th window from each committed day contract
(day14/day15/day28/day0302), flattens with explain.shap_explain.flatten_graph
(1,284 graph-only features; the 5 temporal forecast-history features are
excluded from the reference), and stores means/stds/names. Run from repo root:

    python-ml/venv/bin/python python-ml/pipeline/make_drift_reference.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))

import numpy as np

from explain.shap_explain import flatten_graph, flattened_feature_names
from pipeline.graph_builder import load_graph_sequence

DAYS = ["day14", "day15", "day28", "day0302"]


def main() -> None:
    rows = []
    names = None
    for day in DAYS:
        contract_path = (
            REPO_ROOT / "data" / "processed" / "graph_contracts" / f"{day}.json"
        )
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        sequence = load_graph_sequence({
            "contractVersion": contract["contractVersion"],
            "nodeFeatureNames": contract["nodeFeatureNames"],
            "edgeFeatureNames": contract["edgeFeatureNames"],
            "windows": contract["windows"],
        })
        names = flattened_feature_names(
            sequence.node_feature_names, sequence.edge_feature_names)
        for graph in sequence.graphs[::10]:
            rows.append(flatten_graph(graph))
    matrix = np.stack(rows)
    out = REPO_ROOT / "results" / "live_drift_reference.npz"
    np.savez(out, means=matrix.mean(axis=0), stds=matrix.std(axis=0),
             names=np.array(names))
    print(f"sampled {matrix.shape[0]} windows, "
          f"{matrix.shape[1]} features -> {out}")


if __name__ == "__main__":
    main()
