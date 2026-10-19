"""
Unified CLI Entrypoint for Invoice & Receipt Processing Pipeline with Field Verifier.

Usage:
    python main.py ui                                     # Launch Gradio Web Application
    python main.py run <image_or_pdf_path>                # Process single document end-to-end
    python main.py query [--sql "SELECT ..."]             # Query Parquet datastore via DuckDB
    python main.py train                                  # Train & evaluate Field Verifier model
    python main.py test                                   # Run test suite
"""
from __future__ import annotations


import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure repository root is on sys.path
_repo_root = Path(__file__).resolve().parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pipeline_cli")


def cmd_run(args: argparse.Namespace) -> None:
    from src.pipeline.run import process_document

    doc_path = Path(args.file)
    if not doc_path.exists():
        logger.error("File does not exist: %s", doc_path)
        sys.exit(1)

    logger.info("Processing document: %s (threshold: %.2f)", doc_path, args.threshold)
    result = process_document(
        file_path_or_bytes=str(doc_path),
        save_to_store=not args.no_store,
        use_cache=not args.no_cache,
        threshold=args.threshold,
    )
    print("\n" + "=" * 60)
    print("EXTRACTION & VERIFICATION RESULT")
    print("=" * 60)
    print(f"Document ID : {result.doc_id}")
    print(f"Status      : {result.status}")
    print(f"Vendor Name : {result.vendor_name or 'N/A'}")
    print(f"Date        : {result.invoice_date or 'N/A'}")
    print(f"Total       : {result.currency or 'Rp'} {result.total or '0'}")
    print(f"Line Items  : {len(result.line_items)}")
    print(f"Min Conf    : {result.min_field_confidence:.2%}" if result.min_field_confidence is not None else "Min Conf    : N/A")
    print(f"Needs Review: {'YES (Action Required)' if result.needs_review else 'NO (Auto-Accepted)'}")
    print("=" * 60)

    if args.json:
        print(result.model_dump_json(indent=2))


def cmd_ui(args: argparse.Namespace) -> None:
    from src.app.gradio_app import build_app

    logger.info("Launching Gradio UI on %s:%d...", args.host, args.port)
    app = build_app()
    app.launch(server_name=args.host, server_port=args.port, share=args.share)


def cmd_query(args: argparse.Namespace) -> None:
    from src.store.parquet_store import query_documents

    sql = args.sql or "SELECT doc_id, vendor_name, total, min_field_confidence, needs_review, status FROM documents LIMIT 20"
    logger.info("Executing DuckDB Query: %s", sql)
    df = query_documents(sql)
    if df.empty:
        print("No records returned.")
    else:
        print(df.to_string(index=False))


def cmd_train(args: argparse.Namespace) -> None:
    from src.verifier.run_training import main as run_train_main

    logger.info("Starting Field Verifier training and test evaluation...")
    run_train_main()


def cmd_test(args: argparse.Namespace) -> None:
    import pytest

    test_args = ["tests"]
    if args.verbose:
        test_args.append("-v")
    if args.keyword:
        test_args.extend(["-k", args.keyword])

    logger.info("Running pytest suite...")
    code = pytest.main(test_args)
    sys.exit(code)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="invoice-verifier",
        description="Invoice & Receipt Extraction and Verification Pipeline CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: run
    p_run = subparsers.add_parser("run", help="Process a single document image or PDF")
    p_run.add_argument("file", help="Path to receipt/invoice image or PDF")
    p_run.add_argument("--threshold", type=float, default=0.85, help="Confidence threshold (default: 0.85)")
    p_run.add_argument("--no-store", action="store_true", help="Do not write result to Parquet store")
    p_run.add_argument("--no-cache", action="store_true", help="Bypass Docling cache")
    p_run.add_argument("--json", action="store_true", help="Print complete output as JSON")
    p_run.set_defaults(func=cmd_run)

    # Subcommand: ui
    p_ui = subparsers.add_parser("ui", help="Launch interactive Gradio Web Application")
    p_ui.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    p_ui.add_argument("--port", type=int, default=7860, help="Port (default: 7860)")
    p_ui.add_argument("--share", action="store_true", help="Generate public Gradio share link")
    p_ui.set_defaults(func=cmd_ui)

    # Subcommand: query
    p_query = subparsers.add_parser("query", help="Query Parquet datastore via DuckDB SQL")
    p_query.add_argument("--sql", help="SQL query to execute against 'documents' table")
    p_query.set_defaults(func=cmd_query)

    # Subcommand: train
    p_train = subparsers.add_parser("train", help="Train and evaluate Field Verifier model")
    p_train.set_defaults(func=cmd_train)


    # Subcommand: test
    p_test = subparsers.add_parser("test", help="Run pytest automated test suite")
    p_test.add_argument("-v", "--verbose", action="store_true", help="Verbose test output")
    p_test.add_argument("-k", "--keyword", help="Filter tests by keyword expression")
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
