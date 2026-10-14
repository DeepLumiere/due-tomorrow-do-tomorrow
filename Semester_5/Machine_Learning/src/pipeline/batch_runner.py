"""
Resumable batch extraction runner over CORD images or directory of receipts.
Stores raw extraction records in data/processed/extractions_v1.jsonl.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

from src.pipeline.extract import extract_invoice
from src.pipeline.ingest import ingest_file
from src.pipeline.parse import parse_document
from src.schema.invoice import RawExtraction

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_FILE = Path("data/processed/extractions_v1.jsonl")


def load_existing_doc_ids(output_file: Path) -> Set[str]:
    """Load set of already extracted doc_ids from the output JSONL file."""
    doc_ids: Set[str] = set()
    if not output_file.is_file():
        return doc_ids

    with open(output_file, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if "doc_id" in data:
                    doc_ids.add(data["doc_id"])
            except json.JSONDecodeError:
                logger.warning("Skipping invalid JSON at line %d in %s", line_no, output_file)
    logger.info("Found %d already extracted doc_ids in %s", len(doc_ids), output_file)
    return doc_ids


def collect_document_files(
    input_dir: Optional[str] = None,
    split: Optional[str] = None,
) -> List[Path]:
    """Collect image/PDF file paths from input directory or default CORD splits."""
    extensions = {".png", ".jpg", ".jpeg", ".pdf", ".tif", ".tiff"}

    search_dirs: List[Path] = []
    if input_dir:
        search_dirs.append(Path(input_dir))
    else:
        # Default CORD directory structure
        base_cord = Path("data/raw/cord")
        if split and split != "all":
            search_dirs.append(base_cord / split)
        else:
            search_dirs.extend([base_cord / "train", base_cord / "val", base_cord / "test"])

    files: List[Path] = []
    for d in search_dirs:
        if d.is_dir():
            for f in d.rglob("*"):
                if f.is_file() and f.suffix.lower() in extensions:
                    files.append(f)

    files.sort()
    return files


def run_batch(
    files: List[Path],
    output_file: Path = DEFAULT_OUTPUT_FILE,
    k_samples: int = 0,
    limit: Optional[int] = None,
    use_cache: bool = True,
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Run batch extraction over a list of document files.

    Args:
        files: List of document file paths.
        output_file: Path to destination JSONL file.
        k_samples: Number of consistency samples per doc.
        limit: Max documents to process.
        use_cache: If True, uses Docling cache for parsing.
        dry_run: If True, simulate without calling Ollama or writing.

    Returns:
        Summary statistics dictionary.
    """
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    existing_doc_ids = load_existing_doc_ids(output_file)
    stats = {"total": len(files), "skipped": 0, "processed": 0, "failed": 0}

    to_process = files[:limit] if limit else files
    logger.info("Batch run starting: %d files to process (limit=%s, k_samples=%d)", len(to_process), limit, k_samples)

    for idx, file_path in enumerate(to_process, 1):
        try:
            # 1. Ingest to determine doc_id
            doc_id, saved_path = ingest_file(file_path, file_path.name)

            if doc_id in existing_doc_ids:
                logger.info("[%d/%d] Skipping doc_id=%s (already extracted)", idx, len(to_process), doc_id)
                stats["skipped"] += 1
                continue

            if dry_run:
                logger.info("[DRY RUN] [%d/%d] Would process %s (doc_id=%s)", idx, len(to_process), file_path.name, doc_id)
                stats["processed"] += 1
                continue

            logger.info("[%d/%d] Processing %s (doc_id=%s)...", idx, len(to_process), file_path.name, doc_id)

            # 2. Parse document
            parsed = parse_document(saved_path, doc_id=doc_id, use_cache=use_cache)

            # 3. Extract invoice with Ollama
            extraction = extract_invoice(parsed, k_samples=k_samples)

            if extraction.status != "ok":
                stats["failed"] += 1

            # 4. Append to JSONL atomically
            line = extraction.model_dump_json() + "\n"
            with open(output_file, "a", encoding="utf-8") as out_f:
                out_f.write(line)

            existing_doc_ids.add(doc_id)
            stats["processed"] += 1

        except Exception as exc:
            logger.error("Failed processing file %s: %s", file_path, exc, exc_info=True)
            stats["failed"] += 1

    logger.info("Batch run finished: %s", stats)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Batch extraction runner for receipts/invoices.")
    parser.add_argument("--input-dir", type=str, default=None, help="Directory containing receipt images/PDFs.")
    parser.add_argument("--split", type=str, default=None, choices=["train", "val", "test", "all"], help="CORD split.")
    parser.add_argument("--output-file", type=str, default=str(DEFAULT_OUTPUT_FILE), help="Output JSONL file.")
    parser.add_argument("--limit", type=int, default=None, help="Max documents to process.")
    parser.add_argument("--k-samples", type=int, default=0, help="Number of consistency samples.")
    parser.add_argument("--no-cache", action="store_true", help="Disable Docling cache.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without LLM calls.")

    args = parser.parse_args()

    files = collect_document_files(input_dir=args.input_dir, split=args.split)
    if not files:
        logger.warning("No document files found. Check --input-dir or --split.")
        return

    run_batch(
        files=files,
        output_file=Path(args.output_file),
        k_samples=args.k_samples,
        limit=args.limit,
        use_cache=not args.no_cache,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
