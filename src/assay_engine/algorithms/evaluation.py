"""Classification and regression evaluation metrics.

Covers confusion-matrix derived metrics, ROC/PR curves, calibration,
and regression error measures.

All implementations are pure Python; no external dependencies required.

Usage::

    from assay_engine.algorithms.evaluation import confusion_matrix, roc_auc
    cm = confusion_matrix(y_true=[1, 0, 1, 1], y_pred=[1, 1, 0, 1])
    auc = roc_auc(y_true=[0, 0, 1, 1], y_score=[0.1, 0.4, 0.35, 0.8])
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfusionMatrix:
    """Binary confusion matrix and derived statistics.

    All counts use the convention that label 1 is the *positive* class.

    Attributes
    ----------
    tp:        True positives.
    fp:        False positives.
    fn:        False negatives.
    tn:        True negatives.
    precision: TP / (TP + FP); 0.0 when no positive predictions.
    recall:    TP / (TP + FN); 0.0 when no actual positives.
    f1:        Harmonic mean of precision and recall.
    accuracy:  (TP + TN) / total.
    mcc:       Matthews Correlation Coefficient ∈ [-1, 1].
    support:   Total samples.
    """

    tp: int
    fp: int
    fn: int
    tn: int
    precision: float
    recall: float
    f1: float
    accuracy: float
    mcc: float
    support: int


@dataclass(frozen=True)
class MulticlassReport:
    """Per-class and macro/micro-averaged classification metrics."""

    classes: list[Any]
    per_class_precision: dict[Any, float]
    per_class_recall: dict[Any, float]
    per_class_f1: dict[Any, float]
    per_class_support: dict[Any, int]
    macro_precision: float
    macro_recall: float
    macro_f1: float
    micro_precision: float
    micro_recall: float
    micro_f1: float
    accuracy: float


@dataclass(frozen=True)
class RegressionMetrics:
    """Regression evaluation summary.

    Attributes
    ----------
    mae:   Mean Absolute Error.
    mse:   Mean Squared Error.
    rmse:  Root Mean Squared Error.
    r2:    Coefficient of determination (R²).
    mape:  Mean Absolute Percentage Error (None if any y_true = 0).
    """

    mae: float
    mse: float
    rmse: float
    r2: float
    mape: float | None


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class ClassificationEvaluator(Protocol):
    """A callable that computes a classification metric."""

    def __call__(
        self,
        y_true: Sequence[Any],
        y_pred: Sequence[Any],
    ) -> ConfusionMatrix: ...


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_same_length(a: Sequence[Any], b: Sequence[Any]) -> None:
    if len(a) != len(b):
        raise ValueError(f"y_true and y_pred must have the same length; got {len(a)} and {len(b)}")
    if not a:
        raise ValueError("inputs must be non-empty")


# ---------------------------------------------------------------------------
# Binary classification
# ---------------------------------------------------------------------------


def confusion_matrix(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    *,
    pos_label: Any = 1,
) -> ConfusionMatrix:
    """Binary confusion matrix and derived metrics.

    Parameters
    ----------
    y_true:    Ground-truth labels.
    y_pred:    Predicted labels.
    pos_label: The label to treat as the positive class (default 1).
    """
    _validate_same_length(y_true, y_pred)

    tp = fp = fn = tn = 0
    for yt, yp in zip(y_true, y_pred):
        is_pos_true = yt == pos_label
        is_pos_pred = yp == pos_label
        if is_pos_true and is_pos_pred:
            tp += 1
        elif not is_pos_true and is_pos_pred:
            fp += 1
        elif is_pos_true and not is_pos_pred:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    accuracy = (tp + tn) / (tp + fp + fn + tn)

    denom = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    mcc = (tp * tn - fp * fn) / denom if denom > 0 else 0.0

    return ConfusionMatrix(
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        precision=precision,
        recall=recall,
        f1=f1,
        accuracy=accuracy,
        mcc=mcc,
        support=tp + fp + fn + tn,
    )


def f_beta(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
    *,
    beta: float = 1.0,
    pos_label: Any = 1,
) -> float:
    """F_β score — weighted harmonic mean of precision and recall.

    β = 1: F1 (equal weight).
    β > 1: recall-weighted (miss-cost is high).
    β < 1: precision-weighted (false-alarm cost is high).
    """
    if beta <= 0:
        raise ValueError(f"beta must be positive; got {beta}")
    cm = confusion_matrix(y_true, y_pred, pos_label=pos_label)
    b2 = beta**2
    denom = b2 * cm.precision + cm.recall
    return (1 + b2) * cm.precision * cm.recall / denom if denom > 0 else 0.0


# ---------------------------------------------------------------------------
# Multiclass classification
# ---------------------------------------------------------------------------


def classification_report(
    y_true: Sequence[Any],
    y_pred: Sequence[Any],
) -> MulticlassReport:
    """Per-class and averaged metrics for multiclass classification.

    Uses one-vs-rest to compute per-class precision, recall, and F1.
    Macro average weights each class equally; micro average weights by support.
    """
    _validate_same_length(y_true, y_pred)

    classes = sorted(set(list(y_true) + list(y_pred)), key=str)
    per_tp: dict[Any, int] = {c: 0 for c in classes}
    per_fp: dict[Any, int] = {c: 0 for c in classes}
    per_fn: dict[Any, int] = {c: 0 for c in classes}

    for yt, yp in zip(y_true, y_pred):
        if yt == yp:
            per_tp[yt] += 1
        else:
            per_fp[yp] += 1
            per_fn[yt] += 1

    support: Counter[Any] = Counter(y_true)

    prec, rec, f1 = {}, {}, {}
    for c in classes:
        p = per_tp[c] / (per_tp[c] + per_fp[c]) if (per_tp[c] + per_fp[c]) > 0 else 0.0
        r = per_tp[c] / (per_tp[c] + per_fn[c]) if (per_tp[c] + per_fn[c]) > 0 else 0.0
        prec[c] = p
        rec[c] = r
        f1[c] = 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    n_cls = len(classes)
    macro_p = sum(prec.values()) / n_cls if n_cls else 0.0
    macro_r = sum(rec.values()) / n_cls if n_cls else 0.0
    macro_f1 = 2 * macro_p * macro_r / (macro_p + macro_r) if (macro_p + macro_r) > 0 else 0.0

    total_tp = sum(per_tp.values())
    total_fp = sum(per_fp.values())
    total_fn = sum(per_fn.values())
    micro_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    micro_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) > 0 else 0.0

    n = len(y_true)
    accuracy = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp) / n

    return MulticlassReport(
        classes=classes,
        per_class_precision=prec,
        per_class_recall=rec,
        per_class_f1=f1,
        per_class_support=dict(support),
        macro_precision=macro_p,
        macro_recall=macro_r,
        macro_f1=macro_f1,
        micro_precision=micro_p,
        micro_recall=micro_r,
        micro_f1=micro_f1,
        accuracy=accuracy,
    )


# ---------------------------------------------------------------------------
# ROC / PR curve
# ---------------------------------------------------------------------------


def roc_curve(
    y_true: Sequence[int],
    y_score: Sequence[float],
) -> tuple[list[float], list[float], list[float]]:
    """ROC curve — False Positive Rate vs True Positive Rate.

    Returns (fpr, tpr, thresholds) lists, sorted by ascending threshold.

    Parameters
    ----------
    y_true:  Binary ground-truth labels (0 / 1).
    y_score: Predicted probability / score for the positive class.

    Raises
    ------
    ValueError
        If there are no positives or no negatives in y_true.
    """
    _validate_same_length(y_true, y_score)

    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("y_true must contain both positive and negative examples")

    pairs = sorted(zip(y_score, y_true), reverse=True)
    fprs, tprs, thresholds = [0.0], [0.0], [math.inf]
    tp = fp = 0
    prev_score = math.inf

    for score, label in pairs:
        if score != prev_score:
            fprs.append(fp / n_neg)
            tprs.append(tp / n_pos)
            thresholds.append(score)
            prev_score = score
        if label == 1:
            tp += 1
        else:
            fp += 1

    fprs.append(fp / n_neg)
    tprs.append(tp / n_pos)
    thresholds.append(0.0)

    return fprs, tprs, thresholds


def roc_auc(
    y_true: Sequence[int],
    y_score: Sequence[float],
) -> float:
    """Area Under the ROC Curve (trapezoidal rule).

    Returns a value in [0, 1]; 0.5 = random classifier, 1.0 = perfect.
    """
    fprs, tprs, _ = roc_curve(y_true, y_score)
    auc = 0.0
    for i in range(1, len(fprs)):
        auc += (fprs[i] - fprs[i - 1]) * (tprs[i] + tprs[i - 1]) / 2.0
    return auc


def pr_curve(
    y_true: Sequence[int],
    y_score: Sequence[float],
) -> tuple[list[float], list[float], list[float]]:
    """Precision-Recall curve.

    Returns (precision, recall, thresholds) lists.
    """
    _validate_same_length(y_true, y_score)

    n_pos = sum(y_true)
    if n_pos == 0:
        raise ValueError("y_true must contain at least one positive example")

    pairs = sorted(zip(y_score, y_true), reverse=True)
    precisions, recalls, thresholds = [], [], []
    tp = fp = 0

    for score, label in pairs:
        if label == 1:
            tp += 1
        else:
            fp += 1
        precisions.append(tp / (tp + fp))
        recalls.append(tp / n_pos)
        thresholds.append(score)

    return precisions, recalls, thresholds


def average_precision_score(
    y_true: Sequence[int],
    y_score: Sequence[float],
) -> float:
    """Area under the PR curve (average precision).

    Equivalent to the weighted mean of precision at each recall threshold,
    with the weight being the change in recall from the previous threshold.
    """
    prec, rec, _ = pr_curve(y_true, y_score)
    ap = 0.0
    prev_r = 0.0
    for p, r in zip(prec, rec):
        ap += p * (r - prev_r)
        prev_r = r
    return ap


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------


def expected_calibration_error(
    y_true: Sequence[int],
    y_prob: Sequence[float],
    *,
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error (ECE) — reliability of probability estimates.

    Bins predictions by predicted probability, then averages the absolute
    gap between mean predicted probability and actual fraction of positives.
    Lower ECE = better calibrated.  Perfectly calibrated = 0.0.

    Parameters
    ----------
    n_bins: Number of equal-width probability bins (default 10).
    """
    _validate_same_length(y_true, y_prob)
    n = len(y_true)

    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for prob, label in zip(y_prob, y_true):
        bi = min(int(prob * n_bins), n_bins - 1)
        bins[bi].append((prob, label))

    ece = 0.0
    for b in bins:
        if not b:
            continue
        avg_confidence = sum(p for p, _ in b) / len(b)
        fraction_pos = sum(lbl for _, lbl in b) / len(b)
        ece += len(b) / n * abs(avg_confidence - fraction_pos)

    return ece


# ---------------------------------------------------------------------------
# Regression metrics
# ---------------------------------------------------------------------------


def regression_metrics(
    y_true: Sequence[float],
    y_pred: Sequence[float],
) -> RegressionMetrics:
    """MAE, MSE, RMSE, R², and MAPE for regression evaluation.

    Parameters
    ----------
    y_true: Actual target values.
    y_pred: Predicted values.
    """
    _validate_same_length(y_true, y_pred)

    n = len(y_true)
    mae = sum(abs(yt - yp) for yt, yp in zip(y_true, y_pred)) / n
    mse = sum((yt - yp) ** 2 for yt, yp in zip(y_true, y_pred)) / n
    rmse = math.sqrt(mse)

    mean_true = sum(y_true) / n
    ss_tot = sum((yt - mean_true) ** 2 for yt in y_true)
    ss_res = sum((yt - yp) ** 2 for yt, yp in zip(y_true, y_pred))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 0.0

    if any(yt == 0.0 for yt in y_true):
        mape = None
    else:
        mape = sum(abs((yt - yp) / yt) for yt, yp in zip(y_true, y_pred)) / n * 100.0

    return RegressionMetrics(mae=mae, mse=mse, rmse=rmse, r2=r2, mape=mape)
