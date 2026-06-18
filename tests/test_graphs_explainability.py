"""Tests for assay_engine.graphs.explainability."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torch_geometric")

from assay_engine.graphs.data import GraphData  # noqa: E402
from assay_engine.graphs.explainability import (  # noqa: E402
    GNNExplainerConfig,
    NodeExplanation,
    explain_node,
    explain_nodes,
)


def _tiny_graph() -> GraphData:
    return GraphData(
        edge_index=[(0, 1), (1, 2), (2, 0)],
        num_nodes=3,
        node_features=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
    )


def _trained_node_model() -> object:
    import torch.nn as nn  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from torch_geometric.nn import GCNConv  # noqa: PLC0415

    class _GCN(nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self.conv1 = GCNConv(2, 8)
            self.conv2 = GCNConv(8, 3)

        def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
            x = F.relu(self.conv1(x, edge_index))
            return self.conv2(x, edge_index)

    return _GCN()


def test_explain_node_returns_node_explanation() -> None:
    model = _trained_node_model()
    graph = _tiny_graph()
    cfg = GNNExplainerConfig(epochs=5)
    result = explain_node(model, graph, node_idx=0, config=cfg)
    assert isinstance(result, NodeExplanation)
    assert result.node_idx == 0


def test_explain_node_correct_node_idx() -> None:
    model = _trained_node_model()
    graph = _tiny_graph()
    cfg = GNNExplainerConfig(epochs=5)
    result = explain_node(model, graph, node_idx=2, config=cfg)
    assert result.node_idx == 2


def test_explain_node_n_hops_matches_config() -> None:
    model = _trained_node_model()
    graph = _tiny_graph()
    cfg = GNNExplainerConfig(n_hops=3, epochs=5)
    result = explain_node(model, graph, node_idx=1, config=cfg)
    assert result.n_hops == 3


def test_explain_node_edge_mask_values_in_range() -> None:
    model = _trained_node_model()
    graph = _tiny_graph()
    cfg = GNNExplainerConfig(epochs=5)
    result = explain_node(model, graph, node_idx=0, config=cfg)
    for v in result.edge_mask:
        assert 0.0 <= v <= 1.0


def test_explain_node_out_of_range_raises() -> None:
    model = _trained_node_model()
    graph = _tiny_graph()
    cfg = GNNExplainerConfig(epochs=5)
    with pytest.raises(ValueError, match="out of range"):
        explain_node(model, graph, node_idx=10, config=cfg)


def test_explain_nodes_length_matches_input() -> None:
    model = _trained_node_model()
    graph = _tiny_graph()
    cfg = GNNExplainerConfig(epochs=5)
    indices = [0, 1, 2]
    results = explain_nodes(model, graph, node_indices=indices, config=cfg)
    assert len(results) == len(indices)


def test_explain_nodes_each_has_correct_idx() -> None:
    model = _trained_node_model()
    graph = _tiny_graph()
    cfg = GNNExplainerConfig(epochs=5)
    indices = [0, 2]
    results = explain_nodes(model, graph, node_indices=indices, config=cfg)
    assert results[0].node_idx == 0
    assert results[1].node_idx == 2
