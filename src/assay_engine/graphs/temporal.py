"""Temporal GNNs for time-series security event graphs.

All torch/pyg/pyg-temporal imports are lazy (inside function bodies) so this module is
importable without torch installed.  A3TGCN requires the optional
``torch_geometric_temporal`` package; a clear ImportError is raised if it is absent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from assay_engine.graphs.data import GraphData


@dataclass(frozen=True)
class TemporalSnapshot:
    """A single time-step in a temporal graph sequence.

    Attributes
    ----------
    graph:     The graph at this time-step.
    timestamp: Integer timestamp (e.g. Unix epoch second or sequence index).
    """

    graph: GraphData
    timestamp: int


@dataclass(frozen=True)
class A3TGCNConfig:
    """Configuration for the A3T-GCN temporal GNN model.

    Attributes
    ----------
    in_channels:  Number of input node feature dimensions.
    out_channels: Number of output feature dimensions per node.
    periods:      Number of time-steps in the prediction horizon.
    epochs:       Training epochs.
    lr:           Learning rate.
    """

    in_channels: int
    out_channels: int
    periods: int
    epochs: int = 50
    lr: float = 0.01


class A3TGCNModel:
    """Thin wrapper around ``torch_geometric_temporal.nn.recurrent.A3TGCN``.

    Raises ``ImportError`` at instantiation time if ``torch_geometric_temporal``
    is not installed.
    """

    def __init__(self, in_channels: int, out_channels: int, periods: int) -> None:
        try:
            import torch.nn as nn  # noqa: PLC0415
            from torch_geometric_temporal.nn.recurrent import A3TGCN  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "torch_geometric_temporal is required for A3TGCNModel. "
                "Install it with: pip install torch-geometric-temporal"
            ) from exc

        import torch  # noqa: PLC0415

        class _Model(nn.Module):  # type: ignore[misc]
            def __init__(self) -> None:
                super().__init__()
                self.recurrent = A3TGCN(in_channels, out_channels, periods)

            def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
                return self.recurrent(x, edge_index)

        self._model = _Model()

    def forward(self, x: Any, edge_index: Any) -> Any:
        return self._model(x, edge_index)

    @property
    def module(self) -> Any:
        return self._model


def train_a3tgcn(snapshots: list[TemporalSnapshot], config: A3TGCNConfig) -> A3TGCNModel:
    """Train an A3T-GCN model on a sequence of temporal snapshots.

    Each snapshot must have node features of shape (num_nodes, in_channels, periods).
    The model is trained to minimise MSE between predicted and actual node features.

    Raises ``ImportError`` if ``torch_geometric_temporal`` is not installed.
    """
    import torch  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415

    model = A3TGCNModel(config.in_channels, config.out_channels, config.periods)
    nn_model = model.module
    optimizer = torch.optim.Adam(nn_model.parameters(), lr=config.lr)

    for _ in range(config.epochs):
        nn_model.train()
        total_loss = torch.tensor(0.0)
        for snap in snapshots:
            g = snap.graph
            if not g.node_features:
                continue
            if g.edge_index:
                src = [e[0] for e in g.edge_index]
                dst = [e[1] for e in g.edge_index]
                edge_index_t = torch.tensor([src, dst], dtype=torch.long)
            else:
                edge_index_t = torch.zeros((2, 0), dtype=torch.long)
            x = torch.tensor(g.node_features, dtype=torch.float)
            optimizer.zero_grad()
            out = nn_model(x, edge_index_t)
            loss = F.mse_loss(out, x)
            loss.backward()
            optimizer.step()
            total_loss = total_loss + loss.detach()

    return model
