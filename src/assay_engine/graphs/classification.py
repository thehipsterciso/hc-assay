"""Graph-level classification using Graph Isomorphism Network (Xu et al., 2019).

All torch/pyg imports are lazy (inside function bodies) so this module is importable
without torch installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from assay_engine.graphs.data import GraphData


@dataclass(frozen=True)
class GraphClassificationResult:
    predicted_class: int
    class_probabilities: list[float]
    n_classes: int


@dataclass(frozen=True)
class GINConfig:
    in_channels: int
    hidden_channels: int
    out_channels: int
    num_layers: int = 5
    dropout: float = 0.5
    epochs: int = 100
    lr: float = 0.01
    seed: int | None = None


def GINModel(config: GINConfig) -> object:
    """Factory returning a GIN model for graph classification."""
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415
    from torch_geometric.nn import GINConv, global_mean_pool  # noqa: PLC0415

    class _MLP(nn.Module):  # type: ignore[misc]
        def __init__(self, in_ch: int, out_ch: int) -> None:
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(in_ch, out_ch),
                nn.BatchNorm1d(out_ch),
                nn.ReLU(),
                nn.Linear(out_ch, out_ch),
            )

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.net(x)  # type: ignore[return-value]

    class _GIN(nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self.convs = nn.ModuleList()
            self.bns = nn.ModuleList()
            in_ch = config.in_channels
            for _ in range(config.num_layers):
                mlp = _MLP(in_ch, config.hidden_channels)
                self.convs.append(GINConv(mlp))
                self.bns.append(nn.BatchNorm1d(config.hidden_channels))
                in_ch = config.hidden_channels
            self.classifier = nn.Linear(config.hidden_channels, config.out_channels)
            self.dropout = config.dropout

        def forward(
            self,
            x: torch.Tensor,
            edge_index: torch.Tensor,
            batch: torch.Tensor,
        ) -> torch.Tensor:
            for conv, bn in zip(self.convs, self.bns):
                x = F.relu(bn(conv(x, edge_index)))
                x = F.dropout(x, p=self.dropout, training=self.training)
            x = global_mean_pool(x, batch)
            return self.classifier(x)  # type: ignore[return-value]

    return _GIN()


def train_gin(
    graphs: list[GraphData],
    labels: list[int],
    config: GINConfig,
) -> object:
    """Train a GIN model on labeled graphs."""
    import torch  # noqa: PLC0415
    from torch_geometric.data import Data, DataLoader  # noqa: PLC0415

    if not graphs:
        raise ValueError("graphs must not be empty")
    if len(graphs) != len(labels):
        raise ValueError(
            f"graphs and labels must have the same length, got {len(graphs)} vs {len(labels)}"
        )

    if config.seed is not None:
        torch.manual_seed(config.seed)

    dataset: list[Data] = []
    for g, lbl in zip(graphs, labels):
        if g.edge_index:
            src = [e[0] for e in g.edge_index]
            dst = [e[1] for e in g.edge_index]
            edge_index_t = torch.tensor([src, dst], dtype=torch.long)
        else:
            edge_index_t = torch.zeros((2, 0), dtype=torch.long)

        if g.node_features is not None:
            x = torch.tensor(g.node_features, dtype=torch.float)
        else:
            x = torch.ones((g.num_nodes, config.in_channels), dtype=torch.float)

        data = Data(x=x, edge_index=edge_index_t, y=torch.tensor([lbl], dtype=torch.long))
        dataset.append(data)

    loader = DataLoader(dataset, batch_size=max(1, len(dataset) // 4 + 1), shuffle=True)

    model = GINModel(config)
    import torch.nn as nn  # noqa: PLC0415

    assert isinstance(model, nn.Module)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)
    loss_fn = nn.CrossEntropyLoss()

    model.train()
    for _ in range(config.epochs):
        for batch in loader:
            optimizer.zero_grad()
            out = model(batch.x, batch.edge_index, batch.batch)
            loss = loss_fn(out, batch.y)
            loss.backward()  # type: ignore[no-untyped-call]
            optimizer.step()

    model.eval()
    return model


def classify_graph(model: object, graph: GraphData) -> GraphClassificationResult:
    """Run inference on a single graph and return a classification result."""
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    import torch.nn.functional as F  # noqa: PLC0415

    assert isinstance(model, nn.Module)

    if graph.edge_index:
        src = [e[0] for e in graph.edge_index]
        dst = [e[1] for e in graph.edge_index]
        edge_index_t = torch.tensor([src, dst], dtype=torch.long)
    else:
        edge_index_t = torch.zeros((2, 0), dtype=torch.long)

    if graph.node_features is not None:
        x = torch.tensor(graph.node_features, dtype=torch.float)
    else:
        in_ch = next(iter(model.parameters())).shape[1]
        x = torch.ones((graph.num_nodes, in_ch), dtype=torch.float)

    batch = torch.zeros(graph.num_nodes, dtype=torch.long)

    model.eval()
    with torch.no_grad():
        logits = model(x, edge_index_t, batch)
        probs = F.softmax(logits, dim=-1).squeeze(0)

    probs_list = probs.tolist()
    predicted = int(torch.argmax(probs).item())
    return GraphClassificationResult(
        predicted_class=predicted,
        class_probabilities=probs_list,
        n_classes=len(probs_list),
    )
