"""GNN layer and model implementations.

All torch and torch_geometric imports are lazy (inside function/class bodies) so this
module is importable without torch installed.  Module-level class definitions use a
factory pattern where the actual nn.Module is built on first instantiation.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Single-layer wrappers
# ---------------------------------------------------------------------------


class GCNLayer:
    """Graph Convolutional Network layer (Kipf & Welling, 2017)."""

    def __init__(self, in_channels: int, out_channels: int) -> None:
        import torch.nn as nn  # noqa: PLC0415
        from torch_geometric.nn import GCNConv  # noqa: PLC0415

        self._conv = GCNConv(in_channels, out_channels)
        self._module: nn.Module = self._conv

    def __call__(self, x: Any, edge_index: Any) -> Any:
        return self._conv(x, edge_index)


class GATLayer:
    """Graph Attention Network layer (Veličković et al., 2018) using GATv2Conv."""

    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        heads: int = 1,
        dropout: float = 0.0,
    ) -> None:
        from torch_geometric.nn import GATv2Conv  # noqa: PLC0415

        self._conv = GATv2Conv(
            in_channels, out_channels, heads=heads, dropout=dropout, concat=False
        )

    def __call__(self, x: Any, edge_index: Any) -> Any:
        return self._conv(x, edge_index)


class SAGELayer:
    """GraphSAGE layer (Hamilton et al., 2017)."""

    def __init__(self, in_channels: int, out_channels: int, aggr: str = "mean") -> None:
        from torch_geometric.nn import SAGEConv  # noqa: PLC0415

        self._conv = SAGEConv(in_channels, out_channels, aggr=aggr)

    def __call__(self, x: Any, edge_index: Any) -> Any:
        return self._conv(x, edge_index)


# ---------------------------------------------------------------------------
# Full models (torch.nn.Module subclasses, built lazily via factory functions)
# ---------------------------------------------------------------------------


def GCN(  # noqa: N802
    in_channels: int,
    hidden_channels: int,
    out_channels: int,
    num_layers: int = 2,
    dropout: float = 0.5,
) -> Any:
    """Return a full GCN model (stacked GCNConv + ReLU + dropout).

    Returns a ``torch.nn.Module`` with ``forward(x, edge_index) -> Tensor``.
    """
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from torch_geometric.nn import GCNConv  # noqa: PLC0415

    class _GCN(nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            sizes = [in_channels] + [hidden_channels] * (num_layers - 1) + [out_channels]
            self.convs = nn.ModuleList([GCNConv(sizes[i], sizes[i + 1]) for i in range(num_layers)])
            self._dropout = dropout

        def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
            for i, conv in enumerate(self.convs):
                x = conv(x, edge_index)
                if i < len(self.convs) - 1:
                    x = F.relu(x)
                    x = F.dropout(x, p=self._dropout, training=self.training)
            return x

    return _GCN()


def GAT(  # noqa: N802
    in_channels: int,
    hidden_channels: int,
    out_channels: int,
    num_layers: int = 2,
    heads: int = 4,
    dropout: float = 0.5,
) -> Any:
    """Return a full GAT model (stacked GATv2Conv + ELU + dropout).

    Returns a ``torch.nn.Module`` with ``forward(x, edge_index) -> Tensor``.
    """
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from torch_geometric.nn import GATv2Conv  # noqa: PLC0415

    class _GAT(nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self.convs = nn.ModuleList()
            for i in range(num_layers):
                ic = in_channels if i == 0 else hidden_channels
                oc = out_channels if i == num_layers - 1 else hidden_channels
                h = 1 if i == num_layers - 1 else heads
                self.convs.append(GATv2Conv(ic, oc, heads=h, dropout=dropout, concat=False))
            self._dropout = dropout

        def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
            for i, conv in enumerate(self.convs):
                x = conv(x, edge_index)
                if i < len(self.convs) - 1:
                    x = F.elu(x)
                    x = F.dropout(x, p=self._dropout, training=self.training)
            return x

    return _GAT()


def GraphSAGE(  # noqa: N802
    in_channels: int,
    hidden_channels: int,
    out_channels: int,
    num_layers: int = 2,
    dropout: float = 0.5,
) -> Any:
    """Return a full GraphSAGE model (stacked SAGEConv + ReLU + dropout).

    Returns a ``torch.nn.Module`` with ``forward(x, edge_index) -> Tensor``.
    """
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from torch_geometric.nn import SAGEConv  # noqa: PLC0415

    class _GraphSAGE(nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            sizes = [in_channels] + [hidden_channels] * (num_layers - 1) + [out_channels]
            self.convs = nn.ModuleList(
                [SAGEConv(sizes[i], sizes[i + 1]) for i in range(num_layers)]
            )
            self._dropout = dropout

        def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
            for i, conv in enumerate(self.convs):
                x = conv(x, edge_index)
                if i < len(self.convs) - 1:
                    x = F.relu(x)
                    x = F.dropout(x, p=self._dropout, training=self.training)
            return x

    return _GraphSAGE()
