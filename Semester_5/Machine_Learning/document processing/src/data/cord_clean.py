"""
CORD Dataset Cleaning, Normalization, Deduplication, and Auditing Module.

Implements Task T1:
- Normalizes raw CORD gt_parse JSON (menu dict/list normalization, modifier flattening, void items exclusion).
- High-precision amount parsing (parse_amount) supporting Indonesian / European formats.
- Perceptual hash (pHash) and SHA256 deduplication to identify exact and cross-split near-duplicates.
- Leakage control: drops cross-split duplicates from train.
- Outlier analysis (IQR, p99.5) and missing value rates across all fields.
- Exports:
    - data/processed/cord_docs.parquet (document-level)
    - data/processed/cord_gt.parquet (long-format ground truth)
    - reports/data_audit.json (rigorous audit report)
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


# =====================================================================
# 1. String Sanitization and Amount Parsing
# =====================================================================

def clean_string(s: Optional[str]) -> Optional[str]:
    """
    Sanitize and clean text strings:
    - Strips leading and trailing whitespace
    - Normalizes Unicode to NFKC
    - Collapses consecutive whitespace characters into a single space
    - Returns None if the string is empty or None
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if s else None


def parse_amount(
    s: Optional[str],
    locale_hint: str = "id_ID",
    currency_decimals: int = 0
) -> Optional[Decimal]:
    """
    Parse a numeric/currency amount string into a Decimal.
    
    Adheres strictly to implementation.md §4.2:
    - Currency prefixes/suffixes ('Rp', 'RP', 'IDR', '$', etc.) are stripped.
    - Quantity markers ('x2', '2x', '@15.000') are stripped.
    - Parenthesized and trailing accounting negatives ('(10.000)', '-10.000', '10.000-', '10.000 CR') are handled.
    - Rule for '.' and ',':
      - If the last separator is followed by exactly 3 digits and there is no other
        separator, treat it as a thousands separator (IDR style: 16.500 -> 16500).
      - If followed by 1-2 digits, treat it as a decimal separator (16.50 -> 16.50).
      - If both '.' and ',' are present, disambiguate based on position and digit counts.
      - Multiple identical separators (e.g. 1.250.000 or 1,250,000) are thousands separators.
    - If currency_decimals == 0 and fractional part is 0, converts to integer Decimal.
    - Returns None for non-numeric/unparseable values ('FREE', 'N/A', '', None).
    """
    cleaned = clean_string(s)
    if not cleaned:
        return None

    # Check for obvious non-numeric placeholders
    lower = cleaned.lower()
    if lower in {"free", "n/a", "na", "null", "none", "-", "--", "nil", "zero"}:
        return None

    # Check for negative signs
    is_negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        is_negative = True
        cleaned = cleaned[1:-1].strip()
    elif cleaned.startswith("-") or cleaned.startswith("+"):
        if cleaned.startswith("-"):
            is_negative = True
        cleaned = cleaned[1:].strip()
    # Indonesian trailing ',-' or '.-' shorthand (must be checked before trailing '-')
    if cleaned.endswith(",-") or cleaned.endswith(".-"):
        cleaned = cleaned[:-2].strip()
    elif cleaned.endswith("-"):
        is_negative = True
        cleaned = cleaned[:-1].strip()
    elif re.search(r"\b(cr|dr)\b", cleaned, re.IGNORECASE):
        if re.search(r"\bcr\b", cleaned, re.IGNORECASE):
            is_negative = True
        cleaned = re.sub(r"\b(cr|dr)\b", "", cleaned, flags=re.IGNORECASE).strip()

    # Remove currency symbols and abbreviations
    cleaned = re.sub(r"(?i)\b(rp|idr|usd|eur|gbp|jpy|sgd)\b[\.\s]*", "", cleaned)
    cleaned = re.sub(r"[$€£¥RpRP\.]\s*", lambda m: "" if m.group(0) in "$€£¥" else m.group(0), cleaned)
    cleaned = re.sub(r"^(?:rp|idr)[\.\s]*", "", cleaned, flags=re.IGNORECASE)

    # Remove quantity prefixes like 'x2', '@15.000', or trailing 'x'
    cleaned = re.sub(r"^[@xX]\s*", "", cleaned)
    cleaned = re.sub(r"\s*[xX]$", "", cleaned)
    cleaned = re.sub(r"(?i)\b(pcs|pc|item|items|qty)\b", "", cleaned)
    cleaned = cleaned.strip()

    if not cleaned:
        return None

    # Check if there are any digits
    if not re.search(r"\d", cleaned):
        return None

    # Remove internal spaces around separators, e.g. "16 . 500" -> "16.500"
    cleaned = re.sub(r"\s*([.,])\s*", r"\1", cleaned)

    # Count separators
    dot_count = cleaned.count(".")
    comma_count = cleaned.count(",")

    # Case 1: Both dot and comma present
    if dot_count > 0 and comma_count > 0:
        last_dot = cleaned.rfind(".")
        last_comma = cleaned.rfind(",")
        if last_dot > last_comma:
            # Comma is thousands separator, dot is decimal separator (e.g. 1,250.50)
            cleaned = cleaned.replace(",", "")
        else:
            # Dot is thousands separator, comma is decimal separator (e.g. 1.250,50)
            cleaned = cleaned.replace(".", "").replace(",", ".")
    # Case 2: Only dots present
    elif dot_count > 0:
        if dot_count > 1:
            # Multiple dots -> thousands separators (e.g. 1.250.000)
            cleaned = cleaned.replace(".", "")
        else:
            parts = cleaned.split(".")
            after_dot = parts[1]
            if len(after_dot) == 3:
                # 3 digits after dot -> thousands separator in IDR (e.g. 16.500 -> 16500)
                if currency_decimals == 3:
                    cleaned = parts[0] + "." + parts[1]
                else:
                    cleaned = parts[0] + parts[1]
            else:
                # 1, 2, or >=4 digits after dot -> decimal separator (e.g. 16.50 or 1.5)
                cleaned = parts[0] + "." + parts[1]
    # Case 3: Only commas present
    elif comma_count > 0:
        if comma_count > 1:
            # Multiple commas -> thousands separators (e.g. 1,250,000)
            cleaned = cleaned.replace(",", "")
        else:
            parts = cleaned.split(",")
            after_comma = parts[1]
            if len(after_comma) == 3:
                # 3 digits after comma -> thousands separator (e.g. 1,500 -> 1500)
                if currency_decimals == 3:
                    cleaned = parts[0] + "." + parts[1]
                else:
                    cleaned = parts[0] + parts[1]
            else:
                # 1, 2, or >=4 digits after comma -> decimal separator (e.g. 16,50 -> 16.50)
                cleaned = parts[0] + "." + parts[1]

    # Clean non-digit / non-decimal chars
    cleaned = re.sub(r"[^\d.]", "", cleaned)
    if not cleaned or cleaned == ".":
        return None

    try:
        val = Decimal(cleaned)
        if is_negative:
            val = -val

        if currency_decimals == 0:
            if val == val.to_integral_value():
                return val.to_integral_value()
        return val
    except (InvalidOperation, ValueError):
        return None


