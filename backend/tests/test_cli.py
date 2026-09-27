import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image

from recovery.cli import atomic_write, main, output_lock, run_case
from recovery.comparison import compare
from recovery.extraction import ExtractionReview, ProcessingError
from recovery.validation import validate_pair
from recovery.workflow import CaseStatus, Workflow

SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "pair.json"


def fixture_file(tmp_path, pair_dict):
    path = tmp_path / "fixture.json"
    path.write_text(
        json.dumps({"page_counts": {"PO": 1, "INVOICE": 1}, "extraction": pair_dict}),
        encoding="utf-8",
    )
    return path


def test_cli_draft_and_stale_cleanup(tmp_path, pair_dict):
    out = tmp_path / "out"
    assert main(["--fixture", str(SAMPLE), "--out", str(out)]) == 0
    assert (out / "claim_email.txt").exists()
    pair_dict["invoice"]["prices_include_tax"] = None
    sample = fixture_file(tmp_path, pair_dict)
    assert main(["--fixture", str(sample), "--out", str(out)]) == 2
    assert not (out / "claim_email.txt").exists()
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "NEEDS_REVIEW"
    assert report["comparison"]["potential_credit_net"] is None


def test_success_to_failure_removes_old_draft(tmp_path):
    out = tmp_path / "out"
    assert main(["--fixture", str(SAMPLE), "--out", str(out)]) == 0
    assert main(["--fixture", str(tmp_path / "missing.json"), "--out", str(out)]) == 1
    assert not (out / "claim_email.txt").exists()
    assert json.loads((out / "report.json").read_text())["status"] == "FAILED"


def test_duplicate_history_blocks_new_claim(tmp_path):
    first, second = tmp_path / "case1", tmp_path / "case2"
    assert main(["--fixture", str(SAMPLE), "--out", str(first)]) == 0
    assert (
        main(
            [
                "--fixture",
                str(SAMPLE),
                "--out",
                str(second),
                "--previous-report",
                str(first / "report.json"),
            ]
        )
        == 2
    )
    assert not (second / "claim_email.txt").exists()


def test_no_discrepancy_exit_code(tmp_path, pair_dict):
    po = pair_dict["purchase_order"]
    for field in ("line_items", "subtotal", "tax_total", "total"):
        pair_dict["invoice"][field] = po[field]
    sample = fixture_file(tmp_path, pair_dict)
    out = tmp_path / "out"
    assert main(["--fixture", str(sample), "--out", str(out)]) == 0
    assert not (out / "claim_email.txt").exists()


def test_float_fixture_needs_review(tmp_path, pair_dict):
    pair_dict["invoice"]["line_items"][0]["quantity"] = 22.0
    report = run_case(fixture=fixture_file(tmp_path, pair_dict))
    assert report["status"] == "NEEDS_REVIEW"
    assert report["extraction"]["invoice"]["line_items"][0]["quantity"] == 22.0


def test_pair_confirmation_saved(tmp_path, pair_dict):
    pair_dict["invoice"]["purchase_order_reference"] = None
    sample = fixture_file(tmp_path, pair_dict)
    out = tmp_path / "out"
    assert (
        main(
            [
                "--fixture",
                str(sample),
                "--out",
                str(out),
                "--confirm-pair",
                "--actor",
                "Hanane",
                "--reason",
                "Verified original order",
            ]
        )
        == 0
    )
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["confirmations"][0]["actor"] == "Hanane"


def test_validate_both_files_before_api(tmp_path):
    png = tmp_path / "valid.png"
    Image.new("RGB", (5, 5)).save(png)
    adapter = Mock(metadata=[])
    report = run_case(png, tmp_path / "missing.pdf", extractor=adapter)
    assert report["status"] == "FAILED"
    adapter.extract.assert_not_called()


def test_identical_file_roles_block(tmp_path):
    png = tmp_path / "same.png"
    Image.new("RGB", (5, 5)).save(png)
    adapter = Mock(metadata=[])
    report = run_case(png, png, extractor=adapter)
    assert report["status"] == "NEEDS_REVIEW"
    adapter.extract.assert_not_called()


def test_preserves_first_extraction_when_second_refused(tmp_path, pair):
    po, inv = tmp_path / "po.png", tmp_path / "inv.png"
    Image.new("RGB", (5, 5), "white").save(po)
    Image.new("RGB", (5, 5), "black").save(inv)
    adapter = Mock(metadata=[])
    adapter.extract.side_effect = [pair.purchase_order, ExtractionReview("MODEL_REFUSAL", "Review")]
    report = run_case(po, inv, extractor=adapter)
    assert report["status"] == "NEEDS_REVIEW"
    assert report["extraction"]["purchase_order"]["document_number"] == "PO-124"
    assert report["claim_draft"] is None


def test_output_lock_blocks_concurrent_writer(tmp_path):
    with output_lock(tmp_path), pytest.raises(ProcessingError), output_lock(tmp_path):
        pytest.fail("Second writer acquired lock")
    assert not (tmp_path / ".avoirly.lock").exists()


def test_atomic_replace_failure_keeps_previous_file(tmp_path, monkeypatch):
    target = tmp_path / "report.json"
    target.write_text("old")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("recovery.cli.os.replace", fail)
    with pytest.raises(OSError):
        atomic_write(target, "new")
    assert target.read_text() == "old"
    assert not list(tmp_path.glob(".avoirly-*"))


def test_state_machine_forbids_early_draft_and_terminal_exit(pair):
    flow = Workflow()
    with pytest.raises(ValueError):
        flow._transition("draft_saved")
    flow.start()
    result = compare(validate_pair(pair, page_counts={"PO": 1, "INVOICE": 1}))
    flow.comparison_completed(result)
    assert flow.status is CaseStatus.DISCREPANCY_FOUND
    with pytest.raises(ValueError):
        flow._transition("start")
    flow._transition("close")
    with pytest.raises(ValueError):
        flow._transition("retry")


def test_fixture_never_constructs_openai_client(monkeypatch):
    client = Mock(side_effect=AssertionError("Network must not be used"))
    monkeypatch.setattr("recovery.cli.OpenAIExtractor", client)
    assert run_case(fixture=SAMPLE)["status"] == "CLAIM_DRAFTED"
    client.assert_not_called()
