"""Lease-based PostgreSQL polling worker. API process memory is never the queue."""

import argparse
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select

from .api.errors import DomainError
from .claims import generate_claim
from .comparison import compare, needs_review
from .config import Settings
from .db.models import (
    Case,
    Comparison,
    Confirmation,
    Document,
    Draft,
    Extraction,
    InvoiceIdentity,
    Job,
    WorkerHeartbeat,
)
from .db.session import create_sessions
from .extraction import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    ExtractionReview,
    OpenAIExtractor,
    ProcessingError,
    validate_file,
)
from .models import (
    ComparisonResult,
    DocumentExtractionResult,
    Invoice,
    PairConfirmation,
    PurchaseOrder,
    ValidatedPair,
)
from .operations import usage_record
from .service import (
    change,
    cleanup_deleted,
    current_comparison,
    current_documents,
    latest_extraction,
    owner_lock,
)
from .storage import create_storage
from .validation import description_key, issue, key, validate_pair

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Lease:
    job_id: UUID
    case_id: UUID
    owner_id: UUID
    revision: int
    token: UUID
    model: str
    language: str


def database_now(session):
    return session.scalar(select(func.clock_timestamp()))


def acquire_job(sessions, seconds):
    # Discover candidates without locks, then lock owner -> case -> job consistently.
    with sessions() as session:
        candidates = [
            (j.id, j.case_id, j.owner_id)
            for j in session.scalars(
                select(Job)
                .where(Job.status == "QUEUED", Job.available_at <= func.clock_timestamp())
                .order_by(Job.available_at, Job.id)
                .limit(50)
            )
        ]
    for job_id, case_id, owner in candidates:
        with sessions.begin() as session:
            owner_lock(session, owner)
            case = session.scalar(
                select(Case).where(Case.id == case_id).with_for_update(skip_locked=True)
            )
            if not case:
                continue
            job = session.scalar(
                select(Job)
                .where(Job.id == job_id, Job.status == "QUEUED")
                .with_for_update(skip_locked=True)
            )
            if not job:
                continue
            if case.current_revision != job.revision or case.status != "PENDING":
                job.status, job.error_code = "FAILED", "STALE_REVISION"
                continue
            job.status, job.lease_token = "RUNNING", uuid4()
            job.leased_until = database_now(session) + timedelta(seconds=seconds)
            change(session, case, "start", target="PROCESSING", processing_step="EXTRACTION")
            return Lease(
                job.id, case.id, owner, job.revision, job.lease_token, job.model, job.language
            )
    return None


@contextmanager
def guarded(sessions, lease):
    with sessions.begin() as session:
        owner_lock(session, lease.owner_id)
        case = session.scalar(
            select(Case)
            .where(Case.id == lease.case_id, Case.owner_id == lease.owner_id)
            .with_for_update()
        )
        job = session.scalar(select(Job).where(Job.id == lease.job_id).with_for_update())
        if (
            not case
            or not job
            or case.current_revision != lease.revision
            or job.status != "RUNNING"
            or job.lease_token != lease.token
            or job.leased_until is None
            or job.leased_until <= database_now(session)
        ):
            raise DomainError("STALE_LEASE", "Worker no longer owns the current revision.")
        yield session, case, job
        # Guard the commit as well as entry: work inside this block must remain short.
        if job.leased_until <= database_now(session):
            raise DomainError("STALE_LEASE", "Lease expired before commit.")


def heartbeat(sessions, lease, seconds):
    with guarded(sessions, lease) as (session, _, job):
        job.leased_until = database_now(session) + timedelta(seconds=seconds)


