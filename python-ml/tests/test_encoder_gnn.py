"""Tests for Phases 17-20: GraphSAGE, pooling, sanity overfit, batching."""

from __future__ import annotations

import unittest

import torch
from torch import nn
from torch.nn import functional as F
from torch_geometric.data import Batch

from model.encoder_gnn import GraphEncoder
from pipeline.graph_builder import load_graph_sequence
from pipeline.graph_dataset import make_graph_dataloader
from test_logistic_regression import sequence_payload


class GraphEncoderTest(unittest.TestCase):
    def setUp(self) -> None:
        torch.manual_seed(7)
        self.sequence = load_graph_sequence(sequence_payload(30))

    def test_mean_and_attention_pooling_encode_variable_graph_batches(self) -> None:
        batch = Batch.from_data_list(list(self.sequence.graphs[:3]))
        for pooling in ("mean", "attention"):
            encoder = GraphEncoder(
                node_feature_dim=1,
                edge_feature_dim=1,
                hidden_dim=8,
                output_dim=6,
                num_layers=2,
                pooling=pooling,
                dropout=0.0,
            )
            embedding = encoder(batch)
            self.assertEqual(tuple(embedding.shape), (3, 6))
            self.assertTrue(torch.isfinite(embedding).all())
            embedding.sum().backward()
            self.assertTrue(any(
                parameter.grad is not None for parameter in encoder.parameters()
            ))

    def test_ordered_dataloader_batches_variable_graphs(self) -> None:
        loader = make_graph_dataloader(self.sequence, batch_size=7)
        batches = list(loader)

        self.assertEqual(len(batches), 5)
        self.assertEqual(batches[0].num_graphs, 7)
        self.assertEqual(batches[-1].num_graphs, 2)
        self.assertEqual(
            batches[0].window_start[0], self.sequence.graphs[0].window_start
        )

    def test_encoder_and_linear_head_can_overfit_small_sanity_set(self) -> None:
        graphs = []
        for index, graph in enumerate(self.sequence.graphs[:24]):
            label = float(index % 2)
            graph = graph.clone()
            graph.x = torch.tensor([[label], [label]], dtype=torch.float32)
            graph.edge_attr = torch.tensor([[label]], dtype=torch.float32)
            graph.y_infiltration = torch.tensor([label], dtype=torch.float32)
            graphs.append(graph)
        batch = Batch.from_data_list(graphs)
        encoder = GraphEncoder(
            1,
            1,
            hidden_dim=12,
            output_dim=8,
            num_layers=2,
            dropout=0.0,
        )
        head = nn.Linear(8, 1)
        optimizer = torch.optim.Adam(
            list(encoder.parameters()) + list(head.parameters()), lr=0.03
        )
        target = batch.y_infiltration
        losses = []
        for _ in range(100):
            optimizer.zero_grad()
            logits = head(encoder(batch)).squeeze(-1)
            loss = F.binary_cross_entropy_with_logits(logits, target)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach()))

        self.assertLess(losses[-1], losses[0] * 0.1)
        self.assertLess(losses[-1], 0.05)


if __name__ == "__main__":
    unittest.main()
