"""
Unit tests for src/pipeline/normalize.py:
- Amount parsing covering Indonesian and Western formats, currencies, negatives, shorthands.
- Text cleaning with NFKC and whitespace collapsing.
- Date normalization covering multiple formats and Indonesian/English month names.
- normalize_invoice end-to-end with grounding verification.
"""
import json
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.pipeline.normalize import (
    clean_text,
    normalize_date,
    normalize_invoice,
    parse_amount,
)

from src.schema.invoice import InvoiceExtraction, LineItem


class TestParseAmount:
    """Comprehensive test suite covering >= 20 amount string formats."""

    def test_standard_integers(self):
        assert parse_amount("100") == Decimal("100")
        assert parse_amount("0") == Decimal("0")
        assert parse_amount("50000") == Decimal("50000")

    def test_indonesian_thousand_separator(self):
        assert parse_amount("16.500") == Decimal("16500")
        assert parse_amount("12.000") == Decimal("12000")
        assert parse_amount("1.250.000") == Decimal("1250000")
        assert parse_amount("10.000.000") == Decimal("10000000")

    def test_indonesian_thousand_dot_and_decimal_comma(self):
        assert parse_amount("1.500,50") == Decimal("1500.50")
        assert parse_amount("16.500,75") == Decimal("16500.75")
        assert parse_amount("12.345.678,90") == Decimal("12345678.90")
        assert parse_amount("100.000,00") == Decimal("100000.00")

    def test_western_thousand_comma_and_decimal_dot(self):
        assert parse_amount("1,500.50") == Decimal("1500.50")
        assert parse_amount("16,500.75") == Decimal("16500.75")
        assert parse_amount("12,345,678.90") == Decimal("12345678.90")
        assert parse_amount("1,000,000") == Decimal("1000000")

    def test_single_separator_decimals(self):
        assert parse_amount("1500.50") == Decimal("1500.50")
        assert parse_amount("1500,50") == Decimal("1500.50")
        assert parse_amount("10.5") == Decimal("10.5")
        assert parse_amount("10,5") == Decimal("10.5")
        assert parse_amount("0.75") == Decimal("0.75")
        assert parse_amount("0,75") == Decimal("0.75")

    def test_indonesian_trailing_cent_marker(self):
        # Indonesian receipts often write '10.000,-' or '10000,-' to mean no cents
        assert parse_amount("10.000,-") == Decimal("10000")
        assert parse_amount("10.000.-") == Decimal("10000")
        assert parse_amount("10000,-") == Decimal("10000")

    def test_currency_symbols_and_codes(self):
        assert parse_amount("Rp 12.000") == Decimal("12000")
        assert parse_amount("Rp. 12.000") == Decimal("12000")
        assert parse_amount("RP 12.000") == Decimal("12000")
        assert parse_amount("IDR 12.000") == Decimal("12000")
        assert parse_amount("12.000 IDR") == Decimal("12000")
        assert parse_amount("$ 1,500.50") == Decimal("1500.50")
        assert parse_amount("USD 1500.50") == Decimal("1500.50")
        assert parse_amount("€ 15,50") == Decimal("15.50")
        assert parse_amount("15.50 EUR") == Decimal("15.50")
        assert parse_amount("£ 99.95") == Decimal("99.95")
        assert parse_amount("SGD 45.00") == Decimal("45.00")

    def test_negative_amounts(self):
        assert parse_amount("-16.500") == Decimal("-16500")
        assert parse_amount("- 16.500") == Decimal("-16500")
        assert parse_amount("(16.500)") == Decimal("-16500")
        assert parse_amount("-Rp 12.000") == Decimal("-12000")
        assert parse_amount("Rp -12.000") == Decimal("-12000")
        assert parse_amount("(Rp 12.000)") == Decimal("-12000")
        assert parse_amount("-$ 50.00") == Decimal("-50.00")

    def test_quantities(self):
        assert parse_amount("2") == Decimal("2")
        assert parse_amount("x2") == Decimal("2")
        assert parse_amount("2x") == Decimal("2")
        assert parse_amount("2 pcs") == Decimal("2")
        assert parse_amount("1.5") == Decimal("1.5")

    def test_currency_decimals_handling(self):
        # IDR default (currency_decimals=0): 3 digits after single dot is thousands
        assert parse_amount("16.500", currency_decimals=0) == Decimal("16500")
        # 3-decimal currency (e.g. KWD): 3 digits after dot is decimal
        assert parse_amount("16.500", currency_decimals=3) == Decimal("16.500")

    def test_null_and_invalid_inputs(self):
        assert parse_amount(None) is None
        assert parse_amount("") is None
        assert parse_amount("   ") is None
        assert parse_amount("-") is None
        assert parse_amount("--") is None
        assert parse_amount("N/A") is None
        assert parse_amount("na") is None
        assert parse_amount("None") is None
        assert parse_amount("null") is None
        assert parse_amount("FREE") is None
        assert parse_amount("abc") is None


