"""
Unit tests for src/store/parquet_store.py:
- Atomic file writing with part-{doc_id}.parquet.
- Schema verification (explicit pyarrow.schema for documents, line_items, fields).
- Idempotency: skip if doc_id exists unless overwrite=True.
- Decimal precision & null handling.
- Table compaction: merging part files into consolidated compacted.parquet.
- DuckDB query helpers: query_documents, query_line_items, query_fields, joins.
"""
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import pyarrow.parquet as pq
import pytest

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.store.parquet_store import (
    compact_tables,
    query_documents,
    query_fields,
    query_line_items,
    read_table,
    write_document,
    DOCUMENTS_SCHEMA,
    FIELDS_SCHEMA,
    LINE_ITEMS_SCHEMA,
)

from src.schema.invoice import (
    FieldResult,
    NormalizedInvoice,
    NormalizedLineItem,
)


@pytest.fixture
def sample_invoice():
    return NormalizedInvoice(
        doc_id="doc_test_100",
        source_filename="receipt_100.png",
        ingested_at=datetime(2023, 4, 12, 10, 0, 0, tzinfo=timezone.utc),
        vendor_name="KOPI KENANGAN",
        invoice_number="INV-2023-0091",
        invoice_date=date(2023, 4, 12),
        currency="Rp",
        subtotal=Decimal("48000.00"),
        tax=Decimal("4800.00"),
        total=Decimal("52800.00"),
        amount_paid=Decimal("52800.00"),
        change=Decimal("0.00"),
        payment_method="e-money",
        n_items=2,
        line_items=[
            NormalizedLineItem(
                item_idx=0,
                description="Kopi Kenangan Mantan (R)",
                quantity=Decimal("2.000"),
                unit_price=Decimal("18000.00"),
                line_total=Decimal("36000.00"),
                modifiers=["Less Sugar", "No Ice"],
                confidence=0.98,
                needs_review=False,
            ),
            NormalizedLineItem(
                item_idx=1,
                description="Roti Coklat Klasik",
                quantity=Decimal("1.000"),
                unit_price=Decimal("12000.00"),
                line_total=Decimal("12000.00"),
                modifiers=[],
                confidence=0.95,
                needs_review=False,
            ),
        ],
        fields=[
            FieldResult(
                field_path="total",
                raw_value="52.800",
                value_str="52800.00",
                numeric_value=Decimal("52800.00"),
                grounded=True,
                confidence=0.96,
                needs_review=False,
            ),
            FieldResult(
                field_path="subtotal",
                raw_value="48.000",
                value_str="48000.00",
                numeric_value=Decimal("48000.00"),
                grounded=True,
                confidence=0.97,
                needs_review=False,
            ),
        ],
    )


class TestParquetStoreWriteAndSchemas:
    def test_write_creates_all_tables_with_schemas(self, tmp_path, sample_invoice):
        write_document(sample_invoice, store_dir=tmp_path)

        # Check part files exist
        doc_part = tmp_path / "documents" / f"part-{sample_invoice.doc_id}.parquet"
        items_part = tmp_path / "line_items" / f"part-{sample_invoice.doc_id}.parquet"
        fields_part = tmp_path / "fields" / f"part-{sample_invoice.doc_id}.parquet"

        assert doc_part.exists()
        assert items_part.exists()
        assert fields_part.exists()

        # Check PyArrow schemas match exactly
        doc_meta = pq.read_metadata(doc_part)
        assert doc_meta.schema.to_arrow_schema().equals(DOCUMENTS_SCHEMA)

        items_meta = pq.read_metadata(items_part)
        assert items_meta.schema.to_arrow_schema().equals(LINE_ITEMS_SCHEMA)

        fields_meta = pq.read_metadata(fields_part)
        assert fields_meta.schema.to_arrow_schema().equals(FIELDS_SCHEMA)

    def test_round_trip_values(self, tmp_path, sample_invoice):
        write_document(sample_invoice, store_dir=tmp_path)

        doc_tbl = read_table("documents", store_dir=tmp_path)
        assert doc_tbl.num_rows == 1
        assert doc_tbl.column("doc_id")[0].as_py() == "doc_test_100"
        assert doc_tbl.column("total")[0].as_py() == Decimal("52800.00")
        assert doc_tbl.column("invoice_date")[0].as_py() == date(2023, 4, 12)

        items_tbl = read_table("line_items", store_dir=tmp_path)
        assert items_tbl.num_rows == 2
        assert items_tbl.column("description")[0].as_py() == "Kopi Kenangan Mantan (R)"
        assert items_tbl.column("quantity")[0].as_py() == Decimal("2.000")
        assert items_tbl.column("modifiers")[0].as_py() == ["Less Sugar", "No Ice"]

        fields_tbl = read_table("fields", store_dir=tmp_path)
        assert fields_tbl.num_rows == 2
        assert fields_tbl.column("field_path")[0].as_py() == "total"
        assert fields_tbl.column("grounded")[0].as_py() is True


