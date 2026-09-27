from typing import Literal

from pydantic import Field

from ..models import DocumentExtractionResult, StrictModel


class VersionRequest(StrictModel):
    expected_version: int = Field(ge=1)


class AnalyzeRequest(VersionRequest):
    language: Literal["fr", "en"] = "fr"


class LineMapping(StrictModel):
    po_line_number: int = Field(gt=0)
    invoice_line_number: int = Field(gt=0)


class ReviewRequest(VersionRequest):
    corrected: DocumentExtractionResult
    reason: str = Field(min_length=1, max_length=2000)
    confirm_pair: bool = False
    mappings: list[LineMapping] = Field(default_factory=list, max_length=100)


class EditDraftRequest(VersionRequest):
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=20000)


class CloseRequest(VersionRequest):
    close_reason: Literal["NO_ISSUE", "DISMISSED", "UNSUPPORTED", "EXPORTED", "ABANDONED"]


class DeleteRequest(VersionRequest):
    confirmed: Literal[True]
