"""Tests for assay_engine.algorithms.evaluation."""

import pytest

from assay_engine.algorithms.evaluation import (
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


# ---------------------------------------------------------------------------
# confusion_matrix
# ---------------------------------------------------------------------------


class TestConfusionMatrix:
    Y_TRUE = [1, 0, 1, 1, 0, 0, 1, 0]
    Y_PRED = [1, 0, 0, 1, 1, 0, 1, 0]

    def test_tp_fp_fn_tn(self) -> None:
        cm = confusion_matrix(self.Y_TRUE, self.Y_PRED)
        assert cm.tp == 3
        assert cm.fp == 1
        assert cm.fn == 1
        assert cm.tn == 3

    def test_precision(self) -> None:
        cm = confusion_matrix(self.Y_TRUE, self.Y_PRED)
        assert cm.precision == pytest.approx(3 / 4)

    def test_recall(self) -> None:
        cm = confusion_matrix(self.Y_TRUE, self.Y_PRED)
        assert cm.recall == pytest.approx(3 / 4)

    def test_f1(self) -> None:
        cm = confusion_matrix(self.Y_TRUE, self.Y_PRED)
        assert cm.f1 == pytest.approx(3 / 4)

    def test_accuracy(self) -> None:
        cm = confusion_matrix(self.Y_TRUE, self.Y_PRED)
        assert cm.accuracy == pytest.approx(6 / 8)

    def test_perfect_predictions(self) -> None:
        cm = confusion_matrix([1, 0, 1], [1, 0, 1])
        assert cm.precision == 1.0
        assert cm.recall == 1.0
        assert cm.f1 == 1.0
        assert cm.mcc == pytest.approx(1.0)

    def test_all_wrong(self) -> None:
        cm = confusion_matrix([1, 1, 0], [0, 0, 1])
        assert cm.tp == 0
        assert cm.tn == 0

    def test_mcc_range(self) -> None:
        cm = confusion_matrix(self.Y_TRUE, self.Y_PRED)
        assert -1.0 <= cm.mcc <= 1.0

    def test_support(self) -> None:
        cm = confusion_matrix(self.Y_TRUE, self.Y_PRED)
        assert cm.support == len(self.Y_TRUE)

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError):
            confusion_matrix([1, 0], [1])

    def test_result_type(self) -> None:
        cm = confusion_matrix(self.Y_TRUE, self.Y_PRED)
        assert isinstance(cm, ConfusionMatrix)

    def test_custom_pos_label(self) -> None:
        cm = confusion_matrix(["cat", "dog", "cat"], ["cat", "cat", "dog"], pos_label="cat")
        assert cm.tp == 1
        assert cm.fn == 1
        assert cm.fp == 1


# ---------------------------------------------------------------------------
# f_beta
# ---------------------------------------------------------------------------


class TestFBeta:
    def test_f1(self) -> None:
        cm = confusion_matrix([1, 0, 1, 1, 0], [1, 0, 0, 1, 1])
        p, r = cm.precision, cm.recall
        expected = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        assert f_beta([1, 0, 1, 1, 0], [1, 0, 0, 1, 1], beta=1.0) == pytest.approx(expected)

    def test_beta_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            f_beta([1], [1], beta=0.0)


# ---------------------------------------------------------------------------
# classification_report
# ---------------------------------------------------------------------------


class TestClassificationReport:
    Y_TRUE = [0, 1, 2, 0, 1, 2]
    Y_PRED = [0, 2, 1, 0, 0, 2]

    def test_result_type(self) -> None:
        report = classification_report(self.Y_TRUE, self.Y_PRED)
        assert isinstance(report, MulticlassReport)

    def test_classes(self) -> None:
        report = classification_report(self.Y_TRUE, self.Y_PRED)
        assert report.classes == [0, 1, 2]

    def test_accuracy(self) -> None:
        report = classification_report(self.Y_TRUE, self.Y_PRED)
        # 3 correct: (0→0, 0→0, 2→2)
        assert report.accuracy == pytest.approx(3 / 6)

    def test_macro_f1_range(self) -> None:
        report = classification_report(self.Y_TRUE, self.Y_PRED)
        assert 0.0 <= report.macro_f1 <= 1.0

    def test_per_class_support(self) -> None:
        report = classification_report(self.Y_TRUE, self.Y_PRED)
        assert report.per_class_support[0] == 2
        assert report.per_class_support[1] == 2
        assert report.per_class_support[2] == 2

    def test_perfect_classification(self) -> None:
        report = classification_report([0, 1, 2], [0, 1, 2])
        assert report.accuracy == pytest.approx(1.0)
        assert report.macro_f1 == pytest.approx(1.0)

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError):
            classification_report([0, 1], [0])


