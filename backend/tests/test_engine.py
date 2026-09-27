from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal, localcontext

import pytest

from recovery.claims import generate_claim
from recovery.comparison import compare, line_difference
from recovery.matching import match_lines
from recovery.models import DocumentExtractionResult, PairConfirmation
from recovery.validation import decimal_value, revision_hash, validate_pair
from recovery.workflow import analyze_extraction

D = Decimal
PAGES = {"PO": 1, "INVOICE": 1}


def recalc(doc):
    for row in doc.line_items:
        row.line_total = str(D(row.quantity) * D(row.unit_price))
    doc.subtotal = str(sum(D(r.line_total) for r in doc.line_items))
    doc.tax_total = str(
        sum(
            (D(r.line_total) * D(r.tax_rate) / 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)
            for r in doc.line_items
        )
    )
    doc.total = str(D(doc.subtotal) + D(doc.tax_total))


@pytest.mark.parametrize(
    "qi,pi,outcome,amount",
    [
        ("20", "100", "NO_DISCREPANCY", "0.00"),
        ("22", "100", "DISCREPANCY_FOUND", "200.00"),
        ("20", "110", "DISCREPANCY_FOUND", "200.00"),
        ("22", "110", "DISCREPANCY_FOUND", "420.00"),
        ("10", "110", "DISCREPANCY_FOUND", "100.00"),
        ("22", "90", "NEEDS_REVIEW", None),
        ("23", "90", "DISCREPANCY_FOUND", "70.00"),
    ],
)
def test_spec_examples(pair, qi, pi, outcome, amount):
    pair.invoice.line_items[0].quantity = qi
    pair.invoice.line_items[0].unit_price = pi
    recalc(pair.invoice)
    report = analyze_extraction(pair, page_counts=PAGES)
    assert report["comparison"]["outcome"] == outcome
    assert report["comparison"]["potential_credit_net"] == amount
    assert (report["claim_draft"] is not None) == (outcome == "DISCREPANCY_FOUND")
    if qi == "22" and pi == "110":
        finding = report["comparison"]["findings"][0]
        assert finding["quantity_component_net"] == "220"
        assert D(finding["price_component_net"]) == D("200")
        assert len(report["comparison"]["findings"]) == 1


@pytest.mark.parametrize(
    "difference,expected", [("0.01", "0.00"), ("0.02", "0.02"), ("0.025", "0.03")]
)
def test_rounding_boundary(difference, expected):
    assert line_difference(D(1), D(100), D(1), D(100) + D(difference))[2] == D(expected)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        1.2,
        1,
        True,
        "NaN",
        "Infinity",
        "-Infinity",
        "1e2",
        "1,00",
        "1,000.00",
        " 1",
        "+1",
        "01",
        ".5",
        "1.",
        "1.0000001",
        "1000000000000",
        "١٢",
    ],
)
def test_bad_numbers_never_reach_arithmetic(bad):
    with pytest.raises(ValueError):
        decimal_value(bad)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("quantity", None, "INVALID_NUMBER"),
        ("quantity", "0", "INVALID_NUMBER"),
        ("quantity", "-1", "INVALID_NUMBER"),
        ("unit_price", "NaN", "INVALID_NUMBER"),
        ("unit_price", "-1", "INVALID_NUMBER"),
        ("tax_rate", None, "INVALID_NUMBER"),
        ("tax_rate", "101", "INVALID_NUMBER"),
        ("description", " ", "MISSING_VALUE"),
        ("unit", None, "UNSUPPORTED_UNIT"),
        ("unit", "pallet", "UNSUPPORTED_UNIT"),
        ("line_number", 0, "INVALID_LINE_NUMBER"),
        ("line_total", "50", "LINE_TOTAL_MISMATCH"),
    ],
)
def test_invalid_line_blocks_draft(pair, field, value, code):
    setattr(pair.invoice.line_items[0], field, value)
    report = analyze_extraction(pair, page_counts=PAGES)
    assert report["status"] == "NEEDS_REVIEW"
    assert code in {i["code"] for i in report["review_issues"]}
    assert report["comparison"]["potential_credit_net"] is None
    assert report["comparison"]["findings"] == []
    assert report["claim_draft"] is None


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("document_type", "CREDIT_NOTE", "WRONG_DOCUMENT_TYPE"),
        ("prices_include_tax", True, "UNSUPPORTED_TAX_BASIS"),
        ("prices_include_tax", None, "UNSUPPORTED_TAX_BASIS"),
        ("adjustments_present", True, "UNSUPPORTED_ADJUSTMENTS"),
        ("adjustments_present", None, "UNSUPPORTED_ADJUSTMENTS"),
        ("currency", "JPY", "UNSUPPORTED_CURRENCY"),
        ("currency", "EUR", "CURRENCY_MISMATCH"),
        ("document_number", None, "MISSING_VALUE"),
        ("document_date", "2026-02-30", "INVALID_DATE"),
        ("document_date", "20260915", "INVALID_DATE"),
        ("due_date", "15/10/2026", "INVALID_DATE"),
        ("subtotal", "0", "DOCUMENT_TOTAL_MISMATCH"),
        ("tax_total", "0", "DOCUMENT_TOTAL_MISMATCH"),
        ("total", "0", "DOCUMENT_TOTAL_MISMATCH"),
        ("purchase_order_reference", "PO-WRONG", "PO_REFERENCE_MISMATCH"),
        ("warnings", ["Unreadable page"], "EXTRACTION_WARNING"),
    ],
)
def test_document_checks(pair, field, value, code):
    setattr(pair.invoice, field, value)
    issues = validate_pair(pair, page_counts=PAGES)
    assert isinstance(issues, list)
    assert code in {i.code for i in issues}


