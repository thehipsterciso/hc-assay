"""Tests for assay_engine.graphs.anomaly."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from assay_engine.graphs.anomaly import (  # noqa: E402
    AnomalyGNNResult,
    CODAConfig,
    DOMINANTConfig,
    GANomalyConfig,
    card,
    cola,
    dominant,
)
from assay_engine.graphs.data import GraphData  # noqa: E402


def _triangle_with_features() -> GraphData:
    return GraphData(
        edge_index=[(0, 1), (1, 2), (2, 0)],
        num_nodes=3,
        node_features=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
    )


def _star_graph(n_leaves: int = 4) -> GraphData:
    edges = [(0, i) for i in range(1, n_leaves + 1)] + [(i, 0) for i in range(1, n_leaves + 1)]
    return GraphData(edge_index=edges, num_nodes=n_leaves + 1)


def test_dominant_result_type() -> None:
    g = _triangle_with_features()
    cfg = DOMINANTConfig(hidden_channels=8, epochs=5, seed=0)
    result = dominant(g, cfg)
    assert isinstance(result, AnomalyGNNResult)


def test_dominant_scores_length() -> None:
    g = _triangle_with_features()
    cfg = DOMINANTConfig(hidden_channels=8, epochs=5, seed=0)
    result = dominant(g, cfg)
    assert len(result.scores) == g.num_nodes
    assert len(result.outlier_flags) == g.num_nodes


def test_dominant_n_outliers_consistent() -> None:
    g = _triangle_with_features()
    cfg = DOMINANTConfig(hidden_channels=8, epochs=5, seed=0)
    result = dominant(g, cfg)
    assert result.n_outliers == sum(result.outlier_flags)


def test_dominant_threshold_at_percentile() -> None:
    g = _star_graph(4)
    cfg = DOMINANTConfig(hidden_channels=8, epochs=5, threshold_percentile=80.0, seed=0)
    result = dominant(g, cfg)
    above = [s > result.threshold for s in result.scores]
    assert result.outlier_flags == above


def test_dominant_no_features_synthesises_degree() -> None:
    g = GraphData(edge_index=[(0, 1), (1, 2), (0, 2)], num_nodes=3)
    cfg = DOMINANTConfig(hidden_channels=4, epochs=3, seed=1)
    result = dominant(g, cfg)
    assert len(result.scores) == 3


def test_dominant_empty_edges() -> None:
    g = GraphData(edge_index=[], num_nodes=3)
    cfg = DOMINANTConfig(hidden_channels=4, epochs=3, seed=0)
    result = dominant(g, cfg)
    assert len(result.scores) == 3


def test_dominant_raises_on_empty_graph() -> None:
    g = GraphData(edge_index=[], num_nodes=0)
    cfg = DOMINANTConfig()
    with pytest.raises(ValueError, match="at least one node"):
        dominant(g, cfg)


def test_anomaly_gnn_result_frozen() -> None:
    r = AnomalyGNNResult(scores=[0.1], outlier_flags=[False], threshold=0.5, n_outliers=0)
    with pytest.raises(Exception):
        r.threshold = 0.9  # type: ignore[misc]


def test_coda_config_defaults() -> None:
    cfg = CODAConfig()
    assert cfg.hidden_channels == 64
    assert cfg.epochs == 100
    assert cfg.lr == 0.005
    assert cfg.threshold_percentile == 95.0
    assert cfg.seed is None


def test_coda_config_custom() -> None:
    cfg = CODAConfig(hidden_channels=32, epochs=10, lr=0.001, threshold_percentile=90.0, seed=42)
    assert cfg.hidden_channels == 32
    assert cfg.seed == 42


def test_coda_config_frozen() -> None:
    cfg = CODAConfig()
    with pytest.raises(Exception):
        cfg.epochs = 999  # type: ignore[misc]


def test_ganomaly_config_defaults() -> None:
    cfg = GANomalyConfig()
    assert cfg.hidden_channels == 64
    assert cfg.epochs == 100
    assert cfg.lr == 0.005
    assert cfg.threshold_percentile == 95.0
    assert cfg.seed is None


def test_ganomaly_config_custom() -> None:
    cfg = GANomalyConfig(hidden_channels=16, epochs=5, seed=7)
    assert cfg.hidden_channels == 16
    assert cfg.seed == 7


def test_ganomaly_config_frozen() -> None:
    cfg = GANomalyConfig()
    with pytest.raises(Exception):
        cfg.lr = 1.0  # type: ignore[misc]


def test_cola_result_type() -> None:
    pytest.importorskip("pygod")
    g = _triangle_with_features()
    cfg = CODAConfig(hidden_channels=8, epochs=2, seed=0)
    try:
        result = cola(g, cfg)
    except ImportError as exc:
        pytest.skip(str(exc))
    assert isinstance(result, AnomalyGNNResult)
    assert len(result.scores) == g.num_nodes


def test_card_result_type() -> None:
    pytest.importorskip("pygod")
    g = _triangle_with_features()
    cfg = GANomalyConfig(hidden_channels=8, epochs=2, seed=0)
    try:
        result = card(g, cfg)
    except ImportError as exc:
        pytest.skip(str(exc))
    assert isinstance(result, AnomalyGNNResult)
    assert len(result.scores) == g.num_nodes
