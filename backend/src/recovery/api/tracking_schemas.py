"""Strict manual records: date/amount strings, no implicit float or tax conversion."""

import re
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from .schemas import VersionRequest

MoneyString = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,35})(\.[0-9]{1,2})?$", max_length=39)]
Currency = Literal["MAD", "EUR", "USD", "GBP"]


class SentRequest(VersionRequest):
    occurred_on: date
    recipient: str = Field(min_length=1, max_length=320)
    amount_net: MoneyString
    currency: Currency
    draft_id: UUID
    sent_outside_app: Literal[True]

    @field_validator("occurred_on", mode="before")
    @classmethod
    def iso_date(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Use an ISO calendar date")
        return date.fromisoformat(value)

    @field_validator("sent_outside_app", mode="before")
    @classmethod
    def declared(cls, value):
        if value is not True:
            raise ValueError("Explicit declaration is required")
        return value


class NoteRequest(VersionRequest):
    occurred_on: date
    note: str = Field(min_length=1, max_length=4000)

    _iso_date = field_validator("occurred_on", mode="before")(SentRequest.iso_date.__func__)


class PromiseRequest(NoteRequest):
    amount_net: MoneyString
    currency: Currency
    reference: str = Field(min_length=1, max_length=200)
    due_on: date | None = None

    @field_validator("due_on", mode="before")
    @classmethod
    def due_date(cls, value):
        return SentRequest.iso_date(value) if value is not None else None


class CreditRequest(NoteRequest):
    amount_net: MoneyString
    currency: Currency
    reference: str = Field(min_length=1, max_length=200)
    evidence_id: UUID
    received_and_verified: Literal[True]

    _declared = field_validator("received_and_verified", mode="before")(
        SentRequest.declared.__func__
    )


class VoidRequest(VersionRequest):
    reason: str = Field(min_length=1, max_length=2000)
