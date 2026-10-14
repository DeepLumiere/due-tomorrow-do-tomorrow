"""
Normalization pipeline for receipt/invoice extractions.
Handles amount parsing (Indonesian and Western formats), string NFKC cleaning,
date normalization, and structured invoice normalization.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Optional, List

from src.schema.invoice import (
    InvoiceExtraction,
    NormalizedInvoice,
    NormalizedLineItem,
    FieldResult,
)


MONTH_NAMES = {
    "januari": 1, "jan": 1, "january": 1,
    "februari": 2, "feb": 2, "february": 2,
    "maret": 3, "mar": 3, "march": 3,
    "april": 4, "apr": 4,
    "mei": 5, "may": 5,
    "juni": 6, "jun": 6, "june": 6,
    "juli": 7, "jul": 7, "july": 7,
    "agustus": 8, "agu": 8, "aug": 8, "august": 8,
    "september": 9, "sep": 9,
    "oktober": 10, "okt": 10, "oct": 10, "october": 10,
    "november": 11, "nov": 11,
    "desember": 12, "des": 12, "dec": 12, "december": 12,
}


def clean_text(s: Optional[str]) -> Optional[str]:
    """
    Perform Unicode NFKC normalization, strip surrounding whitespace,
    and collapse multiple spaces into a single space.
    Returns None if the result is empty or input is None.
    """
    if s is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(s))
    cleaned = re.sub(r"\s+", " ", normalized).strip()
    return cleaned if cleaned else None


def parse_amount(
    val_str: Optional[str],
    currency_decimals: int = 0,
) -> Optional[Decimal]:
    """
    Parse an amount string into a Decimal.

    Handles Indonesian receipt formats where '.' is thousand separator and ','
    is decimal (e.g. '16.500' -> 16500, 'Rp 12.000' -> 12000, '1.500,50' -> 1500.50),
    as well as standard Western formats ('1500.50', '1,500.50').
    Strips currency symbols ('Rp', 'IDR', '$', 'USD', 'EUR', etc.) and handles
    negative indicators like leading '-', trailing '-', or parentheses '(1000)'.
    Trailing shorthand ',-' or '.-' (Indonesian no-cent marker) is cleanly stripped.

    Args:
        val_str: Raw amount string to parse.
        currency_decimals: Expected decimal places for the currency (default 0 for IDR).
    """
    if val_str is None:
        return None

    # Step 1: Normalize unicode and strip whitespace
    s = unicodedata.normalize("NFKC", str(val_str)).strip()
    if not s:
        return None

    # Step 2: Check for known null / non-amount representations
    if s.lower() in {"none", "null", "n/a", "na", "-", "--", "free", "nil", ""}:
        return None

    is_negative = False

    # Parentheses indicate negative amount: e.g. "(15.000)" or "(Rp 15.000)"
    if s.startswith("(") and s.endswith(")"):
        is_negative = True
        s = s[1:-1].strip()

    # Indonesian shorthand trailing ',-' or '.-' (e.g. '10.000,-' or '10.000.-')
    if s.endswith(",-") or s.endswith(".-"):
        s = s[:-2].strip()
    elif s.endswith("-"):
        is_negative = True
        s = s[:-1].strip()

    if s.startswith("-"):
        is_negative = True
        s = s[1:].strip()

    # Step 3: Strip currency symbols, currency words, and item units
    s = re.sub(
        r"(?i)\b(rp\.?|idr|usd|eur|sgd|gbp|jpy|pcs|pc|item|items|qty|x)\b",
        " ",
        s,
    )
    s = re.sub(r"[$€£¥xX@:]", " ", s)
    s = s.strip()

    # In case minus was after currency symbol: e.g. "Rp -12.000"
    if s.startswith("-"):
        is_negative = True
        s = s[1:].strip()

    if s.endswith("-"):
        is_negative = True
        s = s[:-1].strip()

    # Step 4: Handle space as thousand separator (e.g. "16 500") or strip all non-digit/separator chars
    if re.match(r"^\d+\s+\d{3}(?:[.,]\d+)?$", s):
        s = re.sub(r"\s+", "", s)
    else:
        s = re.sub(r"[^\d.,]", "", s)

    if not s or not any(c.isdigit() for c in s):
        return None

    # Step 5: Analyze dot and comma separators
    dot_count = s.count(".")
    comma_count = s.count(",")

    try:
        # Case A: Integer without separators
        if dot_count == 0 and comma_count == 0:
            val = Decimal(s)
            return -val if is_negative else val

        # Case B: Both dots and commas present
        if dot_count > 0 and comma_count > 0:
            last_dot = s.rfind(".")
            last_comma = s.rfind(",")
            if last_dot > last_comma:
                # Comma is thousands, dot is decimal: "1,500.50" or "1,234,567.89"
                cleaned = s.replace(",", "")
            else:
                # Dot is thousands, comma is decimal: "1.500,50" or "1.234.567,89"
                cleaned = s.replace(".", "").replace(",", ".")
            val = Decimal(cleaned)
            return -val if is_negative else val

        # Case C: Only dots present
        if dot_count > 0:
            if dot_count > 1:
                # Multiple dots: "16.500.000" -> all are thousand separators
                cleaned = s.replace(".", "")
            else:
                # Exactly one dot: "16.500" vs "1500.50" vs "1500.5"
                parts = s.split(".")
                dec_len = len(parts[1])
                if dec_len == 3:
                    if currency_decimals == 3:
                        cleaned = s  # 3-digit decimal for 3-decimal currencies
                    else:
                        cleaned = s.replace(".", "")  # thousand separator e.g. 16.500 -> 16500
                elif dec_len in (1, 2):
                    cleaned = s  # decimal separator e.g. 1500.50 -> 1500.50
                else:
                    cleaned = s
            val = Decimal(cleaned)
            return -val if is_negative else val

        # Case D: Only commas present
        if comma_count > 0:
            if comma_count > 1:
                # Multiple commas: "16,500,000" -> all are thousand separators
                cleaned = s.replace(",", "")
            else:
                # Exactly one comma: "16,500" vs "1500,50"
                parts = s.split(",")
                dec_len = len(parts[1])
                if dec_len == 3:
                    if currency_decimals == 3:
                        cleaned = s.replace(",", ".")
                    else:
                        cleaned = s.replace(",", "")  # thousand separator e.g. 16,500 -> 16500
                elif dec_len in (1, 2):
                    cleaned = s.replace(",", ".")  # decimal separator e.g. 1500,50 -> 1500.50
                else:
                    cleaned = s.replace(",", ".")
            val = Decimal(cleaned)
            return -val if is_negative else val

    except Exception:
        return None

    return None


def normalize_date(date_str: Optional[str]) -> Optional[date]:
    """
    Parse dates in common receipt and invoice formats into datetime.date:
    - YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD
    - DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    - DD/MM/YY, DD-MM-YY, DD.MM.YY
    - DD Month YYYY, DD Month YY (e.g. '12 April 2023', '12 Apr 23', '12 Oktober 2022')
    - Month DD, YYYY (e.g. 'April 12, 2023')
    - Timestamps with trailing time (e.g. '12/04/2023 14:30:00') are stripped to date.

    Returns:
        datetime.date if successfully parsed, None otherwise.
    """
    if date_str is None:
        return None

    s = unicodedata.normalize("NFKC", str(date_str)).strip()
    if not s or s.lower() in {"none", "null", "n/a", "na", "-"}:
        return None

    # Strip time part if present: 'T14:30:00' or ' 14:30:00' or ' 14:30'
    s = re.sub(r"[T\s]+\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?.*$", "", s).strip()

    # 1. Try ISO date format: YYYY-MM-DD
    try:
        return date.fromisoformat(s)
    except Exception:
        pass

    # 2. Check YYYY[/.]MM[/.]DD
    m_ymd = re.match(r"^(\d{4})[-/. ](\d{1,2})[-/. ](\d{1,2})$", s)
    if m_ymd:
        try:
            return date(int(m_ymd.group(1)), int(m_ymd.group(2)), int(m_ymd.group(3)))
        except ValueError:
            pass

    # 3. Check DD[/.-]MM[/.-]YYYY
    m_dmy = re.match(r"^(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{4})$", s)
    if m_dmy:
        day, month, year = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        if month > 12 and day <= 12:
            day, month = month, day
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # 4. Check DD[/.-]MM[/.-]YY (2-digit year)
    m_dmy2 = re.match(r"^(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{2})$", s)
    if m_dmy2:
        day, month, yy = int(m_dmy2.group(1)), int(m_dmy2.group(2)), int(m_dmy2.group(3))
        year = 2000 + yy if yy < 70 else 1900 + yy
        if month > 12 and day <= 12:
            day, month = month, day
        try:
            return date(year, month, day)
        except ValueError:
            pass

    # 5. Check 'DD Month YYYY' or 'DD Month YY' (e.g. '12 April 2023', '12-Apr-2023', '12 Okt 22')
    m_text = re.match(r"^(\d{1,2})[-/ ]+([a-zA-Z]+)[-/ ]+(\d{2,4})$", s)
    if m_text:
        day = int(m_text.group(1))
        mon_str = m_text.group(2).lower()
        yr_val = int(m_text.group(3))
        year = yr_val if yr_val >= 100 else (2000 + yr_val if yr_val < 70 else 1900 + yr_val)
        month = MONTH_NAMES.get(mon_str)
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    # 6. Check 'Month DD, YYYY' (e.g. 'April 12, 2023')
    m_text2 = re.match(r"^([a-zA-Z]+)[-/ ]+(\d{1,2})[,\s]+(\d{2,4})$", s)
    if m_text2:
        mon_str = m_text2.group(1).lower()
        day = int(m_text2.group(2))
        yr_val = int(m_text2.group(3))
        year = yr_val if yr_val >= 100 else (2000 + yr_val if yr_val < 70 else 1900 + yr_val)
        month = MONTH_NAMES.get(mon_str)
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass

    return None


def _is_grounded(raw_value: Optional[str], doc_text: str) -> bool:
    """
    Check if raw_value appears in doc_text (OCR text).
    Case-insensitive, NFKC-normalized matching. Also checks
    digit sequence presence for numeric values.
    """
    if not raw_value or not doc_text:
        return False

    raw_clean = clean_text(raw_value)
    if not raw_clean:
        return False

    raw_lower = raw_clean.lower()
    doc_clean = unicodedata.normalize("NFKC", doc_text).lower()

    # Direct substring match
    if raw_lower in doc_clean:
        return True

    # For amounts/numbers, also check if digit string matches
    digits = re.sub(r"\D", "", raw_lower)
    if len(digits) >= 3:
        doc_digits = re.sub(r"\D", "", doc_clean)
        if digits in doc_digits:
            return True

    return False


def normalize_invoice(
    raw: InvoiceExtraction,
    doc_id: str,
    filename: str,
    doc_text: str = "",
) -> NormalizedInvoice:
    """
    Convert raw string extractions into normalized amounts, line items,
    and generate FieldResult objects for each field, setting grounded = True
    if the raw_value appears in doc_text.

    Args:
        raw: InvoiceExtraction structured output from LLM.
        doc_id: Unique document identifier.
        filename: Original source filename.
        doc_text: Full OCR / Markdown text from Docling for grounding verification.

    Returns:
        NormalizedInvoice object ready for Parquet persistence and UI presentation.
    """
    # 1. Normalize metadata
    vendor_name = clean_text(raw.vendor_name)
    invoice_number = clean_text(raw.invoice_number)
    invoice_date = normalize_date(raw.invoice_date)
    currency = clean_text(raw.currency)
    payment_method = clean_text(raw.payment_method)

    # 2. Normalize scalar amounts
    subtotal = parse_amount(raw.subtotal)
    discount = parse_amount(raw.discount)
    # Deductions like discount in invoice equations are positive magnitudes
    if discount is not None and discount < 0:
        discount = abs(discount)

    service_charge = parse_amount(raw.service_charge)
    tax = parse_amount(raw.tax)
    total = parse_amount(raw.total)
    amount_paid = parse_amount(raw.amount_paid)
    change = parse_amount(raw.change)

    # 3. Normalize line items
    norm_line_items: List[NormalizedLineItem] = []
    for idx, item in enumerate(raw.line_items):
        item_desc = clean_text(item.description)
        item_qty = parse_amount(item.quantity)
        item_unit_price = parse_amount(item.unit_price)
        item_total = parse_amount(item.line_total)
        item_mods = [clean_text(m) for m in item.modifiers if clean_text(m)]

        norm_line_items.append(
            NormalizedLineItem(
                item_idx=idx,
                description=item_desc,
                quantity=item_qty,
                unit_price=item_unit_price,
                line_total=item_total,
                modifiers=item_mods,
            )
        )

    # 4. Generate FieldResult objects for extracted non-null fields
    field_results: List[FieldResult] = []

    def _add_field(
        path: str,
        raw_val: Optional[str],
        val_str: Optional[str] = None,
        numeric_val: Optional[Decimal] = None,
        dt_val: Optional[date] = None,
    ):
        if raw_val is not None and raw_val.strip() != "":
            field_results.append(
                FieldResult(
                    field_path=path,
                    raw_value=raw_val,
                    value_str=val_str,
                    numeric_value=numeric_val,
                    date_value=dt_val,
                    grounded=_is_grounded(raw_val, doc_text),
                )
            )

    _add_field("vendor_name", raw.vendor_name, val_str=vendor_name)
    _add_field("invoice_number", raw.invoice_number, val_str=invoice_number)
    _add_field(
        "invoice_date",
        raw.invoice_date,
        val_str=invoice_date.isoformat() if invoice_date else None,
        dt_val=invoice_date,
    )
    _add_field("currency", raw.currency, val_str=currency)
    _add_field(
        "subtotal",
        raw.subtotal,
        val_str=f"{subtotal:.2f}" if subtotal is not None else None,
        numeric_val=subtotal,
    )
    _add_field(
        "discount",
        raw.discount,
        val_str=f"{discount:.2f}" if discount is not None else None,
        numeric_val=discount,
    )
    _add_field(
        "service_charge",
        raw.service_charge,
        val_str=f"{service_charge:.2f}" if service_charge is not None else None,
        numeric_val=service_charge,
    )
    _add_field(
        "tax",
        raw.tax,
        val_str=f"{tax:.2f}" if tax is not None else None,
        numeric_val=tax,
    )
    _add_field(
        "total",
        raw.total,
        val_str=f"{total:.2f}" if total is not None else None,
        numeric_val=total,
    )
    _add_field("payment_method", raw.payment_method, val_str=payment_method)
    _add_field(
        "amount_paid",
        raw.amount_paid,
        val_str=f"{amount_paid:.2f}" if amount_paid is not None else None,
        numeric_val=amount_paid,
    )
    _add_field(
        "change",
        raw.change,
        val_str=f"{change:.2f}" if change is not None else None,
        numeric_val=change,
    )

    # Line item fields
    for idx, raw_item in enumerate(raw.line_items):
        norm_item = norm_line_items[idx]
        _add_field(
            f"line_items[{idx}].description",
            raw_item.description,
            val_str=norm_item.description,
        )
        _add_field(
            f"line_items[{idx}].quantity",
            raw_item.quantity,
            val_str=str(norm_item.quantity) if norm_item.quantity is not None else None,
            numeric_val=norm_item.quantity,
        )
        _add_field(
            f"line_items[{idx}].unit_price",
            raw_item.unit_price,
            val_str=f"{norm_item.unit_price:.2f}" if norm_item.unit_price is not None else None,
            numeric_val=norm_item.unit_price,
        )
        _add_field(
            f"line_items[{idx}].line_total",
            raw_item.line_total,
            val_str=f"{norm_item.line_total:.2f}" if norm_item.line_total is not None else None,
            numeric_val=norm_item.line_total,
        )

    return NormalizedInvoice(
        doc_id=doc_id,
        source_filename=filename,
        vendor_name=vendor_name,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        currency=currency,
        subtotal=subtotal,
        discount=discount,
        service_charge=service_charge,
        tax=tax,
        total=total,
        amount_paid=amount_paid,
        change=change,
        payment_method=payment_method,
        line_items=norm_line_items,
        fields=field_results,
        n_items=len(norm_line_items),
        status="ok",
    )
