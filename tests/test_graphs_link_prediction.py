"""Tests for assay_engine.graphs.link_prediction."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from assay_engine.graphs.data import GraphData  # noqa: E402
from assay_engine.graphs.link_prediction import (  # noqa: E402
    LinkPredictionResult,
    LinkPredictor,
    LinkPredictorConfig,
    predict_links,
    train_link_predictor,
)


def _chain_graph() -> GraphData:
    return GraphData(
        edge_index=[(0, 1), (1, 2), (2, 3)],
        num_nodes=4,
        node_features=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.5, 0.5]],
    )


def test_link_predictor_forward_shape() -> None:
    model = LinkPredictor(in_channels=2, hidden_channels=8)
    x = torch.randn(4, 2)
    ei = torch.tensor([[0, 1, 2], [1, 2, 3]], dtype=torch.long)
    z = model(x, ei)
    assert z.shape == (4, 8)


def test_link_predictor_decode_shape() -> None:
    model = LinkPredictor(in_channels=2, hidden_channels=8)
    x = torch.randn(4, 2)
    ei = torch.tensor([[0, 1], [1, 2]], dtype=torch.long)
    z = model(x, ei)
    cands = torch.tensor([[0, 2], [1, 3]], dtype=torch.long)
    scores = model.decode(z, cands)
    assert scores.shape == (2,)
    assert all(0.0 <= s.item() <= 1.0 for s in scores)


def test_train_link_predictor_runs() -> None:
    g = _chain_graph()
    cfg = LinkPredictorConfig(hidden_channels=8, num_layers=1, epochs=5, lr=0.01)
    model = train_link_predictor(g, cfg)
    assert model is not None


def test_train_link_predictor_no_features() -> None:
    g = GraphData(edge_index=[(0, 1), (1, 2), (2, 3)], num_nodes=4)
    cfg = LinkPredictorConfig(hidden_channels=4, num_layers=1, epochs=3)
    model = train_link_predictor(g, cfg)
    assert model is not None


def test_train_link_predictor_empty_graph_raises() -> None:
    g = GraphData(edge_index=[], num_nodes=0)
    cfg = LinkPredictorConfig()
    with pytest.raises(ValueError, match="at least one node"):
        train_link_predictor(g, cfg)


def test_predict_links_result_type() -> None:
    g = _chain_graph()
    cfg = LinkPredictorConfig(hidden_channels=8, num_layers=1, epochs=3)
    model = train_link_predictor(g, cfg)
    candidates = [(0, 2), (1, 3), (0, 3)]
    result = predict_links(model, g, candidates)
    assert isinstance(result, LinkPredictionResult)


def test_predict_links_scores_length() -> None:
    g = _chain_graph()
    cfg = LinkPredictorConfig(hidden_channels=8, num_layers=1, epochs=3)
    model = train_link_predictor(g, cfg)
    candidates = [(0, 2), (1, 3)]
    result = predict_links(model, g, candidates)
    assert len(result.scores) == 2
    assert len(result.candidate_edges) == 2


def test_predict_links_scores_in_range() -> None:
    g = _chain_graph()
    cfg = LinkPredictorConfig(hidden_channels=8, num_layers=1, epochs=3)
    model = train_link_predictor(g, cfg)
    candidates = [(0, 2), (1, 3), (0, 3)]
    result = predict_links(model, g, candidates)
    assert all(0.0 <= s <= 1.0 for s in result.scores)


def test_predict_links_predicted_links_above_threshold() -> None:
    g = _chain_graph()
    cfg = LinkPredictorConfig(hidden_channels=8, num_layers=1, epochs=3)
    model = train_link_predictor(g, cfg)
    candidates = [(0, 2), (1, 3), (0, 3)]
    result = predict_links(model, g, candidates)
    for edge, score in zip(result.candidate_edges, result.scores):
        if score >= 0.5:
            assert edge in result.predicted_links
        else:
            assert edge not in result.predicted_links


def test_predict_links_empty_candidates() -> None:
    g = _chain_graph()
    cfg = LinkPredictorConfig(hidden_channels=4, num_layers=1, epochs=2)
    model = train_link_predictor(g, cfg)
    result = predict_links(model, g, [])
    assert result.candidate_edges == []
    assert result.scores == []
    assert result.predicted_links == []


def test_link_prediction_result_frozen() -> None:
    r = LinkPredictionResult(candidate_edges=[(0, 1)], scores=[0.8], predicted_links=[(0, 1)])
    with pytest.raises(Exception):
        r.scores = [0.0]  # type: ignore[misc]
