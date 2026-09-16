"""Ordered PyTorch Geometric batching for KAIROS graph sequences."""

from __future__ import annotations

from torch_geometric.loader import DataLoader

from pipeline.graph_builder import LoadedGraphSequence


def make_graph_dataloader(
    sequence: LoadedGraphSequence,
    *,
    batch_size: int,
    shuffle: bool = False,
) -> DataLoader:
    """Create a variable-graph-size loader; chronological order is the default."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if not sequence.graphs:
        raise ValueError("graph sequence is empty")
    return DataLoader(
        list(sequence.graphs),
        batch_size=batch_size,
        shuffle=shuffle,
    )
