"""Tests for assay_engine.graphs.classification."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("torch_geometric")

from assay_engine.graphs.classification import (  # noqa: E402
    GINConfig,
    GINModel,
    GraphClassificationResult,
    classify_graph,
    train_gin,
)
from assay_engine.graphs.data import GraphData  # noqa: E402


def _tiny_graph(n_nodes: int = 3, n_features: int = 4) -> GraphData:
    return GraphData(
        edge_index=[(0, 1), (1, 2), (2, 0)],
        num_nodes=n_nodes,
        node_features=[[float(i % 2), float((i + 1) % 2), 0.5, 1.0] for i in range(n_nodes)],
    )


def _make_graphs_and_labels(n: int = 3, n_classes: int = 2) -> tuple[list[GraphData], list[int]]:
    graphs = [_tiny_graph() for _ in range(n)]
    labels = [i % n_classes for i in range(n)]
    return graphs, labels


def test_gin_config_defaults() -> None:
    cfg = GINConfig(in_channels=4, hidden_channels=16, out_channels=2)
    assert cfg.num_layers == 5
    assert cfg.dropout == 0.5
    assert cfg.epochs == 100
    assert cfg.lr == 0.01
    assert cfg.seed is None


def test_train_gin_returns_module() -> None:
    import torch.nn as nn

    cfg = GINConfig(in_channels=4, hidden_channels=8, out_channels=2, epochs=2, seed=0)
    graphs, labels = _make_graphs_and_labels(n=4, n_classes=2)
    model = train_gin(graphs, labels, cfg)
    assert isinstance(model, nn.Module)


def test_classify_graph_result_type() -> None:
    cfg = GINConfig(in_channels=4, hidden_channels=8, out_channels=2, epochs=2, seed=0)
    graphs, labels = _make_graphs_and_labels(n=4, n_classes=2)
    model = train_gin(graphs, labels, cfg)
    result = classify_graph(model, _tiny_graph())
    assert isinstance(result, GraphClassificationResult)
    assert result.n_classes == 2


def test_classify_graph_probabilities_sum_to_one() -> None:
    cfg = GINConfig(in_channels=4, hidden_channels=8, out_channels=3, epochs=2, seed=1)
    graphs, labels = _make_graphs_and_labels(n=6, n_classes=3)
    model = train_gin(graphs, labels, cfg)
    result = classify_graph(model, _tiny_graph())
    assert abs(sum(result.class_probabilities) - 1.0) < 1e-5


def test_classify_graph_n_classes_matches_config() -> None:
    cfg = GINConfig(in_channels=4, hidden_channels=8, out_channels=4, epochs=2, seed=2)
    graphs, labels = _make_graphs_and_labels(n=8, n_classes=4)
    model = train_gin(graphs, labels, cfg)
    result = classify_graph(model, _tiny_graph())
    assert result.n_classes == 4


def test_train_gin_empty_graphs_raises() -> None:
    cfg = GINConfig(in_channels=4, hidden_channels=8, out_channels=2)
    with pytest.raises(ValueError, match="empty"):
        train_gin([], [], cfg)


def test_train_gin_mismatched_labels_raises() -> None:
    cfg = GINConfig(in_channels=4, hidden_channels=8, out_channels=2)
    graphs, _ = _make_graphs_and_labels(n=3)
    with pytest.raises(ValueError):
        train_gin(graphs, [0, 1], cfg)


def test_gin_model_factory_returns_module() -> None:
    import torch.nn as nn

    cfg = GINConfig(in_channels=4, hidden_channels=8, out_channels=2)
    model = GINModel(cfg)
    assert isinstance(model, nn.Module)