def requeue_expired(sessions, seconds, max_attempts=3):
    """Explicit operator action; each expired attempt is closed and replaced, never reused."""
    count = 0
    with sessions() as session:
        stale = [
            (j.id, j.case_id, j.owner_id)
            for j in session.scalars(
                select(Job).where(
                    Job.status == "RUNNING", Job.leased_until <= func.clock_timestamp()
                )
            )
        ]
    for job_id, case_id, owner in stale:
        with sessions.begin() as session:
            owner_lock(session, owner)
            case = session.scalar(select(Case).where(Case.id == case_id).with_for_update())
            job = session.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if not job or job.status != "RUNNING" or job.leased_until > database_now(session):
                continue
            job.status, job.error_code, job.lease_token = "FAILED", "LEASE_EXPIRED", None
            session.flush()
            if (
                case
                and case.current_revision == job.revision
                and case.status in ("NEEDS_REVIEW", "NO_DISCREPANCY")
            ):
                # The durable comparison already completed all required work.
                job.status, job.error_code = "SUCCEEDED", None
                continue
            if (
                case
                and case.current_revision == job.revision
                and case.status in ("PROCESSING", "DISCREPANCY_FOUND")
            ):
                change(session, case, "fail", target="FAILED", error_code="LEASE_EXPIRED")
                if job.attempt >= max_attempts:
                    continue
                change(
                    session,
                    case,
                    "retry",
                    target="PENDING",
                    error_code=None,
                    processing_step="QUEUED",
                )
                session.add(
                    Job(
                        case_id=case.id,
                        owner_id=owner,
                        revision=job.revision,
                        attempt=job.attempt + 1,
                        language=job.language,
                        model=job.model,
                    )
                )
                count += 1
    return count


