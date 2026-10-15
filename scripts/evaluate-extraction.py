"""Opt-in live evaluation of a trusted, generated synthetic corpus. No database writes."""

import argparse
import hashlib
import json
import os
import statistics
import time
from decimal import Decimal, InvalidOperation
from functools import partial
from pathlib import Path

from openai import OpenAI
from recovery.cli import run_case
from recovery.extraction import EXTRACTION_PROMPT, PROMPT_VERSION, OpenAIExtractor


def critical(document):
    if not document:
        return {}
    result = {
        key: document.get(key)
        for key in (
            "document_type",
            "document_number",
            "document_date",
            "currency",
            "prices_include_tax",
            "adjustments_present",
        )
    }
    if "purchase_order_reference" in document:
        result["purchase_order_reference"] = document["purchase_order_reference"]
    for party in ("supplier", "buyer"):
        for key in ("name", "tax_id"):
            result[party + "." + key] = (document.get(party) or {}).get(key)
    for key in ("subtotal", "tax_total", "total"):
        value = document.get(key)
        result[key] = None if value is None else str(Decimal(value).normalize())
    rows = document.get("line_items", [])
    result["line_count"] = len(rows)
    for index, row in enumerate(rows):
        for key in ("sku", "quantity", "unit", "unit_price", "tax_rate", "line_total"):
            value = row.get(key)
            if (
                key in ("quantity", "unit_price", "tax_rate", "line_total")
                and value is not None
            ):
                try:
                    value = str(Decimal(value).normalize())
                except (InvalidOperation, ValueError, TypeError):
                    value = "INVALID_DECIMAL"
            result[f"line_{index}.{key}"] = value
    return result


