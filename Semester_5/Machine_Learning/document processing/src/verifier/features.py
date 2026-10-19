"""
Feature Engineering for Field Verifier.
Extracts rich tabular features from the raw extraction, parsed document text, and OCR metadata.

Strictly adheres to implementation.md §7.2:
- NEVER uses ground truth (no data leakage).
- All features are derived solely from OCR output, document structure, and extraction consistency.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from src.pipeline.checks import (
    check_grand_total,
    check_item_multiplication,
    check_line_items_sum,
)
from src.pipeline.normalize import clean_text, normalize_invoice, parse_amount
from src.schema.invoice import (
    InvoiceExtraction,
    NormalizedInvoice,
    NormalizedLineItem,
    ParsedDoc,
)


def extract_features_for_field(
    field_path: str,
    field_group: str,
    raw_val: Optional[str],
    doc_text: str,
    ocr_items: List[Any],
    normalized_inv: NormalizedInvoice,
    agree_frac: float = 1.0,
) -> Dict[str, Any]:
    """
    Extract feature dictionary for a single extracted field.
    """
    text_lower = doc_text.lower()
    raw_clean = clean_text(raw_val) or ""
    raw_lower = raw_clean.lower()
    doc_len = max(len(doc_text), 1)

    # 1. Identity
    is_line_item = 1 if "line_items" in field_path else 0
    field_name = field_path.split(".")[-1] if "." in field_path else field_path
    if "[" in field_name:
        field_name = field_name.split("[")[0]

    # 2. Grounding in Document Text
    exact_in_text = 1 if (raw_lower and raw_lower in text_lower) else 0
    n_occurrences = text_lower.count(raw_lower) if raw_lower else 0
    
    # Fuzzy ratio against best matching line/snippet
    fuzzy_ratio = 0.0
    if raw_lower:
        fuzzy_ratio = float(fuzz.partial_ratio(raw_lower, text_lower)) / 100.0

    # 3. Numeric Grounding (digits match)
    digits_only = re.sub(r"\D", "", raw_clean)
    digits_text = re.sub(r"\D", "", text_lower)
    digits_in_text = 1 if (digits_only and digits_only in digits_text) else 0

    # 4. OCR Confidence
    matched_confs: List[float] = []
    if ocr_items and raw_lower:
        for item in ocr_items:
            item_text = getattr(item, "text", "") or ""
            conf = getattr(item, "confidence", None)
            if conf is not None and (raw_lower in item_text.lower() or item_text.lower() in raw_lower):
                matched_confs.append(float(conf))

    if matched_confs:
        mean_ocr_conf = float(np.mean(matched_confs))
        min_ocr_conf = float(np.min(matched_confs))
        has_ocr_conf = 1
    else:
        mean_ocr_conf = 0.85 # default imputation
        min_ocr_conf = 0.85
        has_ocr_conf = 0

    # 5. Arithmetic Consistency Signals
    # Cross-field checks computed at document level
    items_consistent, items_diff = check_line_items_sum(
        normalized_inv.subtotal, normalized_inv.line_items
    )
    grand_consistent, grand_diff = check_grand_total(
        total=normalized_inv.total,
        subtotal=normalized_inv.subtotal,
        tax=normalized_inv.tax,
        discount=normalized_inv.discount,
        service=normalized_inv.service_charge,
    )

    # Item multiplication check if this is an item field
    item_mul_diff = 0.0
    item_mul_consistent = True
    if is_line_item:
        match_idx = re.search(r"line_items\[(\d+)\]", field_path)
        if match_idx:
            idx = int(match_idx.group(1))
            if idx < len(normalized_inv.line_items):
                item = normalized_inv.line_items[idx]
                item_mul_consistent, item_mul_diff = check_item_multiplication(
                    item.quantity, item.unit_price, item.line_total
                )

    # 6. Format Features
    n_chars = len(raw_clean)
    n_digits = sum(1 for c in raw_clean if c.isdigit())
    digit_frac = float(n_digits / n_chars) if n_chars > 0 else 0.0
    parsed_num = parse_amount(raw_val)
    parse_ok = 1 if parsed_num is not None else 0
    looks_like_amount = 1 if re.search(r"\d+[.,]\d+", raw_clean) or re.search(r"\b\d{4,}\b", raw_clean) else 0

    # Value is round (e.g. 10000, 25000 in IDR)
    value_is_round = 0
    if parsed_num is not None and parsed_num > 0:
        if parsed_num % 1000 == 0:
            value_is_round = 1

    # 7. Document Context
    n_items = len(normalized_inv.line_items)
    rel_pos = 0.5
    if raw_lower and raw_lower in text_lower:
        first_pos = text_lower.find(raw_lower)
        rel_pos = float(first_pos / doc_len)

    return {
        "field_name": field_name,
        "field_group": field_group,
        "is_line_item": is_line_item,
        "exact_in_text": exact_in_text,
        "n_occurrences": n_occurrences,
        "fuzzy_ratio": fuzzy_ratio,
        "digits_in_text": digits_in_text,
        "mean_ocr_conf": mean_ocr_conf,
        "min_ocr_conf": min_ocr_conf,
        "has_ocr_conf": has_ocr_conf,
        "items_diff": float(items_diff),
        "items_consistent": 1 if items_consistent else 0,
        "grand_diff": float(grand_diff),
        "grand_consistent": 1 if grand_consistent else 0,
        "item_mul_diff": float(item_mul_diff),
        "item_mul_consistent": 1 if item_mul_consistent else 0,
        "n_chars": n_chars,
        "digit_frac": digit_frac,
        "parse_ok": parse_ok,
        "looks_like_amount": looks_like_amount,
        "value_is_round": value_is_round,
        "n_items": n_items,
        "doc_text_len": doc_len,
        "relative_position": rel_pos,
        "agree_frac": float(agree_frac),
    }


def build_document_features(
    parsed_doc: ParsedDoc,
    extraction: InvoiceExtraction,
    doc_id: str,
    split: str = "train",
) -> List[Dict[str, Any]]:
    """
    Build a list of feature dictionaries for all non-null extracted fields of a document.
    """
    normalized_inv = normalize_invoice(
        extraction, doc_id=doc_id, filename=parsed_doc.source_filename, doc_text=parsed_doc.text
    )

    rows: List[Dict[str, Any]] = []

    # Map core document fields
    doc_fields = [
        ("total", "total", extraction.total),
        ("subtotal", "subtotal", extraction.subtotal),
        ("tax", "tax", extraction.tax),
        ("discount", "discount", extraction.discount),
        ("service_charge", "service_charge", extraction.service_charge),
    ]

    for path, group, raw_val in doc_fields:
        if raw_val is not None:
            feat = extract_features_for_field(
                field_path=path,
                field_group=group,
                raw_val=raw_val,
                doc_text=parsed_doc.text,
                ocr_items=parsed_doc.ocr_items,
                normalized_inv=normalized_inv,
            )
            feat["doc_id"] = doc_id
            feat["split"] = split
            feat["field_path"] = path
            feat["raw_value"] = raw_val
            rows.append(feat)

    # Line items
    for i, item in enumerate(extraction.line_items):
        item_fields = [
            (f"line_items[{i}].description", "line_item_description", item.description),
            (f"line_items[{i}].line_total", "line_item_total", item.line_total),
            (f"line_items[{i}].unit_price", "line_item_unit_price", item.unit_price),
            (f"line_items[{i}].quantity", "line_item_qty", item.quantity),
        ]
        for path, group, raw_val in item_fields:
            if raw_val is not None:
                feat = extract_features_for_field(
                    field_path=path,
                    field_group=group,
                    raw_val=raw_val,
                    doc_text=parsed_doc.text,
                    ocr_items=parsed_doc.ocr_items,
                    normalized_inv=normalized_inv,
                )
                feat["doc_id"] = doc_id
                feat["split"] = split
                feat["field_path"] = path
                feat["raw_value"] = raw_val
                rows.append(feat)

    return rows