@pytest.mark.parametrize(
    "party,field,value",
    [
        ("supplier", "name", "Other supplier"),
        ("buyer", "name", "Other buyer"),
        ("supplier", "tax_id", "999"),
        ("buyer", "tax_id", "999"),
        ("supplier", "name", "  "),
    ],
)
def test_identity_mismatch(pair, party, field, value):
    if party == "buyer" and field == "tax_id":
        pair.purchase_order.buyer.tax_id = "123"
    setattr(getattr(pair.invoice, party), field, value)
    assert isinstance(validate_pair(pair, page_counts=PAGES), list)


def test_pair_confirmation_is_revision_bound(pair):
    pair.invoice.purchase_order_reference = None
    assert validate_pair(pair, page_counts=PAGES)[0].code == "PAIR_CONFIRMATION_REQUIRED"
    confirmation = PairConfirmation(
        actor="Hanane", reason="Checked the supplier order", revision_hash=revision_hash(pair)
    )
    assert not isinstance(validate_pair(pair, confirmation, page_counts=PAGES), list)
    pair.invoice.document_number = "INV-NEW"
    assert isinstance(validate_pair(pair, confirmation, page_counts=PAGES), list)


def test_confirmation_does_not_override_other_failure(pair):
    pair.invoice.purchase_order_reference = None
    pair.invoice.prices_include_tax = True
    report = analyze_extraction(
        pair, page_counts=PAGES, confirmation_actor="Hanane", confirmation_reason="Verified pairing"
    )
    assert report["status"] == "NEEDS_REVIEW"
    assert report["confirmations"][0]["revision_hash"] == revision_hash(pair)


@pytest.mark.parametrize("role", ["purchase_order", "invoice"])
def test_duplicate_sku_blocks(pair, role):
    doc = getattr(pair, role)
    new = deepcopy(doc.line_items[0])
    new.line_number = 2
    doc.line_items.append(new)
    recalc(doc)
    report = analyze_extraction(pair, page_counts=PAGES)
    assert "DUPLICATE_SKU" in {i["code"] for i in report["review_issues"]}


def test_reordered_lines_match_by_key(pair):
    for doc in (pair.purchase_order, pair.invoice):
        new = deepcopy(doc.line_items[0])
        new.line_number, new.sku, new.description = 2, "SOAP-1L", "Soap 1L"
        doc.line_items.append(new)
    pair.invoice.line_items.reverse()
    for doc in (pair.purchase_order, pair.invoice):
        recalc(doc)
    validated = validate_pair(pair, page_counts=PAGES)
    matches = match_lines(validated)
    assert [(p.sku, i.sku) for p, i in matches.lines] == [
        ("SOAP-1L", "SOAP-1L"),
        ("OIL-5L", "OIL-5L"),
    ]
    assert compare(validated).potential_credit_net == D("400.00")


def test_description_fallback_normalizes_accents_space_case(pair):
    pair.invoice.line_items[0].sku = None
    pair.invoice.line_items[0].description = " HUILE   VÉGÉTALE 5L "
    pair.invoice.line_items[0].unit = "pièce"
    assert analyze_extraction(pair, page_counts=PAGES)["status"] == "CLAIM_DRAFTED"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("sku", "OIL5L", "UNMATCHED_INVOICE_LINE"),
        ("sku", "0OIL-5L", "UNMATCHED_INVOICE_LINE"),
        ("unit", "box", "UNIT_MISMATCH"),
        ("description", "Huile vegetale 10L", "DESCRIPTION_MISMATCH"),
        ("tax_rate", "10", "TAX_RATE_MISMATCH"),
    ],
)
def test_conflicting_product_attributes(pair, field, value, code):
    setattr(pair.invoice.line_items[0], field, value)
    recalc(pair.invoice)
    report = analyze_extraction(pair, page_counts=PAGES)
    assert code in {i["code"] for i in report["review_issues"]}


