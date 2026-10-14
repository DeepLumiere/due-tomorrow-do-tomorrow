"""
Ground Truth Alignment and Label Construction.
Aligns LLM extractions against CORD ground truth fields and assigns binary correctness labels:
  y = 0 (CORRECT / MATCH)
  y = 1 (WRONG / ERROR / HALLUCINATION)

Uses Hungarian bipartite matching (via scipy.optimize.linear_sum_assignment) on
RapidFuzz string similarities for line item alignment.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from rapidfuzz import fuzz
from scipy.optimize import linear_sum_assignment

from src.pipeline.normalize import clean_text, parse_amount
from src.schema.invoice import InvoiceExtraction, LineItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Scalar field matching rules
# ---------------------------------------------------------

def compare_amounts(
    pred_amount: Optional[Decimal],
    gt_amount: Optional[Decimal],
    rel_tol: float = 0.01,
) -> bool:
    """
    Compare predicted amount against ground truth amount.
    Accepts equal values or relative tolerance <= 1% to tolerate minor rounding.
    Both None -> Match (absent in both).
    One None -> Discrepancy.
    """
    if pred_amount is None and gt_amount is None:
        return True
    if pred_amount is None or gt_amount is None:
        return False
    if pred_amount == gt_amount:
        return True
    diff = abs(pred_amount - gt_amount)
    denom = max(abs(pred_amount), abs(gt_amount))
    if denom == 0:
        return diff == 0
    return float(diff / denom) <= rel_tol


def compare_strings(
    pred_str: Optional[str],
    gt_str: Optional[str],
    threshold: float = 75.0,
) -> bool:
    """
    Compare text strings using RapidFuzz token sort ratio.
    """
    p = clean_text(pred_str)
    g = clean_text(gt_str)
    if not p and not g:
        return True
    if not p or not g:
        return False
    score = fuzz.token_sort_ratio(p.lower(), g.lower())
    return score >= threshold


# ---------------------------------------------------------
# Line item Hungarian matching
# ---------------------------------------------------------

def match_line_items(
    pred_items: List[LineItem],
    gt_items: List[Dict[str, Any]],
    sim_threshold: float = 40.0,
) -> List[Tuple[Optional[int], Optional[int], float]]:
    """
    Perform optimal bipartite matching between predicted line items and ground truth line items
    using the Hungarian algorithm on description string similarity.

    Returns:
        List of tuples (pred_idx, gt_idx, similarity_score).
        pred_idx=None represents unmatched GT items (recall misses).
        gt_idx=None represents unmatched predicted items (hallucinations/false positives).
    """
    n_pred = len(pred_items)
    n_gt = len(gt_items)

    if n_pred == 0 and n_gt == 0:
        return []
    if n_pred == 0:
        return [(None, j, 0.0) for j in range(n_gt)]
    if n_gt == 0:
        return [(i, None, 0.0) for i in range(n_pred)]

    # Build cost matrix: 100 - similarity
    cost_matrix = np.zeros((n_pred, n_gt))
    sim_matrix = np.zeros((n_pred, n_gt))

    for i, p_item in enumerate(pred_items):
        p_desc = clean_text(p_item.description) or ""
        for j, g_item in enumerate(gt_items):
            g_desc = clean_text(g_item.get("nm") or g_item.get("description")) or ""
            score = fuzz.token_sort_ratio(p_desc.lower(), g_desc.lower())
            sim_matrix[i, j] = score
            cost_matrix[i, j] = 100.0 - score

    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    matches: List[Tuple[Optional[int], Optional[int], float]] = []
    matched_preds = set()
    matched_gts = set()

    for r, c in zip(row_ind, col_ind):
        score = sim_matrix[r, c]
        if score >= sim_threshold:
            matches.append((r, c, float(score)))
            matched_preds.add(r)
            matched_gts.add(c)
        else:
            # Below similarity threshold -> treat as separate unmatched
            pass

    for i in range(n_pred):
        if i not in matched_preds:
            matches.append((i, None, 0.0))

    for j in range(n_gt):
        if j not in matched_gts:
            matches.append((None, j, 0.0))

    return matches


# ---------------------------------------------------------
# Full extraction alignment & label assignment
# ---------------------------------------------------------

def align_extraction_with_gt(
    doc_id: str,
    split: str,
    extracted: InvoiceExtraction,
    gt_dict: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Align all extracted fields with CORD ground truth.
    Produces one record per non-null extracted field:
    {
        'doc_id': str,
        'split': str,
        'field_path': str,
        'pred_raw': str,
        'gt_raw': str,
        'is_error': int (1 for wrong, 0 for correct),
        'match_type': str
    }
    """
    records: List[Dict[str, Any]] = []

    def _safe_val(v):
        if isinstance(v, list):
            return v[0] if v else None
        return v

    # 1. Total group
    gt_total_grp = gt_dict.get("total", {})
    if isinstance(gt_total_grp, list):
        gt_total_grp = gt_total_grp[0] if (gt_total_grp and isinstance(gt_total_grp[0], dict)) else {}
    elif not isinstance(gt_total_grp, dict):
        gt_total_grp = {}

    gt_total_raw = _safe_val(gt_total_grp.get("total_price"))
    gt_total_num = parse_amount(gt_total_raw)
    pred_total_raw = extracted.total
    pred_total_num = parse_amount(pred_total_raw)

    if pred_total_raw is not None:
        is_correct = compare_amounts(pred_total_num, gt_total_num)
        records.append({
            "doc_id": doc_id,
            "split": split,
            "field_path": "total",
            "field_group": "total",
            "pred_raw": str(pred_total_raw),
            "gt_raw": str(gt_total_raw) if gt_total_raw is not None else None,
            "is_error": 0 if is_correct else 1,
        })

    # Subtotal
    gt_sub_grp = gt_dict.get("sub_total", {})
    if isinstance(gt_sub_grp, list):
        gt_sub_grp = gt_sub_grp[0] if (gt_sub_grp and isinstance(gt_sub_grp[0], dict)) else {}
    elif not isinstance(gt_sub_grp, dict):
        gt_sub_grp = {}

    gt_sub_raw = _safe_val(gt_sub_grp.get("subtotal_price"))
    gt_sub_num = parse_amount(gt_sub_raw)
    pred_sub_raw = extracted.subtotal
    pred_sub_num = parse_amount(pred_sub_raw)

    if pred_sub_raw is not None:
        is_correct = compare_amounts(pred_sub_num, gt_sub_num)
        records.append({
            "doc_id": doc_id,
            "split": split,
            "field_path": "subtotal",
            "field_group": "subtotal",
            "pred_raw": str(pred_sub_raw),
            "gt_raw": str(gt_sub_raw) if gt_sub_raw is not None else None,
            "is_error": 0 if is_correct else 1,
        })

    # Tax
    gt_tax_raw = _safe_val(gt_sub_grp.get("tax_price"))
    gt_tax_num = parse_amount(gt_tax_raw)
    pred_tax_raw = extracted.tax
    pred_tax_num = parse_amount(pred_tax_raw)

    if pred_tax_raw is not None:
        is_correct = compare_amounts(pred_tax_num, gt_tax_num)
        records.append({
            "doc_id": doc_id,
            "split": split,
            "field_path": "tax",
            "field_group": "tax",
            "pred_raw": str(pred_tax_raw),
            "gt_raw": str(gt_tax_raw) if gt_tax_raw is not None else None,
            "is_error": 0 if is_correct else 1,
        })

    # Discount
    gt_disc_raw = _safe_val(gt_sub_grp.get("discount_price"))
    gt_disc_num = parse_amount(gt_disc_raw)
    pred_disc_raw = extracted.discount
    pred_disc_num = parse_amount(pred_disc_raw)

    if pred_disc_raw is not None:
        is_correct = compare_amounts(pred_disc_num, gt_disc_num)
        records.append({
            "doc_id": doc_id,
            "split": split,
            "field_path": "discount",
            "field_group": "discount",
            "pred_raw": str(pred_disc_raw),
            "gt_raw": str(gt_disc_raw) if gt_disc_raw is not None else None,
            "is_error": 0 if is_correct else 1,
        })

    # Service Charge
    gt_srv_raw = _safe_val(gt_sub_grp.get("service_price"))
    gt_srv_num = parse_amount(gt_srv_raw)
    pred_srv_raw = extracted.service_charge
    pred_srv_num = parse_amount(pred_srv_raw)

    if pred_srv_raw is not None:
        is_correct = compare_amounts(pred_srv_num, gt_srv_num)
        records.append({
            "doc_id": doc_id,
            "split": split,
            "field_path": "service_charge",
            "field_group": "service_charge",
            "pred_raw": str(pred_srv_raw),
            "gt_raw": str(gt_srv_raw) if gt_srv_raw is not None else None,
            "is_error": 0 if is_correct else 1,
        })

    # 2. Line Items
    gt_menu_raw = gt_dict.get("menu", [])
    if isinstance(gt_menu_raw, dict):
        gt_menu_list = [gt_menu_raw]
    elif isinstance(gt_menu_raw, list):
        gt_menu_list = gt_menu_raw
    else:
        gt_menu_list = []

    matches = match_line_items(extracted.line_items, gt_menu_list)

    for p_idx, g_idx, sim in matches:
        if p_idx is None:
            # GT item not predicted (recall miss), not an extraction row to verify
            continue

        pred_item = extracted.line_items[p_idx]
        if g_idx is None:
            # Hallucinated line item: all its non-null fields are marked as errors
            if pred_item.description:
                records.append({
                    "doc_id": doc_id,
                    "split": split,
                    "field_path": f"line_items[{p_idx}].description",
                    "field_group": "line_item_description",
                    "pred_raw": pred_item.description,
                    "gt_raw": None,
                    "is_error": 1,
                })
            if pred_item.line_total:
                records.append({
                    "doc_id": doc_id,
                    "split": split,
                    "field_path": f"line_items[{p_idx}].line_total",
                    "field_group": "line_item_total",
                    "pred_raw": pred_item.line_total,
                    "gt_raw": None,
                    "is_error": 1,
                })
            if pred_item.unit_price:
                records.append({
                    "doc_id": doc_id,
                    "split": split,
                    "field_path": f"line_items[{p_idx}].unit_price",
                    "field_group": "line_item_unit_price",
                    "pred_raw": pred_item.unit_price,
                    "gt_raw": None,
                    "is_error": 1,
                })
            if pred_item.quantity:
                records.append({
                    "doc_id": doc_id,
                    "split": split,
                    "field_path": f"line_items[{p_idx}].quantity",
                    "field_group": "line_item_qty",
                    "pred_raw": pred_item.quantity,
                    "gt_raw": None,
                    "is_error": 1,
                })
        else:
            # Matched line item: compare each attribute
            gt_item = gt_menu_list[g_idx]

            # Description
            if pred_item.description:
                gt_desc = gt_item.get("nm") or gt_item.get("description")
                desc_match = compare_strings(pred_item.description, gt_desc, threshold=70.0)
                records.append({
                    "doc_id": doc_id,
                    "split": split,
                    "field_path": f"line_items[{p_idx}].description",
                    "field_group": "line_item_description",
                    "pred_raw": pred_item.description,
                    "gt_raw": str(gt_desc) if gt_desc is not None else None,
                    "is_error": 0 if desc_match else 1,
                })

            # Line Total
            if pred_item.line_total:
                gt_lt_raw = gt_item.get("price")
                gt_lt_num = parse_amount(gt_lt_raw)
                pred_lt_num = parse_amount(pred_item.line_total)
                lt_match = compare_amounts(pred_lt_num, gt_lt_num)
                records.append({
                    "doc_id": doc_id,
                    "split": split,
                    "field_path": f"line_items[{p_idx}].line_total",
                    "field_group": "line_item_total",
                    "pred_raw": pred_item.line_total,
                    "gt_raw": str(gt_lt_raw) if gt_lt_raw is not None else None,
                    "is_error": 0 if lt_match else 1,
                })

            # Unit Price
            if pred_item.unit_price:
                gt_up_raw = gt_item.get("unitprice")
                gt_up_num = parse_amount(gt_up_raw)
                pred_up_num = parse_amount(pred_item.unit_price)
                up_match = compare_amounts(pred_up_num, gt_up_num)
                records.append({
                    "doc_id": doc_id,
                    "split": split,
                    "field_path": f"line_items[{p_idx}].unit_price",
                    "field_group": "line_item_unit_price",
                    "pred_raw": pred_item.unit_price,
                    "gt_raw": str(gt_up_raw) if gt_up_raw is not None else None,
                    "is_error": 0 if up_match else 1,
                })

            # Quantity
            if pred_item.quantity:
                gt_cnt_raw = str(gt_item.get("cnt", "1"))
                pred_cnt_num = parse_amount(pred_item.quantity)
                gt_cnt_num = parse_amount(gt_cnt_raw)
                cnt_match = compare_amounts(pred_cnt_num, gt_cnt_num)
                records.append({
                    "doc_id": doc_id,
                    "split": split,
                    "field_path": f"line_items[{p_idx}].quantity",
                    "field_group": "line_item_qty",
                    "pred_raw": pred_item.quantity,
                    "gt_raw": gt_cnt_raw,
                    "is_error": 0 if cnt_match else 1,
                })

    return records
