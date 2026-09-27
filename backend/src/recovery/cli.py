"""Avoirly local runner: source files or fully offline extraction fixtures."""

import argparse
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from pydantic import ValidationError

from .comparison import needs_review
from .extraction import ExtractionReview, OpenAIExtractor, ProcessingError, validate_file
from .models import DocumentExtractionResult
from .validation import description_key, issue, key
from .workflow import Workflow, analyze_extraction


def atomic_write(path, content):
    """Replace one file atomically on the same filesystem; never leave half a report."""
    fd, temporary = tempfile.mkstemp(prefix=".avoirly-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def output_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / ".avoirly.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ProcessingError(
            "OUTPUT_BUSY",
            "Output is in use. After a crashed run, remove .avoirly.lock only when no runner remains.",
        ) from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def _read_json(path):
    # Python's JSON parser otherwise accepts nonstandard NaN / Infinity tokens.
    def reject(value):
        raise ValueError(f"Nonstandard JSON constant {value}")

    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=reject)


def _base_report(status, raw=None):
    events = []
    if status == "FAILED":
        flow = Workflow()
        flow.start()
        flow.fail()
        events = flow.events
    return {
        "product": "Avoirly",
        "engine_version": "1",
        "status": status,
        "extraction": raw,
        "validated_pair": None,
        "comparison": None,
        "review_issues": [],
        "claim_draft": None,
        "confirmations": [],
        "events": events,
    }


def _review_report(issues, raw=None):
    result = needs_review(issues)
    flow = Workflow()
    flow.start()
    flow.comparison_completed(result)
    report = _base_report(flow.status.value, raw)
    report.update(
        comparison=result.model_dump(mode="json"),
        events=flow.events,
        review_issues=[i.model_dump() for i in issues],
    )
    return report


def duplicate_issues(raw, documents, previous_reports):
    issues = []
    current_inv = raw.invoice
    hashes = {v["sha256"] for v in documents.values()}
    for previous in previous_reports:
        if not isinstance(previous, dict) or not isinstance(previous.get("extraction"), dict):
            raise ProcessingError(
                "INVALID_HISTORY", "Previous reports must contain extraction objects."
            )
        extraction = previous.get("extraction") or {}
        invoice = extraction.get("invoice") or {}
        if not isinstance(invoice, dict) or not isinstance(invoice.get("supplier"), dict):
            raise ProcessingError(
                "INVALID_HISTORY", "Previous report has no valid invoice identity."
            )
        supplier = invoice.get("supplier") or {}
        if (
            key(current_inv.document_number)
            and key(invoice.get("document_number")) == key(current_inv.document_number)
            and description_key(supplier.get("name")) == description_key(current_inv.supplier.name)
        ):
            issues.append(
                issue(
                    "DUPLICATE_INVOICE",
                    message="Invoice number already exists in supplied local history; resolve before a new claim.",
                )
            )
        previous_documents = previous.get("documents", {})
        if not isinstance(previous_documents, dict) or any(
            not isinstance(v, dict) for v in previous_documents.values()
        ):
            raise ProcessingError("INVALID_HISTORY", "Previous document metadata is invalid.")
        previous_hashes = {v.get("sha256") for v in previous_documents.values()}
        if hashes & previous_hashes:
            issues.append(
                issue(
                    "DUPLICATE_FILE",
                    message="A file hash already exists in supplied local history.",
                )
            )
    return issues


def run_case(
    po_path=None,
    invoice_path=None,
    *,
    fixture=None,
    language="fr",
    confirmation_actor=None,
    confirmation_reason=None,
    previous_reports=(),
    extractor=None,
):
    """Serializable report, no filesystem writes. Provider is injectable for offline tests."""
    documents, extracted, raw_json = {}, {}, None
    adapter = extractor
    try:
        if fixture:
            payload = _read_json(fixture)
            if not isinstance(payload, dict):
                raise ValueError("Fixture must be an object.")
            raw_json = payload["extraction"]
            page_counts = payload["page_counts"]
            if not isinstance(page_counts, dict):
                raise ValueError("Fixture page_counts must be an object.")
        else:
            # Validate BOTH sources before making either model call.
            po_file, invoice_file = validate_file(po_path), validate_file(invoice_path)
            documents = {"PO": po_file.metadata(), "INVOICE": invoice_file.metadata()}
            if po_file.sha256 == invoice_file.sha256:
                report = _review_report(
                    [issue("DUPLICATE_FILE", message="The same file was supplied for both roles.")]
                )
                report["documents"] = documents
                return report
            page_counts = {k: v["page_count"] for k, v in documents.items()}
            adapter = adapter or OpenAIExtractor()
            extracted["purchase_order"] = adapter.extract(po_file, "PO").model_dump(mode="json")
            extracted["invoice"] = adapter.extract(invoice_file, "INVOICE").model_dump(mode="json")
            raw_json = extracted
        raw = DocumentExtractionResult.model_validate(raw_json, strict=True)
        duplicates = duplicate_issues(raw, documents, previous_reports)
        if duplicates:
            report = _review_report(duplicates, raw_json)
        else:
            report = analyze_extraction(
                raw,
                page_counts=page_counts,
                language=language,
                confirmation_actor=confirmation_actor,
                confirmation_reason=confirmation_reason,
            )
        report["mode"] = "offline_fixture" if fixture else "live_extraction"
        report["page_counts"] = page_counts
    except ExtractionReview as exc:
        report = _review_report([issue(exc.code, message=str(exc))], extracted or raw_json)
    except ValidationError as exc:
        report = _review_report(
            [
                issue("INVALID_SCHEMA", field=".".join(map(str, e["loc"])), message=e["msg"])
                for e in exc.errors(include_input=False)
            ],
            raw_json,
        )
    except ProcessingError as exc:
        report = _base_report("FAILED", extracted or raw_json)
        report["error"] = {"code": exc.code, "message": str(exc)}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = _base_report("FAILED", extracted or raw_json)
        report["error"] = {
            "code": "INVALID_INPUT",
            "message": "Cannot read input or fixture; check the format and required fields.",
            "type": type(exc).__name__,
        }
    report["documents"] = documents
    report["extraction_metadata"] = adapter.metadata if adapter is not None else []
    return report


