"""
CORD Dataset Acquisition and Caching Module.
Downloads or loads naver-clova-ix/cord-v2 dataset using Hugging Face datasets.
Caches images and ground truth metadata to data/raw/cord/{split}/{doc_id}.png.
Provides robust offline caching and fallback.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import imagehash
from PIL import Image

logger = logging.getLogger(__name__)


def compute_sha256(data: bytes) -> str:
    """Compute SHA256 hex digest of raw image bytes."""
    return hashlib.sha256(data).hexdigest()


def compute_phash(image: Image.Image) -> str:
    """Compute perceptual hash (phash) hex string for PIL image."""
    return str(imagehash.phash(image))


def image_to_bytes(image: Image.Image, format: str = "PNG") -> bytes:
    """Convert PIL image to bytes."""
    buf = io.BytesIO()
    image.save(buf, format=format)
    return buf.getvalue()


class CordLoader:
    """
    Acquires and caches the naver-clova-ix/cord-v2 dataset from Hugging Face.
    Handles offline caching to data/raw/cord/{split}/{doc_id}.png.
    """

    def __init__(
        self,
        cache_dir: Union[str, Path] = "data/raw/cord",
        dataset_name: str = "naver-clova-ix/cord-v2",
    ):
        self.cache_dir = Path(cache_dir)
        self.dataset_name = dataset_name

    def get_split_dir(self, split: str) -> Path:
        split_name = "val" if split in ("val", "validation") else split
        split_dir = self.cache_dir / split_name
        split_dir.mkdir(parents=True, exist_ok=True)
        return split_dir

    def is_split_cached(self, split: str, expected_min_count: int = 10) -> bool:
        split_dir = self.get_split_dir(split)
        meta_file = split_dir / "metadata.jsonl"
        if not meta_file.exists():
            return False
        # Count non-empty lines
        with open(meta_file, "r", encoding="utf-8") as f:
            count = sum(1 for line in f if line.strip())
        return count >= expected_min_count

    def load_from_local_cache(self, split: str) -> List[Dict[str, Any]]:
        """Load records from local disk cache."""
        split_name = "val" if split in ("val", "validation") else split
        split_dir = self.cache_dir / split_name
        meta_file = split_dir / "metadata.jsonl"
        if not meta_file.exists():
            return []

        records = []
        with open(meta_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
        return records

    def cache_record(
        self,
        split: str,
        doc_id: str,
        image: Image.Image,
        gt_parse: Dict[str, Any],
        raw_ground_truth: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Save image to data/raw/cord/{split}/{doc_id}.png and append record to metadata.jsonl.
        """
        split_name = "val" if split in ("val", "validation") else split
        split_dir = self.get_split_dir(split_name)

        # Convert image to RGB if necessary for PNG saving
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")

        img_bytes = image_to_bytes(image, format="PNG")
        sha256_hash = compute_sha256(img_bytes)
        phash_str = compute_phash(image)

        image_filename = f"{doc_id}.png"
        image_path = split_dir / image_filename
        image.save(image_path, format="PNG")

        record = {
            "doc_id": doc_id,
            "split": split_name,
            "image_path": str(image_path.as_posix()),
            "image_sha256": sha256_hash,
            "image_phash": phash_str,
            "image_width": image.width,
            "image_height": image.height,
            "gt_parse": gt_parse,
            "raw_ground_truth": raw_ground_truth or json.dumps({"gt_parse": gt_parse}),
        }

        meta_file = split_dir / "metadata.jsonl"
        with open(meta_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return record

    def load_split(
        self,
        split: str,
        force_download: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Load a split of CORD. First checks local cache unless force_download=True.
        If cache misses, attempts Hugging Face datasets.load_dataset.
        """
        split_name = "val" if split in ("val", "validation") else split

        if not force_download and self.is_split_cached(split_name):
            logger.info("Loading CORD split '%s' from local cache %s", split_name, self.cache_dir)
            return self.load_from_local_cache(split_name)

        hf_split = "validation" if split_name == "val" else split_name
        logger.info("Attempting to load CORD '%s' from Hugging Face datasets...", hf_split)

        try:
            from datasets import load_dataset
            hf_ds = load_dataset(self.dataset_name, split=hf_split)
        except Exception as e:
            logger.warning(
                "Failed to download CORD from Hugging Face (%s). Checking if local cache exists.", e
            )
            local = self.load_from_local_cache(split_name)
            if local:
                return local
            raise RuntimeError(
                f"Could not load CORD split '{split_name}' from Hugging Face or local cache: {e}"
            )

        # Clear existing metadata file for clean reload if force_download
        split_dir = self.get_split_dir(split_name)
        meta_file = split_dir / "metadata.jsonl"
        if meta_file.exists():
            meta_file.unlink()

        records = []
        for idx, row in enumerate(hf_ds):
            doc_id = f"cord_{split_name}_{idx:04d}"
            image = row["image"]
            gt_raw = row["ground_truth"]

            # Parse gt_parse
            if isinstance(gt_raw, str):
                try:
                    gt_obj = json.loads(gt_raw)
                    gt_parse = gt_obj.get("gt_parse", gt_obj)
                except Exception:
                    gt_parse = {}
            elif isinstance(gt_raw, dict):
                gt_parse = gt_raw.get("gt_parse", gt_raw)
            else:
                gt_parse = {}

            rec = self.cache_record(
                split=split_name,
                doc_id=doc_id,
                image=image,
                gt_parse=gt_parse,
                raw_ground_truth=gt_raw if isinstance(gt_raw, str) else json.dumps(gt_raw),
            )
            records.append(rec)

        return records

    def load_all(self, force_download: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """Load all three splits: train (800), val (100), test (100)."""
        splits = ["train", "val", "test"]
        dataset = {}
        for s in splits:
            dataset[s] = self.load_split(s, force_download=force_download)
        return dataset
