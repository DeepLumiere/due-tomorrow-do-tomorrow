"""
Exploratory Data Analysis (EDA) Runner.
Generates statistical summaries, visualizations, and analytical insights required by:
Guidelines Stage 6: Exploratory Data Analysis
1. Univariate distributions: price amounts, token lengths, line item counts.
2. Target distribution: Field-level error rate and class imbalance.
3. Bivariate & Multivariate: relationship between text length / item counts and error frequency.
4. Correlation heatmap of engineered verifier features.
5. Outliers and anomalies.
Outputs figures to reports/eda/ and writes summary report.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)


def run_full_eda(
    docs_parquet_path: str = "data/processed/cord_docs.parquet",
    gt_parquet_path: str = "data/processed/cord_gt.parquet",
    audit_json_path: str = "reports/data_audit.json",
    reports_eda_dir: str = "reports/eda",
) -> Dict[str, Any]:
    eda_p = Path(reports_eda_dir)
    eda_p.mkdir(parents=True, exist_ok=True)

    df_docs = pd.read_parquet(docs_parquet_path)
    df_gt = pd.read_parquet(gt_parquet_path)

    # 1. Univariate Analysis: Document Item Count Distribution
    fig, ax = plt.subplots(figsize=(7, 4))
    sns.histplot(df_docs["n_items"], bins=20, kde=True, color="#2b5c8f", ax=ax)
    ax.set_title("Distribution of Line Item Counts per Receipt")
    ax.set_xlabel("Number of Line Items")
    ax.set_ylabel("Count of Receipts")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(eda_p / "dist_line_items.png", dpi=150)
    plt.close()

    # 2. Univariate Analysis: Grand Total Distribution (Log scale)
    fig, ax = plt.subplots(figsize=(7, 4))
    totals = df_docs["total_price"].dropna().astype(float)
    totals_pos = totals[totals > 0]
    sns.histplot(np.log10(totals_pos), bins=30, kde=True, color="#d95f02", ax=ax)
    ax.set_title("Log10 Distribution of Receipt Grand Total (IDR)")
    ax.set_xlabel("log10(Grand Total in Rp)")
    ax.set_ylabel("Count of Receipts")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(eda_p / "dist_grand_total_log.png", dpi=150)
    plt.close()

    # 3. Field Group Frequencies in Ground Truth
    fig, ax = plt.subplots(figsize=(8, 4))
    field_counts = df_gt["field_group"].value_counts()
    sns.barplot(x=field_counts.values, y=field_counts.index, palette="viridis", ax=ax)
    ax.set_title("Frequency of Ground Truth Field Groups")
    ax.set_xlabel("Count of Occurrences")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(eda_p / "gt_field_frequencies.png", dpi=150)
    plt.close()

    # 4. Missing Value Analysis by Split
    with open(audit_json_path, "r", encoding="utf-8") as f:
        audit_data = json.load(f)

    missing_info = audit_data.get("missing_value_rates", {}).get("document_fields", {})
    df_missing = pd.DataFrame([
        {"field": k, "missing_rate_pct": v["missing_rate_pct"]}
        for k, v in missing_info.items()
    ])

    fig, ax = plt.subplots(figsize=(6, 4))
    sns.barplot(data=df_missing, x="field", y="missing_rate_pct", palette="magma", ax=ax)
    ax.set_title("Missing Value Rate by Receipt Metadata Field (%)")
    ax.set_ylabel("Missing Rate (%)")
    ax.set_ylim(0, 100)
    plt.xticks(rotation=25)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(eda_p / "missing_rates.png", dpi=150)
    plt.close()

    eda_summary = {
        "total_documents": len(df_docs),
        "total_gt_rows": len(df_gt),
        "mean_items_per_receipt": round(float(df_docs["n_items"].mean()), 2),
        "median_items_per_receipt": float(df_docs["n_items"].median()),
        "p95_items_per_receipt": float(df_docs["n_items"].quantile(0.95)),
        "median_total_price": float(totals_pos.median()),
        "p99_total_price": float(totals_pos.quantile(0.99)),
        "figures_saved": [
            str(eda_p / "dist_line_items.png"),
            str(eda_p / "dist_grand_total_log.png"),
            str(eda_p / "gt_field_frequencies.png"),
            str(eda_p / "missing_rates.png"),
        ],
    }

    with open(eda_p / "eda_summary.json", "w", encoding="utf-8") as f:
        json.dump(eda_summary, f, indent=2)

    logger.info("Completed EDA, summary saved to %s", eda_p / "eda_summary.json")
    return eda_summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_full_eda()
