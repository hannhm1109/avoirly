"""Explicit opt-in only: sends the bundled synthetic PDF and PNG to OpenAI."""

import os
from pathlib import Path

import pytest

from recovery.cli import run_case


@pytest.mark.live
@pytest.mark.skipif(
    os.environ.get("AVOIRLY_LIVE") != "1",
    reason="Set AVOIRLY_LIVE=1 to authorize live synthetic extraction",
)
def test_live_pdf_and_image():
    assert os.environ.get("OPENAI_API_KEY") and os.environ.get("OPENAI_MODEL")
    samples = Path(__file__).resolve().parents[2] / "samples"
    report = run_case(samples / "po.pdf", samples / "invoice.png")
    assert report["status"] == "CLAIM_DRAFTED", report.get("review_issues") or report.get("error")
    assert report["comparison"]["potential_credit_net"] == "200.00"
    assert len(report["extraction_metadata"]) == 2
