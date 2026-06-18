"""Graph embedding methods: random walks, Node2Vec, DeepWalk.

All torch/pyg imports are lazy (inside function bodies) so this module is importable
without torch installed.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from assay_engine.graphs.data import GraphData


@dataclass(frozen=True)
class RandomWalkConfig:
    """Configuration for random walk generation.

    Attributes
    ----------
    walk_length: Number of steps per walk.
    num_walks:   Number of walks per node.
    seed:        Optional RNG seed for reproducibility.
    """

    walk_length: int = 80
    num_walks: int = 10
    seed: int | None = None


def random_walks(g: GraphData, config: RandomWalkConfig) -> list[list[int]]:
    """Generate random walks over a graph using pure Python.

    Returns a list of node-index sequences, one per (node × walk) pair.
    Walks terminate early at sink nodes (no outgoing edges).
    """
    adjacency: dict[int, list[int]] = {i: [] for i in range(g.num_nodes)}
    for src, dst in g.edge_index:
        adjacency[src].append(dst)

    rng = random.Random(config.seed)
    walks: list[list[int]] = []
    for node in range(g.num_nodes):
        for _ in range(config.num_walks):
            walk = [node]
            for _ in range(config.walk_length - 1):
                current = walk[-1]
                neighbours = adjacency[current]
                if not neighbours:
                    break
                walk.append(rng.choice(neighbours))
            walks.append(walk)
    return walks


@dataclass(frozen=True)
class Node2VecConfig:
    """Configuration for Node2Vec embedding.

    Attributes
    ----------
    embedding_dim: Dimension of the output embedding vectors.
    walk_length:   Steps per random walk.
    num_walks:     Walks per node.
    p:             Return parameter (controls likelihood of revisiting a node).
    q:             In-out parameter (controls BFS vs. DFS behaviour).
    epochs:        Training epochs.
    seed:          Optional RNG seed.
    """

    embedding_dim: int = 128
    walk_length: int = 80
    num_walks: int = 10
    p: float = 1.0
    q: float = 1.0
    epochs: int = 5
    seed: int | None = None


def node2vec(g: GraphData, config: Node2VecConfig) -> list[list[float]]:
    """Compute Node2Vec embeddings using ``torch_geometric.nn.Node2Vec``.

    Returns a list of ``embedding_dim``-dimensional float vectors, one per node.
    """
    import torch  # noqa: PLC0415
    from torch_geometric.nn import Node2Vec  # noqa: PLC0415

    if g.edge_index:
        src = [e[0] for e in g.edge_index]
        dst = [e[1] for e in g.edge_index]
        edge_index_t = torch.tensor([src, dst], dtype=torch.long)
    else:
        edge_index_t = torch.zeros((2, 0), dtype=torch.long)

    if config.seed is not None:
        torch.manual_seed(config.seed)

    model = Node2Vec(
        edge_index_t,
        embedding_dim=config.embedding_dim,
        walk_length=config.walk_length,
        context_size=max(1, config.walk_length // 5),
        walks_per_node=config.num_walks,
        p=config.p,
        q=config.q,
        num_nodes=g.num_nodes,
    )
    loader = model.loader(batch_size=max(1, g.num_nodes), shuffle=False)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

    model.train()
    for _ in range(config.epochs):
        for pos_rw, neg_rw in loader:
            optimizer.zero_grad()
            loss = model.loss(pos_rw, neg_rw)
            loss.backward()
            optimizer.step()

    model.eval()
    with torch.no_grad():
        embeddings = model()
    result: list[list[float]] = embeddings.tolist()
    return result


@dataclass(frozen=True)
class DeepWalkConfig:
    """Configuration for DeepWalk embedding.

    DeepWalk is Node2Vec with p=1 and q=1 (unbiased random walks).

    Attributes
    ----------
    embedding_dim: Dimension of the output embedding vectors.
    walk_length:   Steps per random walk.
    num_walks:     Walks per node.
    epochs:        Training epochs.
    seed:          Optional RNG seed.
    """

    embedding_dim: int = 128
    walk_length: int = 80
    num_walks: int = 10
    epochs: int = 5
    seed: int | None = None


def deepwalk(g: GraphData, config: DeepWalkConfig) -> list[list[float]]:
    """Compute DeepWalk embeddings (Node2Vec with p=1, q=1).

    Returns a list of ``embedding_dim``-dimensional float vectors, one per node.
    """
    n2v_config = Node2VecConfig(
        embedding_dim=config.embedding_dim,
        walk_length=config.walk_length,
        num_walks=config.num_walks,
        p=1.0,
        q=1.0,
        epochs=config.epochs,
        seed=config.seed,
    )
    return node2vec(g, n2v_config)
