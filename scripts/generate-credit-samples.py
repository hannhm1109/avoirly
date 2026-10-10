"""Generate visibly synthetic partial-credit proofs for Phase 5 browser checks."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
invoice = json.loads((root / "samples/pair.json").read_text(encoding="utf-8"))[
    "extraction"
]["invoice"]
for number, amount in ((1, "75.25"), (2, "124.75")):
    image = Image.new("RGB", (1400, 780), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=24)
    lines = [
        "SYNTHETIC SAMPLE - AVOIRLY - NOT A REAL CREDIT",
        f"CREDIT NOTE CN-{number}",
        "Date: 2026-10-10",
        "Supplier: Atlas Supplies | Tax ID: 12345678",
        "Buyer: Example Cafe",
        f"Invoice reference: {invoice['document_number']}",
        "Currency: MAD",
        f"Partial credit excluding tax: {amount} MAD",
        "Net-only tracking fixture. No tax or cash receipt claim.",
    ]
    for index, line in enumerate(lines):
        draw.text((40, 40 + index * 65), line, fill="black", font=font)
    image.save(root / f"samples/credit-note-{number}.png")
print("Wrote two visibly synthetic partial credit notes.")
