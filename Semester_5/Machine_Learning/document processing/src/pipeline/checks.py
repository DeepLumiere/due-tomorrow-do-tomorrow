"""
Pure arithmetic consistency check functions for receipt/invoice extraction.
These produce signals for feature engineering (Field Verifier) and validation.
No values are overwritten or guessed; only signals and discrepancies are reported.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple

from src.schema.invoice import NormalizedLineItem


def check_line_items_sum(
    subtotal: Optional[Decimal],
    items: List[NormalizedLineItem],
) -> Tuple[bool, float]:
    """
    Compare subtotal against the sum of line item line_totals.

    Args:
        subtotal: Extracted and normalized subtotal.
        items: List of normalized line items.

    Returns:
        Tuple of:
        - is_consistent (bool): True if sum(line_total) matches subtotal within 0.01 tolerance.
        - relative_diff (float): Discrepancy ratio abs(sum - subtotal) / denom. 0.0 if consistent.
    """
    if subtotal is None:
        return False, 1.0

    if not items:
        # If no items and subtotal is 0, consider consistent
        if subtotal == Decimal(0):
            return True, 0.0
        return False, 1.0

    valid_totals = [it.line_total for it in items if it.line_total is not None]
    if not valid_totals:
        return False, 1.0

    items_sum = sum(valid_totals)
    diff = abs(items_sum - subtotal)
    denom = max(abs(subtotal), abs(items_sum), Decimal("0.01"))
    rel_diff = float(diff / denom)

    # Within 0.01 tolerance (handles rounding differences)
    is_consistent = (diff <= Decimal("0.01"))
    if is_consistent:
        rel_diff = 0.0

    return is_consistent, rel_diff


def check_grand_total(
    total: Optional[Decimal],
    subtotal: Optional[Decimal],
    tax: Optional[Decimal] = None,
    discount: Optional[Decimal] = None,
    service: Optional[Decimal] = None,
) -> Tuple[bool, float]:
    """
    Check arithmetic equation:
    total == subtotal + tax + service - discount

    Args:
        total: Extracted grand total.
        subtotal: Extracted subtotal.
        tax: Tax amount (PB1, VAT, etc.). Defaults to 0 if None.
        discount: Discount amount. Defaults to 0 if None. Handled as deduction.
        service: Service charge. Defaults to 0 if None.

    Returns:
        Tuple of:
        - is_consistent (bool): True if equation holds within 0.01 tolerance.
        - relative_diff (float): Discrepancy ratio abs(total - expected) / denom. 0.0 if consistent.
    """
    if total is None or subtotal is None:
        return False, 1.0

    t = tax if tax is not None else Decimal(0)
    s = service if service is not None else Decimal(0)
    # Discounts are deductions; if provided as negative in extraction, take abs
    d = abs(discount) if discount is not None else Decimal(0)

    expected_total = subtotal + t + s - d
    diff = abs(total - expected_total)
    denom = max(abs(total), abs(expected_total), Decimal("0.01"))
    rel_diff = float(diff / denom)

    is_consistent = (diff <= Decimal("0.01"))
    if is_consistent:
        rel_diff = 0.0

    return is_consistent, rel_diff


def check_item_multiplication(
    qty: Optional[Decimal],
    unit_price: Optional[Decimal],
    line_total: Optional[Decimal],
) -> Tuple[bool, float]:
    """
    Check line item multiplication:
    qty * unit_price == line_total

    Args:
        qty: Extracted item quantity.
        unit_price: Extracted unit price.
        line_total: Extracted line total.

    Returns:
        Tuple of:
        - is_consistent (bool): True if product matches line_total within 0.01 tolerance.
        - relative_diff (float): Discrepancy ratio abs(line_total - expected) / denom. 0.0 if consistent.
    """
    if qty is None or unit_price is None or line_total is None:
        return False, 1.0

    expected_line_total = qty * unit_price
    diff = abs(line_total - expected_line_total)
    denom = max(abs(line_total), abs(expected_line_total), Decimal("0.01"))
    rel_diff = float(diff / denom)

    is_consistent = (diff <= Decimal("0.01"))
    if is_consistent:
        rel_diff = 0.0

    return is_consistent, rel_diff
