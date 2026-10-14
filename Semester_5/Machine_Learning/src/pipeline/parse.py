"""
Docling document parsing module with OCR extraction, caching, and instant replay.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
import types
from pathlib import Path
from typing import List, Optional, Union

# Dynamically ensure PyTorch CUDA DLLs are discoverable by ONNX Runtime on Windows
try:
    import torch
    _torch_lib = Path(torch.__file__).parent / "lib"
    if _torch_lib.is_dir() and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(_torch_lib))
except Exception:
    pass

# Suppress Hugging Face symlink warning and patch symlinks on Windows non-admin accounts
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
try:
    import shutil
    import huggingface_hub.file_download as _hf_fd
    _orig_create_symlink = _hf_fd._create_symlink

    def _safe_create_symlink(src: str, dst: str, new_blob: bool = False) -> None:
        try:
            _orig_create_symlink(src, dst, new_blob=new_blob)
        except OSError:
            abs_src = os.path.abspath(os.path.expanduser(src))
            abs_dst = os.path.abspath(os.path.expanduser(dst))
            os.makedirs(os.path.dirname(abs_dst), exist_ok=True)
            try:
                os.remove(abs_dst)
            except OSError:
                pass
            if new_blob:
                shutil.move(abs_src, abs_dst)
            else:
                shutil.copyfile(abs_src, abs_dst)

    _hf_fd._create_symlink = _safe_create_symlink
except Exception:
    pass

from src.schema.invoice import OCRItem, ParsedDoc

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("data/cache/docling")


def _compute_file_doc_id(file_path: Union[str, Path]) -> str:
    """Compute 16-char sha256 digest prefix of file content."""
    data = Path(file_path).read_bytes()
    return hashlib.sha256(data).hexdigest()[:16]


def parse_document(
    file_path: str,
    doc_id: Optional[str] = None,
    use_cache: bool = True,
    cache_dir: Union[str, Path] = DEFAULT_CACHE_DIR,
) -> ParsedDoc:
    """
    Parse a document image or PDF using Docling with OCR enabled.

    If cached at `data/cache/docling/{doc_id}.json` and `use_cache=True`,
    returns the cached ParsedDoc instantly.
    Otherwise, runs Docling's DocumentConverter, exports markdown text and OCR tokens
    with bounding boxes and confidence, saves to cache, and returns ParsedDoc.

    Args:
        file_path: Path to the document image or PDF.
        doc_id: Unique 16-character identifier. If not provided, computed from file hash.
        use_cache: If True, check and populate cache.
        cache_dir: Directory for cached docling output.

    Returns:
        ParsedDoc instance containing text, OCR items, and timing.
    """
    path_obj = Path(file_path)
    if not path_obj.is_file():
        raise FileNotFoundError(f"Document file not found: {file_path}")

    if not doc_id:
        doc_id = _compute_file_doc_id(path_obj)

    cache_dir_path = Path(cache_dir)
    cache_file = cache_dir_path / f"{doc_id}.json"

    # 1. Instant replay from cache
    if use_cache and cache_file.is_file():
        try:
            cached_data = cache_file.read_text(encoding="utf-8")
            parsed = ParsedDoc.model_validate_json(cached_data)
            logger.info("Loaded parsed document from cache: %s", cache_file)
            return parsed
        except Exception as e:
            logger.warning(
                "Failed to load cached ParsedDoc from %s: %s. Re-parsing.",
                cache_file,
                e,
            )

    # 2. Ensure upright document orientation and parse with Docling
    t0 = time.perf_counter()

    from src.pipeline.orient import auto_orient_file
    oriented_path = auto_orient_file(path_obj)

    import torch
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        OcrAutoOptions,
        PdfPipelineOptions,
        RapidOcrOptions,
    )
    from docling.document_converter import (
        DocumentConverter,
        ImageFormatOption,
        PdfFormatOption,
    )

    use_cuda = torch.cuda.is_available()
    device = AcceleratorDevice.CUDA if use_cuda else AcceleratorDevice.AUTO
    accelerator_options = AcceleratorOptions(
        num_threads=8,
        device=device,
        cuda_use_flash_attention2=False,
    )

    try:
        ocr_options = RapidOcrOptions(
            use_cls=True,  # Enables direction/angle classification
            force_full_page_ocr=True,
        )
    except Exception:
        ocr_options = OcrAutoOptions()

    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=False,
        ocr_options=ocr_options,
        accelerator_options=accelerator_options,
    )

    format_options = {
        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options),
    }

    converter = DocumentConverter(format_options=format_options)
    result = converter.convert(str(oriented_path))

    # 3. Export full markdown text
    text = result.document.export_to_markdown()

    # 4. Extract OCR items (tokens/words with bbox and confidence)
    ocr_items: List[OCRItem] = []

    # Priority 1: Page-level cells from segmented OCR if available
    if hasattr(result, "pages") and result.pages:
        for page in result.pages:
            for cell in getattr(page, "cells", []):
                cell_text = getattr(cell, "text", "")
                if not cell_text:
                    continue
                bbox = None
                if hasattr(cell, "to_bounding_box"):
                    try:
                        b = cell.to_bounding_box()
                        bbox = [float(b.l), float(b.t), float(b.r), float(b.b)]
                    except Exception:
                        pass
                conf = getattr(cell, "confidence", None)
                ocr_items.append(
                    OCRItem(
                        text=cell_text,
                        bbox=bbox,
                        confidence=float(conf) if conf is not None else None,
                    )
                )

    # Priority 2: Fallback to document item iteration
    if not ocr_items and hasattr(result, "document"):
        for item, _level in result.document.iterate_items():
            item_text = getattr(item, "text", None)
            if not item_text:
                continue
            bbox = None
            conf = getattr(item, "confidence", None)
            if hasattr(item, "prov") and item.prov:
                p = item.prov[0]
                if hasattr(p, "bbox") and p.bbox:
                    try:
                        bbox = [
                            float(p.bbox.l),
                            float(p.bbox.t),
                            float(p.bbox.r),
                            float(p.bbox.b),
                        ]
                    except Exception:
                        pass
                if conf is None and hasattr(p, "confidence"):
                    conf = getattr(p, "confidence", None)

            ocr_items.append(
                OCRItem(
                    text=item_text,
                    bbox=bbox,
                    confidence=float(conf) if conf is not None else None,
                )
            )

    parse_seconds = round(time.perf_counter() - t0, 3)
    logger.info(
        "Parsed %s (doc_id=%s) in %.3fs with %d OCR items",
        path_obj.name,
        doc_id,
        parse_seconds,
        len(ocr_items),
    )

    parsed_doc = ParsedDoc(
        doc_id=doc_id,
        source_filename=path_obj.name,
        text=text,
        ocr_items=ocr_items,
        parse_seconds=parse_seconds,
    )

    # 5. Cache result
    if use_cache:
        try:
            cache_dir_path.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(parsed_doc.model_dump_json(indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to write ParsedDoc cache to %s: %s", cache_file, e)

    return parsed_doc
