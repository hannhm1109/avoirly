"""Fail closed on unsupported, incomplete, or internally inconsistent extractions."""

import hashlib
import json
import re
import unicodedata
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

from pydantic import ValidationError

from .models import (
    DocumentExtractionResult,
    PairConfirmation,
    ReviewIssue,
    ValidatedDocument,
    ValidatedLine,
    ValidatedPair,
)

CENT = Decimal("0.01")
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,6})?\Z")
UNITS = {
    "piece": "piece",
    "pièce": "piece",
    "pieces": "piece",
    "pièces": "piece",
    "pce": "piece",
    "pcs": "piece",
    "unit": "piece",
    "box": "box",
    "carton": "box",
    "boîte": "box",
    "kg": "kg",
    "kilogramme": "kg",
    "g": "g",
    "gramme": "g",
    "l": "l",
    "litre": "l",
    "ml": "ml",
    "millilitre": "ml",
}


def key(value: str | None) -> str:
    """SKU/identifier normalization preserves punctuation and leading zeroes."""
    return unicodedata.normalize("NFKC", value or "").strip().casefold()


def description_key(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", key(value))
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).split())


def revision_hash(raw: DocumentExtractionResult) -> str:
    data = json.dumps(raw.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()


def issue(code, role="PAIR", line=None, field=None, message=None):
    return ReviewIssue(
        code=code,
        document_role=role,
        line_number=line,
        field=field,
        message=message or code.replace("_", " ").capitalize(),
    )


def decimal_value(value):
    if not isinstance(value, str) or not NUMBER.fullmatch(value):
        raise ValueError(
            "Expected an unambiguous decimal string (12 integer / 6 fractional digits)."
        )
    return Decimal(value)


def _document(raw, role, pages):
    issues = []

    def add(code, field=None, line=None, message=None):
        issues.append(issue(code, role, line, field, message))

    def number(value, field, line=None, positive=False, maximum=None):
        try:
            result = decimal_value(value)
            if (
                result < 0
                or (positive and result == 0)
                or (maximum is not None and result > maximum)
            ):
                raise ValueError("Value is outside the supported range.")
            return result
        except ValueError as exc:
            add("INVALID_NUMBER", field, line, str(exc))
            return None

    def text(value, field, line=None):
        if not value or not value.strip():
            add("MISSING_VALUE", field, line)
            return None
        return value.strip()

    expected = "PURCHASE_ORDER" if role == "PO" else "INVOICE"
    if raw.document_type != expected:
        add("WRONG_DOCUMENT_TYPE", "document_type")
    if raw.prices_include_tax is not False:
        add("UNSUPPORTED_TAX_BASIS", "prices_include_tax")
    if raw.adjustments_present is not False:
        add("UNSUPPORTED_ADJUSTMENTS", "adjustments_present")
    # Warnings describe uncertain extraction or unsupported content; none are silently ignored.
    for warning in raw.warnings:
        add("EXTRACTION_WARNING", "warnings", message=warning)
    doc_number = text(raw.document_number, "document_number")
    for name in ("supplier", "buyer"):
        text(getattr(raw, name).name, name + ".name")
    doc_date = None
    for field in ("document_date", "due_date") if role == "INVOICE" else ("document_date",):
        value = getattr(raw, field)
        if field == "due_date" and value is None:
            continue
        try:
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                raise ValueError
            parsed = date.fromisoformat(value)
            if field == "document_date":
                doc_date = parsed
        except ValueError:
            add("INVALID_DATE", field)
    if raw.currency not in ("MAD", "EUR", "USD", "GBP"):
        add("UNSUPPORTED_CURRENCY", "currency")
    if not 1 <= len(raw.line_items) <= 100:
        add("LINE_LIMIT", "line_items", message="A document must contain 1–100 product lines.")
    lines, numbers = [], set()
    for row in raw.line_items:
        n = row.line_number
        if n <= 0 or n in numbers:
            add("INVALID_LINE_NUMBER", "line_number", n)
        numbers.add(n)
        desc = text(row.description, "description", n)
        unit = UNITS.get(key(row.unit))
        if not unit:
            add("UNSUPPORTED_UNIT", "unit", n)
        if not 1 <= row.source.page <= pages:
            add("INVALID_SOURCE_PAGE", "source.page", n)
        text(row.source.text, "source.text", n)
        values = {
            "quantity": number(row.quantity, "quantity", n, positive=True),
            "unit_price": number(row.unit_price, "unit_price", n),
            "tax_rate": number(row.tax_rate, "tax_rate", n, maximum=100),
            "line_total": number(row.line_total, "line_total", n),
        }
        if all(v is not None for v in values.values()):
            if abs(values["quantity"] * values["unit_price"] - values["line_total"]) > CENT:
                add("LINE_TOTAL_MISMATCH", "line_total", n)
            if desc and unit and n > 0:
                lines.append(
                    ValidatedLine(
                        line_number=n,
                        sku=row.sku,
                        description=desc,
                        unit=unit,
                        source=row.source,
                        **values,
                    )
                )
    totals = {f: number(getattr(raw, f), f) for f in ("subtotal", "tax_total", "total")}
    if len(lines) == len(raw.line_items) and all(v is not None for v in totals.values()):
        checks = {
            "subtotal": sum((r.line_total for r in lines), Decimal(0)),
            "tax_total": sum(
                (
                    (r.line_total * r.tax_rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
                    for r in lines
                ),
                Decimal(0),
            ),
            "total": totals["subtotal"] + totals["tax_total"],
        }
        for field, expected_value in checks.items():
            if abs(totals[field] - expected_value) > CENT:
                add("DOCUMENT_TOTAL_MISMATCH", field)
    if issues:
        return None, issues
    return ValidatedDocument(
        document_number=doc_number,
        document_date=doc_date,
        currency=raw.currency,
        supplier=raw.supplier,
        buyer=raw.buyer,
        line_items=lines,
        **totals,
    ), []


def validate_pair(raw_pair, confirmations=None, *, page_counts):
    """Return a validated pair OR blocking issues; never partially validated data.

    page_counts must come from validated source files (or declared offline fixture metadata).
    """
    try:
        raw = DocumentExtractionResult.model_validate(raw_pair, strict=True)
    except ValidationError as exc:
        return [
            issue("INVALID_SCHEMA", field=".".join(map(str, e["loc"])), message=e["msg"])
            for e in exc.errors(include_input=False)
        ]
    if not isinstance(page_counts, dict) or any(
        type(page_counts.get(role)) is not int or not 1 <= page_counts[role] <= 10
        for role in ("PO", "INVOICE")
    ):
        return [issue("INVALID_PAGE_COUNT")]
    with localcontext() as ctx:
        ctx.prec = 48
        po, issues = _document(raw.purchase_order, "PO", page_counts["PO"])
        inv, inv_issues = _document(raw.invoice, "INVOICE", page_counts["INVOICE"])
        issues.extend(inv_issues)
    for party in ("supplier", "buyer"):
        a, b = getattr(raw.purchase_order, party), getattr(raw.invoice, party)
        if description_key(a.name) != description_key(b.name):
            issues.append(issue(party.upper() + "_MISMATCH", field=party + ".name"))
        if key(a.tax_id) and key(b.tax_id) and key(a.tax_id) != key(b.tax_id):
            issues.append(issue(party.upper() + "_TAX_ID_MISMATCH", field=party + ".tax_id"))
    if raw.purchase_order.currency != raw.invoice.currency:
        issues.append(issue("CURRENCY_MISMATCH", field="currency"))
    if key(raw.invoice.purchase_order_reference):
        if key(raw.invoice.purchase_order_reference) != key(raw.purchase_order.document_number):
            issues.append(issue("PO_REFERENCE_MISMATCH", field="purchase_order_reference"))
    else:
        confirmed = isinstance(confirmations, PairConfirmation) and (
            confirmations.revision_hash == revision_hash(raw)
            and confirmations.actor.strip()
            and confirmations.reason.strip()
        )
        if not confirmed:
            issues.append(
                issue(
                    "PAIR_CONFIRMATION_REQUIRED",
                    field="purchase_order_reference",
                    message="Confirm the pairing with an author and reason.",
                )
            )
    return issues if issues else ValidatedPair(purchase_order=po, invoice=inv)
