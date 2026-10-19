"""
File ingestion module.
Computes SHA-256 doc_id prefix (16 chars) and persists raw uploads idempotently.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Tuple, Union


DEFAULT_UPLOADS_DIR = Path("data/raw_uploads")


def compute_doc_id(data: bytes) -> str:
    """
    Compute a 16-character SHA-256 hex digest prefix as the document ID.

    Args:
        data: Raw file bytes.

    Returns:
        16-character hex digest string.
    """
    return hashlib.sha256(data).hexdigest()[:16]


def ingest_file(
    file_path_or_bytes: Union[str, Path, bytes],
    original_filename: str,
    target_dir: Union[str, Path] = DEFAULT_UPLOADS_DIR,
) -> Tuple[str, str]:
    """
    Ingest an uploaded document file or raw bytes.

    Computes the 16-character SHA-256 doc_id prefix, saves the file to
    `target_dir/{doc_id}.{ext}`, and returns `(doc_id, saved_path)`.

    Args:
        file_path_or_bytes: Path to existing file, or raw file bytes.
        original_filename: Original name of the uploaded document (for extension).
        target_dir: Directory where raw uploads are stored. Defaults to 'data/raw_uploads'.

    Returns:
        Tuple of (doc_id, saved_path_as_str).
    """
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)

    # Determine file extension from original_filename
    suffix = Path(original_filename).suffix.lstrip(".")
    if not suffix:
        suffix = "bin"
    suffix = suffix.lower()

    if isinstance(file_path_or_bytes, bytes):
        data = file_path_or_bytes
        doc_id = compute_doc_id(data)
        dest_file = target_path / f"{doc_id}.{suffix}"
        dest_file.write_bytes(data)
    else:
        source_path = Path(file_path_or_bytes)
        if not source_path.is_file():
            raise FileNotFoundError(f"Source file not found: {source_path}")
        data = source_path.read_bytes()
        doc_id = compute_doc_id(data)
        dest_file = target_path / f"{doc_id}.{suffix}"

        # Copy if source and destination are different paths
        if source_path.resolve() != dest_file.resolve():
            shutil.copy2(source_path, dest_file)

    return doc_id, str(dest_file)
