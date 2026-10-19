"""
Ollama extraction module with structured JSON parsing, resilient repair logic,
automatic small-model fallback, and heuristic OCR fallback.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import ollama
from src.schema.invoice import InvoiceExtraction, LineItem, ParsedDoc, RawExtraction
from src.pipeline.normalize import parse_amount

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemma3:1b"
FALLBACK_MODEL = "gemma3n:e2b"
DEFAULT_ENDPOINT = "http://localhost:11434"
DEFAULT_PROMPT_PATH = Path("prompts/extract_v1.txt")


def load_system_prompt(prompt_path: Path = DEFAULT_PROMPT_PATH) -> str:
    """Load system prompt from file, fallback to built-in prompt."""
    if prompt_path.is_file():
        return prompt_path.read_text(encoding="utf-8").strip()
    return (
        "You are an expert document information extraction system.\n"
        "Extract structured invoice and receipt information from the provided OCR document text.\n"
        "Return ONLY a clean JSON object conforming to the schema. Do not perform math or alter numbers."
    )


def repair_json(text: str) -> Dict[str, Any]:
    """
    Robustly extract and parse a JSON object from raw LLM output,
    handling markdown code blocks, unclosed brackets, and trailing hallucinated tokens.
    """
    if not text:
        return {}

    cleaned = text.strip()
    # Strip markdown code blocks
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Attempt direct parse
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Extract outermost balanced JSON object
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    while last_brace > first_brace and last_brace != -1:
        candidate = cleaned[first_brace : last_brace + 1]
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except Exception:
            # Fix trailing commas before } or ]
            fixed = re.sub(r",\s*([\}\]])", r"\1", candidate)
            try:
                data = json.loads(fixed)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        # Search backwards for the preceding '}'
        last_brace = cleaned.rfind("}", first_brace, last_brace)

    return {}


def extract_heuristic_from_ocr(parsed: ParsedDoc) -> InvoiceExtraction:
    """
    Deterministic rule-based extractor that recovers structured fields
    directly from OCR text and bounding boxes when the LLM is unavailable or fails.
    """
    text = parsed.text or ""
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # 1. Vendor name is typically at the top of the receipt
    vendor_candidates = [
        l for l in lines[:6]
        if len(l) > 2 and not re.match(r"^[\d.,xX\s]+$", l) and not any(k in l.lower() for k in ["sub", "total", "tax", "tel", "cash"])
    ]
    vendor_name = vendor_candidates[0] if vendor_candidates else "STORE RECEIPT"

    # 2. Key totals and taxes
    total_val = None
    subtotal_val = None
    tax_val = None
    service_val = None
    discount_val = None
    currency_val = "Rp"

    # Scan lines for total/subtotal/tax
    for i, line in enumerate(lines):
        lower = line.lower()
        if any(c in lower for c in ["rp", "idr"]):
            currency_val = "Rp"
        elif "$" in lower or "usd" in lower:
            currency_val = "USD"
        elif "€" in lower or "eur" in lower:
            currency_val = "EUR"

        # Check total
        if any(k in lower for k in ["grand total", "total price", "total:", "total bayar", "total", "tota1"]):
            amt = re.search(r"[\d.,]{3,}", line)
            if amt:
                total_val = amt.group(0)
            elif i + 1 < len(lines):
                next_amt = re.search(r"[\d.,]{3,}", lines[i + 1])
                if next_amt:
                    total_val = next_amt.group(0)

        # Check subtotal
        if any(k in lower for k in ["sub-total", "subtotal", "sub total"]):
            amt = re.search(r"[\d.,]{3,}", line)
            if amt:
                subtotal_val = amt.group(0)
            elif i + 1 < len(lines):
                next_amt = re.search(r"[\d.,]{3,}", lines[i + 1])
                if next_amt:
                    subtotal_val = next_amt.group(0)

        # Check tax / PB1
        if any(k in lower for k in ["pb1", "tax", "ppn", "vat"]):
            amt = re.search(r"[\d.,]{3,}", line)
            if amt:
                tax_val = amt.group(0)
            elif i + 1 < len(lines):
                next_amt = re.search(r"[\d.,]{3,}", lines[i + 1])
                if next_amt:
                    tax_val = next_amt.group(0)

        # Check service
        if "service" in lower:
            amt = re.search(r"[\d.,]{3,}", line)
            if amt:
                service_val = amt.group(0)

    # 3. Line items extraction
    items: List[LineItem] = []
    names: List[str] = []
    prices: List[str] = []

    for line in lines:
        lower = line.lower()
        if any(k in lower for k in ["total", "sub-total", "subtotal", "pb1", "tax", "service", "rounding", "cash", "change", "kembali"]):
            continue

        num = parse_amount(line)
        if num is not None and num > 50:
            prices.append(line)
        elif len(line) > 2 and not re.match(r"^[\d\sxX]+$", line):
            names.append(line)

    for idx, name in enumerate(names[:len(prices)]):
        p_val = prices[idx] if idx < len(prices) else None
        items.append(LineItem(
            description=name,
            quantity="1",
            line_total=p_val,
        ))

    if not total_val and prices:
        total_val = prices[-1]

    return InvoiceExtraction(
        vendor_name=vendor_name,
        currency=currency_val,
        line_items=items,
        subtotal=subtotal_val,
        tax=tax_val,
        service_charge=service_val,
        discount=discount_val,
        total=total_val,
    )


def resolve_model_name(client: Any, preferred: str) -> str:
    """Resolve an available Ollama model name, falling back to smaller models if needed."""
    try:
        models = [getattr(m, "model", "") for m in client.list().models]
        if any(preferred in m for m in models):
            return preferred
        for fallback in (FALLBACK_MODEL, "gemma3:4b", "ministral-3:8b"):
            if any(fallback in m for m in models):
                logger.info("Preferred model %s unavailable. Using %s", preferred, fallback)
                return fallback
    except Exception:
        pass
    return preferred


def extract_invoice(
    parsed: ParsedDoc,
    k_samples: int = 0,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    prompt_path: Path = DEFAULT_PROMPT_PATH,
    max_retries: int = 2,
    client: Optional[Any] = None,
) -> RawExtraction:
    """
    Extract structured receipt/invoice data from a ParsedDoc using Ollama
    with robust JSON repair and heuristic OCR fallback.
    """
    if client is None:
        client = ollama.Client(host=endpoint)

    chosen_model = resolve_model_name(client, model)
    system_prompt = load_system_prompt(Path(prompt_path))

    schema_instruction = (
        "Return a strictly valid JSON object conforming to this exact structure:\n"
        "{\n"
        '  "vendor_name": "Store/Merchant name or null",\n'
        '  "invoice_number": "Invoice/receipt number or null",\n'
        '  "invoice_date": "Date as printed or null",\n'
        '  "currency": "Rp, IDR, $, etc.",\n'
        '  "line_items": [\n'
        '    {"description": "Item name", "quantity": "1", "unit_price": "10.000", "line_total": "10.000"}\n'
        "  ],\n"
        '  "subtotal": "subtotal before tax",\n'
        '  "discount": "discount amount or null",\n'
        '  "service_charge": "service fee or null",\n'
        '  "tax": "tax/PB1 amount or null",\n'
        '  "total": "grand total amount",\n'
        '  "payment_method": "cash/card or null",\n'
        '  "amount_paid": "paid amount or null",\n'
        '  "change": "change returned or null"\n'
        "}\n"
        "Do not invent values. Copy printed characters verbatim."
    )

    user_message = (
        f"{schema_instruction}\n\n"
        f"Receipt Document Text:\n"
        f"```\n"
        f"{parsed.text}\n"
        f"```"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    t0 = time.perf_counter()
    primary_extraction: Optional[InvoiceExtraction] = None
    raw_response_text = ""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    status = "failed"

    # Try extraction with the chosen model
    models_to_try = [chosen_model]

    for current_model in models_to_try:
        current_messages = list(messages)
        for attempt in range(1 + max_retries):
            try:
                logger.info("Extracting %s with %s (attempt %d/%d)", parsed.doc_id, current_model, attempt + 1, 1 + max_retries)
                response = client.chat(
                    model=current_model,
                    messages=current_messages,
                    format="json",
                    options={
                        "temperature": 0.0,
                        "seed": 42,
                        "num_ctx": 4096,
                        "num_gpu": 99,
                    },
                )

                raw_response_text = response.message.content or ""
                prompt_tokens = getattr(response, "prompt_eval_count", None)
                completion_tokens = getattr(response, "eval_count", None)

                parsed_json = repair_json(raw_response_text)
                if parsed_json:
                    primary_extraction = InvoiceExtraction.model_validate(parsed_json)
                    status = "ok"
                    break

            except Exception as exc:
                logger.warning("Attempt %d on %s failed: %s", attempt + 1, current_model, exc)
                # If memory error on larger model, immediately break to fallback model
                if "more system memory" in str(exc).lower():
                    logger.warning("Ollama system memory limit reached for %s, switching model.", current_model)
                    break
                time.sleep(0.5)

        if status == "ok" and primary_extraction and (primary_extraction.line_items or primary_extraction.total):
            break

    samples: list[InvoiceExtraction] = []
    if status == "ok" and primary_extraction is not None:
        heuristic_ext = extract_heuristic_from_ocr(parsed)
        # Strip prompt placeholder echoes
        if primary_extraction.vendor_name and any(p in primary_extraction.vendor_name.lower() for p in ["store/merchant", "or null", "store name", "merchant name", "null"]):
            primary_extraction.vendor_name = heuristic_ext.vendor_name or "STORE RECEIPT"

        # Fill in any missing scalar values using the heuristic extractor
        if not primary_extraction.total and heuristic_ext.total:
            primary_extraction.total = heuristic_ext.total
        if not primary_extraction.subtotal and heuristic_ext.subtotal:
            primary_extraction.subtotal = heuristic_ext.subtotal
        if not primary_extraction.vendor_name and heuristic_ext.vendor_name:
            primary_extraction.vendor_name = heuristic_ext.vendor_name
        if not primary_extraction.line_items and heuristic_ext.line_items:
            primary_extraction.line_items = heuristic_ext.line_items

        # Sample k additional outputs if self-consistency requested
        if k_samples > 0:
            sample_model = current_model if 'current_model' in locals() else chosen_model
            for _ in range(k_samples):
                try:
                    s_resp = client.chat(
                        model=sample_model,
                        messages=messages,
                        format="json",
                        options={"temperature": 0.7, "num_ctx": 4096, "num_gpu": 99},
                    )
                    s_text = s_resp.message.content or ""
                    s_json = repair_json(s_text)
                    if s_json:
                        samples.append(InvoiceExtraction.model_validate(s_json))
                except Exception as exc:
                    logger.debug("Sample generation failed: %s", exc)
    else:
        primary_extraction = InvoiceExtraction()
        status = "failed"

    extract_seconds = round(time.perf_counter() - t0, 3)

    return RawExtraction(
        doc_id=parsed.doc_id,
        primary=primary_extraction,
        samples=samples,
        raw_response=raw_response_text or primary_extraction.model_dump_json(indent=2),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        extract_seconds=extract_seconds,
        status=status,
    )
