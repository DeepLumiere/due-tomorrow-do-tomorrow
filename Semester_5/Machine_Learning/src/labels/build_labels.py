"""
Build Ground Truth Labels for Field Verifier.
Reads extractions from JSONL and aligns each field against CORD ground truth.
Outputs:
  data/processed/labels_v1.parquet (columns: doc_id, split, field_path, field_group, pred_raw, gt_raw, is_error)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.labels.align import align_extraction_with_gt
from src.schema.invoice import InvoiceExtraction

logger = logging.getLogger(__name__)


def build_labels_from_extractions(
    extractions_jsonl_path: str = "data/processed/extractions_v1.jsonl",
    cord_docs_parquet_path: str = "data/processed/cord_docs.parquet",
    cord_raw_dir: str = "data/raw/cord",
    output_parquet_path: str = "data/processed/labels_v1.parquet",
) -> pd.DataFrame:
    """
    Build labels dataset from extraction file and ground truth.
    """
    ext_path = Path(extractions_jsonl_path)
    if not ext_path.exists():
        raise FileNotFoundError(f"Extractions file not found: {ext_path}")

    # Load GT metadata from CORD raw or processed
    gt_by_doc_id: Dict[str, Dict] = {}
    for split in ["train", "val", "test"]:
        meta_file = Path(cord_raw_dir) / split / "metadata.jsonl"
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    gt_by_doc_id[item["doc_id"]] = item.get("gt_parse", {})

    all_label_records: List[Dict] = []

    with open(ext_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            doc_id = data["doc_id"]
            split = data.get("split", "train")
            raw_primary = data.get("primary", {})
            try:
                extraction = InvoiceExtraction.model_validate(raw_primary)
            except Exception as e:
                logger.warning("Failed to validate extraction for %s: %s", doc_id, e)
                continue

            gt_dict = gt_by_doc_id.get(doc_id, {})
            records = align_extraction_with_gt(doc_id, split, extraction, gt_dict)
            all_label_records.extend(records)

    df_labels = pd.DataFrame(all_label_records)
    if df_labels.empty:
        df_labels = pd.DataFrame(columns=[
            "doc_id", "split", "field_path", "field_group", "pred_raw", "gt_raw", "is_error"
        ])

    out_p = Path(output_parquet_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    df_labels.to_parquet(out_p, index=False)
    logger.info("Saved %d field label rows to %s", len(df_labels), out_p)
    return df_labels


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    build_labels_from_extractions()