# =====================================================================
# 2. GT Parse Flattening & Normalization
# =====================================================================

def extract_modifiers(item: Dict[str, Any]) -> List[str]:
    """
    Extract modifier / sub-item strings from CORD menu item dict.
    Flattens 'sub', 'sub_nm', and nested structures into a clean List[str].
    """
    modifiers: List[str] = []

    # Check 'sub' key
    sub_val = item.get("sub")
    if isinstance(sub_val, list):
        for sub_item in sub_val:
            if isinstance(sub_item, dict):
                nm = sub_item.get("nm") or sub_item.get("sub_nm")
                cleaned = clean_string(nm)
                if cleaned:
                    modifiers.append(cleaned)
            elif isinstance(sub_item, str):
                cleaned = clean_string(sub_item)
                if cleaned:
                    modifiers.append(cleaned)
    elif isinstance(sub_val, dict):
        nm = sub_val.get("nm") or sub_val.get("sub_nm")
        cleaned = clean_string(nm)
        if cleaned:
            modifiers.append(cleaned)
    elif isinstance(sub_val, str):
        cleaned = clean_string(sub_val)
        if cleaned:
            modifiers.append(cleaned)

    # Check 'sub_nm' key directly on item
    sub_nm = item.get("sub_nm")
    if isinstance(sub_nm, list):
        for s in sub_nm:
            cleaned = clean_string(s)
            if cleaned and cleaned not in modifiers:
                modifiers.append(cleaned)
    elif isinstance(sub_nm, str):
        cleaned = clean_string(sub_nm)
        if cleaned and cleaned not in modifiers:
            modifiers.append(cleaned)

    return modifiers


def normalize_menu_items(menu_data: Any) -> List[Dict[str, Any]]:
    """
    Normalize CORD menu data:
    - If menu is a dict, wrap in a list.
    - If list, keep as list.
    - If None/other, return empty list.
    """
    if not menu_data:
        return []
    if isinstance(menu_data, dict):
        return [menu_data]
    if isinstance(menu_data, list):
        return [m for m in menu_data if isinstance(m, dict)]
    return []


