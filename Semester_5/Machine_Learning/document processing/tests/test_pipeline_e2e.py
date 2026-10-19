"""
End-to-End Pipeline Integration Test.
Verifies the complete flow from image input through:
- Ingestion & SHA-256 doc_id generation
- Docling parsing (with cache)
- Structured Extraction
- Normalization & Grounding
- Field Verifier confidence scoring
- Parquet storage persistence and DuckDB querying.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.pipeline.run import process_document
from src.store.parquet_store import query_documents, query_line_items, query_fields


def _get_client_or_mock():
    try:
        import ollama
        client = ollama.Client()
        models = [getattr(m, "model", "") for m in client.list().models]
        if any("gemma3n" in m for m in models):
            return None  # live client
    except Exception:
        pass

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.message.content = json.dumps({
        "vendor_name": "RECEIPT STORE",
        "invoice_number": None,
        "invoice_date": "2023-01-15",
        "currency": "Rp",
        "line_items": [
            {
                "description": "Nasi Campur Bali",
                "quantity": "1",
                "unit_price": "75.000",
                "line_total": "75.000",
                "modifiers": []
            },
            {
                "description": "Es Teh Manis",
                "quantity": "2",
                "unit_price": "10.000",
                "line_total": "20.000",
                "modifiers": []
            }
        ],
        "subtotal": "95.000",
        "discount": None,
        "service_charge": "4.750",
        "tax": "9.975",
        "total": "109.725",
        "payment_method": "cash",
        "amount_paid": "110.000",
        "change": "275"
    })
    mock_resp.prompt_eval_count = 120
    mock_resp.eval_count = 85
    mock_client.chat.return_value = mock_resp
    return mock_client


def test_process_document_end_to_end():
    sample_img = "data/raw/cord/train/cord_train_0000.png"
    assert Path(sample_img).exists(), f"Sample image {sample_img} must exist."

    client = _get_client_or_mock()

    # Run end-to-end processing with cache enabled
    inv = process_document(
        file_path_or_bytes=sample_img,
        save_to_store=True,
        use_cache=True,
        threshold=0.85,
        client=client,
    )

    # 1. Assert invoice structure
    assert len(inv.doc_id) == 16
    assert isinstance(inv.doc_id, str)
    assert inv.status in ("ok", "failed")
    assert inv.extract_seconds > 0.0
    assert len(inv.fields) > 0

    # 2. Assert Field Verifier scoring
    assert inv.min_field_confidence is not None
    assert 0.0 <= inv.min_field_confidence <= 1.0
    for f in inv.fields:
        if f.confidence is not None:
            assert 0.0 <= f.confidence <= 1.0
            assert f.needs_review == (f.confidence < 0.85)

    # 3. Assert Parquet store persistence
    doc_part = Path(f"data/store/documents/part-{inv.doc_id}.parquet")
    assert doc_part.exists(), f"Part file {doc_part} must exist."

    # 4. Assert DuckDB querying
    df_docs = query_documents()
    assert not df_docs.empty
    matched = df_docs[df_docs["doc_id"] == inv.doc_id]
    assert len(matched) == 1
    assert matched.iloc[0]["min_field_confidence"] == inv.min_field_confidence
