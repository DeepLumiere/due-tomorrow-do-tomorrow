"""
Unit tests for CORD Data Cleaning, Deduplication, and Auditing (Task T1).
Tests amount parsing, modifier flattening, schema normalization,
cross-split deduplication, IQR/p99.5 outlier analysis, and parquet outputs.
"""
import json
import sys
from decimal import Decimal
from pathlib import Path
import pytest

# Ensure project root is in sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.data.cord_clean import (
    clean_string,
    parse_amount,
    extract_modifiers,
    normalize_menu_items,
    parse_cord_gt_dict,
    hamming_distance,
    detect_duplicates,
    calculate_outlier_stats,
    compute_audit_report,
    build_cord_docs_df,
    build_cord_gt_df,
    save_processed_cord,
    CleanedReceipt,
    CleanedLineItem,
)


class TestParseAmountCORD:
    """Test suite covering >= 20 varied amount string formats per Task T1 spec."""

    def test_integers(self):
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

    def test_western_thousand_comma_and_decimal_dot(self):
        assert parse_amount("1,500.50") == Decimal("1500.50")
        assert parse_amount("16,500.75") == Decimal("16500.75")
        assert parse_amount("1,000,000") == Decimal("1000000")

    def test_single_separator_decimals(self):
        assert parse_amount("1500.50") == Decimal("1500.50")
        assert parse_amount("1500,50") == Decimal("1500.50")
        assert parse_amount("10.5") == Decimal("10.5")
        assert parse_amount("10,5") == Decimal("10.5")

    def test_indonesian_trailing_shorthand(self):
        assert parse_amount("10.000,-") == Decimal("10000")
        assert parse_amount("10.000.-") == Decimal("10000")
        assert parse_amount("10000,-") == Decimal("10000")

    def test_currency_symbols(self):
        assert parse_amount("Rp 12.000") == Decimal("12000")
        assert parse_amount("Rp. 12.000") == Decimal("12000")
        assert parse_amount("RP 12.000") == Decimal("12000")
        assert parse_amount("IDR 12.000") == Decimal("12000")
        assert parse_amount("$ 1,500.50") == Decimal("1500.50")
        assert parse_amount("€ 15,50") == Decimal("15.50")

    def test_negative_amounts(self):
        assert parse_amount("-16.500") == Decimal("-16500")
        assert parse_amount("(16.500)") == Decimal("-16500")
        assert parse_amount("16.500-") == Decimal("-16500")
        assert parse_amount("16.500 CR") == Decimal("-16500")

    def test_quantities_and_multipliers(self):
        assert parse_amount("2") == Decimal("2")
        assert parse_amount("x2") == Decimal("2")
        assert parse_amount("2x") == Decimal("2")
        assert parse_amount("@15.000") == Decimal("15000")

    def test_invalid_and_empty(self):
        assert parse_amount(None) is None
        assert parse_amount("") is None
        assert parse_amount("   ") is None
        assert parse_amount("FREE") is None
        assert parse_amount("N/A") is None
        assert parse_amount("-") is None


class TestModifiersAndMenuNormalization:
    """Test schema inconsistencies handling: dict vs list, modifiers extraction."""

    def test_menu_as_dict_normalized_to_list(self):
        single_dict = {"nm": "Fried Rice", "cnt": "1", "price": "25.000"}
        normalized = normalize_menu_items(single_dict)
        assert isinstance(normalized, list)
        assert len(normalized) == 1
        assert normalized[0]["nm"] == "Fried Rice"

    def test_menu_as_list(self):
        item_list = [
            {"nm": "Item 1", "price": "10.000"},
            {"nm": "Item 2", "price": "20.000"},
        ]
        normalized = normalize_menu_items(item_list)
        assert len(normalized) == 2

    def test_extract_modifiers_from_sub_list_of_dicts(self):
        item = {
            "nm": "Iced Tea",
            "sub": [
                {"nm": "Less Sugar"},
                {"nm": "No Ice"},
            ],
        }
        mods = extract_modifiers(item)
        assert mods == ["Less Sugar", "No Ice"]

    def test_extract_modifiers_from_sub_dict(self):
        item = {"nm": "Coffee", "sub": {"nm": "Oat Milk"}}
        mods = extract_modifiers(item)
        assert mods == ["Oat Milk"]

    def test_extract_modifiers_from_sub_nm_string_and_list(self):
        item1 = {"nm": "Burger", "sub_nm": "Extra Cheese"}
        assert extract_modifiers(item1) == ["Extra Cheese"]

        item2 = {"nm": "Burger", "sub_nm": ["Extra Bacon", "Pickles"]}
        assert extract_modifiers(item2) == ["Extra Bacon", "Pickles"]


