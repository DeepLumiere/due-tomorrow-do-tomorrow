"""
Build Features Dataset for Field Verifier Training and Evaluation.
Reads extractions from JSONL, loads parsed documents from cache,
computes feature vectors for each field, and outputs data/processed/features_v1.parquet.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

import pandas as pd

from src.schema.invoice import InvoiceExtraction, ParsedDoc
from src.verifier.features import build_document_features

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_all_features(
    extractions_jsonl_path: str = "data/processed/extractions_v1.jsonl",
    cache_dir: str = "data/cache/docling",
    output_parquet_path: str = "data/processed/features_v1.parquet",
) -> pd.DataFrame:
    ext_path = Path(extractions_jsonl_path)
    cache_path = Path(cache_dir)
    out_p = Path(output_parquet_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    all_feature_rows: List[dict] = []

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
                logger.warning("Validation error on %s: %s", doc_id, e)
                continue

            cache_file = cache_path / f"{doc_id}.json"
            if not cache_file.exists():
                logger.warning("Cache file missing for %s", doc_id)
                continue

            try:
                parsed_doc = ParsedDoc.model_validate_json(cache_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("Error reading cache for %s: %s", doc_id, e)
                continue

            doc_feats = build_document_features(
                parsed_doc=parsed_doc,
                extraction=extraction,
                doc_id=doc_id,
                split=split,
            )
            all_feature_rows.extend(doc_feats)

    df_feats = pd.DataFrame(all_feature_rows)
    df_feats.to_parquet(out_p, index=False)
    logger.info("Successfully built and saved %d feature rows to %s", len(df_feats), out_p)
    return df_feats


if __name__ == "__main__":
    build_all_features()
