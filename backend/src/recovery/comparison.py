"""Pure Decimal arithmetic. One finding per product; no cross-product offsets."""

from decimal import ROUND_HALF_UP, Decimal, localcontext

from .matching import Matches, match_lines
from .models import ComparisonResult, Finding, ValidatedPair
from .validation import issue

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
LIMITATION = "PO versus invoice checks do not establish delivery, amendments, or credit owed."


def line_difference(qo, po, qi, pi):
    if any(not isinstance(v, Decimal) or not v.is_finite() for v in (qo, po, qi, pi)):
        raise ValueError("Only finite validated Decimal inputs are accepted.")
    if qo <= 0 or qi <= 0 or po < 0 or pi < 0:
        raise ValueError("Unsupported quantity or price.")
    with localcontext() as ctx:
        ctx.prec = 48
        quantity = max(qi - qo, ZERO) * pi
        price = min(qi, qo) * (pi - po)
        candidate = max(quantity + price, ZERO).quantize(CENT, rounding=ROUND_HALF_UP)
        return quantity, price, candidate if candidate > CENT else ZERO


def needs_review(issues, currency=None, warnings=None):
    return ComparisonResult(
        outcome="NEEDS_REVIEW",
        currency=currency,
        findings=[],
        review_issues=issues,
        potential_credit_net=None,
        warnings=warnings or [],
    )


def compare(pair: ValidatedPair, matches: Matches | None = None) -> ComparisonResult:
    checked = match_lines(pair)
    if isinstance(checked, list):
        return needs_review(checked, pair.invoice.currency)
    if matches is not None and matches != checked:
        return needs_review([issue("INVALID_MATCH_SET")], pair.invoice.currency)
    matches = checked
    findings, issues = [], []
    warnings = list(matches.warnings) + [
        LIMITATION,
        "Cumulative billing across multiple invoices is outside these checks.",
    ]
    for po, inv in matches.lines:
        quantity, price, candidate = line_difference(
            po.quantity, po.unit_price, inv.quantity, inv.unit_price
        )
        if inv.quantity < po.quantity:
            warnings.append(f"Invoice line {inv.line_number}: quantity below PO; partial billing.")
        if inv.unit_price < po.unit_price:
            warnings.append(f"Invoice line {inv.line_number}: lower unit price than PO.")
        if inv.quantity > po.quantity and candidate == ZERO:
            issues.append(
                issue(
                    "EXCESS_QUANTITY_WITHOUT_NET_CREDIT",
                    "INVOICE",
                    inv.line_number,
                    message="Quantity exceeds the PO but no positive claim remains.",
                )
            )
        if candidate > ZERO:
            reasons = []
            if inv.quantity > po.quantity:
                reasons.append("QUANTITY_ABOVE_PO")
            if inv.unit_price > po.unit_price:
                reasons.append("PRICE_ABOVE_PO")
            findings.append(
                Finding(
                    po_line_number=po.line_number,
                    invoice_line_number=inv.line_number,
                    reasons=reasons,
                    ordered_quantity=po.quantity,
                    invoiced_quantity=inv.quantity,
                    po_unit_price=po.unit_price,
                    invoice_unit_price=inv.unit_price,
                    quantity_component_net=quantity,
                    price_component_net=price,
                    potential_credit_net=candidate,
                    po_source=po.source,
                    invoice_source=inv.source,
                )
            )
    if issues:
        return needs_review(issues, pair.invoice.currency, warnings)
    with localcontext() as ctx:
        ctx.prec = 48
        total = sum((f.potential_credit_net for f in findings), ZERO)
    return ComparisonResult(
        outcome="DISCREPANCY_FOUND" if findings else "NO_DISCREPANCY",
        currency=pair.invoice.currency,
        findings=findings,
        review_issues=[],
        potential_credit_net=total,
        warnings=warnings,
    )
