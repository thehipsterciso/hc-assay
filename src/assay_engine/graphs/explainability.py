"""Node-level GNN explanations via GNNExplainer (Ying et al., 2019).

All torch/pyg imports are lazy (inside function bodies) so this module is importable
without torch installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from assay_engine.graphs.data import GraphData


@dataclass(frozen=True)
class NodeExplanation:
    node_idx: int
    important_edges: list[tuple[int, int]]
    edge_mask: list[float]
    node_mask: list[float]
    n_hops: int


@dataclass(frozen=True)
class GNNExplainerConfig:
    n_hops: int = 2
    epochs: int = 200
    lr: float = 0.01
    edge_mask_threshold: float = 0.5


def explain_node(
    model: object,
    graph: GraphData,
    node_idx: int,
    config: GNNExplainerConfig,
) -> NodeExplanation:
    """Explain a model's prediction for a single node using GNNExplainer."""
    import torch  # noqa: PLC0415
    import torch.nn as nn  # noqa: PLC0415
    from torch_geometric.explain import Explainer  # noqa: PLC0415
    from torch_geometric.explain.algorithm import GNNExplainer  # noqa: PLC0415

    if node_idx >= graph.num_nodes:
        raise ValueError(
            f"node_idx {node_idx} is out of range for graph with {graph.num_nodes} nodes"
        )

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
        try:
            in_ch = next(iter(model.parameters())).shape[1]
        except StopIteration:
            in_ch = 1
        x = torch.ones((graph.num_nodes, in_ch), dtype=torch.float)

    explainer = Explainer(
        model=model,
        algorithm=GNNExplainer(epochs=config.epochs, lr=config.lr),
        explanation_type="model",
        node_mask_type="attributes",
        edge_mask_type="object",
        model_config={
            "mode": "multiclass_classification",
            "task_level": "node",
            "return_type": "raw",
        },
    )

    explanation = explainer(x, edge_index_t, index=node_idx)

    raw_edge_mask: list[float]
    if hasattr(explanation, "edge_mask") and explanation.edge_mask is not None:
        raw_edge_mask = explanation.edge_mask.tolist()
    else:
        raw_edge_mask = []

    raw_node_mask: list[float]
    if hasattr(explanation, "node_mask") and explanation.node_mask is not None:
        nm = explanation.node_mask
        if nm.dim() > 1:
            nm = nm.mean(dim=-1)
        raw_node_mask = nm.tolist()
    else:
        raw_node_mask = []

    important_edges: list[tuple[int, int]] = []
    if raw_edge_mask and graph.edge_index:
        for i, (weight, edge) in enumerate(zip(raw_edge_mask, graph.edge_index)):
            if weight >= config.edge_mask_threshold:
                important_edges.append(edge)

    return NodeExplanation(
        node_idx=node_idx,
        important_edges=important_edges,
        edge_mask=raw_edge_mask,
        node_mask=raw_node_mask,
        n_hops=config.n_hops,
    )


def explain_nodes(
    model: object,
    graph: GraphData,
    node_indices: list[int],
    config: GNNExplainerConfig,
) -> list[NodeExplanation]:
    """Explain predictions for multiple nodes."""
    return [explain_node(model, graph, idx, config) for idx in node_indices]
