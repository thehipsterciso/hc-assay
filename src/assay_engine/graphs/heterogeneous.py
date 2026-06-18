"""Heterogeneous GNNs for multi-entity security graphs.

All torch/pyg imports are lazy (inside function bodies) so this module is importable
without torch installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HeteroGraphData:
    """Immutable heterogeneous graph representation.

    Attributes
    ----------
    node_types:    List of node type names.
    edge_types:    List of (src_type, relation, dst_type) triples.
    node_features: Mapping from node type to list of feature vectors.
    edge_index:    Mapping from edge-type triple to list of (src, dst) pairs.
    node_labels:   Optional mapping from node type to integer label list.
    """

    node_types: list[str]
    edge_types: list[tuple[str, str, str]]
    node_features: dict[str, list[list[float]]]
    edge_index: dict[tuple[str, str, str], list[tuple[int, int]]]
    node_labels: dict[str, list[int]] | None = None


def to_pyg_hetero(g: HeteroGraphData) -> object:
    """Convert a ``HeteroGraphData`` to a ``torch_geometric.data.HeteroData`` object."""
    import torch  # noqa: PLC0415
    from torch_geometric.data import HeteroData  # noqa: PLC0415

    data = HeteroData()
    for ntype, feats in g.node_features.items():
        data[ntype].x = torch.tensor(feats, dtype=torch.float)
        if g.node_labels and ntype in g.node_labels:
            data[ntype].y = torch.tensor(g.node_labels[ntype], dtype=torch.long)

    for etype, edges in g.edge_index.items():
        if edges:
            src_list = [e[0] for e in edges]
            dst_list = [e[1] for e in edges]
            data[etype].edge_index = torch.tensor([src_list, dst_list], dtype=torch.long)
        else:
            data[etype].edge_index = torch.zeros((2, 0), dtype=torch.long)

    return data


@dataclass(frozen=True)
class HGTConfig:
    """Configuration for the Heterogeneous Graph Transformer (HGT) model.

    Attributes
    ----------
    hidden_channels: Hidden dimension per node type.
    num_heads:       Attention heads in HGTConv.
    num_layers:      Number of stacked HGTConv layers.
    epochs:          Training epochs.
    lr:              Learning rate.
    """

    hidden_channels: int = 64
    num_heads: int = 2
    num_layers: int = 2
    epochs: int = 100
    lr: float = 0.005


def HGTModel(  # noqa: N802
    g: HeteroGraphData,
    target_node_type: str,
    config: HGTConfig,
) -> Any:
    """Return an HGT model for the given heterogeneous graph schema.

    Returns a ``torch.nn.Module`` with ``forward(x_dict, edge_index_dict) -> Tensor``
    that produces logits for *target_node_type* nodes.
    """
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from torch_geometric.nn import HGTConv, Linear  # noqa: PLC0415

    metadata = (g.node_types, g.edge_types)
    target_labels = (g.node_labels or {}).get(target_node_type, [])
    out_channels = max(target_labels) + 1 if target_labels else 2

    in_dims: dict[str, int] = {
        ntype: len(feats[0]) if feats else 1 for ntype, feats in g.node_features.items()
    }

    class _HGT(nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self.lin_dict = nn.ModuleDict(
                {ntype: Linear(dim, config.hidden_channels) for ntype, dim in in_dims.items()}
            )
            self.convs = nn.ModuleList(
                [
                    HGTConv(
                        config.hidden_channels, config.hidden_channels, metadata, config.num_heads
                    )
                    for _ in range(config.num_layers)
                ]
            )
            self.lin_out = Linear(config.hidden_channels, out_channels)

        def forward(
            self,
            x_dict: dict[str, torch.Tensor],
            edge_index_dict: dict[tuple[str, str, str], torch.Tensor],
        ) -> torch.Tensor:
            h = {ntype: F.relu(self.lin_dict[ntype](x)) for ntype, x in x_dict.items()}
            for conv in self.convs:
                h = conv(h, edge_index_dict)
            return self.lin_out(h[target_node_type])  # type: ignore[return-value]

    return _HGT()


def train_hgt(
    g: HeteroGraphData,
    target_node_type: str,
    config: HGTConfig,
) -> Any:
    """Train an HGT model for node classification on *target_node_type*.

    Returns the trained ``torch.nn.Module``.
    """
    import torch  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415

    pyg_data: Any = to_pyg_hetero(g)
    model = HGTModel(g, target_node_type, config)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)

    x_dict = {ntype: pyg_data[ntype].x for ntype in g.node_types if hasattr(pyg_data[ntype], "x")}
    edge_index_dict = {etype: pyg_data[etype].edge_index for etype in g.edge_types}

    if g.node_labels and target_node_type in g.node_labels:
        y = torch.tensor(g.node_labels[target_node_type], dtype=torch.long)
    else:
        n = len(g.node_features.get(target_node_type, []))
        y = torch.zeros(n, dtype=torch.long)

    for _ in range(config.epochs):
        model.train()
        optimizer.zero_grad()
        out = model(x_dict, edge_index_dict)
        loss = F.cross_entropy(out, y)
        loss.backward()  # type: ignore[no-untyped-call]
        optimizer.step()

    return model
