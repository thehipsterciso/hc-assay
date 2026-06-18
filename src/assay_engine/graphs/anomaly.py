"""GNN-based anomaly detection algorithms.

All torch/pyg imports are lazy (inside function bodies) so this module is importable
without torch installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from assay_engine.graphs.data import GraphData


@dataclass(frozen=True)
class AnomalyGNNResult:
    """Output of a GNN-based anomaly detection pass.

    Attributes
    ----------
    scores:        Per-node anomaly score (higher = more anomalous).
    outlier_flags: Boolean flag per node (True = outlier).
    threshold:     Score threshold used to set flags.
    n_outliers:    Count of nodes flagged as outliers.
    """

    scores: list[float]
    outlier_flags: list[bool]
    threshold: float
    n_outliers: int


@dataclass(frozen=True)
class DOMINANTConfig:
    """Configuration for the DOMINANT anomaly detector.

    Attributes
    ----------
    hidden_channels:      Hidden dimension for the GCN encoder.
    epochs:               Training epochs.
    lr:                   Learning rate.
    threshold_percentile: Percentile of score distribution used as the outlier threshold.
    seed:                 Optional RNG seed for reproducibility.
    """

    hidden_channels: int = 64
    epochs: int = 100
    lr: float = 0.005
    threshold_percentile: float = 95.0
    seed: int | None = None


def dominant(g: GraphData, config: DOMINANTConfig) -> AnomalyGNNResult:
    """DOMINANT: GCN-based structure and attribute anomaly detection (Ding et al., 2019).

    Trains a GCN autoencoder that reconstructs both the adjacency matrix (structure)
    and the node feature matrix (attribute).  The per-node anomaly score is:

        score = 0.5 * structure_error + 0.5 * attribute_error

    The outlier threshold is set at ``config.threshold_percentile`` of the score
    distribution over all nodes.

    If ``g.node_features`` is None, a degree-based feature matrix is synthesised
    (each node's single feature = its out-degree / num_nodes).
    """
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from torch_geometric.nn import GCNConv  # noqa: PLC0415

    if config.seed is not None:
        torch.manual_seed(config.seed)

    n = g.num_nodes
    if n == 0:
        raise ValueError("Graph must have at least one node")

    if g.edge_index:
        src = [e[0] for e in g.edge_index]
        dst = [e[1] for e in g.edge_index]
        edge_index_t = torch.tensor([src, dst], dtype=torch.long)
    else:
        edge_index_t = torch.zeros((2, 0), dtype=torch.long)

    if g.node_features is not None:
        x = torch.tensor(g.node_features, dtype=torch.float)
    else:
        degrees = [0.0] * n
        for s, _ in g.edge_index:
            degrees[s] += 1.0
        x = torch.tensor([[d / n] for d in degrees], dtype=torch.float)

    in_dim = x.shape[1]
    hid = config.hidden_channels

    adj_dense = torch.zeros((n, n), dtype=torch.float)
    for s, d in g.edge_index:
        adj_dense[s, d] = 1.0

    class _Encoder(nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self.conv1 = GCNConv(in_dim, hid)
            self.conv2 = GCNConv(hid, hid)

        def forward(self, xin: torch.Tensor, ei: torch.Tensor) -> torch.Tensor:
            z = F.relu(self.conv1(xin, ei))
            return self.conv2(z, ei)

    encoder = _Encoder()
    optimizer = torch.optim.Adam(encoder.parameters(), lr=config.lr)

    for _ in range(config.epochs):
        encoder.train()
        optimizer.zero_grad()
        z = encoder(x, edge_index_t)
        adj_recon = torch.sigmoid(z @ z.T)
        attr_recon = z @ z.T
        struct_loss = F.binary_cross_entropy(adj_recon, adj_dense, reduction="none").mean(dim=1)
        attr_loss = F.mse_loss(attr_recon, x @ x.T, reduction="none").mean(dim=1)
        loss = (0.5 * struct_loss + 0.5 * attr_loss).mean()
        loss.backward()
        optimizer.step()

    encoder.eval()
    with torch.no_grad():
        z = encoder(x, edge_index_t)
        adj_recon = torch.sigmoid(z @ z.T)
        attr_recon = z @ z.T
        struct_err = F.binary_cross_entropy(adj_recon, adj_dense, reduction="none").mean(dim=1)
        attr_err = F.mse_loss(attr_recon, x @ x.T, reduction="none").mean(dim=1)
        scores_t = 0.5 * struct_err + 0.5 * attr_err

    scores = scores_t.tolist()
    threshold = float(torch.quantile(scores_t, config.threshold_percentile / 100.0).item())
    flags = [s > threshold for s in scores]
    return AnomalyGNNResult(
        scores=scores,
        outlier_flags=flags,
        threshold=threshold,
        n_outliers=sum(flags),
    )
