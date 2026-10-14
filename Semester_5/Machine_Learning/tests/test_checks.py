"""
Unit tests for src/pipeline/checks.py:
- check_line_items_sum: line items vs subtotal consistency and relative discrepancy.
- check_grand_total: total == subtotal + tax + service - discount with positive/negative discounts.
- check_item_multiplication: qty * unit_price == line_total.
"""
import sys
from decimal import Decimal
from pathlib import Path
import pytest

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.pipeline.checks import (
    check_grand_total,
    check_item_multiplication,
    check_line_items_sum,
)

from src.schema.invoice import NormalizedLineItem


class TestCheckLineItemsSum:
    def test_exact_match(self):
        items = [
            NormalizedLineItem(item_idx=0, description="Item A", quantity=Decimal("2"), unit_price=Decimal("18000"), line_total=Decimal("36000")),
            NormalizedLineItem(item_idx=1, description="Item B", quantity=Decimal("1"), unit_price=Decimal("12000"), line_total=Decimal("12000")),
        ]
        is_consistent, rel_diff = check_line_items_sum(Decimal("48000"), items)
        assert is_consistent is True
        assert rel_diff == 0.0

    def test_discrepancy(self):
        items = [
            NormalizedLineItem(item_idx=0, description="Item A", line_total=Decimal("30000")),
        ]
        is_consistent, rel_diff = check_line_items_sum(Decimal("50000"), items)
        assert is_consistent is False
        assert rel_diff == pytest.approx(0.4)

    def test_tolerance_within_cent(self):
        # 1 cent rounding difference is accepted as consistent
        items = [
            NormalizedLineItem(item_idx=0, line_total=Decimal("49.99")),
        ]
        is_consistent, rel_diff = check_line_items_sum(Decimal("50.00"), items)
        assert is_consistent is True
        assert rel_diff == 0.0

    def test_missing_subtotal(self):
        items = [NormalizedLineItem(item_idx=0, line_total=Decimal("1000"))]
        is_consistent, rel_diff = check_line_items_sum(None, items)
        assert is_consistent is False
        assert rel_diff == 1.0

    def test_empty_items(self):
        is_consistent, rel_diff = check_line_items_sum(Decimal("1000"), [])
        assert is_consistent is False
        assert rel_diff == 1.0

        is_consistent_zero, rel_diff_zero = check_line_items_sum(Decimal("0"), [])
        assert is_consistent_zero is True
        assert rel_diff_zero == 0.0

    def test_items_with_none_line_total(self):
        items = [
            NormalizedLineItem(item_idx=0, line_total=Decimal("2000")),
            NormalizedLineItem(item_idx=1, line_total=None),
        ]
        is_consistent, rel_diff = check_line_items_sum(Decimal("2000"), items)
        assert is_consistent is True
        assert rel_diff == 0.0


class TestCheckGrandTotal:
    def test_exact_all_components(self):
        # total = 100 + 10 (tax) + 5 (service) - 15 (discount) = 100
        is_consistent, rel_diff = check_grand_total(
            total=Decimal("100.00"),
            subtotal=Decimal("100.00"),
            tax=Decimal("10.00"),
            service=Decimal("5.00"),
            discount=Decimal("15.00"),
        )
        assert is_consistent is True
        assert rel_diff == 0.0

    def test_subtotal_and_total_only(self):
        is_consistent, rel_diff = check_grand_total(
            total=Decimal("50000"),
            subtotal=Decimal("50000"),
        )
        assert is_consistent is True
        assert rel_diff == 0.0

    def test_negative_discount_handled_as_deduction(self):
        # In printed receipts discount is sometimes extracted as negative: -10000
        is_consistent, rel_diff = check_grand_total(
            total=Decimal("90000"),
            subtotal=Decimal("100000"),
            discount=Decimal("-10000"),
        )
        assert is_consistent is True
        assert rel_diff == 0.0

    def test_discrepancy(self):
        is_consistent, rel_diff = check_grand_total(
            total=Decimal("60000"),
            subtotal=Decimal("50000"),
            tax=Decimal("5000"),
        )  # expected 55000, actual 60000
        assert is_consistent is False
        assert rel_diff > 0

    def test_missing_required_fields(self):
        assert check_grand_total(None, Decimal("100")) == (False, 1.0)
        assert check_grand_total(Decimal("100"), None) == (False, 1.0)


class TestCheckItemMultiplication:
    def test_exact_multiplication(self):
        is_consistent, rel_diff = check_item_multiplication(
            qty=Decimal("2"),
            unit_price=Decimal("18000.00"),
            line_total=Decimal("36000.00"),
        )
        assert is_consistent is True
        assert rel_diff == 0.0

    def test_fractional_qty(self):
        is_consistent, rel_diff = check_item_multiplication(
            qty=Decimal("1.5"),
            unit_price=Decimal("20.00"),
            line_total=Decimal("30.00"),
        )
        assert is_consistent is True
        assert rel_diff == 0.0

    def test_rounding_within_one_cent(self):
        # 3 * 33.33 = 99.99 vs 100.00 -> 0.01 diff
        is_consistent, rel_diff = check_item_multiplication(
            qty=Decimal("3"),
            unit_price=Decimal("33.33"),
            line_total=Decimal("100.00"),
        )
        assert is_consistent is True
        assert rel_diff == 0.0

    def test_multiplication_discrepancy(self):
        is_consistent, rel_diff = check_item_multiplication(
            qty=Decimal("2"),
            unit_price=Decimal("10.00"),
            line_total=Decimal("30.00"),  # expected 20.00
        )
        assert is_consistent is False
        assert rel_diff == pytest.approx(10.0 / 30.0)

    def test_missing_values(self):
        assert check_item_multiplication(None, Decimal("10"), Decimal("10")) == (False, 1.0)
        assert check_item_multiplication(Decimal("1"), None, Decimal("10")) == (False, 1.0)
        assert check_item_multiplication(Decimal("1"), Decimal("10"), None) == (False, 1.0)