def write_report(out, report):
    claim = out / "claim_email.txt"
    # Remove first: a failed or blocked rerun must not leave an exportable old claim.
    claim.unlink(missing_ok=True)
    report_path = out / "report.json"
    # A crash between these atomic replacements leaves a report but no stale claim file.
    atomic_write(
        report_path, json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    if report["status"] == "CLAIM_DRAFTED":
        draft = report["claim_draft"]
        atomic_write(claim, f"Subject: {draft['subject']}\n\n{draft['body']}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="avoirly",
        description="Avoirly — Spot invoice discrepancies. Simplify supplier claims.",
    )
    parser.add_argument("--po", type=Path, help="Purchase order PDF, PNG or JPEG")
    parser.add_argument("--invoice", type=Path, help="Invoice PDF, PNG or JPEG")
    parser.add_argument("--fixture", type=Path, help="Offline JSON with extraction and page_counts")
    parser.add_argument("--language", choices=("fr", "en"), default="fr")
    parser.add_argument("--out", type=Path, default=Path("output"))
    parser.add_argument(
        "--confirm-pair", action="store_true", help="Confirm a pairing with a missing PO reference"
    )
    parser.add_argument("--actor", help="Author of the pairing confirmation")
    parser.add_argument("--reason", help="Reason for the pairing confirmation")
    parser.add_argument(
        "--previous-report",
        type=Path,
        action="append",
        default=[],
        help="Prior local report to check for duplicate invoices/files (repeatable)",
    )
    args = parser.parse_args(argv)
    if (args.fixture and (args.po or args.invoice)) or (
        not args.fixture and not (args.po and args.invoice)
    ):
        parser.error("Use --fixture OR both --po and --invoice.")
    if args.confirm_pair and (
        not args.actor or not args.actor.strip() or not args.reason or not args.reason.strip()
    ):
        parser.error("--confirm-pair requires --actor and --reason.")
    if (args.actor or args.reason) and not args.confirm_pair:
        parser.error("--actor and --reason require --confirm-pair.")
    try:
        with output_lock(args.out):
            # Overwriting an output folder is a rerun of that local case, not a second case.
            # Other case reports are explicit history, until the owner-scoped Phase 2 database.
            try:
                history = [_read_json(p) for p in args.previous_report]
                report = run_case(
                    args.po,
                    args.invoice,
                    fixture=args.fixture,
                    language=args.language,
                    confirmation_actor=args.actor,
                    confirmation_reason=args.reason,
                    previous_reports=history,
                )
            except (OSError, ValueError) as exc:
                report = _base_report("FAILED")
                report["error"] = {
                    "code": "INVALID_HISTORY",
                    "message": "Cannot read previous report.",
                    "type": type(exc).__name__,
                }
            write_report(args.out, report)
    except (OSError, ProcessingError) as exc:
        print(
            f"Avoirly: unable to write output ({getattr(exc, 'code', type(exc).__name__)}).",
            file=sys.stderr,
        )
        return 1
    print(f"Avoirly: {report['status']}")
    result = report.get("comparison")
    if result and result["potential_credit_net"] is not None:
        print(
            f"Potential credit excluding tax: {result['potential_credit_net']} {result['currency']}"
        )
        if result["outcome"] == "NO_DISCREPANCY":
            print("No discrepancy detected within supported checks")
    for review in report["review_issues"]:
        print(f"Review required: {review['code']} — {review['message']}")
    if report.get("error"):
        print(f"{report['error']['code']}: {report['error']['message']}", file=sys.stderr)
    return 2 if report["status"] == "NEEDS_REVIEW" else 1 if report["status"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
