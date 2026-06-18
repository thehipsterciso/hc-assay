"""Tests for assay_engine.graphs.data."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from assay_engine.graphs.data import (  # noqa: E402
    GraphData,
    from_adjacency_matrix,
    from_edge_list,
    to_pyg,
)


def _small_graph() -> GraphData:
    return GraphData(
        edge_index=[(0, 1), (1, 2), (2, 0)],
        num_nodes=3,
        node_features=[[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
        node_labels=[0, 1, 0],
    )


def test_graphdata_is_frozen() -> None:
    g = _small_graph()
    with pytest.raises(Exception):
        object.__setattr__(g, "num_nodes", 99)


def test_to_pyg_edge_index_shape() -> None:
    g = _small_graph()
    data = to_pyg(g)
    assert data.edge_index.shape == (2, 3)
    assert data.num_nodes == 3


def test_to_pyg_node_features() -> None:
    g = _small_graph()
    data = to_pyg(g)
    assert data.x is not None
    assert data.x.shape == (3, 2)


def test_to_pyg_node_labels() -> None:
    g = _small_graph()
    data = to_pyg(g)
    assert data.y is not None
    assert data.y.tolist() == [0, 1, 0]


def test_to_pyg_empty_graph() -> None:
    g = GraphData(edge_index=[], num_nodes=4)
    data = to_pyg(g)
    assert data.edge_index.shape == (2, 0)
    assert data.num_nodes == 4
    assert data.x is None


def test_to_pyg_edge_weights() -> None:
    g = GraphData(
        edge_index=[(0, 1), (1, 2)],
        num_nodes=3,
        edge_weights=[0.5, 1.5],
    )
    data = to_pyg(g)
    assert data.edge_attr is not None
    assert data.edge_attr.tolist() == pytest.approx([0.5, 1.5])


def test_from_adjacency_matrix_triangle() -> None:
    matrix = [
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
    ]
    g = from_adjacency_matrix(matrix)
    assert g.num_nodes == 3
    assert len(g.edge_index) == 3
    assert g.edge_weights is not None
    assert all(w == 1.0 for w in g.edge_weights)


def test_from_adjacency_matrix_weighted() -> None:
    matrix = [
        [0.0, 2.5],
        [0.0, 0.0],
    ]
    g = from_adjacency_matrix(matrix)
    assert g.edge_weights is not None
    assert g.edge_weights[0] == pytest.approx(2.5)


def test_from_adjacency_matrix_all_zeros() -> None:
    matrix = [[0.0, 0.0], [0.0, 0.0]]
    g = from_adjacency_matrix(matrix)
    assert g.edge_index == []
    assert g.edge_weights is None


def test_from_edge_list_basic() -> None:
    edges = [(0, 1), (1, 2), (0, 2)]
    g = from_edge_list(edges, num_nodes=3)
    assert g.num_nodes == 3
    assert g.edge_index == edges
    assert g.node_features is None


def test_round_trip_graphdata_to_pyg() -> None:
    g = _small_graph()
    data = to_pyg(g)
    reconstructed_edges = list(zip(data.edge_index[0].tolist(), data.edge_index[1].tolist()))
    assert reconstructed_edges == g.edge_index
