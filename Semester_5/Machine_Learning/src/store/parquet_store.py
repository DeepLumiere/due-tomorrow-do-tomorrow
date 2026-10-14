"""
High-performance Parquet storage for documents, line_items, and fields tables.
Uses pyarrow with explicit schemas, atomic file writing with part-{doc_id}.parquet,
idempotency, compaction, and DuckDB querying helpers.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import List, Optional, Union

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from src.schema.invoice import NormalizedInvoice


DEFAULT_STORE_DIR = Path("data/store")


# -------------------------------------------------------------------------
# Explicit PyArrow Schemas (Single Source of Truth for Parquet Storage)
# -------------------------------------------------------------------------

DOCUMENTS_SCHEMA = pa.schema([
    ("doc_id", pa.string()),
    ("source_filename", pa.string()),
    ("ingested_at", pa.timestamp("us", tz="UTC")),
    ("schema_version", pa.string()),
    ("vendor_name", pa.string()),
    ("invoice_number", pa.string()),
    ("invoice_date", pa.date32()),
    ("currency", pa.string()),
    ("subtotal", pa.decimal128(18, 2)),
    ("discount", pa.decimal128(18, 2)),
    ("service_charge", pa.decimal128(18, 2)),
    ("tax", pa.decimal128(18, 2)),
    ("total", pa.decimal128(18, 2)),
    ("amount_paid", pa.decimal128(18, 2)),
    ("change", pa.decimal128(18, 2)),
    ("payment_method", pa.string()),
    ("n_items", pa.int32()),
    ("min_field_confidence", pa.float32()),
    ("needs_review", pa.bool_()),
    ("status", pa.string()),
    ("llm_model", pa.string()),
    ("llm_digest", pa.string()),
    ("docling_version", pa.string()),
    ("prompt_version", pa.string()),
    ("verifier_version", pa.string()),
    ("extract_seconds", pa.float32()),
])

LINE_ITEMS_SCHEMA = pa.schema([
    ("doc_id", pa.string()),
    ("item_idx", pa.int32()),
    ("description", pa.string()),
    ("quantity", pa.decimal128(10, 3)),
    ("unit_price", pa.decimal128(18, 2)),
    ("line_total", pa.decimal128(18, 2)),
    ("modifiers", pa.list_(pa.string())),
    ("item_confidence", pa.float32()),
    ("confidence", pa.float32()),
    ("needs_review", pa.bool_()),
])

FIELDS_SCHEMA = pa.schema([
    ("doc_id", pa.string()),
    ("field_path", pa.string()),
    ("raw_value", pa.string()),
    ("value_str", pa.string()),
    ("grounded", pa.bool_()),
    ("confidence", pa.float32()),
    ("needs_review", pa.bool_()),
    ("user_corrected", pa.bool_()),
    ("corrected_value", pa.string()),
])


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------

def _resolve_store_dir(store_dir: Optional[Union[str, Path]]) -> Path:
    return Path(store_dir) if store_dir is not None else DEFAULT_STORE_DIR


def _to_decimal18_2(val: Optional[Decimal]) -> Optional[Decimal]:
    if val is None:
        return None
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_decimal10_3(val: Optional[Decimal]) -> Optional[Decimal]:
    if val is None:
        return None
    return val.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _atomic_write_parquet(table: pa.Table, target_file: Path) -> None:
    """Atomically write a pyarrow Table to target_file using a temp file and os.replace."""
    target_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = target_file.parent / f".tmp_{target_file.stem}_{uuid.uuid4().hex}.parquet"
    try:
        pq.write_table(table, temp_file, compression="SNAPPY")
        os.replace(temp_file, target_file)
    except Exception:
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        raise


# -------------------------------------------------------------------------
# Table Builders
# -------------------------------------------------------------------------

def _build_documents_table(norm: NormalizedInvoice) -> pa.Table:
    data = {
        "doc_id": [norm.doc_id],
        "source_filename": [norm.source_filename],
        "ingested_at": [norm.ingested_at],
        "schema_version": [norm.schema_version],
        "vendor_name": [norm.vendor_name],
        "invoice_number": [norm.invoice_number],
        "invoice_date": [norm.invoice_date],
        "currency": [norm.currency],
        "subtotal": [_to_decimal18_2(norm.subtotal)],
        "discount": [_to_decimal18_2(norm.discount)],
        "service_charge": [_to_decimal18_2(norm.service_charge)],
        "tax": [_to_decimal18_2(norm.tax)],
        "total": [_to_decimal18_2(norm.total)],
        "amount_paid": [_to_decimal18_2(norm.amount_paid)],
        "change": [_to_decimal18_2(norm.change)],
        "payment_method": [norm.payment_method],
        "n_items": [norm.n_items],
        "min_field_confidence": [norm.min_field_confidence],
        "needs_review": [norm.needs_review],
        "status": [norm.status],
        "llm_model": [norm.llm_model],
        "llm_digest": [norm.llm_digest],
        "docling_version": [norm.docling_version],
        "prompt_version": [norm.prompt_version],
        "verifier_version": [norm.verifier_version],
        "extract_seconds": [norm.extract_seconds],
    }
    return pa.Table.from_pydict(data, schema=DOCUMENTS_SCHEMA)


def _build_line_items_table(norm: NormalizedInvoice) -> pa.Table:
    if not norm.line_items:
        return pa.Table.from_arrays(
            [pa.array([], type=f.type) for f in LINE_ITEMS_SCHEMA],
            schema=LINE_ITEMS_SCHEMA,
        )

    data = {
        "doc_id": [norm.doc_id] * len(norm.line_items),
        "item_idx": [it.item_idx for it in norm.line_items],
        "description": [it.description for it in norm.line_items],
        "quantity": [_to_decimal10_3(it.quantity) for it in norm.line_items],
        "unit_price": [_to_decimal18_2(it.unit_price) for it in norm.line_items],
        "line_total": [_to_decimal18_2(it.line_total) for it in norm.line_items],
        "modifiers": [it.modifiers for it in norm.line_items],
        "item_confidence": [it.confidence for it in norm.line_items],
        "confidence": [it.confidence for it in norm.line_items],
        "needs_review": [it.needs_review for it in norm.line_items],
    }
    return pa.Table.from_pydict(data, schema=LINE_ITEMS_SCHEMA)


def _build_fields_table(norm: NormalizedInvoice) -> pa.Table:
    if not norm.fields:
        return pa.Table.from_arrays(
            [pa.array([], type=f.type) for f in FIELDS_SCHEMA],
            schema=FIELDS_SCHEMA,
        )

    data = {
        "doc_id": [norm.doc_id] * len(norm.fields),
        "field_path": [f.field_path for f in norm.fields],
        "raw_value": [f.raw_value for f in norm.fields],
        "value_str": [f.value_str for f in norm.fields],
        "grounded": [f.grounded for f in norm.fields],
        "confidence": [f.confidence for f in norm.fields],
        "needs_review": [f.needs_review for f in norm.fields],
        "user_corrected": [f.user_corrected for f in norm.fields],
        "corrected_value": [f.corrected_value for f in norm.fields],
    }
    return pa.Table.from_pydict(data, schema=FIELDS_SCHEMA)


# -------------------------------------------------------------------------
# Core Storage API
# -------------------------------------------------------------------------

def write_document(
    normalized: NormalizedInvoice,
    overwrite: bool = False,
    store_dir: Optional[Union[str, Path]] = None,
) -> None:
    """
    Persist a NormalizedInvoice across the 3 Parquet tables:
    - documents/part-{doc_id}.parquet
    - line_items/part-{doc_id}.parquet
    - fields/part-{doc_id}.parquet

    Idempotency:
    - If part-{doc_id}.parquet already exists in documents and overwrite is False,
      the write is safely skipped.
    - If overwrite is True, existing part files are atomically updated.

    Args:
        normalized: NormalizedInvoice instance to persist.
        overwrite: When True, overwrites existing records for this doc_id.
        store_dir: Path to storage directory (defaults to data/store).
    """
    base_dir = _resolve_store_dir(store_dir)
    docs_dir = base_dir / "documents"
    items_dir = base_dir / "line_items"
    fields_dir = base_dir / "fields"

    doc_file = docs_dir / f"part-{normalized.doc_id}.parquet"
    if doc_file.exists() and not overwrite:
        # Idempotent skip
        return

    # 1. Build pyarrow Tables with explicit schemas
    docs_table = _build_documents_table(normalized)
    items_table = _build_line_items_table(normalized)
    fields_table = _build_fields_table(normalized)

    # 2. Write atomically using temp files + os.replace
    _atomic_write_parquet(docs_table, doc_file)
    _atomic_write_parquet(items_table, items_dir / f"part-{normalized.doc_id}.parquet")
    _atomic_write_parquet(fields_table, fields_dir / f"part-{normalized.doc_id}.parquet")


def compact_tables(store_dir: Optional[Union[str, Path]] = None) -> None:
    """
    Merge all part files in each table directory into single consolidated
    parquet files ('compacted.parquet') and remove the merged part files.
    New documents written later will arrive as part-{doc_id}.parquet and can
    be compacted again in subsequent compaction runs.

    Args:
        store_dir: Path to storage directory (defaults to data/store).
    """
    base_dir = _resolve_store_dir(store_dir)
    table_configs = [
        ("documents", DOCUMENTS_SCHEMA),
        ("line_items", LINE_ITEMS_SCHEMA),
        ("fields", FIELDS_SCHEMA),
    ]

    for table_name, schema in table_configs:
        table_dir = base_dir / table_name
        if not table_dir.exists():
            continue

        part_files = sorted([
            f for f in table_dir.glob("part-*.parquet")
            if not f.name.startswith(".tmp_")
        ])
        compacted_file = table_dir / "compacted.parquet"

        # If no part files and compacted already exists or nothing exists, continue
        if not part_files:
            continue

        tables_to_concat: List[pa.Table] = []
        if compacted_file.exists():
            tables_to_concat.append(pq.read_table(compacted_file, schema=schema))

        for pf in part_files:
            tables_to_concat.append(pq.read_table(pf, schema=schema))

        if not tables_to_concat:
            continue

        merged_table = pa.concat_tables(tables_to_concat)

        # Atomically write merged table to compacted.parquet
        _atomic_write_parquet(merged_table, compacted_file)

        # Remove merged part files
        for pf in part_files:
            try:
                pf.unlink(missing_ok=True)
            except Exception:
                pass


def read_table(
    table_name: str,
    store_dir: Optional[Union[str, Path]] = None,
) -> pa.Table:
    """
    Read an entire store table as a single pyarrow.Table using pyarrow.dataset.

    Args:
        table_name: 'documents', 'line_items', or 'fields'.
        store_dir: Path to storage directory (defaults to data/store).
    """
    base_dir = _resolve_store_dir(store_dir)
    table_dir = base_dir / table_name

    schema_map = {
        "documents": DOCUMENTS_SCHEMA,
        "line_items": LINE_ITEMS_SCHEMA,
        "fields": FIELDS_SCHEMA,
    }
    schema = schema_map.get(table_name)
    if schema is None:
        raise ValueError(f"Unknown table name '{table_name}'. Expected one of {list(schema_map.keys())}")

    if not table_dir.exists():
        return pa.Table.from_arrays([pa.array([], type=f.type) for f in schema], schema=schema)

    parquet_files = [
        f for f in table_dir.glob("*.parquet")
        if not f.name.startswith(".tmp_")
    ]
    if not parquet_files:
        return pa.Table.from_arrays([pa.array([], type=f.type) for f in schema], schema=schema)

    dataset = ds.dataset([str(f) for f in parquet_files], schema=schema, format="parquet")
    return dataset.to_table()


def _get_duckdb_con(store_dir: Optional[Union[str, Path]] = None) -> duckdb.DuckDBPyConnection:
    """Create a DuckDB in-memory connection with views over documents, line_items, and fields."""
    base_dir = _resolve_store_dir(store_dir)
    con = duckdb.connect(":memory:")

    schemas = [
        ("documents", DOCUMENTS_SCHEMA),
        ("line_items", LINE_ITEMS_SCHEMA),
        ("fields", FIELDS_SCHEMA),
    ]

    for tbl_name, schema in schemas:
        tbl_dir = base_dir / tbl_name
        parquet_files = [
            f for f in tbl_dir.glob("*.parquet")
            if not f.name.startswith(".tmp_")
        ] if tbl_dir.exists() else []

        if parquet_files:
            # Replace Windows backslashes with forward slashes for DuckDB
            escaped_pattern = str(tbl_dir / "*.parquet").replace("\\", "/")
            con.execute(f"CREATE OR REPLACE VIEW {tbl_name} AS SELECT * FROM read_parquet('{escaped_pattern}')")
        else:
            empty_table = pa.Table.from_arrays([pa.array([], type=f.type) for f in schema], schema=schema)
            con.register(f"_empty_{tbl_name}", empty_table)
            con.execute(f"CREATE OR REPLACE VIEW {tbl_name} AS SELECT * FROM _empty_{tbl_name}")

    return con


def query_documents(
    duckdb_sql: Optional[str] = None,
    store_dir: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """
    Query documents table using DuckDB or return all documents as a DataFrame.

    Args:
        duckdb_sql: Custom SQL query (can reference documents, line_items, fields views).
                    If None, defaults to 'SELECT * FROM documents'.
        store_dir: Path to storage directory.
    """
    con = _get_duckdb_con(store_dir)
    query = duckdb_sql if duckdb_sql else "SELECT * FROM documents"
    return con.execute(query).df()


def query_line_items(
    duckdb_sql: Optional[str] = None,
    store_dir: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """
    Query line_items table using DuckDB or return all line items as a DataFrame.

    Args:
        duckdb_sql: Custom SQL query. If None, defaults to 'SELECT * FROM line_items'.
        store_dir: Path to storage directory.
    """
    con = _get_duckdb_con(store_dir)
    query = duckdb_sql if duckdb_sql else "SELECT * FROM line_items"
    return con.execute(query).df()


def query_fields(
    duckdb_sql: Optional[str] = None,
    store_dir: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """
    Query fields table using DuckDB or return all fields as a DataFrame.

    Args:
        duckdb_sql: Custom SQL query. If None, defaults to 'SELECT * FROM fields'.
        store_dir: Path to storage directory.
    """
    con = _get_duckdb_con(store_dir)
    query = duckdb_sql if duckdb_sql else "SELECT * FROM fields"
    return con.execute(query).df()
