"""
Gradio UI for Invoice/Receipt Extraction, Verification, and Exploration.
Provides:
- Tab 1: Extract & Review (live document ingestion, Docling OCR, Ollama extraction, Field Verifier scoring, interactive correction)
- Tab 2: Dataset Explorer (Parquet database browsing via DuckDB, needs_review filtering, data export)
- Tab 3: Model Performance & Audit (PR-AUC, metrics.json, data audit report, risk-coverage curve)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import duckdb
import gradio as gr
import pandas as pd

from src.pipeline.run import process_document
from src.schema.invoice import NormalizedInvoice
from src.store.parquet_store import query_documents, query_line_items, write_document

logger = logging.getLogger(__name__)


def run_extraction_ui(
    file_obj,
    threshold: float = 0.85,
    progress=gr.Progress(),
) -> Tuple[Optional[str], Optional[str], Optional[pd.DataFrame], Optional[pd.DataFrame], str]:
    """Process an uploaded image or PDF through the extraction & verification pipeline."""
    if file_obj is None:
        return None, "Please upload an invoice or receipt image/PDF.", None, None, "No file provided"

    file_path = file_obj.name if hasattr(file_obj, "name") else str(file_obj)

    progress(0.1, desc="Ingesting and hashing document...")
    progress(0.3, desc="Parsing layout and running OCR via Docling...")
    progress(0.6, desc="Extracting structured schema via Ollama Gemma3n-E2B...")
    progress(0.85, desc="Executing Field Verifier confidence scoring...")

    try:
        inv: NormalizedInvoice = process_document(
            file_path_or_bytes=file_path,
            threshold=threshold,
        )
    except Exception as e:
        logger.exception("Error in pipeline run: %s", e)
        return None, f"Pipeline Error: {e}", None, None, f"Failed: {e}"

    progress(1.0, desc="Complete!")

    # Format JSON display
    json_display = inv.model_dump_json(indent=2)

    # Format line items dataframe
    item_rows = []
    for item in inv.line_items:
        item_rows.append({
            "Item #": item.item_idx + 1,
            "Description": item.description or "",
            "Qty": str(item.quantity) if item.quantity is not None else "",
            "Unit Price": str(item.unit_price) if item.unit_price is not None else "",
            "Line Total": str(item.line_total) if item.line_total is not None else "",
            "Confidence": f"{item.confidence:.2%}" if item.confidence is not None else "N/A",
            "Needs Review": "⚠️ YES" if item.needs_review else "✅ OK",
        })
    df_items = pd.DataFrame(item_rows) if item_rows else pd.DataFrame(columns=["No items"])

    # Format fields dataframe
    field_rows = []
    for f in inv.fields:
        field_rows.append({
            "Field Path": f.field_path,
            "Extracted Raw": f.raw_value or "",
            "Normalized Value": f.value_str or "",
            "Grounded in OCR": "✅ Yes" if f.grounded else "❌ No",
            "Confidence": f"{f.confidence:.2%}" if f.confidence is not None else "N/A",
            "Review Flag": "⚠️ NEEDS REVIEW" if f.needs_review else "✅ ACCEPTED",
        })
    df_fields = pd.DataFrame(field_rows)

    min_conf_str = f"{inv.min_field_confidence:.2%}" if inv.min_field_confidence is not None else "N/A"
    summary_status = (
        f"Doc ID: {inv.doc_id} | Total: {inv.currency or 'Rp'} {inv.total or '0'} | "
        f"Min Field Confidence: {min_conf_str} | "
        f"Status: {'⚠️ NEEDS MANUAL REVIEW' if inv.needs_review else '✅ AUTO-ACCEPTED'}"
    )

    return file_path, json_display, df_items, df_fields, summary_status


def load_dataset_explorer(filter_option: str = "All") -> pd.DataFrame:
    """Query stored documents from Parquet store via DuckDB."""
    try:
        df = query_documents()
        if df.empty:
            return pd.DataFrame(columns=["doc_id", "source_filename", "total", "min_field_confidence", "needs_review", "status"])

        if filter_option == "Needs Review":
            df = df[df["needs_review"] == True]
        elif filter_option == "Auto-Accepted":
            df = df[df["needs_review"] == False]

        display_cols = [
            "doc_id", "source_filename", "vendor_name", "total",
            "min_field_confidence", "needs_review", "status", "extract_seconds"
        ]
        present_cols = [c for c in display_cols if c in df.columns]
        return df[present_cols]
    except Exception as e:
        logger.error("Dataset explorer query error: %s", e)
        return pd.DataFrame({"Error": [str(e)]})


def load_metrics_tab() -> Tuple[str, str, Optional[str], Optional[str]]:
    """Load performance metrics and figures from reports directory."""
    metrics_path = Path("reports/metrics.json")
    audit_path = Path("reports/data_audit.json")

    metrics_text = metrics_path.read_text(encoding="utf-8") if metrics_path.exists() else "metrics.json not yet generated."
    audit_text = audit_path.read_text(encoding="utf-8") if audit_path.exists() else "data_audit.json not yet generated."

    risk_cov_img = "reports/risk_coverage_curve.png" if Path("reports/risk_coverage_curve.png").exists() else None
    pr_roc_img = "reports/pr_roc_curves.png" if Path("reports/pr_roc_curves.png").exists() else None

    return metrics_text, audit_text, risk_cov_img, pr_roc_img


def build_app() -> gr.Blocks:
    """Build the unified Gradio Blocks application."""
    custom_css = """
    .review-alert { background-color: #fff3cd; color: #856404; padding: 10px; border-radius: 6px; font-weight: bold; }
    .accepted-alert { background-color: #d4edda; color: #155724; padding: 10px; border-radius: 6px; font-weight: bold; }
    """

    with gr.Blocks(title="Invoice & Receipt ML Extraction & Verifier", css=custom_css) as demo:
        gr.Markdown(
            "# 🧾 Document Extraction & Field Verifier Pipeline\n"
            "**Architecture**: Docling OCR + Gemma3n-E2B Structured Extraction + Supervised Field Verifier Classifier + Parquet Store"
        )

        with gr.Tabs():
            # ------------------------------------------------------------------
            # TAB 1: Live Extraction & Review Queue
            # ------------------------------------------------------------------
            with gr.TabItem("🔍 Extract & Review"):
                with gr.Row():
                    with gr.Column(scale=1):
                        input_file = gr.File(label="Upload Receipt / Invoice (Image or PDF)", file_types=["image", ".pdf"])
                        threshold_slider = gr.Slider(
                            minimum=0.50, maximum=0.99, value=0.85, step=0.01,
                            label="Verifier Confidence Threshold P(correct)",
                            info="Fields below this threshold are routed to the manual review queue."
                        )
                        run_btn = gr.Button("🚀 Run Extraction & Verification", variant="primary")
                        doc_preview = gr.Image(label="Document Preview", height=380)

                    with gr.Column(scale=2):
                        status_banner = gr.Markdown("Ready for document upload.")
                        with gr.Tabs():
                            with gr.TabItem("📋 Extracted Line Items"):
                                line_items_table = gr.Dataframe(label="Line Items", interactive=False)
                            with gr.TabItem("🛡️ Field Verification & Grounding"):
                                fields_table = gr.Dataframe(label="Field Verifier Confidence", interactive=False)
                            with gr.TabItem("💻 Structured JSON"):
                                raw_json = gr.Code(label="Normalized JSON Schema Output", language="json", lines=16)

                run_btn.click(
                    fn=run_extraction_ui,
                    inputs=[input_file, threshold_slider],
                    outputs=[doc_preview, raw_json, line_items_table, fields_table, status_banner],
                )

            # ------------------------------------------------------------------
            # TAB 2: Parquet Store Dataset Explorer
            # ------------------------------------------------------------------
            with gr.TabItem("🗄️ Dataset Explorer (Parquet / DuckDB)"):
                gr.Markdown("### Query Ingested Documents from `data/store/documents`")
                with gr.Row():
                    filter_dropdown = gr.Dropdown(
                        choices=["All", "Needs Review", "Auto-Accepted"],
                        value="All",
                        label="Filter Documents",
                    )
                    refresh_btn = gr.Button("🔄 Refresh Store", variant="secondary")

                store_table = gr.Dataframe(label="Stored Documents (DuckDB Query)", interactive=False)
                refresh_btn.click(fn=load_dataset_explorer, inputs=[filter_dropdown], outputs=[store_table])
                filter_dropdown.change(fn=load_dataset_explorer, inputs=[filter_dropdown], outputs=[store_table])

            # ------------------------------------------------------------------
            # TAB 3: Model Performance & Data Audit
            # ------------------------------------------------------------------
            with gr.TabItem("📊 Model Metrics & Data Audit"):
                gr.Markdown("### Evaluation Results on Unseen Test Split")
                refresh_metrics_btn = gr.Button("🔄 Reload Reports", variant="secondary")
                with gr.Row():
                    with gr.Column():
                        pr_roc_plot = gr.Image(label="Precision-Recall & ROC Curves")
                    with gr.Column():
                        risk_cov_plot = gr.Image(label="Risk-Coverage Curve (Auto-acceptance Tradeoff)")

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("#### `reports/metrics.json`")
                        metrics_box = gr.Code(label="Test Split Metrics", language="json", lines=18)
                    with gr.Column():
                        gr.Markdown("#### `reports/data_audit.json`")
                        audit_box = gr.Code(label="CORD Dataset Audit", language="json", lines=18)

                refresh_metrics_btn.click(
                    fn=load_metrics_tab,
                    outputs=[metrics_box, audit_box, risk_cov_plot, pr_roc_plot]
                )

    return demo


if __name__ == "__main__":
    app = build_app()
    app.launch(server_name="127.0.0.1", server_port=7860, inbrowser=False)
