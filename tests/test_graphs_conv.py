"""Tests for assay_engine.graphs.conv."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from assay_engine.graphs.conv import GAT, GCN, GATLayer, GCNLayer, GraphSAGE, SAGELayer  # noqa: E402


def _edge_index() -> "torch.Tensor":
    return torch.tensor([[0, 1, 1, 2], [1, 0, 2, 1]], dtype=torch.long)


def _features(num_nodes: int, in_channels: int) -> "torch.Tensor":
    return torch.randn(num_nodes, in_channels)


def test_gcn_layer_output_shape() -> None:
    layer = GCNLayer(4, 8)
    x = _features(3, 4)
    ei = _edge_index()
    out = layer(x, ei)
    assert out.shape == (3, 8)


def test_gat_layer_output_shape() -> None:
    layer = GATLayer(4, 8, heads=2)
    x = _features(3, 4)
    ei = _edge_index()
    out = layer(x, ei)
    assert out.shape == (3, 8)


def test_sage_layer_output_shape() -> None:
    layer = SAGELayer(4, 8)
    x = _features(3, 4)
    ei = _edge_index()
    out = layer(x, ei)
    assert out.shape == (3, 8)


def test_gcn_model_forward() -> None:
    model = GCN(in_channels=4, hidden_channels=8, out_channels=2, num_layers=2)
    x = _features(3, 4)
    ei = _edge_index()
    out = model(x, ei)
    assert out.shape == (3, 2)


def test_gcn_model_single_layer() -> None:
    model = GCN(in_channels=4, hidden_channels=8, out_channels=3, num_layers=1)
    x = _features(5, 4)
    ei = torch.tensor([[0, 1, 2, 3], [1, 2, 3, 4]], dtype=torch.long)
    out = model(x, ei)
    assert out.shape == (5, 3)


def test_gat_model_forward() -> None:
    model = GAT(in_channels=4, hidden_channels=8, out_channels=2, num_layers=2, heads=2)
    x = _features(3, 4)
    ei = _edge_index()
    out = model(x, ei)
    assert out.shape == (3, 2)


def test_graphsage_model_forward() -> None:
    model = GraphSAGE(in_channels=4, hidden_channels=8, out_channels=2, num_layers=2)
    x = _features(3, 4)
    ei = _edge_index()
    out = model(x, ei)
    assert out.shape == (3, 2)


def test_gcn_training_step() -> None:
    import torch.nn.functional as F

    model = GCN(in_channels=2, hidden_channels=4, out_channels=2)
    x = _features(4, 2)
    ei = torch.tensor([[0, 1, 2], [1, 2, 3]], dtype=torch.long)
    labels = torch.tensor([0, 1, 0, 1], dtype=torch.long)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

    model.train()
    out = model(x, ei)
    loss = F.cross_entropy(out, labels)
    loss.backward()
    optimizer.step()
    assert loss.item() > 0
