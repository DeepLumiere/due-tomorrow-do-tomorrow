"""
End-to-End Invoice / Receipt Processing Pipeline.
Integrates:
1. Ingest: File hashing, doc_id generation, raw persistence.
2. Parse: Docling document conversion + OCR token extraction + caching.
3. Extract: Ollama Gemma3n-E2B structured JSON Schema filling.
4. Normalize: Amount, date, string cleanup and arithmetic consistency checks.
5. Verify: Field Verifier confidence scoring and review routing.
6. Store: Atomic Parquet persistence with pyarrow & DuckDB views.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional, Union

from src.pipeline.extract import extract_invoice
from src.pipeline.ingest import ingest_file
from src.pipeline.normalize import normalize_invoice
from src.pipeline.parse import parse_document
from src.schema.invoice import NormalizedInvoice
from src.store.parquet_store import write_document
from src.verifier.predict import verify_normalized_invoice

logger = logging.getLogger(__name__)


def process_document(
    file_path_or_bytes: Union[str, Path, bytes],
    filename: Optional[str] = None,
    save_to_store: bool = True,
    use_cache: bool = True,
    k_samples: int = 0,
    model_path: str = "models/verifier_v1.joblib",
    threshold: float = 0.85,
    client: Optional[Any] = None,
) -> NormalizedInvoice:
    """
    Execute full end-to-end processing on a single receipt or invoice document.
    """
    t_start = time.time()

    # 1. Ingest
    if isinstance(file_path_or_bytes, (str, Path)):
        p = Path(file_path_or_bytes)
        fname = filename or p.name
        doc_id, saved_path = ingest_file(str(p), fname)
    else:
        fname = filename or "uploaded_document.png"
        doc_id, saved_path = ingest_file(file_path_or_bytes, fname)

    logger.info("Ingested document %s -> doc_id: %s", fname, doc_id)

    # 2. Parse (Docling OCR + cache)
    parsed = parse_document(saved_path, doc_id=doc_id, use_cache=use_cache)
    logger.info("Parsed %s (%d chars, %d OCR tokens in %.2fs)", doc_id, len(parsed.text), len(parsed.ocr_items), parsed.parse_seconds)

    # 3. Extract (Ollama Gemma3n:e2b)
    extraction_res = extract_invoice(parsed, k_samples=k_samples, client=client)
    primary = extraction_res.primary
    logger.info("Extracted %s (status: %s in %.2fs)", doc_id, extraction_res.status, extraction_res.extract_seconds)

    # 4. Normalize & Grounding
    normalized = normalize_invoice(
        raw=primary,
        doc_id=doc_id,
        filename=fname,
        doc_text=parsed.text,
    )
    normalized.extract_seconds = round(time.time() - t_start, 2)
    normalized.status = extraction_res.status

    # 5. Verify & Confidence Scoring
    verified_invoice = verify_normalized_invoice(
        normalized_inv=normalized,
        parsed_doc=parsed,
        extraction=primary,
        model_path=model_path,
        threshold=threshold,
    )
    logger.info(
        "Verification complete for %s (min_conf: %s, needs_review: %s)",
        doc_id,
        verified_invoice.min_field_confidence,
        verified_invoice.needs_review,
    )

    # 6. Parquet Store Persistence
    if save_to_store:
        try:
            write_document(verified_invoice, overwrite=True)
            logger.info("Persisted %s to Parquet store.", doc_id)
        except Exception as e:
            logger.error("Failed to persist %s to Parquet store: %s", doc_id, e)

    return verified_invoice


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    test_path = sys.argv[1] if len(sys.argv) > 1 else "data/raw/cord/train/cord_train_0000.png"
    inv = process_document(test_path)
    print(inv.model_dump_json(indent=2))
