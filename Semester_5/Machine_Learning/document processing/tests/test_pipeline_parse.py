"""
Unit tests for document parsing and ingestion.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import pytest
from src.pipeline.ingest import compute_doc_id, ingest_file
from src.pipeline.parse import parse_document
from src.schema.invoice import OCRItem, ParsedDoc


def test_compute_doc_id():
    data = b"sample receipt image content"
    doc_id = compute_doc_id(data)
    assert len(doc_id) == 16
    assert isinstance(doc_id, str)
    # Deterministic
    assert compute_doc_id(data) == doc_id


def test_ingest_file_from_bytes(tmp_path: Path):
    data = b"raw image binary data"
    doc_id, saved_path = ingest_file(data, "receipt_01.PNG", target_dir=tmp_path)
    
    assert len(doc_id) == 16
    assert saved_path.endswith(f"{doc_id}.png")
    assert Path(saved_path).is_file()
    assert Path(saved_path).read_bytes() == data


def test_ingest_file_from_path(tmp_path: Path):
    source_file = tmp_path / "invoice.pdf"
    source_file.write_bytes(b"%PDF-1.4 sample pdf content")

    target_dir = tmp_path / "uploads"
    doc_id, saved_path = ingest_file(source_file, "invoice.pdf", target_dir=target_dir)

    assert len(doc_id) == 16
    assert saved_path.endswith(f"{doc_id}.pdf")
    assert Path(saved_path).is_file()
    assert Path(saved_path).read_bytes() == b"%PDF-1.4 sample pdf content"


def test_parse_document_instant_replay(tmp_path: Path):
    cache_dir = tmp_path / "docling_cache"
    cache_dir.mkdir(parents=True)

    dummy_doc_id = "abc123def4567890"
    sample_doc = ParsedDoc(
        doc_id=dummy_doc_id,
        source_filename="test.png",
        text="# KOPI KENANGAN\nTotal: 52.800",
        ocr_items=[
            OCRItem(text="KOPI", bbox=[10.0, 10.0, 50.0, 30.0], confidence=0.99),
            OCRItem(text="Total:", bbox=[10.0, 40.0, 50.0, 60.0], confidence=0.98),
            OCRItem(text="52.800", bbox=[60.0, 40.0, 100.0, 60.0], confidence=0.97),
        ],
        parse_seconds=0.12,
    )

    cache_file = cache_dir / f"{dummy_doc_id}.json"
    cache_file.write_text(sample_doc.model_dump_json(indent=2), encoding="utf-8")

    dummy_image = tmp_path / "test.png"
    dummy_image.write_bytes(b"image bytes")

    # With use_cache=True, it must load the cached document without invoking Docling
    result = parse_document(
        str(dummy_image),
        doc_id=dummy_doc_id,
        use_cache=True,
        cache_dir=cache_dir,
    )

    assert result.doc_id == dummy_doc_id
    assert result.text == sample_doc.text
    assert len(result.ocr_items) == 3
    assert result.ocr_items[2].text == "52.800"
    assert result.ocr_items[2].confidence == 0.97
    assert result.parse_seconds == 0.12