class TestIdempotency:
    def test_idempotent_skip_when_overwrite_false(self, tmp_path, sample_invoice):
        write_document(sample_invoice, store_dir=tmp_path)

        # Modify invoice and attempt write with overwrite=False
        sample_invoice.vendor_name = "ALTERED NAME"
        write_document(sample_invoice, overwrite=False, store_dir=tmp_path)

        # Read back and ensure original value remains
        doc_tbl = read_table("documents", store_dir=tmp_path)
        assert doc_tbl.column("vendor_name")[0].as_py() == "KOPI KENANGAN"

    def test_overwrite_true_updates_record(self, tmp_path, sample_invoice):
        write_document(sample_invoice, store_dir=tmp_path)

        # Modify and overwrite
        sample_invoice.vendor_name = "UPDATED VENDOR"
        write_document(sample_invoice, overwrite=True, store_dir=tmp_path)

        doc_tbl = read_table("documents", store_dir=tmp_path)
        assert doc_tbl.column("vendor_name")[0].as_py() == "UPDATED VENDOR"


class TestNullHandling:
    def test_empty_line_items_and_fields(self, tmp_path):
        sparse = NormalizedInvoice(
            doc_id="doc_sparse",
            source_filename="sparse.png",
            subtotal=None,
            total=None,
            line_items=[],
            fields=[],
        )
        write_document(sparse, store_dir=tmp_path)

        doc_tbl = read_table("documents", store_dir=tmp_path)
        assert doc_tbl.column("subtotal")[0].as_py() is None

        items_tbl = read_table("line_items", store_dir=tmp_path)
        assert items_tbl.num_rows == 0

        fields_tbl = read_table("fields", store_dir=tmp_path)
        assert fields_tbl.num_rows == 0


class TestCompaction:
    def test_compact_tables(self, tmp_path):
        # Write 3 separate documents
        for i in range(3):
            inv = NormalizedInvoice(
                doc_id=f"doc_{i}",
                source_filename=f"doc_{i}.png",
                total=Decimal(f"{(i+1)*10000}.00"),
                line_items=[
                    NormalizedLineItem(
                        item_idx=0,
                        description=f"Item {i}",
                        quantity=Decimal("1.000"),
                        unit_price=Decimal("1000.00"),
                        line_total=Decimal("1000.00"),
                    )
                ],
            )
            write_document(inv, store_dir=tmp_path)

        assert len(list((tmp_path / "documents").glob("part-*.parquet"))) == 3

        # Run compaction
        compact_tables(store_dir=tmp_path)

        # Individual parts should be replaced by single compacted.parquet
        assert len(list((tmp_path / "documents").glob("part-*.parquet"))) == 0
        assert (tmp_path / "documents" / "compacted.parquet").exists()
        assert (tmp_path / "line_items" / "compacted.parquet").exists()
        assert (tmp_path / "fields" / "compacted.parquet").exists()

        # All 3 records present in compacted table
        doc_tbl = read_table("documents", store_dir=tmp_path)
        assert doc_tbl.num_rows == 3

        items_tbl = read_table("line_items", store_dir=tmp_path)
        assert items_tbl.num_rows == 3


class TestDuckDBQueries:
    def test_query_documents_all(self, tmp_path, sample_invoice):
        write_document(sample_invoice, store_dir=tmp_path)

        df = query_documents(store_dir=tmp_path)
        assert len(df) == 1
        assert df.iloc[0]["doc_id"] == "doc_test_100"
        assert df.iloc[0]["vendor_name"] == "KOPI KENANGAN"

    def test_custom_duckdb_sql_filter(self, tmp_path, sample_invoice):
        write_document(sample_invoice, store_dir=tmp_path)

        df_high = query_documents("SELECT doc_id, total FROM documents WHERE total > 50000", store_dir=tmp_path)
        assert len(df_high) == 1

        df_low = query_documents("SELECT doc_id, total FROM documents WHERE total > 100000", store_dir=tmp_path)
        assert len(df_low) == 0

    def test_join_query(self, tmp_path, sample_invoice):
        write_document(sample_invoice, store_dir=tmp_path)

        sql = """
        SELECT d.doc_id, d.vendor_name, l.description, l.line_total
        FROM documents d
        JOIN line_items l ON d.doc_id = l.doc_id
        ORDER BY l.item_idx
        """
        df = query_documents(sql, store_dir=tmp_path)
        assert len(df) == 2
        assert df.iloc[0]["description"] == "Kopi Kenangan Mantan (R)"
        assert df.iloc[1]["description"] == "Roti Coklat Klasik"

    def test_empty_store_query(self, tmp_path):
        df = query_documents(store_dir=tmp_path)
        assert len(df) == 0
        assert "doc_id" in df.columns
        assert "total" in df.columns

    def test_overwrite_after_compaction_no_duplicates(self, tmp_path, sample_invoice):
        # 1. Write initial document
        write_document(sample_invoice, store_dir=tmp_path)
        # 2. Compact into compacted.parquet
        compact_tables(store_dir=tmp_path)
        assert (tmp_path / "documents" / "compacted.parquet").exists()

        # 3. Update document and write with overwrite=True
        sample_invoice.vendor_name = "UPDATED KENANGAN"
        sample_invoice.total = Decimal("99000.00")
        sample_invoice.sync_fields()
        write_document(sample_invoice, overwrite=True, store_dir=tmp_path)

        # 4. Query documents - MUST return exactly 1 row with updated values
        df_docs = query_documents(store_dir=tmp_path)
        assert len(df_docs) == 1
        assert df_docs.iloc[0]["vendor_name"] == "UPDATED KENANGAN"
        assert df_docs.iloc[0]["total"] == Decimal("99000.00")

        # 5. Compact again - MUST remain exactly 1 row
        compact_tables(store_dir=tmp_path)
        df_docs_after = query_documents(store_dir=tmp_path)
        assert len(df_docs_after) == 1
        assert df_docs_after.iloc[0]["vendor_name"] == "UPDATED KENANGAN"

