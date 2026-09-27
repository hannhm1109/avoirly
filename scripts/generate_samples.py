"""Rebuild synthetic document fixtures, never real supplier documents."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
pair = json.loads((SAMPLES / "pair.json").read_text(encoding="utf-8"))["extraction"]


def lines(doc, invoice=False):
    return [
        "SYNTHETIC SAMPLE - AVOIRLY",
        "INVOICE" if invoice else "PURCHASE ORDER",
        f"Document number: {doc['document_number']}",
        f"Date: {doc['document_date']}",
        *(
            [
                f"Purchase order reference: {doc['purchase_order_reference']}",
                f"Due date: {doc['due_date']}",
            ]
            if invoice
            else []
        ),
        "Supplier: Atlas Supplies | Tax ID: 12345678",
        "Buyer: Example Cafe",
        "Currency: MAD | All unit prices exclude tax",
        "No discounts, freight, fees or adjustments",
        "SKU | Description | Qty | Unit | Unit price | Tax rate | Line total",
        "OIL-5L | Huile vegetale 5L | "
        + ("22" if invoice else "20")
        + " | piece | 100.00 | 20% | "
        + ("2200.00" if invoice else "2000.00"),
        f"Subtotal excluding tax: {doc['subtotal']} MAD",
        f"Tax total: {doc['tax_total']} MAD",
        f"Total including tax: {doc['total']} MAD",
    ]


writer = PdfWriter()
page = writer.add_blank_page(width=842, height=595)
font = writer._add_object(
    DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
)
page[NameObject("/Resources")] = DictionaryObject(
    {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
)
stream = DecodedStreamObject()
commands = ["BT /F1 12 Tf 35 555 Td 25 TL"]
for index, line in enumerate(lines(pair["purchase_order"])):
    escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    commands.append(("T* " if index else "") + f"({escaped}) Tj")
commands.append("ET")
stream.set_data("\n".join(commands).encode("ascii"))
page[NameObject("/Contents")] = writer._add_object(stream)
writer.write(SAMPLES / "po.pdf")

image = Image.new("RGB", (1800, 1100), "white")
draw = ImageDraw.Draw(image)
font = ImageFont.load_default(size=24)
for index, line in enumerate(lines(pair["invoice"], invoice=True)):
    draw.text((45, 40 + index * 57), line, fill="black", font=font)
image.save(SAMPLES / "invoice.png")
print("Wrote synthetic samples/po.pdf and samples/invoice.png")
