import json
import re

malformed = '{"vendor_name": "Nasi Campur Bali", "invoice_date": "2023-08-28", "currency": "Rp", "line_items": [{"description": "Nasi Campur Bali", "quantity": "1", "unit_price": "10.000", "line_total": "10.000"}], "total": "150,000"}, "]}] </body> */"'

def repair_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    # Extract outermost valid JSON object
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    while last_brace > first_brace and last_brace != -1:
        candidate = text[first_brace:last_brace+1]
        try:
            return json.loads(candidate)
        except Exception:
            # Try removing trailing commas
            cleaned = re.sub(r",\s*([\}\]])", r"\1", candidate)
            try:
                return json.loads(cleaned)
            except Exception:
                pass
        # Search backwards for previous '}'
        last_brace = text.rfind("}", first_brace, last_brace)

    return {}

repaired = repair_json(malformed)
print("REPAIR SUCCESS:", repaired.get("vendor_name"), repaired.get("total"), len(repaired.get("line_items", [])))