class TestCleanText:
    """Test text cleaning, NFKC normalization, whitespace collapsing."""

    def test_none_and_empty(self):
        assert clean_text(None) is None
        assert clean_text("") is None
        assert clean_text("   ") is None
        assert clean_text("\n\t  ") is None

    def test_whitespace_collapsing(self):
        assert clean_text("KOPI   KENANGAN") == "KOPI KENANGAN"
        assert clean_text("  Item   Name  \n  Extra  ") == "Item Name Extra"

    def test_nfkc_normalization(self):
        # Full-width characters
        fullwidth = "ＫＯＰＩ"
        assert clean_text(fullwidth) == "KOPI"
        # Non-breaking space \u00a0
        nbsp_str = "Total\u00a0Price"
        assert clean_text(nbsp_str) == "Total Price"


class TestNormalizeDate:
    """Test parsing dates across ISO, DMY, YMD, textual, and Indonesian months."""

    def test_iso_format(self):
        assert normalize_date("2023-04-12") == date(2023, 4, 12)
        assert normalize_date("2021-12-31") == date(2021, 12, 31)

    def test_dmy_formats(self):
        assert normalize_date("12/04/2023") == date(2023, 4, 12)
        assert normalize_date("12-04-2023") == date(2023, 4, 12)
        assert normalize_date("12.04.2023") == date(2023, 4, 12)

    def test_two_digit_years(self):
        assert normalize_date("12/04/23") == date(2023, 4, 12)
        assert normalize_date("12-04-23") == date(2023, 4, 12)

    def test_indonesian_month_names(self):
        assert normalize_date("12 April 2023") == date(2023, 4, 12)
        assert normalize_date("15 Januari 2022") == date(2022, 1, 15)
        assert normalize_date("25 Desember 2021") == date(2021, 12, 25)
        assert normalize_date("17 Agustus 1945") == date(1945, 8, 17)
        assert normalize_date("10 Okt 2023") == date(2023, 10, 10)
        assert normalize_date("1 Mei 2024") == date(2024, 5, 1)

    def test_english_month_names(self):
        assert normalize_date("12 August 2023") == date(2023, 8, 12)
        assert normalize_date("April 12, 2023") == date(2023, 4, 12)
        assert normalize_date("Jan 15, 2022") == date(2022, 1, 15)

    def test_dates_with_timestamps(self):
        assert normalize_date("12/04/2023 14:32:05") == date(2023, 4, 12)
        assert normalize_date("2023-04-12T10:00:00") == date(2023, 4, 12)

    def test_invalid_dates(self):
        assert normalize_date(None) is None
        assert normalize_date("") is None
        assert normalize_date("not-a-date") is None
        assert normalize_date("99/99/9999") is None


class TestNormalizeInvoice:
    """Test full document normalization and field grounding."""

    def test_sample_invoice_fixture(self):
        with open("tests/fixtures/sample_invoice.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        raw = InvoiceExtraction.model_validate(data)
        doc_text = """
        KOPI KENANGAN
        INV-2023-0091
        12/04/2023
        Kopi Kenangan Mantan (R)  2x  18.000  36.000
        Roti Coklat Klasik        1x  12.000  12.000
        Subtotal: 48.000
        Tax: 4.800
        Total: 52.800
        e-money
        Paid: 52.800
        Change: 0
        """

        norm = normalize_invoice(raw, doc_id="doc_001", filename="sample.jpg", doc_text=doc_text)

        assert norm.doc_id == "doc_001"
        assert norm.source_filename == "sample.jpg"
        assert norm.vendor_name == "KOPI KENANGAN"
        assert norm.invoice_number == "INV-2023-0091"
        assert norm.invoice_date == date(2023, 4, 12)
        assert norm.currency == "Rp"
        assert norm.subtotal == Decimal("48000")
        assert norm.tax == Decimal("4800")
        assert norm.total == Decimal("52800")
        assert norm.amount_paid == Decimal("52800")
        assert norm.change == Decimal("0")
        assert norm.n_items == 2

        # Check line items
        assert norm.line_items[0].description == "Kopi Kenangan Mantan (R)"
        assert norm.line_items[0].quantity == Decimal("2")
        assert norm.line_items[0].unit_price == Decimal("18000")
        assert norm.line_items[0].line_total == Decimal("36000")
        assert norm.line_items[0].modifiers == ["Less Sugar", "No Ice"]

        # Check field results and grounding
        total_field = next(f for f in norm.fields if f.field_path == "total")
        assert total_field.numeric_value == Decimal("52800")
        assert total_field.grounded is True

        vendor_field = next(f for f in norm.fields if f.field_path == "vendor_name")
        assert vendor_field.grounded is True

    def test_negative_discount_normalized_to_positive(self):
        raw = InvoiceExtraction(
            vendor_name="Test Store",
            subtotal="100.000",
            discount="-10.000",
            total="90.000",
        )
        norm = normalize_invoice(raw, doc_id="d1", filename="d1.png", doc_text="Test Store 100.000 -10.000 90.000")
        # In invoice calculations discount is subtracted, so its magnitude is positive
        assert norm.discount == Decimal("10000")
        assert norm.total == Decimal("90000")

    def test_grounding_failure_when_not_in_text(self):
        raw = InvoiceExtraction(
            vendor_name="Ghost Store",
            total="99.999",
        )
        norm = normalize_invoice(raw, doc_id="d2", filename="d2.png", doc_text="Completely different receipt text")
        total_field = next(f for f in norm.fields if f.field_path == "total")
        assert total_field.grounded is False
