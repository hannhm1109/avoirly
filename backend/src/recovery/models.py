"""Extraction wire contracts and internal domain contracts from the build guide."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Party(StrictModel):
    name: str | None
    tax_id: str | None


class SourceRef(StrictModel):
    page: int
    text: str | None


class ExtractedLine(StrictModel):
    line_number: int
    sku: str | None
    description: str | None
    quantity: str | None
    unit: str | None
    unit_price: str | None
    tax_rate: str | None
    line_total: str | None
    source: SourceRef


class ExtractedDocument(StrictModel):
    document_number: str | None
    document_date: str | None
    currency: str | None
    supplier: Party
    buyer: Party
    prices_include_tax: bool | None
    adjustments_present: bool | None
    line_items: list[ExtractedLine]
    subtotal: str | None
    tax_total: str | None
    total: str | None
    warnings: list[str]


class PurchaseOrder(ExtractedDocument):
    document_type: Literal["PURCHASE_ORDER", "OTHER", "UNKNOWN"]


class Invoice(ExtractedDocument):
    document_type: Literal["INVOICE", "CREDIT_NOTE", "OTHER", "UNKNOWN"]
    due_date: str | None
    purchase_order_reference: str | None


class DocumentExtractionResult(StrictModel):
    purchase_order: PurchaseOrder
    invoice: Invoice


class ValidatedLine(StrictModel):
    line_number: int = Field(gt=0)
    sku: str | None
    description: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0, allow_inf_nan=False)
    unit: Literal["piece", "box", "kg", "g", "l", "ml"]
    unit_price: Decimal = Field(ge=0, allow_inf_nan=False)
    tax_rate: Decimal = Field(ge=0, le=100, allow_inf_nan=False)
    line_total: Decimal = Field(ge=0, allow_inf_nan=False)
    source: SourceRef


class ValidatedDocument(StrictModel):
    document_number: str = Field(min_length=1)
    document_date: date
    currency: Literal["MAD", "EUR", "USD", "GBP"]
    supplier: Party
    buyer: Party
    line_items: list[ValidatedLine] = Field(min_length=1)
    subtotal: Decimal = Field(ge=0, allow_inf_nan=False)
    tax_total: Decimal = Field(ge=0, allow_inf_nan=False)
    total: Decimal = Field(ge=0, allow_inf_nan=False)


class ValidatedPair(StrictModel):
    purchase_order: ValidatedDocument
    invoice: ValidatedDocument


class ReviewIssue(StrictModel):
    code: str
    document_role: Literal["PO", "INVOICE", "PAIR"]
    line_number: int | None
    field: str | None
    message: str


class Finding(StrictModel):
    po_line_number: int
    invoice_line_number: int
    reasons: list[Literal["QUANTITY_ABOVE_PO", "PRICE_ABOVE_PO"]]
    ordered_quantity: Decimal
    invoiced_quantity: Decimal
    po_unit_price: Decimal
    invoice_unit_price: Decimal
    quantity_component_net: Decimal
    price_component_net: Decimal
    potential_credit_net: Decimal
    po_source: SourceRef
    invoice_source: SourceRef


class ComparisonResult(StrictModel):
    outcome: Literal["NO_DISCREPANCY", "NEEDS_REVIEW", "DISCREPANCY_FOUND"]
    currency: str | None
    findings: list[Finding]
    review_issues: list[ReviewIssue]
    potential_credit_net: Decimal | None
    warnings: list[str]


class ClaimDraft(StrictModel):
    subject: str
    body: str
    language: Literal["fr", "en"]


class PairConfirmation(StrictModel):
    """Phase 1 confirmation recorded against the exact extraction revision hash."""

    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    revision_hash: str