class TestParseCordGTDict:
    """Test full ground truth dictionary parsing."""

    @pytest.fixture
    def sample_cord_gt(self):
        return {
            "menu": [
                {
                    "nm": "Nasi Goreng Spesial",
                    "cnt": "2",
                    "unitprice": "25.000",
                    "price": "50.000",
                    "sub": [{"nm": "Pedas"}],
                },
                {
                    "nm": "Es Teh Manis",
                    "cnt": "1",
                    "unitprice": "5.000",
                    "price": "5.000",
                },
            ],
            "sub_total": {
                "subtotal_price": "55.000",
                "discount_price": "5.000",
                "service_price": "2.500",
                "tax_price": "5.250",
            },
            "total": {
                "total_price": "57.750",
                "cashprice": "100.000",
                "changeprice": "42.250",
            },
            "void_menu": [
                {
                    "nm": "Canceled Juice",
                    "cnt": "1",
                    "price": "15.000",
                }
            ],
        }

    def test_parse_complete_receipt(self, sample_cord_gt):
        receipt = parse_cord_gt_dict(
            doc_id="cord_train_0001",
            split="train",
            gt_parse=sample_cord_gt,
            image_path="data/raw/cord/train/cord_train_0001.png",
            image_sha256="abc123sha",
            image_phash="ffff0000ffff0000",
        )

        assert receipt.doc_id == "cord_train_0001"
        assert receipt.split == "train"
        assert receipt.has_menu is True
        assert receipt.n_items == 2

        # Check line items
        assert receipt.line_items[0].description == "Nasi Goreng Spesial"
        assert receipt.line_items[0].quantity_numeric == Decimal("2")
        assert receipt.line_items[0].unit_price_numeric == Decimal("25000")
        assert receipt.line_items[0].line_total_numeric == Decimal("50000")
        assert receipt.line_items[0].modifiers == ["Pedas"]
        assert receipt.line_items[0].is_void is False

        # Check totals
        assert receipt.subtotal_price_numeric == Decimal("55000")
        assert receipt.discount_price_numeric == Decimal("5000")
        assert receipt.service_price_numeric == Decimal("2500")
        assert receipt.tax_price_numeric == Decimal("5250")
        assert receipt.total_price_numeric == Decimal("57750")
        assert receipt.cash_price_numeric == Decimal("100000")
        assert receipt.change_price_numeric == Decimal("42250")

        # Check void menu items are separated
        assert len(receipt.void_items) == 1
        assert receipt.void_items[0].description == "Canceled Juice"
        assert receipt.void_items[0].is_void is True


