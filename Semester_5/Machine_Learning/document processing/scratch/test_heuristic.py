import re
from pathlib import Path
from decimal import Decimal
from src.schema.invoice import ParsedDoc, InvoiceExtraction, LineItem
from src.pipeline.normalize import parse_amount

p = Path("data/cache/docling/cord_train_0000.json")
doc = ParsedDoc.model_validate_json(p.read_text(encoding="utf-8"))

def extract_heuristic_from_ocr(parsed: ParsedDoc) -> InvoiceExtraction:
    text = parsed.text
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Vendor is typically in top 3 lines
    vendor_candidates = [l for l in lines[:5] if len(l) > 2 and not re.match(r"^\d+[xX]?$", l)]
    vendor = vendor_candidates[0] if vendor_candidates else "RECEIPT STORE"

    # Identify amounts and keywords
    total_val = None
    subtotal_val = None
    tax_val = None
    service_val = None
    discount_val = None

    for i, line in enumerate(lines):
        lower = line.lower()
        # Look for total
        if any(k in lower for k in ["grand total", "total", "jumlah", "tagihan", "tota1", "tota"]):
            # Find closest amount line or amount in line
            amt_match = re.search(r"[\d.,]{3,}", line)
            if amt_match:
                total_val = amt_match.group(0)
            elif i + 1 < len(lines):
                next_amt = re.search(r"[\d.,]{3,}", lines[i+1])
                if next_amt:
                    total_val = next_amt.group(0)

        if "sub-total" in lower or "subtotal" in lower or "sub total" in lower:
            amt_match = re.search(r"[\d.,]{3,}", line)
            if amt_match:
                subtotal_val = amt_match.group(0)
            elif i + 1 < len(lines):
                next_amt = re.search(r"[\d.,]{3,}", lines[i+1])
                if next_amt:
                    subtotal_val = next_amt.group(0)

        if "pb1" in lower or "tax" in lower or "ppn" in lower:
            amt_match = re.search(r"[\d.,]{3,}", line)
            if amt_match:
                tax_val = amt_match.group(0)
            elif i + 1 < len(lines):
                next_amt = re.search(r"[\d.,]{3,}", lines[i+1])
                if next_amt:
                    tax_val = next_amt.group(0)

        if "service" in lower:
            amt_match = re.search(r"[\d.,]{3,}", line)
            if amt_match:
                service_val = amt_match.group(0)
            elif i + 1 < len(lines):
                next_amt = re.search(r"[\d.,]{3,}", lines[i+1])
                if next_amt:
                    service_val = next_amt.group(0)

    # Line items: find items with name and price
    items = []
    # If document has separate blocks (item names and prices)
    names = []
    prices = []
    for line in lines:
        if any(k in line.lower() for k in ["total", "sub", "pb1", "service", "rounding", "cash", "change", "kembali"]):
            continue
        cleaned_num = parse_amount(line)
        if cleaned_num is not None and cleaned_num > 100:
            prices.append(line)
        elif len(line) > 2 and not re.match(r"^\d+[xX]?$", line):
            names.append(line)

    for idx, name in enumerate(names[:len(prices)]):
        p_val = prices[idx] if idx < len(prices) else None
        items.append(LineItem(description=name, quantity="1", line_total=p_val))

    return InvoiceExtraction(
        vendor_name=vendor,
        line_items=items,
        subtotal=subtotal_val,
        tax=tax_val,
        service_charge=service_val,
        total=total_val or (prices[-1] if prices else "0"),
        currency="Rp",
    )

ext = extract_heuristic_from_ocr(doc)
print("HEURISTIC VENDOR:", ext.vendor_name)
print("HEURISTIC ITEMS COUNT:", len(ext.line_items))
print("HEURISTIC TOTAL:", ext.total)
print("HEURISTIC SUBTOTAL:", ext.subtotal)
