"""
Field Verifier Training and Evaluation Driver.
Executes the full pipeline:
- Load features and labels
- Run Baselines (B0, B1) and Model Comparison (LR, RF, HistGradientBoosting) with 5-fold StratifiedGroupKFold
- Hyperparameter Tuning (RandomizedSearchCV)
- Probability Calibration
- Single-pass Test Set Evaluation with 1000-resample bootstrap 95% CIs
- Export reports/metrics.json and publication-grade plots to reports/
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from src.verifier.evaluate import evaluate_test_set
from src.verifier.train import train_verifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("train_driver")


def main():
    feat_path = "data/processed/features_v1.parquet"
    label_path = "data/processed/labels_v1.parquet"

    logger.info("Loading features from %s and labels from %s...", feat_path, label_path)
    features_df = pd.read_parquet(feat_path)
    labels_df = pd.read_parquet(label_path)

    # 1. Train and tune
    results, calibrated_model, test_df = train_verifier(
        features_df=features_df,
        labels_df=labels_df,
        model_output_path="models/verifier_v1.joblib",
        n_iter_search=20,
        random_state=42,
    )

    logger.info("Baseline and Model CV Results:")
    logger.info("  B0 Majority PR-AUC: %.4f", results["B0_Majority"]["pr_auc"])
    logger.info("  B1 Rule-Based PR-AUC: %.4f", results["B1_RuleBased"]["pr_auc"])
    for name, score in results["cv_comparison"].items():
        logger.info("  %s PR-AUC: %.4f", name, score)
    logger.info("  Tuned Model PR-AUC: %.4f", results["best_cv_pr_auc"])

    # 2. Evaluate on test split
    logger.info("Evaluating calibrated model on unseen test split (%d rows)...", len(test_df))
    metrics = evaluate_test_set(
        model=calibrated_model,
        test_df=test_df,
        threshold=0.85,
        reports_dir="reports",
    )

    # Append CV comparison to metrics.json
    metrics["cv_comparison"] = results["cv_comparison"]
    metrics["baselines"] = {
        "B0_Majority": results["B0_Majority"],
        "B1_RuleBased": results["B1_RuleBased"],
    }
    metrics["best_tuned_cv_pr_auc"] = results["best_cv_pr_auc"]
    metrics["best_params"] = results["best_params"]

    with open("reports/metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    logger.info("Final metrics updated in reports/metrics.json")
    logger.info("Test PR-AUC: %.4f %s", metrics["performance"]["pr_auc"], metrics["performance"]["pr_auc_ci95"])
    logger.info("Test ROC-AUC: %.4f %s", metrics["performance"]["roc_auc"], metrics["performance"]["roc_auc_ci95"])
    logger.info("Test Balanced Accuracy: %.4f", metrics["performance"]["balanced_accuracy"])
    logger.info("Training and evaluation completed successfully!")


if __name__ == "__main__":
    main()
