"""Graph data types and conversion utilities.

All torch/pyg imports are lazy (inside function bodies) so this module is importable
without torch installed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphData:
    """Immutable graph representation compatible with PyTorch Geometric.

    Attributes
    ----------
    edge_index:    List of (src, dst) integer pairs.
    num_nodes:     Total number of nodes in the graph.
    node_features: Optional per-node feature vectors.
    edge_weights:  Optional per-edge scalar weights.
    node_labels:   Optional per-node integer class labels.
    """

    edge_index: list[tuple[int, int]]
    num_nodes: int
    node_features: list[list[float]] | None = None
    edge_weights: list[float] | None = None
    node_labels: list[int] | None = None


def to_pyg(g: GraphData) -> object:
    """Convert a ``GraphData`` instance to a ``torch_geometric.data.Data`` object."""
    import torch  # noqa: PLC0415
    from torch_geometric.data import Data  # noqa: PLC0415

    if g.edge_index:
        src = [e[0] for e in g.edge_index]
        dst = [e[1] for e in g.edge_index]
        edge_index_t = torch.tensor([src, dst], dtype=torch.long)
    else:
        edge_index_t = torch.zeros((2, 0), dtype=torch.long)

    x = torch.tensor(g.node_features, dtype=torch.float) if g.node_features is not None else None
    edge_attr = (
        torch.tensor(g.edge_weights, dtype=torch.float) if g.edge_weights is not None else None
    )
    y = torch.tensor(g.node_labels, dtype=torch.long) if g.node_labels is not None else None
    return Data(x=x, edge_index=edge_index_t, edge_attr=edge_attr, y=y, num_nodes=g.num_nodes)


def from_adjacency_matrix(matrix: list[list[float]]) -> GraphData:
    """Build a ``GraphData`` from a square adjacency matrix (non-zero = edge)."""
    n = len(matrix)
    edges: list[tuple[int, int]] = []
    weights: list[float] = []
    for i in range(n):
        for j in range(n):
            if matrix[i][j] != 0.0:
                edges.append((i, j))
                weights.append(matrix[i][j])
    return GraphData(
        edge_index=edges,
        num_nodes=n,
        edge_weights=weights if weights else None,
    )


def from_edge_list(edges: list[tuple[int, int]], num_nodes: int) -> GraphData:
    """Build a ``GraphData`` from an explicit edge list."""
    return GraphData(edge_index=edges, num_nodes=num_nodes)