def test_ambiguous_description(pair):
    pair.invoice.line_items[0].sku = None
    new = deepcopy(pair.purchase_order.line_items[0])
    new.sku, new.line_number = "OTHER", 2
    pair.purchase_order.line_items.append(new)
    recalc(pair.purchase_order)
    assert "AMBIGUOUS_DESCRIPTION" in {
        i["code"] for i in analyze_extraction(pair, page_counts=PAGES)["review_issues"]
    }


def test_unmatched_po_is_information_only(pair):
    new = deepcopy(pair.purchase_order.line_items[0])
    new.sku, new.line_number, new.description = "SOAP", 2, "Soap"
    pair.purchase_order.line_items.append(new)
    recalc(pair.purchase_order)
    report = analyze_extraction(pair, page_counts=PAGES)
    assert report["status"] == "CLAIM_DRAFTED"
    assert any("not billed" in w for w in report["comparison"]["warnings"])


def test_favorable_other_product_cannot_offset_claim(pair):
    for doc in (pair.purchase_order, pair.invoice):
        new = deepcopy(doc.line_items[0])
        new.sku, new.line_number, new.description, new.quantity = "SOAP", 2, "Soap", "20"
        new.unit_price = "10" if doc is pair.invoice else "100"
        doc.line_items.append(new)
        recalc(doc)
    assert (
        analyze_extraction(pair, page_counts=PAGES)["comparison"]["potential_credit_net"]
        == "200.00"
    )


def test_case_level_review_discards_other_findings(pair):
    for doc in (pair.purchase_order, pair.invoice):
        new = deepcopy(doc.line_items[0])
        new.sku, new.line_number, new.description = "SOAP", 2, "Soap"
        new.unit_price = "90" if doc is pair.invoice else "100"
        doc.line_items.append(new)
        recalc(doc)
    report = analyze_extraction(pair, page_counts=PAGES)
    assert report["status"] == "NEEDS_REVIEW"
    assert report["comparison"]["findings"] == []


@pytest.mark.parametrize("page", [0, 2, -1])
def test_source_page_bounds(pair, page):
    pair.invoice.line_items[0].source.page = page
    assert "INVALID_SOURCE_PAGE" in {i.code for i in validate_pair(pair, page_counts=PAGES)}


def test_source_text_required(pair):
    pair.invoice.line_items[0].source.text = None
    assert isinstance(validate_pair(pair, page_counts=PAGES), list)


@pytest.mark.parametrize("count", [0, 101])
def test_line_limits(pair, count):
    pair.invoice.line_items = [deepcopy(pair.invoice.line_items[0]) for _ in range(count)]
    assert "LINE_LIMIT" in {i.code for i in validate_pair(pair, page_counts=PAGES)}


def test_explicit_zero_tax_and_missing_optional_fields(pair):
    for doc in (pair.purchase_order, pair.invoice):
        doc.line_items[0].tax_rate = "0"
        doc.supplier.tax_id = None
        recalc(doc)
    pair.invoice.due_date = None
    assert analyze_extraction(pair, page_counts=PAGES)["status"] == "CLAIM_DRAFTED"


def test_money_precision_does_not_depend_on_calling_thread():
    with localcontext() as ctx:
        ctx.prec = 6
        amount = line_difference(
            D("999999999999.999999"),
            D("999999999999.999998"),
            D("999999999999.999999"),
            D("999999999999.999999"),
        )[2]
    assert amount == D("1000000.00")


@pytest.mark.parametrize("language", ["fr", "en"])
def test_drafts_only_use_validated_comparison(pair, language):
    validated = validate_pair(pair, page_counts=PAGES)
    result = compare(validated)
    draft = generate_claim(validated, result, language)
    assert "200.00 MAD" in draft.body
    assert "240.00" not in draft.body
    assert "INV-8821" in draft.subject and "PO-124" in draft.subject
    result.potential_credit_net = D("9999")
    with pytest.raises(ValueError):
        generate_claim(validated, result, language)


def test_wire_contract_forbids_extra_fields_and_float(pair_dict):
    pair_dict["invoice"]["line_items"][0]["quantity"] = 22.0
    assert validate_pair(pair_dict, page_counts=PAGES)[0].code == "INVALID_SCHEMA"
    pair_dict["invoice"]["line_items"][0]["quantity"] = "22"
    pair_dict["invoice"]["confidence"] = 0.9
    assert validate_pair(pair_dict, page_counts=PAGES)[0].code == "INVALID_SCHEMA"


def test_required_nullable_schema_fields():
    schema = DocumentExtractionResult.model_json_schema()
    for definition in schema["$defs"].values():
        assert set(definition["required"]) == set(definition["properties"])
        assert definition["additionalProperties"] is False
