"""Unique exact matches only. No fuzzy matching or automatic unit conversion."""

from collections import Counter
from dataclasses import dataclass

from .models import ReviewIssue, ValidatedLine, ValidatedPair
from .validation import description_key, issue, key


@dataclass(frozen=True)
class Matches:
    lines: tuple[tuple[ValidatedLine, ValidatedLine], ...]
    warnings: tuple[str, ...]


def match_lines(pair: ValidatedPair) -> Matches | list[ReviewIssue]:
    pos, invs = pair.purchase_order.line_items, pair.invoice.line_items
    issues, matched, warnings, used = [], [], [], set()
    for role, lines in (("PO", pos), ("INVOICE", invs)):
        counts = Counter(key(r.sku) for r in lines if key(r.sku))
        for sku, count in counts.items():
            if count > 1:
                issues.append(
                    issue(
                        "DUPLICATE_SKU",
                        role,
                        field="sku",
                        message=f"SKU {sku!r} is repeated; correct the lines.",
                    )
                )
    if issues:
        return issues
    po_desc = Counter(description_key(r.description) for r in pos)
    inv_desc = Counter(description_key(r.description) for r in invs)
    for inv in invs:
        candidates = [po for po in pos if key(inv.sku) and key(po.sku) == key(inv.sku)]
        if not candidates:
            desc = description_key(inv.description)
            candidates = [
                po
                for po in pos
                if (not key(po.sku) or not key(inv.sku)) and description_key(po.description) == desc
            ]
            if candidates and (po_desc[desc] != 1 or inv_desc[desc] != 1):
                issues.append(
                    issue("AMBIGUOUS_DESCRIPTION", "INVOICE", inv.line_number, "description")
                )
                continue
        if len(candidates) != 1:
            issues.append(issue("UNMATCHED_INVOICE_LINE", "INVOICE", inv.line_number))
            continue
        po = candidates[0]
        if po.line_number in used:
            issues.append(issue("AMBIGUOUS_MATCH", "INVOICE", inv.line_number))
            continue
        used.add(po.line_number)
        if po.unit != inv.unit:
            issues.append(issue("UNIT_MISMATCH", "INVOICE", inv.line_number, "unit"))
        if po.tax_rate != inv.tax_rate:
            issues.append(issue("TAX_RATE_MISMATCH", "INVOICE", inv.line_number, "tax_rate"))
        # Exact SKU alone cannot establish whether conflicting descriptions hide pack changes.
        # Conservative first release: review any description change for an exact SKU match.
        if description_key(po.description) != description_key(inv.description):
            issues.append(
                issue(
                    "DESCRIPTION_MISMATCH",
                    "INVOICE",
                    inv.line_number,
                    "description",
                    "Verify description, pack size and model code.",
                )
            )
        matched.append((po, inv))
    for po in pos:
        if po.line_number not in used:
            warnings.append(f"PO line {po.line_number} is not billed; partial billing is possible.")
    return issues if issues else Matches(tuple(matched), tuple(warnings))
