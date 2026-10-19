"""
Schema definition for receipt/invoice extraction, normalisation, and verification.
Single source of truth used across pipeline, storage, verifier, and UI.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, List, Optional
from pydantic import BaseModel, Field, ValidationInfo, field_validator


# ---------------------------------------------------------
# 1. Extraction Schema (sent to LLM / Ollama as JSON Schema)
# ---------------------------------------------------------

class LineItem(BaseModel):
    """Raw line item extracted by LLM as printed in document."""
    description: Optional[str] = Field(default=None, description="Item name or description as printed")
    quantity: Optional[str] = Field(default=None, description="Item count or quantity as printed, e.g. '2', '1x'")
    unit_price: Optional[str] = Field(default=None, description="Unit price as printed")
    line_total: Optional[str] = Field(default=None, description="Total price for this line item as printed")
    modifiers: List[str] = Field(default_factory=list, description="Sub-items or modifications (e.g. 'no ice', 'extra cheese')")

    @field_validator("*", mode="before")
    @classmethod
    def coerce_line_item_field(cls, v: Any, info: ValidationInfo) -> Any:
        if v is None:
            return None
        if info.field_name == "modifiers":
            if isinstance(v, list):
                return [str(m).strip() for m in v if m is not None and str(m).strip()]
            return [str(v).strip()] if str(v).strip() else []
        if isinstance(v, (int, float)):
            return str(v)
        return str(v).strip()


class InvoiceExtraction(BaseModel):
    """
    LLM structured output schema. Flat and concise for high reliability with smaller models (e.g. Gemma 3n 2B).
    Amounts are kept as raw strings to avoid LLM arithmetic hallucination.
    """
    # Extended fields (common in standard invoices; not present in CORD receipts GT)
    vendor_name: Optional[str] = Field(default=None, description="Seller / store / merchant name")
    invoice_number: Optional[str] = Field(default=None, description="Invoice or receipt number")
    invoice_date: Optional[str] = Field(default=None, description="Date of receipt/invoice as printed")
    currency: Optional[str] = Field(default=None, description="Currency symbol or code (e.g. 'IDR', 'Rp', 'USD', '$')")

    # Core fields (present in CORD receipts GT and evaluated by Field Verifier)
    line_items: List[LineItem] = Field(default_factory=list, description="List of purchased line items")
    subtotal: Optional[str] = Field(default=None, description="Subtotal amount before tax/service/discount")
    discount: Optional[str] = Field(default=None, description="Total discount amount")
    service_charge: Optional[str] = Field(default=None, description="Service charge or fee")
    tax: Optional[str] = Field(default=None, description="Tax amount (e.g. PB1, VAT)")
    total: Optional[str] = Field(default=None, description="Grand total payable")
    payment_method: Optional[str] = Field(default=None, description="Method of payment (e.g. cash, credit card, e-wallet)")
    amount_paid: Optional[str] = Field(default=None, description="Tendered or paid amount")
    change: Optional[str] = Field(default=None, description="Change returned to customer")

    @field_validator("*", mode="before")
    @classmethod
    def coerce_invoice_field(cls, v: Any, info: ValidationInfo) -> Any:
        if v is None:
            return None
        if info.field_name == "line_items":
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                return [v]
            return []
        if isinstance(v, (int, float)):
            return str(v)
        return str(v).strip()


# ---------------------------------------------------------
# 2. Pipeline Intermediate Models
# ---------------------------------------------------------

class OCRItem(BaseModel):
    """Word or line bounding box and OCR confidence from Docling."""
    text: str
    bbox: Optional[List[float]] = None # [x0, y0, x1, y1] normalized or absolute
    confidence: Optional[float] = None


class ParsedDoc(BaseModel):
    """Result of Docling document parsing."""
    doc_id: str
    source_filename: str
    text: str # Markdown / plain text exported by Docling
    ocr_items: List[OCRItem] = Field(default_factory=list)
    parse_seconds: float = 0.0


class RawExtraction(BaseModel):
    """Raw extraction result containing primary output and optional consistency samples."""
    doc_id: str
    primary: InvoiceExtraction
    samples: List[InvoiceExtraction] = Field(default_factory=list)
    raw_response: str = ""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    extract_seconds: float = 0.0
    status: str = "ok" # "ok" | "failed"


# ---------------------------------------------------------
# 3. Normalised & Verified Models (Stored in Parquet / Shown in UI)
# ---------------------------------------------------------

class FieldResult(BaseModel):
    """Verification and grounding metadata for an individual extracted field."""
    field_path: str # e.g. "total", "line_items[0].description"
    raw_value: Optional[str] = None
    value_str: Optional[str] = None
    numeric_value: Optional[Decimal] = None
    date_value: Optional[date] = None
    grounded: bool = False # Was raw_value found in Docling OCR text?
    confidence: Optional[float] = None # Field Verifier P(correct)
    needs_review: bool = False # Flagged if confidence < threshold
    verified: Optional[bool] = None # Evaluated against ground truth
    user_corrected: bool = False
    corrected_value: Optional[str] = None


class NormalizedLineItem(BaseModel):
    """Normalized line item with clean Decimals and field results."""
    item_idx: int
    description: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    line_total: Optional[Decimal] = None
    modifiers: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    needs_review: bool = False


class NormalizedInvoice(BaseModel):
    """Final normalized invoice object ready for Parquet persistence and UI presentation."""
    doc_id: str
    source_filename: str
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "1.0"

    # Extended metadata
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    currency: Optional[str] = None

    # Core normalized amounts
    subtotal: Optional[Decimal] = None
    discount: Optional[Decimal] = None
    service_charge: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total: Optional[Decimal] = None
    amount_paid: Optional[Decimal] = None
    change: Optional[Decimal] = None
    payment_method: Optional[str] = None

    line_items: List[NormalizedLineItem] = Field(default_factory=list)
    fields: List[FieldResult] = Field(default_factory=list)

    # Document level summaries
    n_items: int = 0
    min_field_confidence: Optional[float] = None
    needs_review: bool = False
    status: str = "ok" # "ok" | "failed" | "corrected"

    # Provenance
    llm_model: str = "gemma3n:e2b"
    llm_digest: Optional[str] = None
    docling_version: Optional[str] = None
    prompt_version: str = "v1"
    verifier_version: Optional[str] = None
    extract_seconds: float = 0.0

    def sync_fields(self) -> None:
        """
        Synchronize the fields list with the current state of header attributes and line items.
        Ensures that user corrections, added line items, or removed line items are accurately
        reflected in fields for complete auditability and Parquet storage integrity.
        """
        def _fmt(val: Optional[Decimal]) -> Optional[str]:
            if val is None:
                return None
            try:
                if val == val.to_integral():
                    return f"{int(val):,}"
                return f"{val:,.2f}"
            except Exception:
                return str(val)

        existing_map = {f.field_path: f for f in self.fields}
        updated_fields: List[FieldResult] = []

        header_defs = [
            ("vendor_name", self.vendor_name, None),
            ("invoice_number", self.invoice_number, None),
            ("invoice_date", self.invoice_date.isoformat() if self.invoice_date else None, self.invoice_date),
            ("currency", self.currency, None),
            ("subtotal", _fmt(self.subtotal), self.subtotal),
            ("discount", _fmt(self.discount), self.discount),
            ("service_charge", _fmt(self.service_charge), self.service_charge),
            ("tax", _fmt(self.tax), self.tax),
            ("total", _fmt(self.total), self.total),
            ("amount_paid", _fmt(self.amount_paid), self.amount_paid),
            ("change", _fmt(self.change), self.change),
            ("payment_method", self.payment_method, None),
        ]

        for path, val_str, num_or_dt in header_defs:
            if val_str is None and path not in existing_map:
                continue
            f = existing_map.get(path)
            if f is not None:
                if val_str != f.value_str:
                    f.user_corrected = True
                    f.corrected_value = val_str
                    f.value_str = val_str
                    f.confidence = 1.0
                    f.needs_review = False
                if isinstance(num_or_dt, Decimal):
                    f.numeric_value = num_or_dt
                elif isinstance(num_or_dt, date):
                    f.date_value = num_or_dt
                updated_fields.append(f)
            elif val_str is not None:
                new_f = FieldResult(
                    field_path=path,
                    raw_value=val_str,
                    value_str=val_str,
                    numeric_value=num_or_dt if isinstance(num_or_dt, Decimal) else None,
                    date_value=num_or_dt if isinstance(num_or_dt, date) else None,
                    grounded=True,
                    confidence=1.0,
                    needs_review=False,
                    user_corrected=True,
                    corrected_value=val_str,
                )
                updated_fields.append(new_f)

        for idx, item in enumerate(self.line_items):
            item.item_idx = idx
            item_fields = [
                (f"line_items[{idx}].description", item.description, None),
                (f"line_items[{idx}].quantity", _fmt(item.quantity) if item.quantity is not None else None, item.quantity),
                (f"line_items[{idx}].unit_price", _fmt(item.unit_price) if item.unit_price is not None else None, item.unit_price),
                (f"line_items[{idx}].line_total", _fmt(item.line_total) if item.line_total is not None else None, item.line_total),
            ]
            for path, val_str, num_val in item_fields:
                f = existing_map.get(path)
                if f is not None:
                    if val_str != f.value_str:
                        f.user_corrected = True
                        f.corrected_value = val_str
                        f.value_str = val_str
                        f.confidence = 1.0
                        f.needs_review = False
                    if num_val is not None:
                        f.numeric_value = num_val
                    updated_fields.append(f)
                elif val_str is not None:
                    new_f = FieldResult(
                        field_path=path,
                        raw_value=val_str,
                        value_str=val_str,
                        numeric_value=num_val,
                        grounded=True,
                        confidence=1.0,
                        needs_review=False,
                        user_corrected=True,
                        corrected_value=val_str,
                    )
                    updated_fields.append(new_f)

        self.fields = updated_fields
        self.n_items = len(self.line_items)

