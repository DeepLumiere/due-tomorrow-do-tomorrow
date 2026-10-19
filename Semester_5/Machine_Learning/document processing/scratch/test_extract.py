import json
import time
from pathlib import Path
import ollama
from src.schema.invoice import ParsedDoc, InvoiceExtraction

p = Path("data/cache/docling/cord_train_0000.json")
doc = ParsedDoc.model_validate_json(p.read_text(encoding="utf-8"))

client = ollama.Client()
t0 = time.time()

prompt = """Extract the receipt/invoice data as a JSON object adhering to:
{
  "vendor_name": "Store Name",
  "invoice_date": "Date as printed",
  "currency": "Rp",
  "line_items": [
    {"description": "Item name", "quantity": "1", "unit_price": "10.000", "line_total": "10.000"}
  ],
  "subtotal": "subtotal amount",
  "tax": "tax amount",
  "service_charge": "service amount",
  "discount": "discount amount or null",
  "total": "grand total amount"
}

Document Text:
""" + doc.text[:1200]

print("Sending chat request to Ollama...")
resp = client.chat(
    model="gemma3:1b",
    messages=[{"role": "user", "content": prompt}],
    format="json",
    options={"temperature": 0.0}
)
print("Extract completed in", round(time.time() - t0, 2), "s")
raw_text = resp.message.content
print("RAW TEXT:")
print(raw_text)

parsed_obj = json.loads(raw_text)
extraction = InvoiceExtraction.model_validate(parsed_obj)
print("SUCCESS! Line items count:", len(extraction.line_items))
print("TOTAL:", extraction.total)
print("SUBTOTAL:", extraction.subtotal)
