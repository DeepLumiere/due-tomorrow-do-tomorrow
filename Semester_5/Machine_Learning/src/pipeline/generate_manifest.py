"""
Generate Run Manifest documenting environment, model digest, and provenance.
"""
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def generate_manifest(output_path: str = "reports/run_manifest.json"):
    # Ollama model info
    try:
        ollama_proc = subprocess.run(["ollama", "show", "gemma3n:e2b"], capture_output=True, text=True, check=True)
        ollama_details = ollama_proc.stdout[:800]
    except Exception as e:
        ollama_details = str(e)

    # Core package versions
    pkgs = {}
    for mod in ["docling", "ollama", "duckdb", "pyarrow", "pydantic", "sklearn", "imblearn", "rapidfuzz", "gradio", "torch"]:
        try:
            m = __import__(mod)
            pkgs[mod] = getattr(m, "__version__", "unknown")
        except Exception:
            pkgs[mod] = "not installed"

    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": sys.version,
        },
        "packages": pkgs,
        "ollama_model": {
            "model_name": "gemma3n:e2b",
            "details": ollama_details,
        },
        "artifacts_produced": [
            "data/processed/cord_docs.parquet",
            "data/processed/cord_gt.parquet",
            "data/processed/extractions_v1.jsonl",
            "data/processed/labels_v1.parquet",
            "data/processed/features_v1.parquet",
            "models/verifier_v1.joblib",
            "reports/data_audit.json",
            "reports/metrics.json",
            "reports/pr_roc_curves.png",
            "reports/risk_coverage_curve.png",
            "reports/calibration_curve.png",
            "reports/final_report.md",
            "models/model_card.md",
            "docs/ai_usage_log.md",
        ]
    }

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"Generated {out_p}")


if __name__ == "__main__":
    generate_manifest()
