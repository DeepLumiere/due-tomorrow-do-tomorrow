import json
import sys
from decimal import Decimal
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.schema.invoice import InvoiceExtraction, NormalizedInvoice, NormalizedLineItem, FieldResult

def test_invoice_extraction_schema():
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "sample_invoice.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    extracted = InvoiceExtraction.model_validate(data)
    assert extracted.vendor_name == "KOPI KENANGAN"
    assert len(extracted.line_items) == 2
    assert extracted.line_items[0].description == "Kopi Kenangan Mantan (R)"
    assert extracted.total == "52.800"

def test_normalized_invoice_schema():
    norm = NormalizedInvoice(
        doc_id="test_001",
        source_filename="test.png",
        vendor_name="KOPI KENANGAN",
        subtotal=Decimal("48000.00"),
        total=Decimal("52800.00"),
        n_items=2,
        line_items=[
            NormalizedLineItem(
                item_idx=0,
                description="Kopi Kenangan Mantan (R)",
                quantity=Decimal("2"),
                unit_price=Decimal("18000.00"),
                line_total=Decimal("36000.00"),
                confidence=0.98,
                needs_review=False
            )
        ],
        fields=[
            FieldResult(
                field_path="total",
                raw_value="52.800",
                value_str="52800.00",
                numeric_value=Decimal("52800.00"),
                grounded=True,
                confidence=0.95,
                needs_review=False
            )
        ]
    )
    assert norm.total == Decimal("52800.00")
    assert norm.line_items[0].quantity == Decimal("2")
    assert norm.fields[0].grounded is True
