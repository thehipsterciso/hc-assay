"""Tests for assay_engine.graphs.heterogeneous."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from assay_engine.graphs.heterogeneous import (  # noqa: E402
    HGTConfig,
    HGTModel,
    HeteroGraphData,
    to_pyg_hetero,
    train_hgt,
)


def _simple_hetero() -> HeteroGraphData:
    return HeteroGraphData(
        node_types=["user", "host"],
        edge_types=[("user", "connects", "host")],
        node_features={
            "user": [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]],
            "host": [[0.5, 0.5], [0.2, 0.8]],
        },
        edge_index={
            ("user", "connects", "host"): [(0, 0), (1, 1), (2, 0)],
        },
        node_labels={"user": [0, 1, 0]},
    )


def test_hetero_graph_data_frozen() -> None:
    g = _simple_hetero()
    with pytest.raises(Exception):
        g.node_types = []  # type: ignore[misc]


def test_to_pyg_hetero_node_features() -> None:
    g = _simple_hetero()
    data = to_pyg_hetero(g)
    assert data["user"].x.shape == (3, 2)
    assert data["host"].x.shape == (2, 2)


def test_to_pyg_hetero_edge_index() -> None:
    g = _simple_hetero()
    data = to_pyg_hetero(g)
    ei = data[("user", "connects", "host")].edge_index
    assert ei.shape == (2, 3)


def test_to_pyg_hetero_node_labels() -> None:
    g = _simple_hetero()
    data = to_pyg_hetero(g)
    assert data["user"].y.tolist() == [0, 1, 0]


def test_to_pyg_hetero_no_labels() -> None:
    g = HeteroGraphData(
        node_types=["user"],
        edge_types=[],
        node_features={"user": [[1.0], [0.0]]},
        edge_index={},
    )
    data = to_pyg_hetero(g)
    assert not hasattr(data["user"], "y") or data["user"].y is None


def test_hgt_model_output_shape() -> None:
    g = _simple_hetero()
    cfg = HGTConfig(hidden_channels=16, num_heads=1, num_layers=1)
    model = HGTModel(g, "user", cfg)
    import torch  # noqa: PLC0415
    from torch_geometric.data import HeteroData  # noqa: PLC0415

    pyg_data: HeteroData = to_pyg_hetero(g)  # type: ignore[assignment]
    x_dict = {ntype: pyg_data[ntype].x for ntype in g.node_types}
    edge_index_dict = {etype: pyg_data[etype].edge_index for etype in g.edge_types}
    model.eval()
    with torch.no_grad():
        out = model(x_dict, edge_index_dict)
    assert out.shape[0] == 3


def test_train_hgt_runs() -> None:
    g = _simple_hetero()
    cfg = HGTConfig(hidden_channels=8, num_heads=1, num_layers=1, epochs=3, lr=0.01)
    model = train_hgt(g, "user", cfg)
    assert model is not None


def test_train_hgt_no_labels() -> None:
    g = HeteroGraphData(
        node_types=["host"],
        edge_types=[],
        node_features={"host": [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]},
        edge_index={},
    )
    cfg = HGTConfig(hidden_channels=4, num_heads=1, num_layers=1, epochs=2)
    model = train_hgt(g, "host", cfg)
    assert model is not None
