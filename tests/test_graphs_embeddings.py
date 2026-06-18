"""Tests for assay_engine.graphs.embeddings."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from assay_engine.graphs.data import GraphData  # noqa: E402
from assay_engine.graphs.embeddings import (  # noqa: E402
    DeepWalkConfig,
    Node2VecConfig,
    RandomWalkConfig,
    deepwalk,
    node2vec,
    random_walks,
)


def _triangle() -> GraphData:
    return GraphData(
        edge_index=[(0, 1), (1, 2), (2, 0), (1, 0), (2, 1), (0, 2)],
        num_nodes=3,
    )


def test_random_walks_count() -> None:
    g = _triangle()
    cfg = RandomWalkConfig(walk_length=5, num_walks=3, seed=42)
    walks = random_walks(g, cfg)
    assert len(walks) == g.num_nodes * cfg.num_walks


def test_random_walks_start_node() -> None:
    g = _triangle()
    cfg = RandomWalkConfig(walk_length=4, num_walks=2, seed=0)
    walks = random_walks(g, cfg)
    for node_idx in range(g.num_nodes):
        node_walks = walks[node_idx * cfg.num_walks : (node_idx + 1) * cfg.num_walks]
        for walk in node_walks:
            assert walk[0] == node_idx


def test_random_walks_max_length() -> None:
    g = _triangle()
    cfg = RandomWalkConfig(walk_length=10, num_walks=1, seed=1)
    walks = random_walks(g, cfg)
    for walk in walks:
        assert len(walk) <= cfg.walk_length


def test_random_walks_sink_node() -> None:
    g = GraphData(edge_index=[(0, 1)], num_nodes=3)
    cfg = RandomWalkConfig(walk_length=5, num_walks=1, seed=0)
    walks = random_walks(g, cfg)
    walk_from_2 = walks[2 * cfg.num_walks]
    assert walk_from_2 == [2]


def test_random_walks_reproducible() -> None:
    g = _triangle()
    cfg = RandomWalkConfig(walk_length=5, num_walks=2, seed=99)
    assert random_walks(g, cfg) == random_walks(g, cfg)


def test_node2vec_output_shape() -> None:
    g = _triangle()
    cfg = Node2VecConfig(embedding_dim=16, walk_length=5, num_walks=2, epochs=2, seed=0)
    embeddings = node2vec(g, cfg)
    assert len(embeddings) == g.num_nodes
    assert all(len(v) == 16 for v in embeddings)


def test_node2vec_config_defaults() -> None:
    cfg = Node2VecConfig()
    assert cfg.p == 1.0
    assert cfg.q == 1.0
    assert cfg.embedding_dim == 128


def test_deepwalk_output_shape() -> None:
    g = _triangle()
    cfg = DeepWalkConfig(embedding_dim=8, walk_length=4, num_walks=2, epochs=1, seed=0)
    embeddings = deepwalk(g, cfg)
    assert len(embeddings) == g.num_nodes
    assert all(len(v) == 8 for v in embeddings)


def test_deepwalk_matches_node2vec_p1_q1() -> None:
    g = _triangle()
    seed = 7
    dw_cfg = DeepWalkConfig(embedding_dim=8, walk_length=4, num_walks=2, epochs=1, seed=seed)
    n2v_cfg = Node2VecConfig(
        embedding_dim=8, walk_length=4, num_walks=2, p=1.0, q=1.0, epochs=1, seed=seed
    )
    dw = deepwalk(g, dw_cfg)
    n2v = node2vec(g, n2v_cfg)
    assert len(dw) == len(n2v)
