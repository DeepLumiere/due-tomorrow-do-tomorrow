"""
Field Verifier Rigorous Test Evaluation.
Performs clean, single-pass evaluation on the unseen test split:
- Metrics: PR-AUC (Average Precision), ROC-AUC, Brier Score, Balanced Accuracy, Precision, Recall, F1.
- Receipt-level bootstrap 95% confidence intervals (1,000 resamples).
- Risk-coverage analysis (coverage % vs residual error rate).
- Exports metrics to reports/metrics.json and plots to reports/.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)

from src.verifier.train import CATEGORICAL_FEATURES, NUMERIC_FEATURES

logger = logging.getLogger(__name__)


def compute_risk_coverage(
    y_true: np.ndarray, y_proba_error: np.ndarray, n_points: int = 50
) -> List[Dict[str, float]]:
    """
    Compute Risk-Coverage curve data:
    Sort fields by verifier confidence P(correct) = 1 - P(error) in descending order.
    For each coverage level (top k% auto-accepted), compute the error rate of accepted fields.
    """
    confidences = 1.0 - y_proba_error
    order = np.argsort(-confidences) # highest confidence first
    y_sorted = y_true[order]

    curve = []
    n = len(y_sorted)
    for frac in np.linspace(0.05, 1.0, n_points):
        k = max(1, int(n * frac))
        accepted = y_sorted[:k]
        error_rate = float(np.mean(accepted))
        accuracy = 1.0 - error_rate
        curve.append({
            "coverage_pct": round(float(frac * 100), 2),
            "accepted_count": int(k),
            "error_rate_pct": round(float(error_rate * 100), 2),
            "accuracy_pct": round(float(accuracy * 100), 2),
        })
    return curve


def compute_bootstrap_ci(
    test_df: pd.DataFrame,
    y_true: np.ndarray,
    y_proba: np.ndarray,
    n_bootstrap: int = 1000,
    random_state: int = 42,
) -> Dict[str, Tuple[float, float]]:
    """
    Receipt-level cluster bootstrap for 95% confidence intervals.
    """
    rng = np.random.RandomState(random_state)
    doc_ids = np.unique(test_df["doc_id"].values)
    n_docs = len(doc_ids)

    boot_pr_aucs = []
    boot_roc_aucs = []
    boot_brier = []

    for _ in range(n_bootstrap):
        sampled_docs = rng.choice(doc_ids, size=n_docs, replace=True)
        # Select all rows matching sampled doc_ids
        mask = np.isin(test_df["doc_id"].values, sampled_docs)
        if np.sum(mask) == 0:
            continue
        y_b = y_true[mask]
        p_b = y_proba[mask]
        if len(np.unique(y_b)) < 2:
            continue

        boot_pr_aucs.append(average_precision_score(y_b, p_b))
        boot_roc_aucs.append(roc_auc_score(y_b, p_b))
        boot_brier.append(brier_score_loss(y_b, p_b))

    return {
        "pr_auc_ci95": (
            float(np.percentile(boot_pr_aucs, 2.5)),
            float(np.percentile(boot_pr_aucs, 97.5)),
        ),
        "roc_auc_ci95": (
            float(np.percentile(boot_roc_aucs, 2.5)),
            float(np.percentile(boot_roc_aucs, 97.5)),
        ),
        "brier_ci95": (
            float(np.percentile(boot_brier, 2.5)),
            float(np.percentile(boot_brier, 97.5)),
        ),
    }


def evaluate_test_set(
    model: Any,
    test_df: pd.DataFrame,
    threshold: float = 0.85, # Confidence threshold P(correct) >= threshold to accept
    reports_dir: str = "reports",
) -> Dict[str, Any]:
    """
    Perform complete evaluation on test set and write metrics and figures.
    """
    rep_p = Path(reports_dir)
    rep_p.mkdir(parents=True, exist_ok=True)

    X_test = test_df[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y_test = test_df["is_error"].values

    # Predict probabilities: proba[:, 1] is P(error), proba[:, 0] is P(correct)
    probas = model.predict_proba(X_test)
    p_error = probas[:, 1]
    p_correct = probas[:, 0]

    # Needs review flag: if confidence P(correct) < threshold -> needs_review (predict error=1)
    y_pred_review = np.where(p_correct < threshold, 1, 0)

    # Core metrics
    pr_auc = float(average_precision_score(y_test, p_error))
    roc_auc = float(roc_auc_score(y_test, p_error))
    brier = float(brier_score_loss(y_test, p_error))
    bal_acc = float(balanced_accuracy_score(y_test, y_pred_review))
    f1 = float(f1_score(y_test, y_pred_review, zero_division=0))
    prec = float(precision_score(y_test, y_pred_review, zero_division=0))
    rec = float(recall_score(y_test, y_pred_review, zero_division=0))

    cm = confusion_matrix(y_test, y_pred_review).tolist()

    # Bootstrap CIs
    ci_dict = compute_bootstrap_ci(test_df, y_test, p_error)

    # Risk-Coverage Curve
    risk_coverage = compute_risk_coverage(y_test, p_error)

    # Error analysis by field type
    field_breakdown = {}
    for fg, group_df in test_df.groupby("field_group"):
        g_idx = group_df.index
        g_mask = np.isin(test_df.index, g_idx)
        g_y = y_test[g_mask]
        g_pred = y_pred_review[g_mask]
        field_breakdown[fg] = {
            "total_count": int(len(g_y)),
            "error_count": int(np.sum(g_y)),
            "error_rate_pct": round(float(np.mean(g_y) * 100), 2) if len(g_y) > 0 else 0.0,
            "detected_error_count": int(np.sum((g_y == 1) & (g_pred == 1))),
            "recall_pct": round(float(recall_score(g_y, g_pred, zero_division=0) * 100), 2),
        }

    metrics_output = {
        "dataset": {
            "test_rows": len(test_df),
            "test_documents": int(test_df["doc_id"].nunique()),
            "error_rate_pct": round(float(np.mean(y_test) * 100), 2),
            "threshold_confidence": threshold,
        },
        "performance": {
            "pr_auc": round(pr_auc, 4),
            "pr_auc_ci95": [round(ci_dict["pr_auc_ci95"][0], 4), round(ci_dict["pr_auc_ci95"][1], 4)],
            "roc_auc": round(roc_auc, 4),
            "roc_auc_ci95": [round(ci_dict["roc_auc_ci95"][0], 4), round(ci_dict["roc_auc_ci95"][1], 4)],
            "brier_score": round(brier, 4),
            "brier_ci95": [round(ci_dict["brier_ci95"][0], 4), round(ci_dict["brier_ci95"][1], 4)],
            "balanced_accuracy": round(bal_acc, 4),
            "error_precision": round(prec, 4),
            "error_recall": round(rec, 4),
            "error_f1": round(f1, 4),
            "confusion_matrix": {
                "tn": cm[0][0],
                "fp": cm[0][1],
                "fn": cm[1][0],
                "tp": cm[1][1],
            },
        },
        "field_breakdown": field_breakdown,
        "risk_coverage": risk_coverage,
    }

    # Save metrics JSON
    metrics_file = rep_p / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics_output, f, indent=2)
    logger.info("Saved metrics to %s", metrics_file)

    # -------------------------------------------------------------
    # Plotting: Generate publication-grade figures
    # -------------------------------------------------------------
    try:
        # 1. PR and ROC curves
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        precision_vals, recall_vals, _ = precision_recall_curve(y_test, p_error)
        axes[0].plot(recall_vals, precision_vals, color="#1f77b4", lw=2, label=f"PR curve (AUC = {pr_auc:.3f})")
        axes[0].axhline(y=np.mean(y_test), color="gray", linestyle="--", label=f"Random baseline ({np.mean(y_test):.3f})")
        axes[0].set_xlabel("Recall (Error Detection)")
        axes[0].set_ylabel("Precision")
        axes[0].set_title("Precision-Recall Curve (Minority Error Class)")
        axes[0].legend()
        axes[0].grid(alpha=0.3)

        fpr, tpr, _ = roc_curve(y_test, p_error)
        axes[1].plot(fpr, tpr, color="#ff7f0e", lw=2, label=f"ROC curve (AUC = {roc_auc:.3f})")
        axes[1].plot([0, 1], [0, 1], color="gray", linestyle="--")
        axes[1].set_xlabel("False Positive Rate")
        axes[1].set_ylabel("True Positive Rate")
        axes[1].set_title("ROC Curve")
        axes[1].legend()
        axes[1].grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(rep_p / "pr_roc_curves.png", dpi=150)
        plt.close()

        # 2. Risk-Coverage Curve
        fig, ax = plt.subplots(figsize=(7, 5))
        cov_pct = [r["coverage_pct"] for r in risk_coverage]
        acc_pct = [r["accuracy_pct"] for r in risk_coverage]
        ax.plot(cov_pct, acc_pct, marker="o", color="#2ca02c", lw=2, label="Field Verifier Selection")
        baseline_acc = (1.0 - np.mean(y_test)) * 100.0
        ax.axhline(y=baseline_acc, color="red", linestyle="--", label=f"Unfiltered Overall Accuracy ({baseline_acc:.1f}%)")
        ax.set_xlabel("Coverage (% of fields auto-accepted)")
        ax.set_ylabel("Accuracy on Accepted Fields (%)")
        ax.set_title("Risk-Coverage Curve")
        ax.legend()
        ax.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(rep_p / "risk_coverage_curve.png", dpi=150)
        plt.close()

        # 3. Calibration Curve
        prob_true, prob_pred = calibration_curve(y_test, p_error, n_bins=10)
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.plot(prob_pred, prob_true, marker="s", color="#9467bd", lw=2, label="Calibrated Model")
        ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfect Calibration")
        ax.set_xlabel("Mean Predicted Probability P(error)")
        ax.set_ylabel("Fraction of True Errors")
        ax.set_title(f"Reliability Diagram (Brier Score = {brier:.4f})")
        ax.legend()
        ax.grid(alpha=0.3)
        plt.tight_layout()
        plt.savefig(rep_p / "calibration_curve.png", dpi=150)
        plt.close()

        logger.info("Generated all evaluation plots in %s", rep_p)
    except Exception as e:
        logger.warning("Could not generate plots: %s", e)

    return metrics_output
