"""``assay_engine.algorithms`` — pure-Python ML and data-science algorithms.

Modules are grouped by category.  Each module exposes its own typed
Protocol interface and standalone implementations.

Categories
----------
similarity     Pairwise distance and similarity measures.
stats          Descriptive statistics and distributional summaries.
testing        Statistical hypothesis tests and multiple-comparison corrections.
clustering     Unsupervised grouping (k-means, hierarchical, DBSCAN).
ranking        Information-retrieval scoring (TF-IDF, BM25) and IR metrics.
sampling       Resampling, cross-validation, and bootstrap.
anomaly        Outlier and anomaly detection (z-score, IQR, MAD, LOF).
evaluation     Classification and regression evaluation metrics.
text_metrics   Text similarity and generation quality (BLEU, ROUGE).

Quick imports
-------------
All Protocol types and primary result dataclasses are re-exported here so
callers can type-check against a single import path::

    from assay_engine.algorithms import SimilarityFn, SummaryStats, ClusterResult
"""

from assay_engine.algorithms.anomaly import (
    AnomalyDetector,
    AnomalyResult,
    iqr_detector,
    isolation_score,
    lof,
    mad_detector,
    zscore_detector,
)
from assay_engine.algorithms.clustering import (
    ClusterResult,
    Clusterer,
    agglomerative,
    davies_bouldin_index,
    dbscan,
    kmeans,
    silhouette_score,
)
from assay_engine.algorithms.evaluation import (
    ClassificationEvaluator,
    ConfusionMatrix,
    MulticlassReport,
    RegressionMetrics,
    average_precision_score,
    classification_report,
    confusion_matrix,
    expected_calibration_error,
    f_beta,
    pr_curve,
    regression_metrics,
    roc_auc,
    roc_curve,
)
from assay_engine.algorithms.ranking import (
    RankingFn,
    RankingResult,
    ScoredDocument,
    bm25_score,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    reciprocal_rank_fusion,
    tfidf_score,
)
from assay_engine.algorithms.sampling import (
    BootstrapResult,
    Splitter,
    SplitResult,
    bootstrap,
    kfold,
    reservoir_sample,
    stratified_kfold,
    train_test_split,
    train_val_test_split,
)
from assay_engine.algorithms.similarity import (
    DistanceFn,
    SimilarityFn,
    canberra,
    chebyshev,
    cosine,
    distance_matrix,
    euclidean,
    hamming,
    jaccard,
    manhattan,
    minkowski,
    overlap_coefficient,
    pearson,
    similarity_matrix,
)
from assay_engine.algorithms.stats import (
    Summarizer,
    SummaryStats,
    describe,
    entropy,
    geometric_mean,
    harmonic_mean,
    quantile,
    robust_z_scores,
    trim_mean,
    winsorise,
    z_scores,
)
from assay_engine.algorithms.testing import (
    CorrectionResult,
    StatisticalTest,
    TestResult,
    benjamini_hochberg,
    bonferroni,
    chi_squared_test,
    holm,
    ks_test,
    mann_whitney,
    one_sample_t_test,
    permutation_test,
    welch_t_test,
)
from assay_engine.algorithms.text_metrics import (
    BLEUResult,
    ROUGEResult,
    StringMetric,
    bleu,
    damerau_levenshtein,
    jaccard_token,
    jaro,
    jaro_winkler,
    levenshtein,
    ngram_overlap,
    normalized_levenshtein,
    rouge_l,
    rouge_n,
    rouge_s,
)

__all__ = [
    # --- Protocols ---
    "AnomalyDetector",
    "ClassificationEvaluator",
    "Clusterer",
    "DistanceFn",
    "RankingFn",
    "SimilarityFn",
    "Splitter",
    "StatisticalTest",
    "StringMetric",
    "Summarizer",
    # --- Result dataclasses ---
    "AnomalyResult",
    "BLEUResult",
    "BootstrapResult",
    "ClusterResult",
    "ConfusionMatrix",
    "CorrectionResult",
    "MulticlassReport",
    "ROUGEResult",
    "RankingResult",
    "RegressionMetrics",
    "ScoredDocument",
    "SplitResult",
    "SummaryStats",
    "TestResult",
    # --- similarity ---
    "cosine",
    "pearson",
    "jaccard",
    "overlap_coefficient",
    "euclidean",
    "manhattan",
    "chebyshev",
    "minkowski",
    "hamming",
    "canberra",
    "similarity_matrix",
    "distance_matrix",
    # --- stats ---
    "describe",
    "quantile",
    "z_scores",
    "robust_z_scores",
    "geometric_mean",
    "harmonic_mean",
    "winsorise",
    "trim_mean",
    "entropy",
    # --- testing ---
    "welch_t_test",
    "one_sample_t_test",
    "mann_whitney",
    "ks_test",
    "chi_squared_test",
    "permutation_test",
    "bonferroni",
    "holm",
    "benjamini_hochberg",
    # --- clustering ---
    "kmeans",
    "agglomerative",
    "dbscan",
    "silhouette_score",
    "davies_bouldin_index",
    # --- ranking ---
    "tfidf_score",
    "bm25_score",
    "reciprocal_rank_fusion",
    "ndcg",
    "mean_average_precision",
    "mean_reciprocal_rank",
    "precision_at_k",
    "recall_at_k",
    "reciprocal_rank",
    # --- sampling ---
    "train_test_split",
    "train_val_test_split",
    "kfold",
    "stratified_kfold",
    "bootstrap",
    "reservoir_sample",
    # --- anomaly ---
    "zscore_detector",
    "iqr_detector",
    "mad_detector",
    "lof",
    "isolation_score",
    # --- evaluation ---
    "confusion_matrix",
    "f_beta",
    "classification_report",
    "roc_curve",
    "roc_auc",
    "pr_curve",
    "average_precision_score",
    "expected_calibration_error",
    "regression_metrics",
    # --- text_metrics ---
    "levenshtein",
    "normalized_levenshtein",
    "damerau_levenshtein",
    "jaro",
    "jaro_winkler",
    "jaccard_token",
    "ngram_overlap",
    "bleu",
    "rouge_n",
    "rouge_l",
    "rouge_s",
]