@dataclass
class CleanedLineItem:
    item_idx: int
    description: Optional[str]
    quantity_raw: Optional[str]
    quantity_numeric: Optional[Decimal]
    unit_price_raw: Optional[str]
    unit_price_numeric: Optional[Decimal]
    line_total_raw: Optional[str]
    line_total_numeric: Optional[Decimal]
    modifiers: List[str]
    is_void: bool = False


@dataclass
class CleanedReceipt:
    doc_id: str
    split: str
    image_path: str
    image_sha256: str
    image_phash: str
    has_menu: bool
    n_items: int
    subtotal_price_raw: Optional[str]
    subtotal_price_numeric: Optional[Decimal]
    discount_price_raw: Optional[str]
    discount_price_numeric: Optional[Decimal]
    service_price_raw: Optional[str]
    service_price_numeric: Optional[Decimal]
    tax_price_raw: Optional[str]
    tax_price_numeric: Optional[Decimal]
    total_price_raw: Optional[str]
    total_price_numeric: Optional[Decimal]
    cash_price_raw: Optional[str]
    cash_price_numeric: Optional[Decimal]
    change_price_raw: Optional[str]
    change_price_numeric: Optional[Decimal]
    credit_card_price_raw: Optional[str]
    credit_card_price_numeric: Optional[Decimal]
    emoney_price_raw: Optional[str]
    emoney_price_numeric: Optional[Decimal]
    line_items: List[CleanedLineItem] = field(default_factory=list)
    void_items: List[CleanedLineItem] = field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None


def parse_cord_gt_dict(
    doc_id: str,
    split: str,
    gt_parse: Dict[str, Any],
    image_path: str = "",
    image_sha256: str = "",
    image_phash: str = ""
) -> CleanedReceipt:
    """
    Parse and clean a CORD gt_parse dictionary into a structured CleanedReceipt.
    """
    # 1. Menu items
    raw_menu = gt_parse.get("menu")
    menu_list = normalize_menu_items(raw_menu)
    cleaned_items: List[CleanedLineItem] = []

    for idx, item in enumerate(menu_list):
        nm = clean_string(item.get("nm"))
        cnt_raw = clean_string(item.get("cnt"))
        unitprice_raw = clean_string(item.get("unitprice"))
        price_raw = clean_string(item.get("price"))

        cnt_num = parse_amount(cnt_raw, currency_decimals=0) if cnt_raw else Decimal("1")
        unitprice_num = parse_amount(unitprice_raw) if unitprice_raw else None
        price_num = parse_amount(price_raw) if price_raw else None
        mods = extract_modifiers(item)

        cleaned_items.append(
            CleanedLineItem(
                item_idx=idx,
                description=nm,
                quantity_raw=cnt_raw,
                quantity_numeric=cnt_num,
                unit_price_raw=unitprice_raw,
                unit_price_numeric=unitprice_num,
                line_total_raw=price_raw,
                line_total_numeric=price_num,
                modifiers=mods,
                is_void=False,
            )
        )

    # 2. Void menu items (excluded from valid line items)
    raw_void = gt_parse.get("void_menu")
    void_list = normalize_menu_items(raw_void)
    cleaned_void: List[CleanedLineItem] = []

    for idx, item in enumerate(void_list):
        nm = clean_string(item.get("nm"))
        cnt_raw = clean_string(item.get("cnt"))
        unitprice_raw = clean_string(item.get("unitprice"))
        price_raw = clean_string(item.get("price"))

        cnt_num = parse_amount(cnt_raw, currency_decimals=0) if cnt_raw else None
        unitprice_num = parse_amount(unitprice_raw) if unitprice_raw else None
        price_num = parse_amount(price_raw) if price_raw else None
        mods = extract_modifiers(item)

        cleaned_void.append(
            CleanedLineItem(
                item_idx=idx,
                description=nm,
                quantity_raw=cnt_raw,
                quantity_numeric=cnt_num,
                unit_price_raw=unitprice_raw,
                unit_price_numeric=unitprice_num,
                line_total_raw=price_raw,
                line_total_numeric=price_num,
                modifiers=mods,
                is_void=True,
            )
        )

    # 3. Subtotal fields
    sub_total = gt_parse.get("sub_total", {})
    if not isinstance(sub_total, dict):
        sub_total = {}

    subtotal_raw = clean_string(sub_total.get("subtotal_price"))
    discount_raw = clean_string(sub_total.get("discount_price"))
    service_raw = clean_string(sub_total.get("service_price"))
    tax_raw = clean_string(sub_total.get("tax_price"))

    subtotal_num = parse_amount(subtotal_raw) if subtotal_raw else None
    discount_num = parse_amount(discount_raw) if discount_raw else None
    if discount_num is not None and discount_num < 0:
        discount_num = abs(discount_num)

    service_num = parse_amount(service_raw) if service_raw else None
    tax_num = parse_amount(tax_raw) if tax_raw else None

    # 4. Total fields
    total_dict = gt_parse.get("total", {})
    if not isinstance(total_dict, dict):
        total_dict = {}

    total_raw = clean_string(total_dict.get("total_price"))
    cash_raw = clean_string(total_dict.get("cashprice"))
    change_raw = clean_string(total_dict.get("changeprice"))
    credit_raw = clean_string(total_dict.get("creditcardprice"))
    emoney_raw = clean_string(total_dict.get("emoneyprice"))

    total_num = parse_amount(total_raw) if total_raw else None
    cash_num = parse_amount(cash_raw) if cash_raw else None
    change_num = parse_amount(change_raw) if change_raw else None
    credit_num = parse_amount(credit_raw) if credit_raw else None
    emoney_num = parse_amount(emoney_raw) if emoney_raw else None

    has_menu = len(cleaned_items) > 0

    return CleanedReceipt(
        doc_id=doc_id,
        split=split,
        image_path=image_path,
        image_sha256=image_sha256,
        image_phash=image_phash,
        has_menu=has_menu,
        n_items=len(cleaned_items),
        subtotal_price_raw=subtotal_raw,
        subtotal_price_numeric=subtotal_num,
        discount_price_raw=discount_raw,
        discount_price_numeric=discount_num,
        service_price_raw=service_raw,
        service_price_numeric=service_num,
        tax_price_raw=tax_raw,
        tax_price_numeric=tax_num,
        total_price_raw=total_raw,
        total_price_numeric=total_num,
        cash_price_raw=cash_raw,
        change_price_raw=change_raw,
        credit_card_price_raw=credit_raw,
        emoney_price_raw=emoney_raw,
        cash_price_numeric=cash_num,
        change_price_numeric=change_num,
        credit_card_price_numeric=credit_num,
        emoney_price_numeric=emoney_num,
        line_items=cleaned_items,
        void_items=cleaned_void,
    )


