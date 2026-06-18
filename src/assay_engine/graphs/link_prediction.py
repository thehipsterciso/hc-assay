"""Link prediction for inferring relationships in security graphs.

All torch/pyg imports are lazy (inside function bodies) so this module is importable
without torch installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from assay_engine.graphs.data import GraphData


@dataclass(frozen=True)
class LinkPredictionResult:
    """Output of link prediction inference.

    Attributes
    ----------
    candidate_edges: Edges scored by the model.
    scores:          Predicted probability (0-1) per candidate edge.
    predicted_links: Candidate edges with score >= threshold.
    """

    candidate_edges: list[tuple[int, int]]
    scores: list[float]
    predicted_links: list[tuple[int, int]]


@dataclass(frozen=True)
class LinkPredictorConfig:
    """Configuration for the GCN-based link predictor.

    Attributes
    ----------
    hidden_channels: Hidden dimension for the GCN encoder.
    num_layers:      Number of GCN layers.
    epochs:          Training epochs.
    lr:              Learning rate.
    threshold:       Probability threshold above which a link is predicted.
    """

    hidden_channels: int = 64
    num_layers: int = 2
    epochs: int = 100
    lr: float = 0.005
    threshold: float = 0.5


def LinkPredictor(  # noqa: N802
    in_channels: int,
    hidden_channels: int,
    num_layers: int = 2,
) -> Any:
    """Return a GCN encoder + dot-product decoder for link prediction.

    Returns a ``torch.nn.Module`` whose ``forward(x, edge_index)`` produces
    per-node embeddings, and whose ``decode(z, edge_pairs)`` scores candidate edges.
    """
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from torch_geometric.nn import GCNConv  # noqa: PLC0415

    class _LinkPredictor(nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            sizes = [in_channels] + [hidden_channels] * num_layers
            self.convs = nn.ModuleList([GCNConv(sizes[i], sizes[i + 1]) for i in range(num_layers)])

        def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
            for i, conv in enumerate(self.convs):
                x = conv(x, edge_index)
                if i < len(self.convs) - 1:
                    x = F.relu(x)
            return x

        def decode(self, z: torch.Tensor, edge_pairs: torch.Tensor) -> torch.Tensor:
            """Score candidate edges via dot product of endpoint embeddings."""
            return torch.sigmoid((z[edge_pairs[0]] * z[edge_pairs[1]]).sum(dim=-1))

    return _LinkPredictor()


def train_link_predictor(g: GraphData, config: LinkPredictorConfig) -> Any:
    """Train a GCN link predictor on positive edges from *g* with random negative samples.

    Returns the trained ``torch.nn.Module``.  If *g* has no node features a
    degree-based single-feature matrix is synthesised.
    """
    import torch  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from torch_geometric.utils import negative_sampling  # noqa: PLC0415

    n = g.num_nodes
    if n == 0:
        raise ValueError("Graph must have at least one node")

    if g.node_features is not None:
        x = torch.tensor(g.node_features, dtype=torch.float)
    else:
        degrees = [0.0] * n
        for s, _ in g.edge_index:
            degrees[s] += 1.0
        x = torch.tensor([[d / max(n, 1)] for d in degrees], dtype=torch.float)

    in_channels = x.shape[1]

    if g.edge_index:
        src = [e[0] for e in g.edge_index]
        dst = [e[1] for e in g.edge_index]
        edge_index_t = torch.tensor([src, dst], dtype=torch.long)
    else:
        edge_index_t = torch.zeros((2, 0), dtype=torch.long)

    model = LinkPredictor(in_channels, config.hidden_channels, config.num_layers)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)

    for _ in range(config.epochs):
        model.train()
        optimizer.zero_grad()
        z = model(x, edge_index_t)
        if edge_index_t.numel() == 0:
            loss = torch.tensor(0.0, requires_grad=True)
        else:
            neg_edge = negative_sampling(
                edge_index_t, num_nodes=n, num_neg_samples=edge_index_t.size(1)
            )
            pos_scores = model.decode(z, edge_index_t)
            neg_scores = model.decode(z, neg_edge)
            scores = torch.cat([pos_scores, neg_scores])
            labels = torch.cat([torch.ones(pos_scores.size(0)), torch.zeros(neg_scores.size(0))])
            loss = F.binary_cross_entropy(scores, labels)
        loss.backward()  # type: ignore[no-untyped-call]
        optimizer.step()

    return model


def predict_links(
    model: Any,
    g: GraphData,
    candidate_edges: list[tuple[int, int]],
) -> LinkPredictionResult:
    """Score *candidate_edges* with a trained link predictor.

    Returns a ``LinkPredictionResult`` with probabilities and predicted links above
    the model's implicit threshold (0.5 by default; callers can filter ``scores``
    directly for custom thresholds).
    """
    import torch  # noqa: PLC0415

    n = g.num_nodes
    if g.node_features is not None:
        x = torch.tensor(g.node_features, dtype=torch.float)
    else:
        degrees = [0.0] * n
        for s, _ in g.edge_index:
            degrees[s] += 1.0
        x = torch.tensor([[d / max(n, 1)] for d in degrees], dtype=torch.float)

    if g.edge_index:
        src = [e[0] for e in g.edge_index]
        dst = [e[1] for e in g.edge_index]
        edge_index_t = torch.tensor([src, dst], dtype=torch.long)
    else:
        edge_index_t = torch.zeros((2, 0), dtype=torch.long)

    if not candidate_edges:
        return LinkPredictionResult(candidate_edges=[], scores=[], predicted_links=[])

    cand_src = [e[0] for e in candidate_edges]
    cand_dst = [e[1] for e in candidate_edges]
    cand_t = torch.tensor([cand_src, cand_dst], dtype=torch.long)

    model.eval()
    with torch.no_grad():
        z = model(x, edge_index_t)
        scores_t = model.decode(z, cand_t)

    scores = scores_t.tolist()
    predicted = [e for e, s in zip(candidate_edges, scores) if s >= 0.5]
    return LinkPredictionResult(
        candidate_edges=candidate_edges,
        scores=scores,
        predicted_links=predicted,
    )
