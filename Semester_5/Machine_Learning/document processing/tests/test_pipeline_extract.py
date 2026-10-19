"""
Unit tests for invoice extraction, structured output schema, retry logic, and consistency.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import pytest
from src.pipeline.extract import extract_invoice
from src.schema.invoice import InvoiceExtraction, LineItem, OCRItem, ParsedDoc


def test_structured_schema_structure():
    """Verify JSON schema produced by InvoiceExtraction matches required fields."""
    schema = InvoiceExtraction.model_json_schema()
    assert "properties" in schema
    props = schema["properties"]
    
    # Core fields
    assert "total" in props
    assert "subtotal" in props
    assert "tax" in props
    assert "discount" in props
    assert "service_charge" in props
    assert "line_items" in props
    assert "payment_method" in props
    assert "amount_paid" in props
    assert "change" in props

    # Extended fields
    assert "vendor_name" in props
    assert "invoice_number" in props
    assert "invoice_date" in props
    assert "currency" in props


def test_extract_invoice_success(tmp_path):
    parsed = ParsedDoc(
        doc_id="test_001",
        source_filename="receipt.png",
        text="KOPI KENANGAN\nTotal: 52.800\nPayment: Cash",
        ocr_items=[],
        parse_seconds=0.1,
    )

    valid_json = json.dumps({
        "vendor_name": "KOPI KENANGAN",
        "invoice_number": None,
        "invoice_date": None,
        "currency": "Rp",
        "line_items": [
            {
                "description": "Latte",
                "quantity": "1",
                "unit_price": "25.000",
                "line_total": "25.000",
                "modifiers": []
            }
        ],
        "subtotal": "25.000",
        "discount": None,
        "service_charge": None,
        "tax": None,
        "total": "52.800",
        "payment_method": "cash",
        "amount_paid": "52.800",
        "change": "0"
    })

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.message.content = valid_json
    mock_resp.prompt_eval_count = 150
    mock_resp.eval_count = 80
    mock_client.chat.return_value = mock_resp

    extraction = extract_invoice(parsed, client=mock_client)

    assert extraction.status == "ok"
    assert extraction.doc_id == "test_001"
    assert extraction.primary.vendor_name == "KOPI KENANGAN"
    assert extraction.primary.total == "52.800"
    assert len(extraction.primary.line_items) == 1
    assert extraction.prompt_tokens == 150
    assert extraction.completion_tokens == 80
    assert extraction.extract_seconds >= 0.0


def test_extract_invoice_retry_on_malformed_json():
    """Verify up to 2 retries on malformed JSON and successful recovery."""
    parsed = ParsedDoc(
        doc_id="test_002",
        source_filename="receipt.png",
        text="Total: 10.000",
        ocr_items=[],
    )

    bad_resp = MagicMock()
    bad_resp.message.content = "Malformed JSON {total: 10000"

    good_json = json.dumps({
        "vendor_name": None,
        "invoice_number": None,
        "invoice_date": None,
        "currency": None,
        "line_items": [],
        "subtotal": None,
        "discount": None,
        "service_charge": None,
        "tax": None,
        "total": "10.000",
        "payment_method": None,
        "amount_paid": None,
        "change": None
    })
    good_resp = MagicMock()
    good_resp.message.content = good_json
    good_resp.prompt_eval_count = 100
    good_resp.eval_count = 50

    mock_client = MagicMock()
    # First attempt fails with malformed JSON, second attempt succeeds
    mock_client.chat.side_effect = [bad_resp, good_resp]

    extraction = extract_invoice(parsed, max_retries=2, client=mock_client)

    assert extraction.status == "ok"
    assert extraction.primary.total == "10.000"
    assert mock_client.chat.call_count == 2


def test_extract_invoice_all_retries_fail():
    """Verify status is 'failed' if all retry attempts fail."""
    parsed = ParsedDoc(
        doc_id="test_003",
        source_filename="receipt.png",
        text="Corrupted text",
        ocr_items=[],
    )

    bad_resp = MagicMock()
    bad_resp.message.content = "Not JSON at all"

    mock_client = MagicMock()
    mock_client.chat.return_value = bad_resp

    extraction = extract_invoice(parsed, max_retries=2, client=mock_client)

    assert extraction.status == "failed"
    assert mock_client.chat.call_count == 3  # initial + 2 retries
    assert extraction.primary.total is None


def test_extract_invoice_with_k_samples():
    """Verify self-consistency k-sample generation at temperature 0.7."""
    parsed = ParsedDoc(
        doc_id="test_004",
        source_filename="receipt.png",
        text="Total: 40.000",
        ocr_items=[],
    )

    primary_json = json.dumps({
        "line_items": [],
        "total": "40.000",
    })
    sample_json = json.dumps({
        "line_items": [],
        "total": "40.000",
    })

    primary_resp = MagicMock()
    primary_resp.message.content = primary_json

    sample_resp = MagicMock()
    sample_resp.message.content = sample_json

    mock_client = MagicMock()
    mock_client.chat.side_effect = [primary_resp, sample_resp, sample_resp, sample_resp]

    extraction = extract_invoice(parsed, k_samples=3, client=mock_client)

    assert extraction.status == "ok"
    assert len(extraction.samples) == 3
    assert all(s.total == "40.000" for s in extraction.samples)
    assert mock_client.chat.call_count == 4  # 1 primary + 3 samples