# =====================================================================
# 3. Perceptual Hashing & Cross-Split Deduplication
# =====================================================================

def hamming_distance(hex1: str, hex2: str) -> int:
    """Calculate Hamming distance between two hex hash strings."""
    if not hex1 or not hex2:
        return 999
    try:
        val1 = int(hex1, 16)
        val2 = int(hex2, 16)
        return bin(val1 ^ val2).count("1")
    except ValueError:
        return 999


def detect_duplicates(
    receipts: List[CleanedReceipt],
    phash_threshold: int = 2
) -> Tuple[List[CleanedReceipt], Dict[str, Any]]:
    """
    Detect exact SHA256 and near-duplicate pHash receipts across splits and within splits.
    
    Leakage control:
    If a receipt in 'train' duplicates any receipt in 'val' or 'test',
    it is dropped from train!
    
    Returns:
        clean_receipts: filtered receipts with cross-split duplicates removed from train
        audit_duplicates: metadata dictionary recording all duplicate stats and pairs
    """
    sha_map: Dict[str, List[CleanedReceipt]] = {}
    for r in receipts:
        if r.image_sha256:
            sha_map.setdefault(r.image_sha256, []).append(r)

    duplicate_pairs: List[Dict[str, Any]] = []
    dropped_train_ids: List[str] = []
    exact_duplicates_count = 0
    near_duplicates_count = 0
    cross_split_duplicates_count = 0

    # 1. Exact duplicates by SHA256
    for sha, group in sha_map.items():
        if len(group) > 1:
            exact_duplicates_count += len(group) - 1
            primary = group[0]
            for secondary in group[1:]:
                secondary.is_duplicate = True
                secondary.duplicate_of = primary.doc_id
                is_cross_split = primary.split != secondary.split
                if is_cross_split:
                    cross_split_duplicates_count += 1
                duplicate_pairs.append({
                    "doc_a": primary.doc_id,
                    "split_a": primary.split,
                    "doc_b": secondary.doc_id,
                    "split_b": secondary.split,
                    "match_type": "exact_sha256",
                    "hash_dist": 0,
                    "cross_split": is_cross_split,
                })
                # Drop from train if cross-split
                if secondary.split == "train" and primary.split in ("val", "test", "validation"):
                    dropped_train_ids.append(secondary.doc_id)
                elif primary.split == "train" and secondary.split in ("val", "test", "validation"):
                    dropped_train_ids.append(primary.doc_id)

    # 2. Near duplicates by pHash Hamming distance
    n = len(receipts)
    for i in range(n):
        r1 = receipts[i]
        if not r1.image_phash:
            continue
        for j in range(i + 1, n):
            r2 = receipts[j]
            if not r2.image_phash:
                continue
            if r1.image_sha256 and r1.image_sha256 == r2.image_sha256:
                # Already captured by exact match
                continue

            dist = hamming_distance(r1.image_phash, r2.image_phash)
            if dist <= phash_threshold:
                near_duplicates_count += 1
                is_cross_split = r1.split != r2.split
                if is_cross_split:
                    cross_split_duplicates_count += 1
                duplicate_pairs.append({
                    "doc_a": r1.doc_id,
                    "split_a": r1.split,
                    "doc_b": r2.doc_id,
                    "split_b": r2.split,
                    "match_type": "near_phash",
                    "hash_dist": dist,
                    "cross_split": is_cross_split,
                })
                # Drop from train if cross-split
                if r2.split == "train" and r1.split in ("val", "test", "validation"):
                    dropped_train_ids.append(r2.doc_id)
                    r2.is_duplicate = True
                    r2.duplicate_of = r1.doc_id
                elif r1.split == "train" and r2.split in ("val", "test", "validation"):
                    dropped_train_ids.append(r1.doc_id)
                    r1.is_duplicate = True
                    r1.duplicate_of = r2.doc_id

    dropped_set = set(dropped_train_ids)
    cleaned_receipts = [r for r in receipts if r.doc_id not in dropped_set]

    audit_duplicates = {
        "exact_duplicates_count": exact_duplicates_count,
        "near_duplicates_count": near_duplicates_count,
        "cross_split_duplicates_count": cross_split_duplicates_count,
        "dropped_from_train_count": len(dropped_set),
        "dropped_from_train_ids": sorted(list(dropped_set)),
        "duplicate_pairs": duplicate_pairs,
    }
    return cleaned_receipts, audit_duplicates