class Worker:
    def __init__(self, settings, sessions, *, extractor_factory=None, storage=None):
        settings.validate()
        self.settings, self.sessions = settings, sessions
        self.storage = storage or create_storage(settings)
        self.worker_id = uuid4()
        self.extractor_factory = extractor_factory or (lambda model: OpenAIExtractor(model=model))

    def _heartbeat_loop(self, lease, stop, lost):
        while not stop.wait(self.settings.lease_seconds / 3):
            try:
                heartbeat(self.sessions, lease, self.settings.lease_seconds)
                self.record_heartbeat()
            except Exception:  # noqa: BLE001 - heartbeat loss must fail closed, without leaking DB errors
                lost.set()
                return

    def run_once(self):
        self.record_heartbeat()
        cleanup_deleted(self.sessions, self.storage)
        lease = acquire_job(self.sessions, self.settings.lease_seconds)
        if lease is None:
            return False
        stop, lost = threading.Event(), threading.Event()
        thread = threading.Thread(
            target=self._heartbeat_loop, args=(lease, stop, lost), daemon=True
        )
        thread.start()
        try:
            self.process(lease)
        except DomainError as exc:
            if exc.code != "STALE_LEASE":
                self.fail(lease, exc.code)
        except ProcessingError as exc:
            self.fail(lease, exc.code)
        except Exception as exc:  # noqa: BLE001 - worker boundary persists redacted technical failures
            log.error("worker_failed job_id=%s type=%s", lease.job_id, type(exc).__name__)
            self.fail(lease, "PROCESSING_ERROR")
        finally:
            stop.set()
            thread.join(timeout=5)
        return True

    def record_heartbeat(self):
        with self.sessions.begin() as session:
            session.merge(WorkerHeartbeat(id=self.worker_id, last_seen=database_now(session)))

    def fail(self, lease, code):
        try:
            with guarded(self.sessions, lease) as (session, case, job):
                change(
                    session, case, "fail", target="FAILED", error_code=code, processing_step=None
                )
                job.status, job.error_code, job.lease_token = "FAILED", code, None
        except DomainError as exc:
            if exc.code != "STALE_LEASE":
                raise

    def process(self, lease):
        with guarded(self.sessions, lease) as (session, case, _job):
            existing = current_comparison(session, case)
            docs = current_documents(session, case)
            if set(docs) != {"PO", "INVOICE"}:
                raise ProcessingError("MISSING_DOCUMENTS", "Both source documents are required.")
            # Detached scalar snapshots avoid keeping a transaction open during external calls.
            doc_info = {
                role: {
                    "id": d.id,
                    "key": d.storage_key,
                    "sha256": d.sha256,
                    "pages": d.page_count,
                }
                for role, d in docs.items()
            }
        if existing:
            self.finish_comparison(lease, existing.id)
            return

        values, extraction_ids = {}, {}
        adapter = None
        for role in ("PO", "INVOICE"):
            info = doc_info[role]
            with guarded(self.sessions, lease) as (session, _, _job):
                document = session.get(Document, info["id"])
                cached = latest_extraction(session, document)
                reusable = (
                    cached
                    and cached.input_hash == info["sha256"]
                    and (
                        cached.corrected_json is not None
                        or (
                            cached.model == lease.model
                            and cached.prompt_version == PROMPT_VERSION
                            and cached.schema_version == SCHEMA_VERSION
                        )
                    )
                )
                if reusable:
                    values[role] = (
                        cached.corrected_json
                        if cached.corrected_json is not None
                        else cached.raw_json
                    )
                    extraction_ids[role] = str(cached.id)
            if reusable:
                continue
            with self.storage.materialize(info["key"]) as path:
                file = validate_file(path)
            if file.sha256 != info["sha256"]:
                raise ProcessingError("SOURCE_CHANGED", "Stored document hash changed.")
            adapter = adapter or self.extractor_factory(lease.model)
            try:
                extracted = adapter.extract(file, role)
            except ExtractionReview as exc:
                result = needs_review([issue(exc.code, role=role, message=str(exc))])
                comparison_id = self.persist_comparison(lease, result, None, extraction_ids)
                self.finish_comparison(lease, comparison_id)
                return
            value = extracted.model_dump(mode="json")
            metadata = adapter.metadata[-1] if adapter.metadata else {}
            with guarded(self.sessions, lease) as (session, _, _job):
                document = session.get(Document, info["id"])
                previous = latest_extraction(session, document)
                record = Extraction(
                    id=uuid4(),
                    document_id=document.id,
                    version=previous.version + 1 if previous else 1,
                    raw_json=value,
                    model=lease.model,
                    prompt_version=PROMPT_VERSION,
                    schema_version=SCHEMA_VERSION,
                    input_hash=info["sha256"],
                    request_id=metadata.get("request_id"),
                    token_usage=metadata.get("token_usage"),
                    duration_ms=metadata.get("duration_ms"),
                )
                session.add(record)
                usage = usage_record(self.settings, lease.model, metadata)
                if usage is not None:
                    session.add(usage)
                values[role], extraction_ids[role] = value, str(record.id)

        raw = DocumentExtractionResult(
            purchase_order=PurchaseOrder.model_validate(values["PO"], strict=True),
            invoice=Invoice.model_validate(values["INVOICE"], strict=True),
        )
        with guarded(self.sessions, lease) as (session, case, _job):
            record = session.scalar(
                select(Confirmation).where(
                    Confirmation.case_id == case.id,
                    Confirmation.revision == lease.revision,
                    Confirmation.kind == "PAIR",
                )
            )
            confirmation = (
                PairConfirmation.model_validate(record.value_json["value"]) if record else None
            )
        validated = validate_pair(
            raw, confirmation, page_counts={k: d["pages"] for k, d in doc_info.items()}
        )
        result = needs_review(validated) if isinstance(validated, list) else compare(validated)
        comparison_id = self.persist_comparison(
            lease,
            result,
            None if isinstance(validated, list) else validated,
            extraction_ids,
            raw=raw,
        )
        self.finish_comparison(lease, comparison_id)

    def persist_comparison(self, lease, result, validated, extraction_ids, raw=None):
        with guarded(self.sessions, lease) as (session, case, _job):
            # Owner advisory lock serializes check+reservation across concurrent invoices.
            if (
                raw
                and raw.invoice.document_type == "INVOICE"
                and description_key(raw.invoice.supplier.name)
                and key(raw.invoice.document_number)
            ):
                invoice_key = key(raw.invoice.document_number)
                supplier_keys = ["name:" + description_key(raw.invoice.supplier.name)]
                if key(raw.invoice.supplier.tax_id):
                    supplier_keys.append("tax:" + key(raw.invoice.supplier.tax_id))
                previous = list(
                    session.scalars(
                        select(InvoiceIdentity).where(
                            InvoiceIdentity.owner_id == case.owner_id,
                            InvoiceIdentity.supplier_key.in_(supplier_keys),
                            InvoiceIdentity.invoice_key == invoice_key,
                        )
                    )
                )
                if any(p.case_id != case.id for p in previous):
                    result = needs_review(
                        result.review_issues
                        + [
                            issue(
                                "DUPLICATE_INVOICE",
                                message="This supplier invoice already exists in another case.",
                            )
                        ],
                        raw.invoice.currency,
                    )
                    validated = None
                else:
                    existing_keys = {p.supplier_key for p in previous}
                    for supplier_key in set(supplier_keys) - existing_keys:
                        session.add(
                            InvoiceIdentity(
                                owner_id=case.owner_id,
                                case_id=case.id,
                                supplier_key=supplier_key,
                                invoice_key=invoice_key,
                            )
                        )
            record = Comparison(
                id=uuid4(),
                case_id=case.id,
                revision=lease.revision,
                result_json=result.model_dump(mode="json"),
                validated_json=validated.model_dump(mode="json") if validated else None,
                extraction_ids=extraction_ids,
                engine_version="1",
            )
            session.add(record)
            # This transaction commits before any draft is generated.
            event = {
                "DISCREPANCY_FOUND": "discrepancy",
                "NO_DISCREPANCY": "no_discrepancy",
                "NEEDS_REVIEW": "review",
            }[result.outcome]
            change(
                session,
                case,
                event,
                target=result.outcome,
                processing_step="DRAFT" if result.outcome == "DISCREPANCY_FOUND" else None,
                currency=result.currency,
                potential_credit_net=result.potential_credit_net,
            )
            return record.id

    def finish_comparison(self, lease, comparison_id):
        with guarded(self.sessions, lease) as (session, case, job):
            record = session.get(Comparison, comparison_id)
            if record.case_id != case.id or record.revision != lease.revision:
                raise DomainError("STALE_LEASE", "Comparison revision changed.")
            result = ComparisonResult.model_validate(record.result_json)
            if case.status == "PROCESSING":
                event = {
                    "DISCREPANCY_FOUND": "discrepancy",
                    "NO_DISCREPANCY": "no_discrepancy",
                    "NEEDS_REVIEW": "review",
                }[result.outcome]
                change(
                    session,
                    case,
                    event,
                    target=result.outcome,
                    currency=result.currency,
                    potential_credit_net=result.potential_credit_net,
                )
            validated_json = record.validated_json
        if result.outcome == "DISCREPANCY_FOUND":
            draft = generate_claim(
                ValidatedPair.model_validate(validated_json), result, lease.language
            )
            with guarded(self.sessions, lease) as (session, case, job):
                session.add(
                    Draft(
                        case_id=case.id,
                        comparison_id=comparison_id,
                        version=1,
                        subject=draft.subject,
                        body=draft.body,
                        language=draft.language,
                    )
                )
                change(session, case, "draft_saved", target="CLAIM_DRAFTED", processing_step=None)
                job.status, job.lease_token = "SUCCEEDED", None
        else:
            with guarded(self.sessions, lease) as (_, _case, job):
                job.status, job.lease_token = "SUCCEEDED", None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Avoirly durable worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--requeue-expired", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings.from_env()
    engine, sessions = create_sessions(settings.database_url)
    worker = Worker(settings, sessions)
    worker.storage.check_private()
    try:
        if args.requeue_expired:
            print(
                f"Requeued {requeue_expired(sessions, settings.lease_seconds, settings.max_attempts)} expired jobs."
            )
            return
        if args.once:
            worker.run_once()
            return
        stop = threading.Event()
        while True:
            try:
                if not worker.run_once():
                    stop.wait(2)
            except Exception as exc:  # noqa: BLE001 - keep polling through temporary outages without leaking SQL
                log.error("worker_poll_failed type=%s", type(exc).__name__)
                stop.wait(5)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