def finding_keys(rows):
    return {
        (
            row["po_line_number"],
            row["invoice_line_number"],
            str(Decimal(row["potential_credit_net"]).normalize()),
        )
        for row in rows
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-usd", type=Decimal, required=True)
    parser.add_argument("--allow-live", action="store_true")
    args = parser.parse_args()
    if not args.allow_live or not Decimal(0) < args.max_usd <= Decimal("1.00"):
        raise ValueError(
            "Explicit live authorization and an evaluation allowance of at most USD1 are required"
        )
    manifest_bytes = (args.corpus / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    args.out.mkdir(parents=True, exist_ok=True)
    summary_path = args.out / "summary.json"
    if summary_path.exists():
        raise ValueError("Refusing a repeated paid run in an existing results folder")
    model = os.environ["OPENAI_MODEL"]
    input_rate = Decimal(os.environ["AVOIRLY_INPUT_USD_PER_MILLION"])
    output_rate = Decimal(os.environ["AVOIRLY_OUTPUT_USD_PER_MILLION"])
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=90, max_retries=0)
    # Same live extraction adapter, with a documented evaluation output bound.
    client.chat.completions.parse = partial(
        client.chat.completions.parse, max_completion_tokens=6000
    )
    results, spent, stopped = [], Decimal(0), None
    for case in manifest["cases"]:
        if spent + Decimal("0.10") > args.max_usd:
            stopped = "EVALUATION_BUDGET_RESERVE"
            break
        for role in ("po", "invoice"):
            data = (args.corpus / case[role + "_file"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != case[role + "_sha256"]:
                raise ValueError("Fixture checksum changed")
        adapter = OpenAIExtractor(client=client, model=model)
        started = time.monotonic()
        report = run_case(
            args.corpus / case["po_file"],
            args.corpus / case["invoice_file"],
            extractor=adapter,
        )
        elapsed = round(time.monotonic() - started, 3)
        (args.out / (case["id"] + ".json")).write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        metadata = report.get("extraction_metadata", [])
        incoming = sum(
            (row.get("token_usage") or {}).get("prompt_tokens", 0) for row in metadata
        )
        outgoing = sum(
            (row.get("token_usage") or {}).get("completion_tokens", 0)
            for row in metadata
        )
        cost = (incoming * input_rate + outgoing * output_rate) / Decimal(1000000)
        spent += cost
        comparison = report.get("comparison") or {}
        actual_amount = comparison.get("potential_credit_net")
        drafted = report["status"] == "CLAIM_DRAFTED"
        correct_draft = (
            drafted
            and case["expected_status"] == "CLAIM_DRAFTED"
            and actual_amount == case["expected_amount"]
        )
        correct, total = 0, 0
        for key in ("purchase_order", "invoice"):
            expected = critical(case["extraction"][key])
            actual = critical((report.get("extraction") or {}).get(key))
            total += len(expected)
            correct += sum(
                key in actual and actual[key] == value
                for key, value in expected.items()
            )
        gold = finding_keys(case["expected_findings"])
        predicted = finding_keys(comparison.get("findings", []))
        row = {
            "id": case["id"],
            "split": case["split"],
            "format": case["format"],
            "scenario": case["scenario"],
            "expected_status": case["expected_status"],
            "actual_status": report["status"],
            "expected_amount": case["expected_amount"],
            "actual_amount": actual_amount,
            "false_draft": drafted and not correct_draft,
            "status_and_amount_match": report["status"] == case["expected_status"]
            and actual_amount == case["expected_amount"],
            "critical_fields_correct": correct,
            "critical_fields_total": total,
            "finding_tp": len(predicted & gold),
            "finding_fp": len(predicted - gold),
            "finding_fn": len(gold - predicted),
            "review_codes": [item["code"] for item in report.get("review_issues", [])],
            "error_code": (report.get("error") or {}).get("code"),
            "seconds": elapsed,
            "input_tokens": incoming,
            "output_tokens": outgoing,
            "reported_estimated_usd": str(cost),
        }
        results.append(row)
        summary_path.write_text(
            json.dumps(
                {
                    "running": True,
                    "results": results,
                    "reported_estimated_usd": str(spent),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    key: row[key]
                    for key in (
                        "id",
                        "actual_status",
                        "false_draft",
                        "seconds",
                        "reported_estimated_usd",
                    )
                }
            ),
            flush=True,
        )
        if report["status"] == "FAILED" or any(
            row.get("token_usage") is None for row in metadata
        ):
            stopped = "PROVIDER_FAILURE_OR_UNREPORTED_USAGE"
            break
    total_fields = sum(row["critical_fields_total"] for row in results)
    correct_fields = sum(row["critical_fields_correct"] for row in results)
    tp = sum(row["finding_tp"] for row in results)
    fp = sum(row["finding_fp"] for row in results)
    fn = sum(row["finding_fn"] for row in results)
    ambiguous = [row for row in results if row["expected_status"] == "NEEDS_REVIEW"]
    summary = {
        "running": False,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": hashlib.sha256(EXTRACTION_PROMPT.encode()).hexdigest(),
        "corpus_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "requested_pairs": len(manifest["cases"]),
        "evaluated_pairs": len(results),
        "held_out_pairs": sum(row["split"] == "held_out" for row in results),
        "normalized_critical_field_match": {
            "correct": correct_fields,
            "total": total_fields,
        },
        "status_and_amount_matches": sum(
            row["status_and_amount_match"] for row in results
        ),
        "false_drafts": sum(row["false_draft"] for row in results),
        "ambiguous_cases_blocked": sum(
            row["actual_status"] == "NEEDS_REVIEW" for row in ambiguous
        ),
        "ambiguous_cases_total": len(ambiguous),
        "finding_precision": {"correct": tp, "predicted": tp + fp},
        "finding_recall": {"found": tp, "expected": tp + fn},
        "review_cases": sum(row["actual_status"] == "NEEDS_REVIEW" for row in results),
        "median_seconds_per_pair": statistics.median(row["seconds"] for row in results)
        if results
        else None,
        "reported_estimated_usd": str(spent),
        "stopped_reason": stopped,
        "evaluation_settings": {
            "output_token_limit": 6000,
            "transport_retries": 0,
            "budget_allowance_usd": str(args.max_usd),
        },
        "limitations": manifest["limitations"],
        "results": results,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps({key: value for key, value in summary.items() if key != "results"}),
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - provider details and credentials stay private
        print(json.dumps({"evaluation_failed": type(exc).__name__}), flush=True)
        raise SystemExit(1) from None