# =====================================================================
# 4. Outlier Analysis & Missing Value Statistics
# =====================================================================

def calculate_outlier_stats(values: List[float], field_name: str) -> Dict[str, Any]:
    """
    Compute rigorous IQR and p99.5 outlier statistics for a list of numeric values.
    """
    if not values:
        return {
            "field": field_name,
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std": None,
            "q1_p25": None,
            "q3_p75": None,
            "iqr": None,
            "lower_bound": None,
            "upper_bound": None,
            "p99_5": None,
            "outlier_count_iqr": 0,
            "outlier_count_p99_5": 0,
        }

    arr = np.array(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return {"field": field_name, "count": 0}

    q1 = float(np.percentile(arr, 25))
    q3 = float(np.percentile(arr, 75))
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    p99_5 = float(np.percentile(arr, 99.5))

    outliers_iqr = int(np.sum((arr < lower_bound) | (arr > upper_bound)))
    outliers_p99_5 = int(np.sum(arr > p99_5))

    return {
        "field": field_name,
        "count": len(arr),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "std": float(np.std(arr)),
        "q1_p25": q1,
        "q3_p75": q3,
        "iqr": iqr,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "p99_5": p99_5,
        "outlier_count_iqr": outliers_iqr,
        "outlier_count_p99_5": outliers_p99_5,
    }


def compute_audit_report(
    receipts_before: List[CleanedReceipt],
    receipts_after: List[CleanedReceipt],
    duplicates_meta: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate comprehensive data_audit.json data structure.
    """
    splits_before = {"train": 0, "val": 0, "test": 0, "total": len(receipts_before)}
    for r in receipts_before:
        s = "val" if r.split in ("val", "validation") else r.split
        splits_before[s] = splits_before.get(s, 0) + 1

    splits_after = {"train": 0, "val": 0, "test": 0, "total": len(receipts_after)}
    for r in receipts_after:
        s = "val" if r.split in ("val", "validation") else r.split
        splits_after[s] = splits_after.get(s, 0) + 1

    # Missing rates across documents
    total_docs = len(receipts_after)
    field_counts: Dict[str, int] = {
        "subtotal_price": 0,
        "discount_price": 0,
        "service_price": 0,
        "tax_price": 0,
        "total_price": 0,
        "cash_price": 0,
        "change_price": 0,
        "credit_card_price": 0,
        "emoney_price": 0,
    }
    for r in receipts_after:
        if r.subtotal_price_numeric is not None:
            field_counts["subtotal_price"] += 1
        if r.discount_price_numeric is not None:
            field_counts["discount_price"] += 1
        if r.service_price_numeric is not None:
            field_counts["service_price"] += 1
        if r.tax_price_numeric is not None:
            field_counts["tax_price"] += 1
        if r.total_price_numeric is not None:
            field_counts["total_price"] += 1
        if r.cash_price_numeric is not None:
            field_counts["cash_price"] += 1
        if r.change_price_numeric is not None:
            field_counts["change_price"] += 1
        if r.credit_card_price_numeric is not None:
            field_counts["credit_card_price"] += 1
        if r.emoney_price_numeric is not None:
            field_counts["emoney_price"] += 1

    missing_rates_doc = {}
    for f_name, present in field_counts.items():
        missing_count = total_docs - present
        missing_rates_doc[f_name] = {
            "present_count": present,
            "missing_count": missing_count,
            "total_documents": total_docs,
            "missing_rate_pct": round((missing_count / total_docs * 100), 2) if total_docs > 0 else 0.0,
        }

    # Missing rates across line items
    all_items = [it for r in receipts_after for it in r.line_items]
    total_items = len(all_items)
    item_field_counts = {
        "description": sum(1 for it in all_items if it.description is not None),
        "quantity": sum(1 for it in all_items if it.quantity_numeric is not None),
        "unit_price": sum(1 for it in all_items if it.unit_price_numeric is not None),
        "line_total": sum(1 for it in all_items if it.line_total_numeric is not None),
        "modifiers": sum(1 for it in all_items if len(it.modifiers) > 0),
    }
    missing_rates_items = {}
    for f_name, present in item_field_counts.items():
        missing_count = total_items - present
        missing_rates_items[f_name] = {
            "present_count": present,
            "missing_count": missing_count,
            "total_items": total_items,
            "missing_rate_pct": round((missing_count / total_items * 100), 2) if total_items > 0 else 0.0,
        }

    # Outlier Analysis
    price_totals = [float(r.total_price_numeric) for r in receipts_after if r.total_price_numeric is not None]
    price_subtotals = [float(r.subtotal_price_numeric) for r in receipts_after if r.subtotal_price_numeric is not None]
    price_line_totals = [float(it.line_total_numeric) for it in all_items if it.line_total_numeric is not None]
    price_unit_prices = [float(it.unit_price_numeric) for it in all_items if it.unit_price_numeric is not None]
    quantities = [float(it.quantity_numeric) for it in all_items if it.quantity_numeric is not None]

    outliers = {
        "total_price": calculate_outlier_stats(price_totals, "total_price"),
        "subtotal_price": calculate_outlier_stats(price_subtotals, "subtotal_price"),
        "line_total": calculate_outlier_stats(price_line_totals, "line_total"),
        "unit_price": calculate_outlier_stats(price_unit_prices, "unit_price"),
        "quantity": calculate_outlier_stats(quantities, "quantity"),
    }

    # Flag specific outliers (qty > 50 or price > p99.5)
    flagged_outliers = []
    p99_line_total = outliers["line_total"]["p99_5"] or 1e9
    for r in receipts_after:
        for it in r.line_items:
            q = float(it.quantity_numeric) if it.quantity_numeric is not None else 0.0
            p = float(it.line_total_numeric) if it.line_total_numeric is not None else 0.0
            if q > 50 or p > p99_line_total:
                flagged_outliers.append({
                    "doc_id": r.doc_id,
                    "split": r.split,
                    "item_idx": it.item_idx,
                    "description": it.description,
                    "quantity": q,
                    "line_total": p,
                    "reason": "quantity > 50" if q > 50 else f"line_total > p99.5 ({p99_line_total:.2f})",
                })

    # Line item statistics per receipt
    item_counts = [r.n_items for r in receipts_after]
    n_with_menu = sum(1 for r in receipts_after if r.has_menu)
    total_void_items = sum(len(r.void_items) for r in receipts_after)

    line_item_stats = {
        "total_valid_line_items": total_items,
        "total_void_line_items": total_void_items,
        "receipts_with_menu_count": n_with_menu,
        "receipts_without_menu_count": total_docs - n_with_menu,
        "items_per_receipt": {
            "min": int(np.min(item_counts)) if item_counts else 0,
            "max": int(np.max(item_counts)) if item_counts else 0,
            "mean": float(np.mean(item_counts)) if item_counts else 0.0,
            "median": float(np.median(item_counts)) if item_counts else 0.0,
            "p95": float(np.percentile(item_counts, 95)) if item_counts else 0.0,
        },
    }

    audit_report = {
        "dataset_metadata": {
            "source": "naver-clova-ix/cord-v2",
            "license": "CC-BY-4.0",
            "description": "Consolidated Receipt Dataset (CORD) Indonesian receipts ground truth audit",
        },
        "splits_before_cleaning": splits_before,
        "splits_after_cleaning": splits_after,
        "deduplication": duplicates_meta,
        "missing_value_rates": {
            "document_fields": missing_rates_doc,
            "line_item_fields": missing_rates_items,
        },
        "outlier_analysis": {
            "field_distributions": outliers,
            "flagged_outliers_count": len(flagged_outliers),
            "flagged_outlier_samples": flagged_outliers[:20],
        },
        "line_item_stats": line_item_stats,
    }
    return audit_report


# =====================================================================
# 5. Parquet Dataframe Construction
# =====================================================================

def build_cord_docs_df(receipts: List[CleanedReceipt]) -> pd.DataFrame:
    """
    Construct cord_docs.parquet dataframe (one row per document).
    """
    rows = []
    for r in receipts:
        rows.append({
            "doc_id": r.doc_id,
            "split": r.split,
            "image_path": r.image_path,
            "image_sha256": r.image_sha256,
            "image_phash": r.image_phash,
            "has_menu": r.has_menu,
            "n_items": r.n_items,
            "subtotal_price": float(r.subtotal_price_numeric) if r.subtotal_price_numeric is not None else None,
            "discount_price": float(r.discount_price_numeric) if r.discount_price_numeric is not None else None,
            "service_price": float(r.service_price_numeric) if r.service_price_numeric is not None else None,
            "tax_price": float(r.tax_price_numeric) if r.tax_price_numeric is not None else None,
            "total_price": float(r.total_price_numeric) if r.total_price_numeric is not None else None,
            "cash_price": float(r.cash_price_numeric) if r.cash_price_numeric is not None else None,
            "change_price": float(r.change_price_numeric) if r.change_price_numeric is not None else None,
            "credit_card_price": float(r.credit_card_price_numeric) if r.credit_card_price_numeric is not None else None,
            "emoney_price": float(r.emoney_price_numeric) if r.emoney_price_numeric is not None else None,
            "is_duplicate": r.is_duplicate,
            "duplicate_of": r.duplicate_of,
        })
    df = pd.DataFrame(rows)
    return df


def build_cord_gt_df(receipts: List[CleanedReceipt]) -> pd.DataFrame:
    """
    Construct cord_gt.parquet dataframe (long format: one row per field).
    """
    rows = []
    for r in receipts:
        # Document level fields
        doc_fields = [
            ("sub_total", "subtotal", "subtotal", r.subtotal_price_raw, r.subtotal_price_numeric),
            ("sub_total", "discount", "discount", r.discount_price_raw, r.discount_price_numeric),
            ("sub_total", "service_charge", "service_charge", r.service_price_raw, r.service_price_numeric),
            ("sub_total", "tax", "tax", r.tax_price_raw, r.tax_price_numeric),
            ("total", "total", "total", r.total_price_raw, r.total_price_numeric),
            ("total", "cash_price", "amount_paid", r.cash_price_raw, r.cash_price_numeric),
            ("total", "change", "change", r.change_price_raw, r.change_price_numeric),
            ("total", "credit_card_price", "amount_paid", r.credit_card_price_raw, r.credit_card_price_numeric),
            ("total", "emoney_price", "amount_paid", r.emoney_price_raw, r.emoney_price_numeric),
        ]
        for grp, name, path, raw_v, num_v in doc_fields:
            if raw_v is not None or num_v is not None:
                rows.append({
                    "doc_id": r.doc_id,
                    "split": r.split,
                    "field_group": grp,
                    "field_name": name,
                    "field_path": path,
                    "item_idx": None,
                    "gt_value_raw": raw_v,
                    "gt_value_numeric": float(num_v) if num_v is not None else None,
                    "modifiers": None,
                    "is_void": False,
                })

        # Valid line item fields
        for it in r.line_items:
            prefix = f"line_items[{it.item_idx}]"
            # Description
            if it.description is not None:
                rows.append({
                    "doc_id": r.doc_id,
                    "split": r.split,
                    "field_group": "menu",
                    "field_name": "description",
                    "field_path": f"{prefix}.description",
                    "item_idx": it.item_idx,
                    "gt_value_raw": it.description,
                    "gt_value_numeric": None,
                    "modifiers": it.modifiers if it.modifiers else None,
                    "is_void": False,
                })
            # Quantity
            if it.quantity_raw is not None or it.quantity_numeric is not None:
                rows.append({
                    "doc_id": r.doc_id,
                    "split": r.split,
                    "field_group": "menu",
                    "field_name": "quantity",
                    "field_path": f"{prefix}.quantity",
                    "item_idx": it.item_idx,
                    "gt_value_raw": it.quantity_raw,
                    "gt_value_numeric": float(it.quantity_numeric) if it.quantity_numeric is not None else None,
                    "modifiers": None,
                    "is_void": False,
                })
            # Unit Price
            if it.unit_price_raw is not None or it.unit_price_numeric is not None:
                rows.append({
                    "doc_id": r.doc_id,
                    "split": r.split,
                    "field_group": "menu",
                    "field_name": "unit_price",
                    "field_path": f"{prefix}.unit_price",
                    "item_idx": it.item_idx,
                    "gt_value_raw": it.unit_price_raw,
                    "gt_value_numeric": float(it.unit_price_numeric) if it.unit_price_numeric is not None else None,
                    "modifiers": None,
                    "is_void": False,
                })
            # Line Total
            if it.line_total_raw is not None or it.line_total_numeric is not None:
                rows.append({
                    "doc_id": r.doc_id,
                    "split": r.split,
                    "field_group": "menu",
                    "field_name": "line_total",
                    "field_path": f"{prefix}.line_total",
                    "item_idx": it.item_idx,
                    "gt_value_raw": it.line_total_raw,
                    "gt_value_numeric": float(it.line_total_numeric) if it.line_total_numeric is not None else None,
                    "modifiers": None,
                    "is_void": False,
                })

        # Void items (marked is_void = True)
        for it in r.void_items:
            prefix = f"void_menu[{it.item_idx}]"
            rows.append({
                "doc_id": r.doc_id,
                "split": r.split,
                "field_group": "void_menu",
                "field_name": "description",
                "field_path": f"{prefix}.description",
                "item_idx": it.item_idx,
                "gt_value_raw": it.description,
                "gt_value_numeric": None,
                "modifiers": it.modifiers if it.modifiers else None,
                "is_void": True,
            })
            if it.line_total_raw is not None or it.line_total_numeric is not None:
                rows.append({
                    "doc_id": r.doc_id,
                    "split": r.split,
                    "field_group": "void_menu",
                    "field_name": "line_total",
                    "field_path": f"{prefix}.line_total",
                    "item_idx": it.item_idx,
                    "gt_value_raw": it.line_total_raw,
                    "gt_value_numeric": float(it.line_total_numeric) if it.line_total_numeric is not None else None,
                    "modifiers": None,
                    "is_void": True,
                })

    df = pd.DataFrame(rows)
    return df


def save_processed_cord(
    receipts_before: List[CleanedReceipt],
    processed_dir: Union[str, Path] = "data/processed",
    reports_dir: Union[str, Path] = "reports",
    phash_threshold: int = 2
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Execute full cleaning, deduplication, auditing, and Parquet saving pipeline.
    """
    proc_path = Path(processed_dir)
    rep_path = Path(reports_dir)
    proc_path.mkdir(parents=True, exist_ok=True)
    rep_path.mkdir(parents=True, exist_ok=True)

    # 1. Deduplication & leakage control
    receipts_clean, duplicates_meta = detect_duplicates(receipts_before, phash_threshold=phash_threshold)

    # 2. Build DataFrames
    df_docs = build_cord_docs_df(receipts_clean)
    df_gt = build_cord_gt_df(receipts_clean)

    # 3. Save Parquet datasets
    docs_parquet_path = proc_path / "cord_docs.parquet"
    gt_parquet_path = proc_path / "cord_gt.parquet"

    df_docs.to_parquet(docs_parquet_path, index=False, engine="pyarrow")
    df_gt.to_parquet(gt_parquet_path, index=False, engine="pyarrow")

    # 4. Generate and save audit report
    audit_data = compute_audit_report(receipts_before, receipts_clean, duplicates_meta)
    audit_path = rep_path / "data_audit.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2)

    logger.info("Successfully saved %s (%d rows)", docs_parquet_path, len(df_docs))
    logger.info("Successfully saved %s (%d rows)", gt_parquet_path, len(df_gt))
    logger.info("Successfully saved audit report to %s", audit_path)

    return df_docs, df_gt, audit_data
