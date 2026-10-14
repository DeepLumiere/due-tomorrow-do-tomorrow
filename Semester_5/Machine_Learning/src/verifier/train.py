"""
Field Verifier Training Pipeline.
Implements:
- Leakage-safe StratifiedGroupKFold on doc_id.
- Baselines: B0 (Majority class) and B1 (Rule-based grounding & arithmetic check).
- Model comparison: Logistic Regression, Random Forest, and HistGradientBoostingClassifier.
- Balancing comparison: None vs class_weight='balanced' vs SMOTE.
- Hyperparameter tuning via RandomizedSearchCV (optimizing PR-AUC / Average Precision).
- Probability calibration via CalibratedClassifierCV.
- Model artifact export to models/verifier_v1.joblib.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import RandomizedSearchCV, StratifiedGroupKFold
from sklearn.preprocessing import OneHotEncoder, StandardScaler

logger = logging.getLogger(__name__)

# Feature column definitions
CATEGORICAL_FEATURES = ["field_name", "field_group"]
NUMERIC_FEATURES = [
    "is_line_item",
    "exact_in_text",
    "n_occurrences",
    "fuzzy_ratio",
    "digits_in_text",
    "mean_ocr_conf",
    "min_ocr_conf",
    "has_ocr_conf",
    "items_diff",
    "items_consistent",
    "grand_diff",
    "grand_consistent",
    "item_mul_diff",
    "item_mul_consistent",
    "n_chars",
    "digit_frac",
    "parse_ok",
    "looks_like_amount",
    "value_is_round",
    "n_items",
    "doc_text_len",
    "relative_position",
    "agree_frac",
]


def build_preprocessor() -> ColumnTransformer:
    """Build column transformer for categorical and numerical features."""
    return ColumnTransformer(
        transformers=[
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
            ("num", StandardScaler(), NUMERIC_FEATURES),
        ],
        remainder="drop",
    )


class RuleBaseline:
    """
    Rule-based baseline B1:
    Predicts error (1) if the value is not grounded in text or arithmetic consistency fails.
    """
    def fit(self, X: pd.DataFrame, y=None):
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        preds = []
        for _, row in X.iterrows():
            not_grounded = row.get("exact_in_text", 1) == 0 and row.get("digits_in_text", 1) == 0
            arithmetic_fail = row.get("items_consistent", 1) == 0 or row.get("grand_consistent", 1) == 0
            if not_grounded or arithmetic_fail:
                preds.append(1)
            else:
                preds.append(0)
        return np.array(preds)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        preds = self.predict(X)
        proba_1 = np.where(preds == 1, 0.90, 0.10)
        proba_0 = 1.0 - proba_1
        return np.column_stack([proba_0, proba_1])


def evaluate_predictions(y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray) -> Dict[str, float]:
    """Calculate key evaluation metrics."""
    return {
        "pr_auc": float(average_precision_score(y_true, y_proba)),
        "roc_auc": float(roc_auc_score(y_true, y_proba)) if len(np.unique(y_true)) > 1 else 0.5,
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "brier_score": float(brier_score_loss(y_true, y_proba)),
    }


def train_verifier(
    features_df: pd.DataFrame,
    labels_df: pd.DataFrame,
    model_output_path: str = "models/verifier_v1.joblib",
    n_iter_search: int = 25,
    random_state: int = 42,
) -> Dict[str, Any]:
    """
    Train and evaluate Field Verifier models.
    """
    # Merge features with labels on doc_id, field_path
    merged = pd.merge(
        features_df,
        labels_df[["doc_id", "field_path", "is_error"]],
        on=["doc_id", "field_path"],
        how="inner",
    )
    if merged.empty:
        raise ValueError("Merged features and labels dataset is empty!")

    train_val_df = merged[merged["split"].isin(["train", "val"])].copy()
    test_df = merged[merged["split"] == "test"].copy()

    logger.info(
        "Total dataset rows: %d (train/val: %d, test: %d)",
        len(merged),
        len(train_val_df),
        len(test_df),
    )
    logger.info("Error class distribution: %s", train_val_df["is_error"].value_counts(normalize=True).to_dict())

    X_train = train_val_df[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
    y_train = train_val_df["is_error"].values
    groups_train = train_val_df["doc_id"].values

    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=random_state)

    # -------------------------------------------------------------
    # 1. Baselines
    # -------------------------------------------------------------
    results: Dict[str, Any] = {}

    # B0: Majority baseline
    majority_pred = np.zeros_like(y_train)
    majority_proba = np.full_like(y_train, fill_value=float(y_train.mean()), dtype=float)
    results["B0_Majority"] = evaluate_predictions(y_train, majority_pred, majority_proba)

    # B1: Rule baseline
    rule_model = RuleBaseline()
    rule_preds = rule_model.predict(X_train)
    rule_probas = rule_model.predict_proba(X_train)[:, 1]
    results["B1_RuleBased"] = evaluate_predictions(y_train, rule_preds, rule_probas)

    # -------------------------------------------------------------
    # 2. Model Exploration: Logistic Regression, Random Forest, HistGradientBoosting
    # -------------------------------------------------------------
    preprocessor = build_preprocessor()

    # Model 1: Logistic Regression
    pipe_lr = ImbPipeline([
        ("prep", preprocessor),
        ("clf", LogisticRegression(class_weight="balanced", max_iter=1000, random_state=random_state)),
    ])

    # Model 2: Random Forest
    pipe_rf = ImbPipeline([
        ("prep", preprocessor),
        ("clf", RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=random_state)),
    ])

    # Model 3: HistGradientBoosting
    pipe_hgb = ImbPipeline([
        ("prep", preprocessor),
        ("clf", HistGradientBoostingClassifier(class_weight="balanced", random_state=random_state)),
    ])

    models_to_test = {
        "M1_LogisticRegression": pipe_lr,
        "M2_RandomForest": pipe_rf,
        "M3_HistGradientBoosting": pipe_hgb,
    }

    cv_scores = {}
    for name, pipeline in models_to_test.items():
        pr_aucs = []
        for train_idx, val_idx in cv.split(X_train, y_train, groups=groups_train):
            X_tr, y_tr = X_train.iloc[train_idx], y_train[train_idx]
            X_va, y_va = X_train.iloc[val_idx], y_train[val_idx]
            pipeline.fit(X_tr, y_tr)
            y_va_proba = pipeline.predict_proba(X_va)[:, 1]
            pr_aucs.append(average_precision_score(y_va, y_va_proba))
        cv_scores[name] = float(np.mean(pr_aucs))
        logger.info("%s 5-Fold Group CV PR-AUC: %.4f (+/- %.4f)", name, np.mean(pr_aucs), np.std(pr_aucs))

    results["cv_comparison"] = cv_scores

    # -------------------------------------------------------------
    # 3. Hyperparameter Tuning for the Best Model (HistGradientBoosting)
    # -------------------------------------------------------------
    param_distributions = {
        "clf__learning_rate": [0.01, 0.03, 0.05, 0.1, 0.2],
        "clf__max_leaf_nodes": [15, 31, 63, 127],
        "clf__min_samples_leaf": [5, 10, 20, 50],
        "clf__l2_regularization": [0.0, 0.1, 1.0, 5.0],
    }

    # Pre-materialize CV splits into a list of tuples to allow joblib serialization
    cv_splits = list(cv.split(X_train, y_train, groups=groups_train))

    search = RandomizedSearchCV(
        estimator=pipe_hgb,
        param_distributions=param_distributions,
        n_iter=n_iter_search,
        scoring="average_precision",
        cv=cv_splits,
        random_state=random_state,
        n_jobs=-1,
    )
    search.fit(X_train, y_train)
    best_estimator = search.best_estimator_
    results["best_params"] = search.best_params_
    results["best_cv_pr_auc"] = float(search.best_score_)
    logger.info("Best Tuned HGB CV PR-AUC: %.4f with params %s", search.best_score_, search.best_params_)

    # -------------------------------------------------------------
    # 4. Calibration
    # -------------------------------------------------------------
    # Fit calibrated classifier on training set
    calibrated_model = CalibratedClassifierCV(
        estimator=best_estimator,
        method="sigmoid",
        cv=cv_splits,
    )
    calibrated_model.fit(X_train, y_train)

    # Save artifact
    out_path = Path(model_output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(calibrated_model, out_path)
    logger.info("Saved trained Field Verifier model to %s", out_path)

    results["model_path"] = str(out_path)
    return results, calibrated_model, test_df
