"""
Document Orientation and Direction Awareness Module.
Detects and corrects orientation for receipts and invoices:
1. EXIF orientation correction (phone camera metadata).
2. Aspect ratio and text box orientation analysis (90°, 180°, 270° detection).
3. Auto-rotation to upright orientation before OCR layout parsing.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageOps

import os
import sys

logger = logging.getLogger(__name__)

# Dynamically ensure PyTorch CUDA DLLs are discoverable by ONNX Runtime on Windows
try:
    import torch
    _torch_lib = Path(torch.__file__).parent / "lib"
    if _torch_lib.is_dir() and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(_torch_lib))
except Exception:
    pass

# Lightweight singleton for fast orientation scoring
_RAPID_OCR_DET = None


def get_orientation_detector():
    """Lazy initialization of RapidOCR detector for orientation checking."""
    global _RAPID_OCR_DET
    if _RAPID_OCR_DET is None:
        try:
            from rapidocr import RapidOCR
            use_cuda = False
            try:
                import torch
                use_cuda = torch.cuda.is_available()
            except Exception:
                pass
            params = {"EngineConfig.onnxruntime.use_cuda": use_cuda}
            _RAPID_OCR_DET = RapidOCR(params=params)
        except Exception as e:
            logger.warning("Could not initialize RapidOCR for orientation: %s", e)
            _RAPID_OCR_DET = None
    return _RAPID_OCR_DET


def detect_and_correct_orientation(
    img: Image.Image,
) -> Tuple[Image.Image, int]:
    """
    Detect document orientation and rotate image upright.

    Returns:
        (upright_image, applied_rotation_degrees)
    """
    # 1. Apply EXIF orientation transposition
    img_corrected = ImageOps.exif_transpose(img)
    if img_corrected is None:
        img_corrected = img

    if img_corrected.mode not in ("RGB", "L"):
        img_corrected = img_corrected.convert("RGB")

    width, height = img_corrected.size

    # 2. Check if image is heavily landscape (receipts are typically portrait)
    # If width is much greater than height (e.g. 1.3x), test 90° / 270° rotation
    detector = get_orientation_detector()
    if detector is None:
        return img_corrected, 0

    # Downscale thumbnail for fast orientation checking (max dimension 640px)
    thumb = img_corrected.copy()
    thumb.thumbnail((640, 640), Image.Resampling.BILINEAR)

    # Evaluate angles: test 0°, 90°, 270° (or 180° if needed)
    # Score based on count of valid horizontal text boxes
    angles_to_test = [0, 90, 270] if width > height else [0, 90, 180, 270]

    best_angle = 0
    best_score = -1.0

    for angle in angles_to_test:
        test_img = thumb if angle == 0 else thumb.rotate(angle, expand=True)
        try:
            out = detector(np.array(test_img))
            if out is not None and out.scores is not None and len(out.scores) > 0:
                # Bonus score if bounding boxes are wider than tall (characteristic of horizontal text)
                h_box_bonus = 0.0
                if out.boxes is not None:
                    for b in out.boxes:
                        # b is 4 points: [[x0, y0], [x1, y1], [x2, y2], [x3, y3]]
                        bw = np.linalg.norm(b[1] - b[0])
                        bh = np.linalg.norm(b[2] - b[1])
                        if bw > bh * 1.1: # horizontal text box
                            h_box_bonus += 1.0

                total_score = float(sum(out.scores)) + h_box_bonus * 0.5
            else:
                total_score = 0.0
        except Exception:
            total_score = 0.0

        if total_score > best_score:
            best_score = total_score
            best_angle = angle

    if best_angle != 0:
        logger.info("Auto-rotating document by %d degrees to upright orientation (score: %.1f).", best_angle, best_score)
        upright_img = img_corrected.rotate(best_angle, expand=True)
        return upright_img, best_angle

    return img_corrected, 0


def auto_orient_file(file_path: Union[str, Path], output_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Ensure an image file is oriented upright before OCR parsing.
    If the file is already a PDF, returns the path as-is.
    If it's an image, corrects EXIF and auto-detects 90/180/270 rotation.
    """
    p = Path(file_path)
    if p.suffix.lower() == ".pdf":
        return p

    try:
        with Image.open(p) as img:
            upright_img, rot = detect_and_correct_orientation(img)
            target = Path(output_path) if output_path else p
            if rot != 0 or img.format != "PNG":
                upright_img.save(target, format="PNG")
                logger.info("Saved auto-oriented image to %s (rotated %d°)", target, rot)
                return target
    except Exception as e:
        logger.warning("Orientation check skipped on %s: %s", file_path, e)

    return p