class TestDeduplicationAndLeakageControl:
    """Test exact SHA256 and near-duplicate pHash detection, dropping cross-split duplicates from train."""

    def test_exact_sha256_cross_split_leakage_dropped(self):
        r_train = CleanedReceipt(
            doc_id="cord_train_0010",
            split="train",
            image_path="",
            image_sha256="identical_sha_hash",
            image_phash="1111222233334444",
            has_menu=True,
            n_items=1,
            subtotal_price_raw=None, subtotal_price_numeric=None,
            discount_price_raw=None, discount_price_numeric=None,
            service_price_raw=None, service_price_numeric=None,
            tax_price_raw=None, tax_price_numeric=None,
            total_price_raw="10.000", total_price_numeric=Decimal("10000"),
            cash_price_raw=None, cash_price_numeric=None,
            change_price_raw=None, change_price_numeric=None,
            credit_card_price_raw=None, credit_card_price_numeric=None,
            emoney_price_raw=None, emoney_price_numeric=None,
        )
        r_test = CleanedReceipt(
            doc_id="cord_test_0005",
            split="test",
            image_path="",
            image_sha256="identical_sha_hash",
            image_phash="1111222233334444",
            has_menu=True,
            n_items=1,
            subtotal_price_raw=None, subtotal_price_numeric=None,
            discount_price_raw=None, discount_price_numeric=None,
            service_price_raw=None, service_price_numeric=None,
            tax_price_raw=None, tax_price_numeric=None,
            total_price_raw="10.000", total_price_numeric=Decimal("10000"),
            cash_price_raw=None, cash_price_numeric=None,
            change_price_raw=None, change_price_numeric=None,
            credit_card_price_raw=None, credit_card_price_numeric=None,
            emoney_price_raw=None, emoney_price_numeric=None,
        )

        receipts = [r_train, r_test]
        cleaned, audit = detect_duplicates(receipts)

        # Cross-split duplicate in train must be DROPPED
        remaining_ids = [r.doc_id for r in cleaned]
        assert "cord_test_0005" in remaining_ids
        assert "cord_train_0010" not in remaining_ids
        assert audit["exact_duplicates_count"] == 1
        assert audit["cross_split_duplicates_count"] == 1
        assert "cord_train_0010" in audit["dropped_from_train_ids"]

    def test_near_phash_distance(self):
        # 0000 and 0001 differ by 1 bit (Hamming distance 1 <= threshold 2)
        h1 = "0000000000000000"
        h2 = "0000000000000001"
        assert hamming_distance(h1, h2) == 1

        h3 = "ffffffffffffffff"
        assert hamming_distance(h1, h3) == 64


class TestOutlierAndAuditAnalysis:
    """Test IQR and p99.5 outlier calculation and audit report structure."""

    def test_outlier_stats(self):
        prices = [10000.0, 12000.0, 15000.0, 18000.0, 20000.0, 22000.0, 25000.0, 500000.0]
        stats = calculate_outlier_stats(prices, "price")

        assert stats["count"] == 8
        assert stats["min"] == 10000.0
        assert stats["max"] == 500000.0
        assert stats["iqr"] is not None
        assert stats["outlier_count_iqr"] >= 1
        assert stats["p99_5"] is not None

    def test_dataframe_generation(self):
        r = CleanedReceipt(
            doc_id="cord_train_0001",
            split="train",
            image_path="path.png",
            image_sha256="sha",
            image_phash="phash",
            has_menu=True,
            n_items=1,
            subtotal_price_raw="10.000", subtotal_price_numeric=Decimal("10000"),
            discount_price_raw=None, discount_price_numeric=None,
            service_price_raw=None, service_price_numeric=None,
            tax_price_raw="1.000", tax_price_numeric=Decimal("1000"),
            total_price_raw="11.000", total_price_numeric=Decimal("11000"),
            cash_price_raw="15.000", cash_price_numeric=Decimal("15000"),
            change_price_raw="4.000", change_price_numeric=Decimal("4000"),
            credit_card_price_raw=None, credit_card_price_numeric=None,
            emoney_price_raw=None, emoney_price_numeric=None,
            line_items=[
                CleanedLineItem(
                    item_idx=0,
                    description="Kopi",
                    quantity_raw="1",
                    quantity_numeric=Decimal("1"),
                    unit_price_raw="10.000",
                    unit_price_numeric=Decimal("10000"),
                    line_total_raw="10.000",
                    line_total_numeric=Decimal("10000"),
                    modifiers=["No Sugar"],
                )
            ],
            void_items=[],
        )

        df_docs = build_cord_docs_df([r])
        assert len(df_docs) == 1
        assert df_docs.iloc[0]["doc_id"] == "cord_train_0001"
        assert df_docs.iloc[0]["total_price"] == 11000.0

        df_gt = build_cord_gt_df([r])
        assert len(df_gt) > 0
        field_paths = set(df_gt["field_path"].tolist())
        assert "total" in field_paths
        assert "tax" in field_paths
        assert "line_items[0].description" in field_paths
        assert "line_items[0].line_total" in field_paths
