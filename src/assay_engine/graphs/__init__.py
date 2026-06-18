"""``assay_engine.graphs`` — PyTorch Geometric GNN module.

Provides graph data types, GNN layers and models, embedding methods, anomaly
detection, temporal GNNs, heterogeneous GNNs, and link prediction.

All torch/pyg imports are lazy; ``import assay_engine.graphs`` succeeds even
without torch installed.  Install the optional ``gnn`` extra to use the
torch-dependent functions::

    pip install assay-engine[gnn]

Quick imports
-------------
All public types and functions are re-exported here::

    from assay_engine.graphs import GraphData, GCN, node2vec, dominant

Categories
----------
data             Graph data types and conversion utilities.
conv             GNN layer and model implementations (GCN, GAT, GraphSAGE).
embeddings       Graph embedding methods (random walks, Node2Vec, DeepWalk).
anomaly          GNN-based anomaly detection (DOMINANT, CoLA, CARD).
classification   Graph classification (GIN).
explainability   Node-level GNN explanations (GNNExplainer).
temporal         Temporal GNNs for time-series event graphs (A3T-GCN).
heterogeneous    Heterogeneous GNNs for multi-entity graphs (HGT).
link_prediction  Link prediction for inferring relationships.
"""

from assay_engine.graphs.anomaly import (
    AnomalyGNNResult,
    CODAConfig,
    DOMINANTConfig,
    GANomalyConfig,
    card,
    cola,
    dominant,
)
from assay_engine.graphs.classification import (
    GINConfig,
    GINModel,
    GraphClassificationResult,
    classify_graph,
    train_gin,
)
from assay_engine.graphs.explainability import (
    GNNExplainerConfig,
    NodeExplanation,
    explain_node,
    explain_nodes,
)
from assay_engine.graphs.conv import GAT, GCN, GATLayer, GCNLayer, GraphSAGE, SAGELayer
from assay_engine.graphs.data import (
    GraphData,
    from_adjacency_matrix,
    from_edge_list,
    to_pyg,
)
from assay_engine.graphs.embeddings import (
    DeepWalkConfig,
    Node2VecConfig,
    RandomWalkConfig,
    deepwalk,
    node2vec,
    random_walks,
)
from assay_engine.graphs.heterogeneous import (
    HGTConfig,
    HGTModel,
    HeteroGraphData,
    to_pyg_hetero,
    train_hgt,
)
from assay_engine.graphs.link_prediction import (
    LinkPredictionResult,
    LinkPredictor,
    LinkPredictorConfig,
    predict_links,
    train_link_predictor,
)
from assay_engine.graphs.temporal import (
    A3TGCNConfig,
    A3TGCNModel,
    TemporalSnapshot,
    train_a3tgcn,
)

__all__ = [
    # --- data ---
    "GraphData",
    "to_pyg",
    "from_adjacency_matrix",
    "from_edge_list",
    # --- conv ---
    "GCNLayer",
    "GATLayer",
    "SAGELayer",
    "GCN",
    "GAT",
    "GraphSAGE",
    # --- embeddings ---
    "RandomWalkConfig",
    "random_walks",
    "Node2VecConfig",
    "node2vec",
    "DeepWalkConfig",
    "deepwalk",
    # --- anomaly ---
    "AnomalyGNNResult",
    "DOMINANTConfig",
    "dominant",
    "CODAConfig",
    "cola",
    "GANomalyConfig",
    "card",
    # --- classification ---
    "GINConfig",
    "GINModel",
    "GraphClassificationResult",
    "train_gin",
    "classify_graph",
    # --- explainability ---
    "GNNExplainerConfig",
    "NodeExplanation",
    "explain_node",
    "explain_nodes",
    # --- temporal ---
    "TemporalSnapshot",
    "A3TGCNConfig",
    "A3TGCNModel",
    "train_a3tgcn",
    # --- heterogeneous ---
    "HeteroGraphData",
    "to_pyg_hetero",
    "HGTConfig",
    "HGTModel",
    "train_hgt",
    # --- link_prediction ---
    "LinkPredictionResult",
    "LinkPredictorConfig",
    "LinkPredictor",
    "train_link_predictor",
    "predict_links",
]
