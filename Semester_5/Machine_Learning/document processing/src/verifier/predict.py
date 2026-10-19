"""
Runtime Field Verifier Scoring.
Applies the trained Field Verifier model to score each extracted field,
assign confidence scores P(correct), and flag fields requiring user review.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import joblib
import numpy as np
import pandas as pd

from src.schema.invoice import NormalizedInvoice, ParsedDoc, InvoiceExtraction
from src.verifier.features import (
    build_document_features,
    extract_features_for_field,
)
from src.verifier.train import CATEGORICAL_FEATURES, NUMERIC_FEATURES

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_PATH = "models/verifier_v1.joblib"
_LOADED_MODEL = None


def get_verifier_model(model_path: str = _DEFAULT_MODEL_PATH):
    """Singleton loader for verifier model."""
    global _LOADED_MODEL
    if _LOADED_MODEL is None:
        p = Path(model_path)
        if not p.exists():
            logger.warning("Verifier model not found at %s. Returning None (pass-through).", p)
            return None
        _LOADED_MODEL = joblib.load(p)
    return _LOADED_MODEL


def verify_normalized_invoice(
    normalized_inv: NormalizedInvoice,
    parsed_doc: ParsedDoc,
    extraction: InvoiceExtraction,
    model_path: str = _DEFAULT_MODEL_PATH,
    threshold: float = 0.85,
) -> NormalizedInvoice:
    """
    Score all fields in a NormalizedInvoice using the trained Field Verifier.
    Sets confidence P(correct) and needs_review flags on each field and on the document.
    """
    model = get_verifier_model(model_path)

    # Build features for document fields
    feature_rows = build_document_features(
        parsed_doc=parsed_doc,
        extraction=extraction,
        doc_id=normalized_inv.doc_id,
        split="inference",
    )

    if not feature_rows:
        return normalized_inv

    df_feats = pd.DataFrame(feature_rows)

    if model is not None:
        try:
            X = df_feats[CATEGORICAL_FEATURES + NUMERIC_FEATURES]
            probas = model.predict_proba(X)
            # probas[:, 0] is P(correct), probas[:, 1] is P(error)
            p_correct = probas[:, 0]
        except Exception as e:
            logger.warning("Verifier prediction failed (%s). Falling back to rule-based confidence.", e)
            p_correct = np.where(df_feats["exact_in_text"] == 1, 0.95, 0.40)
    else:
        # Fallback heuristic if model not yet trained
        p_correct = np.where(df_feats["exact_in_text"] == 1, 0.95, 0.40)

    # Map scores back to FieldResult objects
    score_by_path = {}
    for idx, row in df_feats.iterrows():
        path = row["field_path"]
        conf = float(p_correct[idx])
        needs_rev = bool(conf < threshold)
        score_by_path[path] = (conf, needs_rev)

    all_confs: List[float] = []
    any_needs_review = False

    for field in normalized_inv.fields:
        if field.field_path in score_by_path:
            conf, needs_rev = score_by_path[field.field_path]
            field.confidence = round(conf, 4)
            field.needs_review = needs_rev
            all_confs.append(conf)
            if needs_rev:
                any_needs_review = True

    # Update line item summary confidences
    for item in normalized_inv.line_items:
        item_prefix = f"line_items[{item.item_idx}]"
        item_confs = [
            field.confidence
            for field in normalized_inv.fields
            if field.field_path.startswith(item_prefix) and field.confidence is not None
        ]
        if item_confs:
            item.confidence = round(float(np.mean(item_confs)), 4)
            item.needs_review = any(c < threshold for c in item_confs)
            if item.needs_review:
                any_needs_review = True

    normalized_inv.min_field_confidence = round(float(np.min(all_confs)), 4) if all_confs else None
    normalized_inv.needs_review = any_needs_review
    return normalized_inv
