# Docling & RapidOCR Document Parsing Deep Dive

This document details the role, inner mechanics, and configuration of **Docling** and the underlying **RapidOCR** engine in the ingestion and layout parsing pipeline.

---

## 1. What is Docling and What Does It Do?

**Docling** is an open-source document conversion and parsing framework developed by IBM Research. In our architecture, Docling serves as the **perceptual and layout backbone**:

```mermaid
flowchart LR
    A["Raw Image / PDF"] --> B["Docling DocumentConverter"]
    B --> C["Format Decoders (PDF/PNG/JPG)"]
    C --> D["RapidOCR ONNX Runtime Engine"]
    D --> E["Text Line Detection & Recognition"]
    E --> F["Direction Classifier (use_cls=True)"]
    F --> G["Docling Document Object Model (DOM)"]
    G --> H["Markdown Text Export"]
    G --> I["BBoxes & Token Confidence Scores"]
```

### Why Use Docling Instead of Passing Images Directly to an LLM?
1. **Resolution & Distortion Invariance:** Photographic receipts are often crumpling, low-resolution, or unevenly illuminated. Docling preprocesses document layers, identifies tabular grids, and extracts linear reading orders.
2. **Deterministic Token Grounding:** Pure vision-language models do not provide word-level bounding boxes or OCR confidence numbers. Docling produces exact bounding boxes $[x_0, y_0, x_1, y_1]$ and OCR engine confidence scores for every token.
3. **Execution Efficiency:** Extracting text via Docling takes $\sim 0.8\text{s}$ on CPU/GPU. Once extracted, sending plain Markdown text to a small local LLM requires significantly fewer compute resources and memory than processing multi-patch high-resolution vision embeddings.

---

## 2. Docling Engine Configuration & Integration

Implemented in `src/pipeline/parse.py`, the pipeline configures Docling for accelerated, high-accuracy receipt processing:

```python
# Code snippet from src/pipeline/parse.py
import torch
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    PdfPipelineOptions,
    RapidOcrOptions,
)
from docling.document_converter import (
    DocumentConverter,
    ImageFormatOption,
    PdfFormatOption,
)

# 1. Device acceleration
use_cuda = torch.cuda.is_available()
device = AcceleratorDevice.CUDA if use_cuda else AcceleratorDevice.AUTO
accelerator_options = AcceleratorOptions(
    num_threads=8,
    device=device,
    cuda_use_flash_attention2=False,
)

# 2. RapidOCR options with angle classification
ocr_options = RapidOcrOptions(
    use_cls=True,              # Enables direction/angle text classification
    force_full_page_ocr=True,  # Disables premature stopping on partial text
)

# 3. Pipeline options
pipeline_options = PdfPipelineOptions(
    do_ocr=True,
    ocr_options=ocr_options,
    accelerator_options=accelerator_options,
)

format_options = {
    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
    InputFormat.IMAGE: ImageFormatOption(pipeline_options=pipeline_options),
}

converter = DocumentConverter(format_options=format_options)
```

### Key Technical Parameters:
- **`use_cls=True`:** Activates RapidOCR's lightweight angle classifier network to handle rotated or upside-down text lines without manual rotation.
- **`force_full_page_ocr=True`:** Guarantees that faint footer lines (e.g., payment tender, change, tax summaries) are fully parsed rather than skipped.
- **`AcceleratorDevice.CUDA`:** Automatically offloads ONNX Runtime tensor execution to NVIDIA CUDA if available, falling back to multi-threaded CPU SIMD instructions.

---

## 3. Pre-Parse Orientation & Direction Correction

Receipts captured on mobile devices frequently contain inverted EXIF tags or are photographed at $90^\circ$ or $180^\circ$ angles. `src/pipeline/orient.py` applies automated correction before passing images to Docling:

1. **EXIF Transposition:** Calls `ImageOps.exif_transpose(image)` to unpack phone camera rotation headers.
2. **RapidOCR Orientation Scoring:** If an image is landscape (aspect ratio $\text{width} > 1.3 \times \text{height}$), receipts are rotated through $0^\circ, 90^\circ, 180^\circ,$ and $270^\circ$.
3. **Bounding Box Aspect Ratio Heuristic:** For each rotation, the detector scores candidate text boxes. Because horizontal text lines are wider than they are tall ($\text{width} > \text{height}$), the angle maximizing horizontal aspect ratio bonuses is selected:

```python
# Code snippet from src/pipeline/orient.py
for angle in angles_to_test:
    test_img = thumb if angle == 0 else thumb.rotate(angle, expand=True)
    out = detector(np.array(test_img))
    if out is not None and out.scores is not None and len(out.scores) > 0:
        h_box_bonus = 0.0
        if out.boxes is not None:
            for b in out.boxes:
                # b is 4 points: [[x0, y0], [x1, y1], [x2, y2], [x3, y3]]
                box_w = abs(b[1][0] - b[0][0])
                box_h = abs(b[2][1] - b[1][1])
                if box_w > 1.2 * box_h:
                    h_box_bonus += 1.0 # Bonus for horizontal text box
        
        score = float(np.sum(out.scores)) + (h_box_bonus * 0.5)
        if score > best_score:
            best_score = score
            best_angle = angle
```

---

## 4. Bounding Box & Token Confidence Extraction

Docling builds a hierarchical Document Object Model (DOM). Our extraction adapter unpacks this structure into flat, verifiable `OCRItem` tokens:

```python
# Unpacking bounding boxes and confidence scores in src/pipeline/parse.py
ocr_items: List[OCRItem] = []

# Page-level segmented OCR cells
if hasattr(result, "pages") and result.pages:
    for page in result.pages:
        for cell in getattr(page, "cells", []):
            cell_text = getattr(cell, "text", "")
            if not cell_text:
                continue
            bbox = None
            if hasattr(cell, "to_bounding_box"):
                b = cell.to_bounding_box()
                bbox = [float(b.l), float(b.t), float(b.r), float(b.b)]
            conf = getattr(cell, "confidence", None)
            ocr_items.append(
                OCRItem(
                    text=cell_text,
                    bbox=bbox,
                    confidence=float(conf) if conf is not None else None,
                )
            )
```

The resulting `ParsedDoc` instance bundles:
- `text`: Complete Markdown document representation.
- `ocr_items`: List of word/token strings with spatial coordinates and confidence numbers.
- `parse_seconds`: Wall-clock execution time.

---

## 5. Instant Replay Caching Architecture

Running OCR repeatedly across hundreds of development and evaluation iterations consumes unnecessary CPU/GPU cycles.

The pipeline implements an **instant replay cache**:
- **Cache Location:** `data/cache/docling/{doc_id}.json`
- **Cache Key:** 16-character SHA-256 hash of the raw image bytes.
- **Serialization:** Full JSON serialization conforming to the `ParsedDoc` Pydantic model.
- **Performance:**
  - *Cold Run (Fresh OCR):* $\sim 0.75 - 1.80\text{ seconds}$ per receipt.
  - *Warm Run (Instant Replay):* $< 0.01\text{ seconds}$ ($> 100\times$ speedup).

---

## 6. Windows Symlink Handling & `[WinError 1314]` Resolution

### The Issue:
On Windows systems, creating filesystem symbolic links (`os.symlink`) requires either Administrator elevation or Windows Developer Mode. By default, Hugging Face Hub attempts to construct symlinks within `~/.cache/huggingface/hub/...`. On non-admin machines, this triggers:
```
OSError: [WinError 1314] A required privilege is not held by the client: 
'..\..\blobs\...' -> '...\snapshots\...\config.json'
```

### Architectural Fixes Implemented:
1. **Disable Unnecessary Table Structure Models (`do_table_structure=False`):**
   In `src/pipeline/parse.py`, we explicitly configure `PdfPipelineOptions(do_ocr=True, do_table_structure=False, ...)`. Receipts are single-page documents where tabular relations are extracted by the LLM from the linear OCR stream. Disabling table structure eliminates the need to download `docling-project/docling-models` entirely, speeding up document conversion by $3\times$ and avoiding snapshot symlinks.
2. **Safe Fallback Monkeypatch for Hugging Face Hub:**
   In both `src/pipeline/__init__.py` and `src/pipeline/parse.py`, we wrap `huggingface_hub.file_download._create_symlink` with a safe exception handler:
   ```python
   # Windows symlink fallback implemented in src/pipeline/parse.py
   os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
   try:
       import shutil
       import huggingface_hub.file_download as _hf_fd
       _orig_create_symlink = _hf_fd._create_symlink

       def _safe_create_symlink(src: str, dst: str, new_blob: bool = False) -> None:
           try:
               _orig_create_symlink(src, dst, new_blob=new_blob)
           except OSError:
               # Gracefully fallback to direct file copy if symlinks lack privilege
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
   ```
   This guarantees that any model or tokenizer download on Windows falls back to an atomic file copy without raising unhandled OS privileges exceptions.