# ---------------------------------------------------------------------------
# ROC / AUC
# ---------------------------------------------------------------------------


class TestROC:
    Y_TRUE = [0, 0, 1, 1]
    Y_SCORE = [0.1, 0.4, 0.35, 0.8]

    def test_roc_curve_boundaries(self) -> None:
        fprs, tprs, _ = roc_curve(self.Y_TRUE, self.Y_SCORE)
        assert fprs[0] == 0.0 and tprs[0] == 0.0
        assert fprs[-1] == 1.0 and tprs[-1] == 1.0

    def test_auc_above_half(self) -> None:
        # A reasonable classifier should beat chance
        auc = roc_auc(self.Y_TRUE, self.Y_SCORE)
        assert auc > 0.5

    def test_perfect_auc(self) -> None:
        auc = roc_auc([0, 0, 1, 1], [0.0, 0.0, 1.0, 1.0])
        assert auc == pytest.approx(1.0)

    def test_auc_range(self) -> None:
        auc = roc_auc(self.Y_TRUE, self.Y_SCORE)
        assert 0.0 <= auc <= 1.0

    def test_no_positives_raises(self) -> None:
        with pytest.raises(ValueError):
            roc_curve([0, 0, 0], [0.1, 0.5, 0.9])

    def test_no_negatives_raises(self) -> None:
        with pytest.raises(ValueError):
            roc_curve([1, 1, 1], [0.1, 0.5, 0.9])


# ---------------------------------------------------------------------------
# PR curve / average precision
# ---------------------------------------------------------------------------


class TestPR:
    def test_ap_perfect(self) -> None:
        ap = average_precision_score([0, 0, 1, 1], [0.0, 0.1, 0.9, 1.0])
        assert ap == pytest.approx(1.0)

    def test_ap_range(self) -> None:
        ap = average_precision_score([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8])
        assert 0.0 <= ap <= 1.0

    def test_pr_curve_lengths_match(self) -> None:
        y_true = [0, 0, 1, 1]
        y_score = [0.1, 0.4, 0.35, 0.8]
        prec, rec, thresholds = pr_curve(y_true, y_score)
        assert len(prec) == len(rec) == len(thresholds)


# ---------------------------------------------------------------------------
# ECE
# ---------------------------------------------------------------------------


class TestECE:
    def test_perfect_calibration(self) -> None:
        # Perfectly calibrated: prob=0.5 and half are positive
        y_true = [0, 1] * 50
        y_prob = [0.5] * 100
        ece = expected_calibration_error(y_true, y_prob)
        assert ece == pytest.approx(0.0, abs=0.05)

    def test_overconfident(self) -> None:
        y_true = [0] * 50 + [1] * 50
        y_prob = [1.0] * 50 + [1.0] * 50
        ece = expected_calibration_error(y_true, y_prob)
        assert ece > 0.0

    def test_ece_range(self) -> None:
        y_true = [0, 1, 0, 1]
        y_prob = [0.2, 0.8, 0.4, 0.6]
        ece = expected_calibration_error(y_true, y_prob)
        assert 0.0 <= ece <= 1.0


# ---------------------------------------------------------------------------
# regression_metrics
# ---------------------------------------------------------------------------


class TestRegressionMetrics:
    Y_TRUE = [3.0, -0.5, 2.0, 7.0]
    Y_PRED = [2.5, 0.0, 2.0, 8.0]

    def test_result_type(self) -> None:
        m = regression_metrics(self.Y_TRUE, self.Y_PRED)
        assert isinstance(m, RegressionMetrics)

    def test_mae(self) -> None:
        m = regression_metrics(self.Y_TRUE, self.Y_PRED)
        expected = (0.5 + 0.5 + 0.0 + 1.0) / 4
        assert m.mae == pytest.approx(expected)

    def test_mse(self) -> None:
        m = regression_metrics(self.Y_TRUE, self.Y_PRED)
        expected = (0.25 + 0.25 + 0.0 + 1.0) / 4
        assert m.mse == pytest.approx(expected)

    def test_rmse(self) -> None:
        import math

        m = regression_metrics(self.Y_TRUE, self.Y_PRED)
        assert m.rmse == pytest.approx(math.sqrt(m.mse))

    def test_r2_perfect(self) -> None:
        m = regression_metrics([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert m.r2 == pytest.approx(1.0)

    def test_r2_range(self) -> None:
        m = regression_metrics(self.Y_TRUE, self.Y_PRED)
        assert m.r2 <= 1.0

    def test_mape_none_when_zero_true(self) -> None:
        m = regression_metrics([0.0, 1.0], [0.1, 1.0])
        assert m.mape is None

    def test_mismatched_lengths_raise(self) -> None:
        with pytest.raises(ValueError):
            regression_metrics([1.0, 2.0], [1.0])
